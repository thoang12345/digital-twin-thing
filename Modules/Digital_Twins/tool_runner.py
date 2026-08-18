from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from openai import OpenAI

from Modules.Digital_Twins.backends import MockBatteryBusBackend, SimulinkBackend
from Modules.Digital_Twins.policy import LLMControlPolicy, SocBandPolicy
from Modules.Digital_Twins.reporting import write_mission_report
from Modules.Digital_Twins.runner import AutonomousRunner, write_runner_events_csv
from Modules.Digital_Twins.types import DTGoal, RunnerConfig, RunnerEvent, RunnerResult
from Modules.Digital_Twins.udp_backend import UdpLiveSimulinkBackend


def run_autonomous_DT(
    backend: str = "mock",
    policy: str = "heuristic",
    max_sim_seconds: float = 30.0,
    tick_seconds: float = 5.0,
    startup_grace_seconds: float = 1.0,
    success_hold_seconds: float = 999.0,
    soc_min: float = 40.0,
    soc_max: float = 80.0,
    bus_nominal: float = 400.0,
    max_p_batt: float = 500.0,
    max_p_batt_step: float = 100.0,
    prevent_source_backfeed: bool = True,
    source_min_power: float = 0.0,
    source_power_margin: float = 25.0,
    source_power_limit: float | None = None,
    prevent_charge_without_source_headroom: bool = True,
    charge_power_margin: float = 25.0,
    charge_bus_hysteresis_volts: float = 5.0,
    charge_recovery_hold_seconds: float = 10.0,
    post_discharge_charge_hold_seconds: float = 10.0,
    block_discharge_below_soc_min: bool = True,
    allow_source_support_below_soc_min: bool = True,
    source_support_entry_margin: float = 5.0,
    source_support_clear_margin: float = 1.0,
    source_support_bus_hysteresis_volts: float = 5.0,
    source_support_hold_seconds: float = 3.0,
    bus_support_min: float = 150.0,
    bus_support_gain: float = 5.0,
    bus_support_integral_gain: float = 0.0,
    bus_support_integral_max: float = 20.0,
    bus_support_integral_leak: float = 0.25,
    bus_support_integral_deadband_volts: float = 0.25,
    bus_support_trim_gain: float = 0.0,
    bus_support_trim_max: float = 12.0,
    bus_support_trim_decay: float = 0.25,
    bus_support_trim_deadband_volts: float = 0.25,
    bus_support_trim_source_slack_deadband: float = 2.0,
    bus_support_target_slew_down: float = 0.0,
    safety_recovery: bool = False,
    safety_recovery_attempts: int = 2,
    initial_soc: float = 55.0,
    real_time: bool = False,
    model_path: str | None = None,
    model_name: str = "DT_enviroment",
    udp_command_host: str = "127.0.0.1",
    udp_command_port: int = 55000,
    udp_observation_host: str = "0.0.0.0",
    udp_observation_port: int = 55001,
    udp_timeout: float = 2.0,
    udp_reset_timeout: float = 5.0,
    udp_command_resend_period: float = 0.25,
    udp_send_reset: bool = False,
    udp_republish_host: str | None = None,
    udp_republish_port: int | None = None,
    llm_model: str = "llama-3-groq-8b-tool-use",
    llm_base_url: str = "http://localhost:1234/v1",
    llm_api_key: str = "lm-studio",
    llm_temperature: float = 0.0,
    llm_max_tokens: int = 120,
    llm_command_limit: float = 500.0,
    llm_mode_gate: bool = False,
    llm_strict: bool = False,
    output_dir: str = "logs/agent_dt_runs",
    run_label: str | None = None,
) -> dict[str, Any]:
    """Run the autonomous DT mission as an agent-callable tool.

    This is intentionally a thin programmatic wrapper around the existing
    autonomous runner. It returns a compact result suitable for the main agent
    tool loop while writing the detailed CSV/report/LLM trace artifacts to disk.
    """

    backend = _choice("backend", backend, {"mock", "simulink", "udp"})
    policy = _choice("policy", policy, {"heuristic", "llm"})
    max_sim_seconds = _positive_float("max_sim_seconds", max_sim_seconds)
    tick_seconds = _positive_float("tick_seconds", tick_seconds)
    startup_grace_seconds = max(0.0, float(startup_grace_seconds))
    success_hold_seconds = max(0.0, float(success_hold_seconds))
    max_p_batt = abs(float(max_p_batt))
    max_p_batt_step = abs(float(max_p_batt_step))
    source_min_power = max(0.0, float(source_min_power))
    source_power_margin = max(0.0, float(source_power_margin))
    if source_power_limit is not None:
        source_power_limit = max(0.0, float(source_power_limit))
    charge_power_margin = max(0.0, float(charge_power_margin))
    charge_bus_hysteresis_volts = max(0.0, float(charge_bus_hysteresis_volts))
    charge_recovery_hold_seconds = max(0.0, float(charge_recovery_hold_seconds))
    post_discharge_charge_hold_seconds = max(
        0.0,
        float(post_discharge_charge_hold_seconds),
    )
    source_support_entry_margin = max(0.0, float(source_support_entry_margin))
    source_support_clear_margin = max(0.0, float(source_support_clear_margin))
    source_support_bus_hysteresis_volts = max(
        0.0,
        float(source_support_bus_hysteresis_volts),
    )
    source_support_hold_seconds = max(0.0, float(source_support_hold_seconds))
    bus_support_min = max(0.0, float(bus_support_min))
    bus_support_gain = max(0.0, float(bus_support_gain))
    bus_support_integral_gain = max(0.0, float(bus_support_integral_gain))
    bus_support_integral_max = max(0.0, float(bus_support_integral_max))
    bus_support_integral_leak = max(0.0, float(bus_support_integral_leak))
    bus_support_integral_deadband_volts = max(
        0.0,
        float(bus_support_integral_deadband_volts),
    )
    bus_support_trim_gain = max(0.0, float(bus_support_trim_gain))
    bus_support_trim_max = max(0.0, float(bus_support_trim_max))
    bus_support_trim_decay = max(0.0, float(bus_support_trim_decay))
    bus_support_trim_deadband_volts = max(
        0.0,
        float(bus_support_trim_deadband_volts),
    )
    bus_support_trim_source_slack_deadband = max(
        0.0,
        float(bus_support_trim_source_slack_deadband),
    )
    bus_support_target_slew_down = max(0.0, float(bus_support_target_slew_down))
    safety_recovery_attempts = max(0, int(safety_recovery_attempts))

    paths = _artifact_paths(output_dir=output_dir, run_label=run_label)
    goal = DTGoal(
        soc_min_pct=float(soc_min),
        soc_max_pct=float(soc_max),
        bus_nominal_v=float(bus_nominal),
        success_hold_s=success_hold_seconds,
        max_sim_time_s=max_sim_seconds,
    )
    config = RunnerConfig(
        supervisor_period_s=tick_seconds,
        startup_grace_s=startup_grace_seconds,
        max_p_batt_abs_w=max_p_batt,
        max_p_batt_step_w=max_p_batt_step,
        prevent_source_backfeed=bool(prevent_source_backfeed),
        source_min_power_w=source_min_power,
        source_power_margin_w=source_power_margin,
        source_power_limit_w=source_power_limit,
        prevent_charge_without_source_headroom=bool(
            prevent_charge_without_source_headroom
        ),
        charge_power_margin_w=charge_power_margin,
        charge_bus_hysteresis_v=charge_bus_hysteresis_volts,
        charge_recovery_hold_s=charge_recovery_hold_seconds,
        post_discharge_charge_hold_s=post_discharge_charge_hold_seconds,
        block_discharge_below_soc_min=bool(block_discharge_below_soc_min),
        allow_source_support_below_soc_min=bool(
            allow_source_support_below_soc_min
        ),
        source_support_entry_margin_w=source_support_entry_margin,
        source_support_clear_margin_w=source_support_clear_margin,
        source_support_bus_hysteresis_v=source_support_bus_hysteresis_volts,
        source_support_hold_s=source_support_hold_seconds,
        bus_support_min_w=bus_support_min,
        bus_support_gain_w_per_v=bus_support_gain,
        bus_support_integral_gain_w_per_v_s=bus_support_integral_gain,
        bus_support_integral_max_w=bus_support_integral_max,
        bus_support_integral_leak_per_s=bus_support_integral_leak,
        bus_support_integral_deadband_v=bus_support_integral_deadband_volts,
        bus_support_trim_gain_w_per_v_s=bus_support_trim_gain,
        bus_support_trim_max_w=bus_support_trim_max,
        bus_support_trim_decay_w_per_s=bus_support_trim_decay,
        bus_support_trim_deadband_v=bus_support_trim_deadband_volts,
        bus_support_trim_source_slack_deadband_w=(
            bus_support_trim_source_slack_deadband
        ),
        bus_support_target_slew_down_w_per_s=bus_support_target_slew_down,
        safety_recovery_enabled=bool(safety_recovery),
        safety_recovery_attempts=safety_recovery_attempts,
        real_time=bool(real_time),
    )
    selected_backend = _build_backend(
        backend=backend,
        initial_soc=initial_soc,
        bus_nominal=bus_nominal,
        model_path=model_path,
        model_name=model_name,
        udp_command_host=udp_command_host,
        udp_command_port=udp_command_port,
        udp_observation_host=udp_observation_host,
        udp_observation_port=udp_observation_port,
        udp_timeout=udp_timeout,
        udp_reset_timeout=udp_reset_timeout,
        udp_command_resend_period=udp_command_resend_period,
        udp_send_reset=udp_send_reset,
        udp_republish_host=udp_republish_host,
        udp_republish_port=udp_republish_port,
    )
    selected_policy = _build_policy(
        policy=policy,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
        llm_api_key=llm_api_key,
        llm_temperature=llm_temperature,
        llm_max_tokens=llm_max_tokens,
        llm_command_limit=llm_command_limit,
        llm_mode_gate=llm_mode_gate,
        llm_strict=llm_strict,
        llm_log_path=str(paths["llm_log"]),
    )

    runner = AutonomousRunner(
        backend=selected_backend,
        goal=goal,
        policy=selected_policy,
        config=config,
    )
    result = runner.run()
    write_runner_events_csv(result.events, paths["csv"])
    write_mission_report(result, goal, paths["report"])

    return _tool_result(
        result=result,
        backend=backend,
        policy=policy,
        goal=goal,
        config=config,
        paths=paths,
        selected_policy=selected_policy,
    )


