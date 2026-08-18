from __future__ import annotations

import json
import math
import time
from typing import Any

from Modules.Digital_Twins.types import DTCommand, DTObservation


PROTOCOL_NAME = "dt_udp"
PROTOCOL_VERSION = 1
MAX_DATAGRAM_BYTES = 8192


class UdpProtocolError(ValueError):
    """Raised when a UDP datagram does not match the DT protocol."""


def mode_to_code(mode: str) -> float:
    normalized = str(mode or "HOLD").strip().upper()
    if normalized == "CHARGE":
        return -1.0
    if normalized == "DISCHARGE":
        return 1.0
    if normalized == "SAFE":
        return 99.0
    return 0.0


def code_to_mode(code: float) -> str:
    if float(code) == -1.0:
        return "CHARGE"
    if float(code) == 1.0:
        return "DISCHARGE"
    if float(code) == 99.0:
        return "SAFE"
    return "HOLD"


def make_command_packet(command: DTCommand, seq: int) -> dict[str, Any]:
    payload = command.to_dict()
    payload["mode_code"] = mode_to_code(command.mode)
    return _base_packet("command", seq=seq, command=payload)


def make_control_packet(action: str, seq: int, reason: str = "") -> dict[str, Any]:
    return _base_packet(
        "control",
        seq=seq,
        control={"action": str(action), "reason": str(reason)},
    )


def make_observation_packet(observation: DTObservation, seq: int) -> dict[str, Any]:
    return _base_packet(
        "observation",
        seq=seq,
        observation=observation.to_dict(),
    )


def packet_to_datagram(packet: dict[str, Any]) -> bytes:
    datagram = json.dumps(packet, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(datagram) > MAX_DATAGRAM_BYTES:
        raise UdpProtocolError(
            f"UDP datagram is {len(datagram)} bytes; limit is {MAX_DATAGRAM_BYTES}"
        )
    return datagram


def packet_from_datagram(datagram: bytes) -> dict[str, Any]:
    try:
        packet = json.loads(datagram.decode("utf-8"))
    except Exception as exc:
        raise UdpProtocolError(f"invalid JSON datagram: {exc}") from exc

    if not isinstance(packet, dict):
        raise UdpProtocolError("UDP datagram must decode to a JSON object")
    if packet.get("protocol") != PROTOCOL_NAME:
        raise UdpProtocolError(f"unsupported protocol: {packet.get('protocol')}")
    if int(packet.get("version", -1)) != PROTOCOL_VERSION:
        raise UdpProtocolError(f"unsupported protocol version: {packet.get('version')}")
    if packet.get("kind") not in {"command", "observation", "control", "ack"}:
        raise UdpProtocolError(f"unsupported packet kind: {packet.get('kind')}")
    return packet


def observation_from_packet(packet: dict[str, Any]) -> DTObservation:
    if packet.get("kind") != "observation":
        raise UdpProtocolError(f"expected observation packet, got {packet.get('kind')}")

    payload = packet.get("observation")
    if not isinstance(payload, dict):
        raise UdpProtocolError("observation packet is missing an observation object")

    fault_flags = payload.get("fault_flags")
    if not isinstance(fault_flags, dict):
        fault_flags = {}

    extra = payload.get("extra")
    if not isinstance(extra, dict):
        extra = {}

    return DTObservation(
        sim_time_s=_float_payload(payload, "sim_time_s", 0.0),
        soc_pct=_float_payload(payload, "soc_pct", math.nan),
        v_bus_v=_float_payload(payload, "v_bus_v", math.nan),
        v_batt_v=_float_payload(payload, "v_batt_v", math.nan),
        i_batt_a=_float_payload(payload, "i_batt_a", math.nan),
        p_batt_w=_float_payload(payload, "p_batt_w", math.nan),
        p_load_w=_float_payload(payload, "p_load_w", math.nan),
        load_consumption_w=_optional_float_payload(payload, "load_consumption_w"),
        p_source_w=_float_payload(payload, "p_source_w", math.nan),
        max_safe_discharge_w=_optional_float_payload(payload, "max_safe_discharge_w"),
        max_safe_charge_w=_optional_float_payload(payload, "max_safe_charge_w"),
        source_power_limit_w=_optional_float_payload(payload, "source_power_limit_w"),
        source_can_sink_power=_bool_payload(payload, "source_can_sink_power", False),
        source_at_limit=_bool_payload(payload, "source_at_limit", False),
        source_available=_bool_payload(payload, "source_available", True),
        fault_flags={str(name): _coerce_bool(value) for name, value in fault_flags.items()},
        extra=dict(extra),
    )


def command_from_packet(packet: dict[str, Any]) -> DTCommand:
    if packet.get("kind") != "command":
        raise UdpProtocolError(f"expected command packet, got {packet.get('kind')}")

    payload = packet.get("command")
    if not isinstance(payload, dict):
        raise UdpProtocolError("command packet is missing a command object")

    mode = str(payload.get("mode", "HOLD")).strip().upper()
    if mode not in {"CHARGE", "HOLD", "DISCHARGE", "SAFE"}:
        mode = code_to_mode(_float_payload(payload, "mode_code", 0.0))
    return DTCommand(
        mode=mode,
        p_batt_cmd_w=_float_payload(payload, "p_batt_cmd_w", 0.0),
        enable=_bool_payload(payload, "enable", True),
        reason=str(payload.get("reason", "")),
    )


def _base_packet(kind: str, seq: int, **payload: Any) -> dict[str, Any]:
    return {
        "protocol": PROTOCOL_NAME,
        "version": PROTOCOL_VERSION,
        "kind": kind,
        "seq": int(seq),
        "sent_at_epoch_s": time.time(),
        **payload,
    }


def _float_payload(payload: dict[str, Any], key: str, default: float) -> float:
    value = payload.get(key, default)
    if isinstance(value, list):
        value = value[-1] if value else default
    if value is None:
        return default
    return float(value)


def _optional_float_payload(payload: dict[str, Any], key: str) -> float | None:
    if key not in payload:
        return None
    value = payload.get(key)
    if isinstance(value, list):
        value = value[-1] if value else None
    if value is None:
        return None
    resolved = float(value)
    if not math.isfinite(resolved):
        return None
    return resolved


def _bool_payload(payload: dict[str, Any], key: str, default: bool) -> bool:
    return _coerce_bool(payload.get(key, default))


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, list):
        value = value[-1] if value else False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
