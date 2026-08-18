import socket
import threading
import time
import unittest

from Modules.Digital_Twins.types import DTCommand, DTObservation
from Modules.Digital_Twins.udp_backend import UdpLiveSimulinkBackend
from Modules.Digital_Twins.udp_protocol import (
    command_from_packet,
    make_observation_packet,
    observation_from_packet,
    packet_from_datagram,
    packet_to_datagram,
)


class UdpLiveBackendTests(unittest.TestCase):
    def test_protocol_round_trips_observation(self):
        observation = DTObservation(
            sim_time_s=12.5,
            soc_pct=55.0,
            v_bus_v=400.0,
            p_batt_w=125.0,
            p_load_w=-200.0,
            max_safe_discharge_w=175.0,
            max_safe_charge_w=225.0,
            source_power_limit_w=3000.0,
            fault_flags={"unit_test": False},
        )

        packet = packet_from_datagram(
            packet_to_datagram(make_observation_packet(observation, seq=7))
        )
        decoded = observation_from_packet(packet)

        self.assertEqual(packet["kind"], "observation")
        self.assertEqual(packet["seq"], 7)
        self.assertEqual(decoded.sim_time_s, 12.5)
        self.assertEqual(decoded.soc_pct, 55.0)
        self.assertEqual(decoded.v_bus_v, 400.0)
        self.assertEqual(decoded.p_load_w, -200.0)
        self.assertEqual(decoded.resolved_load_consumption_w(), 200.0)
        self.assertEqual(decoded.max_safe_discharge_w, 175.0)
        self.assertEqual(decoded.max_safe_charge_w, 225.0)
        self.assertEqual(decoded.source_power_limit_w, 3000.0)

    def test_backend_receives_observation_and_sends_command(self):
        command_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        command_socket.bind(("127.0.0.1", 0))
        command_socket.settimeout(2.0)
        command_port = command_socket.getsockname()[1]
        observation_port = _free_udp_port()

        backend = UdpLiveSimulinkBackend(
            command_host="127.0.0.1",
            command_port=command_port,
            observation_host="127.0.0.1",
            observation_port=observation_port,
            receive_timeout_s=1.0,
            reset_timeout_s=1.0,
        )

        sender = threading.Thread(
            target=_send_observation_after_delay,
            args=(observation_port, 0.05, 1.0),
            daemon=True,
        )
        sender.start()
        try:
            observation = backend.reset()
            backend.apply_command(DTCommand.discharge(100.0, reason="unit test"))
            datagram, _sender = command_socket.recvfrom(65535)
        finally:
            backend.close()
            command_socket.close()

        packet = packet_from_datagram(datagram)
        command = command_from_packet(packet)

        self.assertEqual(observation.sim_time_s, 1.0)
        self.assertEqual(packet["kind"], "command")
        self.assertEqual(command.mode, "DISCHARGE")
        self.assertEqual(command.p_batt_cmd_w, 100.0)
        self.assertEqual(command.reason, "unit test")

    def test_backend_repeats_latest_command_while_advancing(self):
        command_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        command_socket.bind(("127.0.0.1", 0))
        command_socket.settimeout(1.0)
        command_port = command_socket.getsockname()[1]
        observation_port = _free_udp_port()

        backend = UdpLiveSimulinkBackend(
            command_host="127.0.0.1",
            command_port=command_port,
            observation_host="127.0.0.1",
            observation_port=observation_port,
            receive_timeout_s=0.05,
            reset_timeout_s=1.0,
            command_resend_period_s=0.02,
        )

        sender = threading.Thread(
            target=_send_observation_after_delay,
            args=(observation_port, 0.05, 1.0),
            daemon=True,
        )
        sender.start()
        try:
            backend.reset()
            backend.apply_command(DTCommand.discharge(100.0, reason="unit test"))
            backend.advance(0.05)
            packets = []
            while len(packets) < 2:
                datagram, _sender = command_socket.recvfrom(65535)
                packets.append(packet_from_datagram(datagram))
        finally:
            backend.close()
            command_socket.close()

        self.assertGreaterEqual(len(packets), 2)
        self.assertEqual(packets[0]["command"]["p_batt_cmd_w"], 100.0)
        self.assertEqual(packets[-1]["command"]["p_batt_cmd_w"], 100.0)
        self.assertGreater(packets[-1]["seq"], packets[0]["seq"])


def _free_udp_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


def _send_observation_after_delay(port: int, delay_s: float, sim_time_s: float) -> None:
    time.sleep(delay_s)
    observation = DTObservation(
        sim_time_s=sim_time_s,
        soc_pct=50.0,
        v_bus_v=400.0,
        p_batt_w=0.0,
    )
    packet = make_observation_packet(observation, seq=1)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(packet_to_datagram(packet), ("127.0.0.1", port))
    finally:
        sock.close()


if __name__ == "__main__":
    unittest.main()