def _build_backend(
    *,
    backend: str,
    initial_soc: float,
    bus_nominal: float,
    model_path: str | None,
    model_name: str,
    udp_command_host: str,
    udp_command_port: int,
    udp_observation_host: str,
    udp_observation_port: int,
    udp_timeout: float,
    udp_reset_timeout: float,
    udp_command_resend_period: float,
    udp_send_reset: bool,
    udp_republish_host: str | None,
    udp_republish_port: int | None,
):
    if backend == "mock":
        return MockBatteryBusBackend(
            initial_soc_pct=float(initial_soc),
            bus_nominal_v=float(bus_nominal),
        )
    if backend == "simulink":
        return SimulinkBackend(
            model_name=model_name,
            model_path=model_path,
        )
    return UdpLiveSimulinkBackend(
        command_host=udp_command_host,
        command_port=int(udp_command_port),
        observation_host=udp_observation_host,
        observation_port=int(udp_observation_port),
        receive_timeout_s=float(udp_timeout),
        reset_timeout_s=float(udp_reset_timeout),
        command_resend_period_s=float(udp_command_resend_period),
        send_reset_on_reset=bool(udp_send_reset),
        telemetry_host=udp_republish_host,
        telemetry_port=udp_republish_port,
    )


def _build_policy(
    *,
    policy: str,
    llm_model: str,
    llm_base_url: str,
    llm_api_key: str,
    llm_temperature: float,
    llm_max_tokens: int,
    llm_command_limit: float,
    llm_mode_gate: bool,
    llm_strict: bool,
    llm_log_path: str,
):
    if policy == "heuristic":
        return SocBandPolicy()

    client = OpenAI(base_url=llm_base_url, api_key=llm_api_key)
    return LLMControlPolicy(
        client=client,
        model=llm_model,
        temperature=float(llm_temperature),
        max_tokens=int(llm_max_tokens),
        max_command_abs_w=abs(float(llm_command_limit)),
        mode_gate=bool(llm_mode_gate),
        trace_path=llm_log_path,
        strict=bool(llm_strict),
        verbose=False,
    )


