from __future__ import annotations

import select
import socket
import time
from dataclasses import dataclass, field
from typing import Any

from Modules.Digital_Twins.types import DTCommand, DTObservation
from Modules.Digital_Twins.udp_protocol import (
    UdpProtocolError,
    make_command_packet,
    make_control_packet,
    observation_from_packet,
    packet_from_datagram,
    packet_to_datagram,
)


@dataclass(slots=True)
class UdpLiveSimulinkBackend:
    """UDP backend for a Simulink model that is already running live.

    The backend does not advance Simulink by calling ``sim(...)``. It sends
    command packets to the model and waits for observation packets produced by
    UDP blocks or MATLAB System blocks inside the running simulation.
    """

    command_host: str = "127.0.0.1"
    command_port: int = 55000
    observation_host: str = "0.0.0.0"
    observation_port: int = 55001
    receive_timeout_s: float = 2.0
    reset_timeout_s: float = 5.0
    command_resend_period_s: float = 0.25
    send_reset_on_reset: bool = False
    telemetry_host: str | None = None
    telemetry_port: int | None = None
    _socket: socket.socket | None = field(init=False, default=None, repr=False)
    _telemetry_socket: socket.socket | None = field(
        init=False,
        default=None,
        repr=False,
    )
    _latest_observation: DTObservation | None = field(
        init=False,
        default=None,
        repr=False,
    )
    _last_command: DTCommand = field(init=False, repr=False)
    _command_seq: int = field(init=False, default=0, repr=False)
    _control_seq: int = field(init=False, default=0, repr=False)
    _last_command_send_monotonic_s: float = field(
        init=False,
        default=0.0,
        repr=False,
    )
    _socket_reset_count: int = field(init=False, default=0, repr=False)

    def __post_init__(self) -> None:
        self._socket = None
        self._telemetry_socket = None
        self._latest_observation = None
        self._last_command = DTCommand.hold("initial UDP command")
        self._command_seq = 0
        self._control_seq = 0
        self._last_command_send_monotonic_s = 0.0
        self._socket_reset_count = 0

    def reset(self) -> DTObservation:
        self._ensure_socket()
        if self.send_reset_on_reset:
            self._control_seq += 1
            self._send_packet(
                make_control_packet(
                    action="reset",
                    seq=self._control_seq,
                    reason="runner reset",
                )
            )
        self._latest_observation = None
        return self._receive_observation(
            timeout_s=self.reset_timeout_s,
            allow_cached_on_timeout=False,
        )

    def observe(self) -> DTObservation:
        self._ensure_socket()
        return self._receive_observation(
            timeout_s=self.receive_timeout_s,
            allow_cached_on_timeout=True,
        )

    def apply_command(self, command: DTCommand) -> None:
        self._ensure_socket()
        self._last_command = command
        self._send_command(command)

    def advance(self, seconds: float) -> DTObservation:
        if seconds <= 0:
            raise ValueError("advance seconds must be positive")

        self._ensure_socket()
        start_observation = self._latest_observation
        start_sim_time_s = (
            start_observation.sim_time_s if start_observation is not None else None
        )
        target_sim_time_s = (
            start_sim_time_s + seconds if start_sim_time_s is not None else None
        )
        deadline = time.monotonic() + seconds + self.receive_timeout_s
        latest = start_observation

        while time.monotonic() < deadline:
            self._resend_last_command_if_due()
            timeout_s = min(
                self.receive_timeout_s,
                self._resend_poll_period_s(),
                max(0.0, deadline - time.monotonic()),
            )
            try:
                latest = self._receive_observation(
                    timeout_s=timeout_s,
                    allow_cached_on_timeout=False,
                )
            except TimeoutError:
                self._resend_last_command_if_due()
                continue

            if target_sim_time_s is None:
                return latest
            if latest.sim_time_s >= target_sim_time_s:
                return latest
            if start_sim_time_s is not None and latest.sim_time_s < start_sim_time_s:
                return latest

        if latest is not None:
            return latest
        raise TimeoutError("no UDP observation received while advancing live Simulink")

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        if self._telemetry_socket is not None:
            self._telemetry_socket.close()
            self._telemetry_socket = None

    def _ensure_socket(self) -> socket.socket:
        if self._socket is not None:
            return self._socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.observation_host, int(self.observation_port)))
        sock.setblocking(False)
        self._socket = sock

        if self.telemetry_host is not None and self.telemetry_port is not None:
            telemetry_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            telemetry_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._telemetry_socket = telemetry_sock

        return sock

    def _send_packet(self, packet: dict[str, Any]) -> None:
        sock = self._ensure_socket()
        sock.sendto(
            packet_to_datagram(packet),
            (self.command_host, int(self.command_port)),
        )

    def _send_command(self, command: DTCommand) -> None:
        self._command_seq += 1
        self._send_packet(make_command_packet(command=command, seq=self._command_seq))
        self._last_command_send_monotonic_s = time.monotonic()

    def _resend_last_command_if_due(self) -> None:
        if self.command_resend_period_s <= 0:
            return
        now_s = time.monotonic()
        if now_s - self._last_command_send_monotonic_s < self.command_resend_period_s:
            return
        self._send_command(self._last_command)

    def _resend_poll_period_s(self) -> float:
        if self.command_resend_period_s <= 0:
            return self.receive_timeout_s
        return max(0.01, self.command_resend_period_s)

    def _receive_observation(
        self,
        timeout_s: float,
        allow_cached_on_timeout: bool,
    ) -> DTObservation:
        deadline = time.monotonic() + max(0.0, timeout_s)
        last_protocol_error: UdpProtocolError | None = None

        while True:
            remaining_s = deadline - time.monotonic()
            if remaining_s < 0:
                if allow_cached_on_timeout and self._latest_observation is not None:
                    return self._latest_observation
                if last_protocol_error is not None:
                    raise TimeoutError(
                        f"no valid UDP observation received: {last_protocol_error}"
                    )
                raise TimeoutError("no UDP observation received")

            sock = self._ensure_socket()
            readable, _, _ = select.select([sock], [], [], remaining_s)
            if not readable:
                continue

            try:
                datagram, _sender = sock.recvfrom(65535)
            except ConnectionResetError as exc:
                # On Windows, UDP sendto() can make a later recvfrom() raise
                # WSAECONNRESET if the remote command port is not listening
                # or the Simulink receiver block was released. UDP is
                # connectionless, so keep listening; if observations do not
                # resume before the deadline we report a normal timeout with
                # this socket-reset detail.
                self._socket_reset_count += 1
                last_protocol_error = UdpProtocolError(
                    f"UDP socket reset while waiting for observation: {exc}"
                )
                continue
            try:
                packet = packet_from_datagram(datagram)
                if packet.get("kind") != "observation":
                    continue
                observation = observation_from_packet(packet)
            except UdpProtocolError as exc:
                last_protocol_error = exc
                continue

            self._latest_observation = observation
            self._republish_observation(datagram)
            return observation

    def _republish_observation(self, datagram: bytes) -> None:
        if (
            self._telemetry_socket is None
            or self.telemetry_host is None
            or self.telemetry_port is None
        ):
            return
        self._telemetry_socket.sendto(
            datagram,
            (self.telemetry_host, int(self.telemetry_port)),
        )
