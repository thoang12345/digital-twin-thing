from __future__ import annotations

from collections import Counter
from pathlib import Path

from Modules.Digital_Twins.types import DTGoal, RunnerEvent, RunnerResult


def write_mission_report(
    result: RunnerResult,
    goal: DTGoal,
    output_path: str | Path,
) -> None:
    """Write a human-readable Markdown report for a runner mission."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(build_mission_report(result, goal), encoding="utf-8")
    tmp_path.replace(path)


def build_mission_report(result: RunnerResult, goal: DTGoal) -> str:
    events = result.events
    observations = [event.observation for event in events]
    if result.final_observation is not None:
        observations = [*observations, result.final_observation]

    lines: list[str] = [
        "# Autonomous DT Mission Report",
        "",
        "## Mission outcome",
        "",
        f"- Status: `{result.status.value}`",
        f"- Reason: {result.reason}",
        f"- Supervisor decisions: {len(events)}",
    ]

    if observations:
        start = observations[0]
        end = observations[-1]
        lines.extend(
            [
                f"- Simulated time: {start.sim_time_s:.3f} s to {end.sim_time_s:.3f} s",
                f"- SOC: {start.soc_pct:.3f}% -> {end.soc_pct:.3f}%",
                f"- Bus voltage: {start.v_bus_v:.3f} V -> {end.v_bus_v:.3f} V",
            ]
        )

    lines.extend(
        [
            "",
            "## Goal",
            "",
            f"- SOC target band: {goal.soc_min_pct:.3f}% to {goal.soc_max_pct:.3f}%",
            f"- SOC hard limits: {goal.soc_min_hard_pct:.3f}% to {goal.soc_max_hard_pct:.3f}%",
            f"- Bus nominal: {goal.bus_nominal_v:.3f} V",
            f"- Bus soft band: {goal.bus_min_v:.3f} V to {goal.bus_max_v:.3f} V",
            f"- Bus hard band: {goal.bus_min_hard_v:.3f} V to {goal.bus_max_hard_v:.3f} V",
        ]
    )

    if observations:
        lines.extend(_summary_lines(observations))

    lines.extend(_decision_summary_lines(events))
    lines.extend(_violation_lines(events))
    lines.extend(_timeline_lines(events))
    return "\n".join(lines).rstrip() + "\n"


def _summary_lines(observations) -> list[str]:
    soc_values = [obs.soc_pct for obs in observations]
    v_bus_values = [obs.v_bus_v for obs in observations]
    p_batt_values = [obs.p_batt_w for obs in observations]
    p_load_values = [obs.p_load_w for obs in observations]
    load_consumption_values = [obs.resolved_load_consumption_w() for obs in observations]
    p_source_values = [obs.p_source_w for obs in observations]
    source_deficit_values = [
        float(obs.extra["source_deficit_w"])
        for obs in observations
        if "source_deficit_w" in obs.extra
    ]
    bus_support_target_values = [
        float(obs.extra["bus_support_target_w"])
        for obs in observations
        if "bus_support_target_w" in obs.extra
    ]
    bus_support_integral_values = [
        float(obs.extra["bus_support_integral_w"])
        for obs in observations
        if "bus_support_integral_w" in obs.extra
    ]
    bus_support_trim_values = [
        float(obs.extra["bus_support_trim_w"])
        for obs in observations
        if "bus_support_trim_w" in obs.extra
    ]
    safe_discharge_values = [
        obs.max_safe_discharge_w
        for obs in observations
        if obs.max_safe_discharge_w is not None
    ]
    safe_charge_values = [
        obs.max_safe_charge_w
        for obs in observations
        if obs.max_safe_charge_w is not None
    ]

    lines = [
        "",
        "## Telemetry summary",
        "",
        f"- SOC min/max: {_min(soc_values):.3f}% / {_max(soc_values):.3f}%",
        f"- Bus voltage min/max: {_min(v_bus_values):.3f} V / {_max(v_bus_values):.3f} V",
        f"- Battery power min/max: {_min(p_batt_values):.3f} W / {_max(p_batt_values):.3f} W",
        f"- Raw load power min/max: {_min(p_load_values):.3f} W / {_max(p_load_values):.3f} W",
        f"- Load consumption min/max: {_min(load_consumption_values):.3f} W / {_max(load_consumption_values):.3f} W",
        f"- Source power min/max: {_min(p_source_values):.3f} W / {_max(p_source_values):.3f} W",
    ]
    if source_deficit_values:
        lines.append(
            "- Source deficit min/max: "
            f"{_min(source_deficit_values):.3f} W / {_max(source_deficit_values):.3f} W"
        )
    if bus_support_target_values:
        lines.append(
            "- Bus support target min/max: "
            f"{_min(bus_support_target_values):.3f} W / {_max(bus_support_target_values):.3f} W"
        )
    if bus_support_integral_values:
        lines.append(
            "- Bus support integral contribution min/max: "
            f"{_min(bus_support_integral_values):.3f} W / {_max(bus_support_integral_values):.3f} W"
        )
    if bus_support_trim_values:
        lines.append(
            "- Bus support trim contribution min/max: "
            f"{_min(bus_support_trim_values):.3f} W / {_max(bus_support_trim_values):.3f} W"
        )
    if safe_discharge_values:
        lines.append(
            "- Safe discharge cap min/max: "
            f"{_min(safe_discharge_values):.3f} W / {_max(safe_discharge_values):.3f} W"
        )
    if safe_charge_values:
        lines.append(
            "- Safe charge cap min/max: "
            f"{_min(safe_charge_values):.3f} W / {_max(safe_charge_values):.3f} W"
        )
    recent_observations = _recent_window(observations, window_s=30.0)
    if len(recent_observations) >= 2:
        recent_v_bus_values = [obs.v_bus_v for obs in recent_observations]
        recent_p_batt_values = [obs.p_batt_w for obs in recent_observations]
        lines.append(
            "- Recent bus voltage ripple (last 30 s): "
            f"{_min(recent_v_bus_values):.3f} V / "
            f"{_max(recent_v_bus_values):.3f} V "
            f"(p2p {_peak_to_peak(recent_v_bus_values):.3f} V)"
        )
        lines.append(
            "- Recent battery power ripple (last 30 s): "
            f"{_min(recent_p_batt_values):.3f} W / "
            f"{_max(recent_p_batt_values):.3f} W "
            f"(p2p {_peak_to_peak(recent_p_batt_values):.3f} W)"
        )
    return lines


def _decision_summary_lines(events: list[RunnerEvent]) -> list[str]:
    applied_counts = Counter(event.command.mode for event in events)
    policy_counts = Counter(
        event.policy_command.mode for event in events if event.policy_command is not None
    )
    if not applied_counts:
        return [
            "",
            "## Decision summary",
            "",
            "- No supervisor decisions were recorded.",
        ]

    applied_command_values = [event.command.p_batt_cmd_w for event in events]
    policy_command_values = [
        event.policy_command.p_batt_cmd_w
        for event in events
        if event.policy_command is not None
    ]
    lines = [
        "",
        "## Decision summary",
        "",
        "- Policy/LLM requested battery power min/max: "
        f"{_min(policy_command_values):.3f} W / {_max(policy_command_values):.3f} W",
        "- Applied battery power min/max: "
        f"{_min(applied_command_values):.3f} W / {_max(applied_command_values):.3f} W",
        "- Policy/LLM mode counts:",
    ]
    if policy_counts:
        for mode, count in sorted(policy_counts.items()):
            lines.append(f"  - {mode}: {count}")
    else:
        lines.append("  - none recorded")
    lines.append("- Applied mode counts:")
    for mode, count in sorted(applied_counts.items()):
        lines.append(f"  - {mode}: {count}")
    return lines


def _violation_lines(events: list[RunnerEvent]) -> list[str]:
    violations = [
        (event.observation.sim_time_s, violation)
        for event in events
        for violation in event.violations
    ]
    lines = ["", "## Constraint violations", ""]
    if not violations:
        lines.append("- No soft or hard constraint violations were recorded.")
        return lines

    for sim_time_s, violation in violations:
        lines.append(f"- t={sim_time_s:.3f} s: {violation}")
    bridge_errors = [
        (event.observation.sim_time_s, event.observation.extra.get("bridge_error"))
        for event in events
        if event.observation.extra.get("bridge_error")
    ]
    if bridge_errors:
        lines.extend(["", "Bridge error details:"])
        for sim_time_s, bridge_error in bridge_errors:
            lines.append(f"- t={sim_time_s:.3f} s: {_single_line(bridge_error)}")
    return lines


def _timeline_lines(events: list[RunnerEvent]) -> list[str]:
    lines = [
        "",
        "## Decision timeline",
        "",
        "| t (s) | SOC (%) | Vbus (V) | P_batt (W) | P_load raw (W) | Load consumed (W) | P_source (W) | Source deficit (W) | Source slack (W) | Bus error (V) | Bus support | Bus I (W) | Bus trim (W) | Raw target (W) | Bus target (W) | Source support | Source target (W) | Max safe discharge (W) | Max safe charge (W) | Faults | Policy/LLM Mode | Policy/LLM P_batt_cmd (W) | Applied Mode | Applied P_batt_cmd (W) | Python adjustment | Policy/LLM reason |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---|---:|---:|---:|---|---|---:|---|---:|---|---|",
    ]
    if not events:
        lines.append("| - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | - | No events recorded. |")
        return lines

    for event in events:
        obs = event.observation
        policy_cmd = event.policy_command
        cmd = event.command
        active_faults = [
            name for name, is_active in obs.fault_flags.items() if is_active
        ]
        lines.append(
            "| "
            f"{obs.sim_time_s:.3f} | "
            f"{obs.soc_pct:.3f} | "
            f"{obs.v_bus_v:.3f} | "
            f"{obs.p_batt_w:.3f} | "
            f"{obs.p_load_w:.3f} | "
            f"{obs.resolved_load_consumption_w():.3f} | "
            f"{obs.p_source_w:.3f} | "
            f"{_optional_extra_float_cell(obs, 'source_deficit_w')} | "
            f"{_optional_extra_float_cell(obs, 'bus_support_trim_source_slack_w')} | "
            f"{_optional_extra_float_cell(obs, 'bus_voltage_error_v')} | "
            f"{_md_cell(_bus_support_cell(obs))} | "
            f"{_optional_extra_float_cell(obs, 'bus_support_integral_w')} | "
            f"{_optional_extra_float_cell(obs, 'bus_support_trim_w')} | "
            f"{_optional_extra_float_cell(obs, 'bus_support_target_unslewed_w')} | "
            f"{_optional_extra_float_cell(obs, 'bus_support_target_w')} | "
            f"{_md_cell(_source_support_cell(obs))} | "
            f"{_optional_extra_float_cell(obs, 'source_support_target_w')} | "
            f"{_optional_float_cell(obs.max_safe_discharge_w)} | "
            f"{_optional_float_cell(obs.max_safe_charge_w)} | "
            f"{_md_cell(', '.join(active_faults))} | "
            f"{_md_cell(_optional_mode(policy_cmd))} | "
            f"{_optional_power_cell(policy_cmd)} | "
            f"{_md_cell(cmd.mode)} | "
            f"{cmd.p_batt_cmd_w:.3f} | "
            f"{_md_cell(event.constraint_note())} | "
            f"{_md_cell(_optional_reason(policy_cmd))} |"
        )
    return lines


def _min(values: list[float]) -> float:
    return min(values) if values else 0.0


def _max(values: list[float]) -> float:
    return max(values) if values else 0.0


def _peak_to_peak(values: list[float]) -> float:
    if not values:
        return 0.0
    return _max(values) - _min(values)


def _recent_window(observations, *, window_s: float):
    if not observations:
        return []
    end_time_s = observations[-1].sim_time_s
    start_time_s = end_time_s - max(0.0, window_s)
    return [obs for obs in observations if obs.sim_time_s >= start_time_s]


def _md_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _single_line(value) -> str:
    return str(value).replace("\r", " ").replace("\n", " ")


def _optional_float_cell(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.3f}"


def _optional_extra_float_cell(observation, key: str) -> str:
    value = observation.extra.get(key)
    if value is None:
        return "-"
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "-"


def _source_support_cell(observation) -> str:
    active = bool(observation.extra.get("source_support_active"))
    needed = bool(observation.extra.get("source_support_needed"))
    if active:
        return "active"
    if needed:
        return "needed"
    return "-"


def _bus_support_cell(observation) -> str:
    if bool(observation.extra.get("bus_voltage_support_active")):
        return "active"
    return "-"


def _optional_mode(command) -> str:
    if command is None:
        return "-"
    return str(command.mode)


def _optional_power_cell(command) -> str:
    if command is None:
        return "-"
    return f"{command.p_batt_cmd_w:.3f}"


def _optional_reason(command) -> str:
    if command is None:
        return ""
    return str(command.reason)