def _artifact_paths(output_dir: str, run_label: str | None) -> dict[str, Path]:
    safe_label = _safe_label(run_label)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"{safe_label}_{timestamp}" if safe_label else f"dt_tool_run_{timestamp}"
    root = Path(output_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return {
        "csv": root / f"{stem}.csv",
        "report": root / f"{stem}_report.md",
        "llm_log": root / f"{stem}_llm.jsonl",
    }


def _tool_result(
    *,
    result: RunnerResult,
    backend: str,
    policy: str,
    goal: DTGoal,
    config: RunnerConfig,
    paths: dict[str, Path],
    selected_policy,
) -> dict[str, Any]:
    final_observation = (
        result.final_observation.to_dict() if result.final_observation else None
    )
    payload: dict[str, Any] = {
        "tool": "run_autonomous_DT",
        "backend": backend,
        "policy": policy,
        "status": result.status.value,
        "reason": result.reason,
        "event_count": len(result.events),
        "goal": {
            "soc_min_pct": goal.soc_min_pct,
            "soc_max_pct": goal.soc_max_pct,
            "bus_nominal_v": goal.bus_nominal_v,
            "bus_min_v": goal.bus_min_v,
            "bus_max_v": goal.bus_max_v,
            "max_sim_time_s": goal.max_sim_time_s,
            "success_hold_s": goal.success_hold_s,
        },
        "runner_guards": {
            "prevent_source_backfeed": config.prevent_source_backfeed,
            "source_min_power_w": config.source_min_power_w,
            "source_power_margin_w": config.source_power_margin_w,
            "source_power_limit_w": config.source_power_limit_w,
            "prevent_charge_without_source_headroom": (
                config.prevent_charge_without_source_headroom
            ),
            "charge_power_margin_w": config.charge_power_margin_w,
            "charge_bus_hysteresis_v": config.charge_bus_hysteresis_v,
            "charge_recovery_hold_s": config.charge_recovery_hold_s,
            "post_discharge_charge_hold_s": config.post_discharge_charge_hold_s,
            "block_discharge_below_soc_min": config.block_discharge_below_soc_min,
            "allow_source_support_below_soc_min": (
                config.allow_source_support_below_soc_min
            ),
            "source_support_entry_margin_w": config.source_support_entry_margin_w,
            "source_support_clear_margin_w": config.source_support_clear_margin_w,
            "source_support_bus_hysteresis_v": (
                config.source_support_bus_hysteresis_v
            ),
            "source_support_hold_s": config.source_support_hold_s,
            "bus_support_min_w": config.bus_support_min_w,
            "bus_support_gain_w_per_v": config.bus_support_gain_w_per_v,
            "bus_support_integral_gain_w_per_v_s": (
                config.bus_support_integral_gain_w_per_v_s
            ),
            "bus_support_integral_max_w": config.bus_support_integral_max_w,
            "bus_support_integral_leak_per_s": (
                config.bus_support_integral_leak_per_s
            ),
            "bus_support_integral_deadband_v": (
                config.bus_support_integral_deadband_v
            ),
            "bus_support_trim_gain_w_per_v_s": (
                config.bus_support_trim_gain_w_per_v_s
            ),
            "bus_support_trim_max_w": config.bus_support_trim_max_w,
            "bus_support_trim_decay_w_per_s": config.bus_support_trim_decay_w_per_s,
            "bus_support_trim_deadband_v": config.bus_support_trim_deadband_v,
            "bus_support_trim_source_slack_deadband_w": (
                config.bus_support_trim_source_slack_deadband_w
            ),
            "bus_support_target_slew_down_w_per_s": (
                config.bus_support_target_slew_down_w_per_s
            ),
            "safety_recovery_enabled": config.safety_recovery_enabled,
            "safety_recovery_attempts": config.safety_recovery_attempts,
        },
        "final_observation": final_observation,
        "artifacts": {
            "csv": str(paths["csv"]),
            "report": str(paths["report"]),
            "llm_log": str(paths["llm_log"]) if policy == "llm" else None,
        },
        "recent_events": [_event_summary(event) for event in result.events[-5:]],
    }
    if isinstance(selected_policy, LLMControlPolicy):
        payload["llm_calls"] = {
            "attempted": selected_policy.attempted_calls,
            "successful": selected_policy.successful_calls,
            "fallbacks": selected_policy.fallback_calls,
        }
    return payload


def _event_summary(event: RunnerEvent) -> dict[str, Any]:
    obs = event.observation
    policy_cmd = event.policy_command
    cmd = event.command
    return {
        "tick_index": event.tick_index,
        "status": event.status.value,
        "sim_time_s": obs.sim_time_s,
        "soc_pct": obs.soc_pct,
        "v_bus_v": obs.v_bus_v,
        "p_batt_w": obs.p_batt_w,
        "p_load_w": obs.p_load_w,
        "load_consumption_w": obs.resolved_load_consumption_w(),
        "p_source_w": obs.p_source_w,
        "max_safe_discharge_w": obs.max_safe_discharge_w,
        "max_safe_charge_w": obs.max_safe_charge_w,
        "source_power_limit_w": obs.source_power_limit_w,
        "source_deficit_w": obs.extra.get("source_deficit_w"),
        "source_support_needed": obs.extra.get("source_support_needed"),
        "source_support_active": obs.extra.get("source_support_active"),
        "source_support_target_w": obs.extra.get("source_support_target_w"),
        "bus_voltage_error_v": obs.extra.get("bus_voltage_error_v"),
        "bus_voltage_support_w": obs.extra.get("bus_voltage_support_w"),
        "bus_voltage_support_active": obs.extra.get("bus_voltage_support_active"),
        "bus_support_integral_error_v": obs.extra.get(
            "bus_support_integral_error_v"
        ),
        "bus_support_integral_v_s": obs.extra.get("bus_support_integral_v_s"),
        "bus_support_integral_w": obs.extra.get("bus_support_integral_w"),
        "bus_support_integral_context_active": obs.extra.get(
            "bus_support_integral_context_active"
        ),
        "bus_support_trim_error_v": obs.extra.get("bus_support_trim_error_v"),
        "bus_support_trim_source_slack_w": obs.extra.get(
            "bus_support_trim_source_slack_w"
        ),
        "bus_support_trim_w": obs.extra.get("bus_support_trim_w"),
        "bus_support_target_unslewed_w": obs.extra.get(
            "bus_support_target_unslewed_w"
        ),
        "bus_support_target_slew_active": obs.extra.get(
            "bus_support_target_slew_active"
        ),
        "bus_support_target_w": obs.extra.get("bus_support_target_w"),
        "policy_mode": policy_cmd.mode if policy_cmd else None,
        "policy_p_batt_cmd_w": policy_cmd.p_batt_cmd_w if policy_cmd else None,
        "policy_command_reason": policy_cmd.reason if policy_cmd else None,
        "command_mode": cmd.mode,
        "p_batt_cmd_w": cmd.p_batt_cmd_w,
        "command_reason": cmd.reason,
        "constraint_note": event.constraint_note(),
        "violations": list(event.violations),
    }


def _choice(name: str, value: str, allowed: set[str]) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in allowed:
        raise ValueError(f"{name} must be one of {sorted(allowed)}, got {value!r}")
    return normalized


def _positive_float(name: str, value: float) -> float:
    resolved = float(value)
    if resolved <= 0:
        raise ValueError(f"{name} must be positive, got {value!r}")
    return resolved


def _safe_label(value: str | None) -> str:
    if not value:
        return ""
    safe_chars = []
    for char in str(value):
        if char.isalnum() or char in {"-", "_"}:
            safe_chars.append(char)
        elif char.isspace():
            safe_chars.append("_")
    return "".join(safe_chars).strip("_")[:80]
