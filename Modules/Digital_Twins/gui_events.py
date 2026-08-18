from __future__ import annotations

import json
import math
from typing import Any

from Modules.Digital_Twins.types import RunnerResult


DT_GUI_EVENT_PREFIX = "DT_GUI_EVENT "
LOCAL_STATE_NAMES = {
    0: "HOLD",
    1: "CHARGE",
    2: "BUS_SUPPORT",
    3: "SAFE_LOCAL",
}


def local_state_name(state_code: Any) -> str:
    """Return the state-machine label carried in Simulink telemetry."""

    code = _state_code(state_code)
    if code is None:
        return "NOT_REPORTED"
    return LOCAL_STATE_NAMES.get(code, f"UNKNOWN_{code}")


def build_dt_gui_event(result: RunnerResult) -> dict[str, Any] | None:
    """Build the compact event consumed by the Tkinter authority display.

    The observation describes the latest state reported by Simulink.  The
    policy and guarded command describe the next supervisory request sent by
    the Python runner, so the payload keeps those concepts explicitly
    separate.
    """

    if not result.events:
        return None

    event = result.events[-1]
    observation = event.observation
    policy_command = event.policy_command
    guarded_command = event.command
    state_code = _state_code(observation.extra.get("state_code"))
    state_name = local_state_name(state_code)

    return {
        "schema": "dt_gui_event_v1",
        "event": "supervisor_decision",
        "tick_index": int(event.tick_index),
        "mission_status": event.status.value,
        "sim_time_s": _finite_number(observation.sim_time_s),
        "soc_pct": _finite_number(observation.soc_pct),
        "v_bus_v": _finite_number(observation.v_bus_v),
        "p_batt_measured_w": _finite_number(observation.p_batt_w),
        "p_load_w": _finite_number(observation.p_load_w),
        "p_source_w": _finite_number(observation.p_source_w),
        "request_summary": _command_summary(policy_command),
        "runner_output_summary": _command_summary(guarded_command),
        "local_control_summary": (
            state_name if state_code is None else f"{state_name} [code {state_code}]"
        ),
        "feedback_summary": f"P_batt = {observation.p_batt_w:+.1f} W",
        "telemetry_summary": (
            f"t={observation.sim_time_s:.1f} s  "
            f"Vbus={observation.v_bus_v:.1f} V  SOC={observation.soc_pct:.1f} %"
        ),
        "interface_note": event.constraint_note(),
        "supervisor_request": _command_payload(policy_command),
        "guarded_udp_intent": _command_payload(guarded_command),
        "reported_local_state": {
            "code": state_code,
            "name": state_name,
        },
        "python_adjustment": event.constraint_note(),
        "violations": list(event.violations),
    }


def format_dt_gui_event(result: RunnerResult) -> str | None:
    payload = build_dt_gui_event(result)
    if payload is None:
        return None
    return DT_GUI_EVENT_PREFIX + json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


def parse_dt_gui_event(line: str) -> dict[str, Any] | None:
    stripped = str(line).strip()
    if not stripped.startswith(DT_GUI_EVENT_PREFIX):
        return None

    try:
        payload = json.loads(stripped[len(DT_GUI_EVENT_PREFIX) :])
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema") != "dt_gui_event_v1":
        return None
    return payload


def _command_payload(command) -> dict[str, Any] | None:
    if command is None:
        return None
    return {
        "mode": str(command.mode),
        "p_batt_cmd_w": _finite_number(command.p_batt_cmd_w),
        "enable": bool(command.enable),
        "reason": str(command.reason),
    }


def _command_summary(command) -> str:
    if command is None:
        return "No request"
    disabled = " (disabled)" if not command.enable else ""
    return f"{command.mode} {command.p_batt_cmd_w:+.1f} W{disabled}"


def _state_code(value: Any) -> int | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    rounded = int(round(numeric))
    if abs(numeric - rounded) > 0.25:
        return None
    return rounded


def _finite_number(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None
