from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from Modules.Digital_Twins.types import DTCommand, DTGoal, DTObservation


class ControlPolicy(Protocol):
    """Decision interface used by the autonomous runner."""

    def choose_action(self, observation: DTObservation, goal: DTGoal) -> DTCommand:
        """Choose one bounded supervisory command from the current observation."""


@dataclass(slots=True)
class SocBandPolicy:
    """Simple deterministic policy for the first autonomous-control prototype."""

    charge_power_w: float = 100.0
    discharge_power_w: float = 100.0
    bus_support_power_w: float = 150.0
    soc_deadband_pct: float = 1.0
    source_overload_margin_w: float = 25.0

    def choose_action(self, observation: DTObservation, goal: DTGoal) -> DTCommand:
        active_faults = [
            name for name, is_active in observation.fault_flags.items() if is_active
        ]
        if active_faults:
            return DTCommand.safe(
                reason=f"active model fault flags: {', '.join(active_faults)}"
            )

        source_overload_w = _source_overload_w(
            observation,
            margin_w=self.source_overload_margin_w,
        )
        bus_support_target_w = _nonnegative_float_or_default(
            observation.extra.get("bus_support_target_w"),
            0.0,
        )
        if observation.v_bus_v < goal.bus_min_v or source_overload_w > 0.0:
            if observation.soc_pct > goal.soc_min_hard_pct:
                requested_support_w = (
                    bus_support_target_w
                    if bus_support_target_w > 0.0
                    else self.bus_support_power_w
                )
                if source_overload_w > 0.0:
                    requested_support_w = max(requested_support_w, source_overload_w)
                requested_support_w = _cap_to_safe_discharge(
                    requested_support_w,
                    observation,
                )
                if requested_support_w <= 0.0:
                    return DTCommand.hold(
                        reason=(
                            "bus/source support requested but no safe battery "
                            "discharge headroom is available"
                        )
                    )
                if source_overload_w > 0.0:
                    return DTCommand.discharge(
                        requested_support_w,
                        reason=(
                            "source is overloaded relative to load demand; "
                            "preemptively support load bus"
                        ),
                    )
                return DTCommand.discharge(
                    requested_support_w,
                    reason="bus voltage below soft lower limit; support load bus",
                )
            return DTCommand.safe(
                reason="bus voltage low but battery SOC is at/under hard reserve"
            )

        if observation.v_bus_v > goal.bus_max_v and observation.soc_pct < goal.soc_max_pct:
            charge_power_w = _cap_to_safe_charge(self.charge_power_w, observation)
            if charge_power_w > 0.0:
                return DTCommand.charge(
                    charge_power_w,
                    reason="bus voltage above soft upper limit; absorb power by charging",
                )
            return DTCommand.hold(
                reason="bus voltage is high but no safe charging headroom is available"
            )

        if observation.soc_pct < goal.soc_min_pct + self.soc_deadband_pct:
            charge_power_w = _cap_to_safe_charge(self.charge_power_w, observation)
            if charge_power_w > 0.0:
                return DTCommand.charge(
                    charge_power_w,
                    reason="SOC below target band; recharge battery",
                )
            return DTCommand.hold(
                reason="SOC is low but source is unavailable or power-limited"
            )

        if observation.soc_pct > goal.soc_max_pct - self.soc_deadband_pct:
            return DTCommand.discharge(
                _cap_to_safe_discharge(self.discharge_power_w, observation),
                reason="SOC above target band; discharge into load bus",
            )

        return DTCommand.hold(reason="SOC and bus voltage are inside target band")


@dataclass(slots=True)
class LLMControlPolicy:
    """OpenAI-compatible AI policy for bounded DT supervisory control.

    The LLM proposes only a high-level command. The runner still owns action
    clipping, rate limiting, hard safety stops, and mission success/failure.
    If the model call or JSON parse fails, this policy falls back to the
    deterministic SOC-band policy.
    """

    client: Any
    model: str
    temperature: float = 0.0
    max_tokens: int = 120
    max_command_abs_w: float = 500.0
    mode_gate: bool = False
    fallback_policy: SocBandPolicy = field(default_factory=SocBandPolicy)
    trace_path: str | Path | None = None
    verbose: bool = False
    strict: bool = False
    attempted_calls: int = 0
    successful_calls: int = 0
    fallback_calls: int = 0
    safety_recovery_attempted_calls: int = 0
    safety_recovery_successful_calls: int = 0
    safety_recovery_fallback_calls: int = 0

    def choose_action(self, observation: DTObservation, goal: DTGoal) -> DTCommand:
        fallback = self.fallback_policy.choose_action(observation, goal)
        messages = self._build_messages(observation, goal)
        self.attempted_calls += 1
        self._write_trace(
            "request",
            {
                "observation": observation.to_dict(),
                "goal": {
                    "soc_min_pct": goal.soc_min_pct,
                    "soc_max_pct": goal.soc_max_pct,
                    "soc_min_hard_pct": goal.soc_min_hard_pct,
                    "soc_max_hard_pct": goal.soc_max_hard_pct,
                    "bus_nominal_v": goal.bus_nominal_v,
                    "bus_min_v": goal.bus_min_v,
                    "bus_max_v": goal.bus_max_v,
                    "bus_min_hard_v": goal.bus_min_hard_v,
                    "bus_max_hard_v": goal.bus_max_hard_v,
                },
                "messages": messages,
            },
        )
        if self.verbose:
            print(
                "[llm-policy] request "
                f"#{self.attempted_calls} t={observation.sim_time_s:.3f}s "
                f"model={self.model}"
            )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            content = response.choices[0].message.content or ""
            self._write_trace("response", {"content": content})
            payload = self._parse_json_object(content)
            command = self._command_from_payload(payload)
            if self.mode_gate:
                self._raise_if_command_conflicts_with_rule_policy(
                    command,
                    fallback,
                    observation,
                    goal,
                )
            self.successful_calls += 1
            if self.verbose:
                print(
                    "[llm-policy] response "
                    f"#{self.attempted_calls}: {command.mode} "
                    f"{command.p_batt_cmd_w:.3f} W"
                )
            return command
        except Exception as exc:
            self.fallback_calls += 1
            error_message = f"{type(exc).__name__}: {exc}"
            self._write_trace("fallback", {"error": error_message})
            if self.verbose:
                print(f"[llm-policy] fallback #{self.attempted_calls}: {error_message}")
            if self.strict:
                raise RuntimeError(f"LLM policy failed: {error_message}") from exc
            fallback.reason = f"LLM policy fallback: {error_message}; {fallback.reason}"
            return fallback

    def choose_safety_recovery_action(
        self,
        observation: DTObservation,
        goal: DTGoal,
        safety_reason: str,
        *,
        attempt_index: int,
        max_attempts: int,
        recent_events: list[Any] | None = None,
    ) -> DTCommand:
        """Ask the LLM whether a hard-limit event is recoverable.

        This is deliberately separate from the normal policy prompt. Recovery
        arbitration is allowed to propose one bounded recovery command, but the
        runner still applies deterministic constraints and owns the terminal
        safety-stop decision.
        """

        messages = self._build_safety_recovery_messages(
            observation=observation,
            goal=goal,
            safety_reason=safety_reason,
            attempt_index=attempt_index,
            max_attempts=max_attempts,
            recent_events=recent_events or [],
        )
        self.attempted_calls += 1
        self.safety_recovery_attempted_calls += 1
        self._write_trace(
            "safety_recovery_request",
            {
                "safety_reason": safety_reason,
                "attempt_index": attempt_index,
                "max_attempts": max_attempts,
                "observation": observation.to_dict(),
                "goal": {
                    "soc_min_pct": goal.soc_min_pct,
                    "soc_max_pct": goal.soc_max_pct,
                    "soc_min_hard_pct": goal.soc_min_hard_pct,
                    "soc_max_hard_pct": goal.soc_max_hard_pct,
                    "bus_nominal_v": goal.bus_nominal_v,
                    "bus_min_v": goal.bus_min_v,
                    "bus_max_v": goal.bus_max_v,
                    "bus_min_hard_v": goal.bus_min_hard_v,
                    "bus_max_hard_v": goal.bus_max_hard_v,
                },
                "messages": messages,
            },
        )
        if self.verbose:
            print(
                "[llm-policy] safety recovery request "
                f"#{self.attempted_calls} attempt={attempt_index}/{max_attempts} "
                f"t={observation.sim_time_s:.3f}s model={self.model}"
            )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            content = response.choices[0].message.content or ""
            self._write_trace("safety_recovery_response", {"content": content})
            payload = self._parse_json_object(content)
            command = self._command_from_payload(payload)
            self.successful_calls += 1
            self.safety_recovery_successful_calls += 1
            if self.verbose:
                print(
                    "[llm-policy] safety recovery response "
                    f"#{self.attempted_calls}: {command.mode} "
                    f"{command.p_batt_cmd_w:.3f} W"
                )
            return command
        except Exception as exc:
            self.fallback_calls += 1
            self.safety_recovery_fallback_calls += 1
            error_message = f"{type(exc).__name__}: {exc}"
            self._write_trace("safety_recovery_fallback", {"error": error_message})
            if self.verbose:
                print(
                    "[llm-policy] safety recovery fallback "
                    f"#{self.attempted_calls}: {error_message}"
                )
            if self.strict:
                raise RuntimeError(
                    f"LLM safety recovery failed: {error_message}"
                ) from exc
            return DTCommand.safe(
                reason=f"LLM safety recovery fallback: {error_message}"
            )

    def _build_messages(
        self,
        observation: DTObservation,
        goal: DTGoal,
    ) -> list[dict[str, Any]]:
        load_consumption_w = observation.resolved_load_consumption_w()
        max_safe_discharge_w = (
            0.0
            if observation.max_safe_discharge_w is None
            else float(observation.max_safe_discharge_w)
        )
        if observation.max_safe_charge_w is None:
            max_safe_charge_w = (
                self.max_command_abs_w
                if observation.source_available and not observation.source_at_limit
                else 0.0
            )
        else:
            max_safe_charge_w = float(observation.max_safe_charge_w)
        active_faults = [
            name for name, is_active in observation.fault_flags.items() if is_active
        ]
        source_available = "true" if observation.source_available else "false"
        source_at_limit = "true" if observation.source_at_limit else "false"
        source_can_sink = "true" if observation.source_can_sink_power else "false"
        faults = ", ".join(active_faults) if active_faults else "none"
        source_overload_w = _source_overload_w(observation)
        source_deficit_w = _nonnegative_float_or_default(
            observation.extra.get("source_deficit_w"),
            source_overload_w,
        )
        source_support_needed = _optional_bool(
            observation.extra.get("source_support_needed")
        )
        if source_support_needed is None:
            source_support_needed = source_overload_w > 0.0
        source_support_active = _optional_bool(
            observation.extra.get("source_support_active")
        )
        if source_support_active is None:
            source_support_active = source_support_needed
        source_support_target_w = _nonnegative_float_or_default(
            observation.extra.get("source_support_target_w"),
            source_overload_w,
        )
        bus_voltage_error_v = _nonnegative_float_or_default(
            observation.extra.get("bus_voltage_error_v"),
            max(0.0, goal.bus_nominal_v - observation.v_bus_v),
        )
        bus_voltage_support_w = _nonnegative_float_or_default(
            observation.extra.get("bus_voltage_support_w"),
            0.0,
        )
        bus_support_target_w = _nonnegative_float_or_default(
            observation.extra.get("bus_support_target_w"),
            source_support_target_w,
        )
        bus_support_integral_w = _nonnegative_float_or_default(
            observation.extra.get("bus_support_integral_w"),
            0.0,
        )
        bus_support_trim_w = _nonnegative_float_or_default(
            observation.extra.get("bus_support_trim_w"),
            0.0,
        )
        bus_support_target_unslewed_w = _nonnegative_float_or_default(
            observation.extra.get("bus_support_target_unslewed_w"),
            bus_support_target_w,
        )
        bus_voltage_support_active = _optional_bool(
            observation.extra.get("bus_voltage_support_active")
        )
        if bus_voltage_support_active is None:
            bus_voltage_support_active = (
                observation.v_bus_v < goal.bus_nominal_v
                and (
                    observation.v_bus_v < goal.bus_min_v
                    or source_support_active
                    or source_support_needed
                )
            )
        if observation.v_bus_v < goal.bus_min_v:
            fallback_bus_support_w = min(max_safe_discharge_w, 300.0)
            bus_support_target_w = max(
                bus_support_target_w,
                source_support_target_w,
                fallback_bus_support_w,
            )
        soc_status = _band_status(
            observation.soc_pct,
            goal.soc_min_pct,
            goal.soc_max_pct,
        )
        bus_status = _band_status(
            observation.v_bus_v,
            goal.bus_min_v,
            goal.bus_max_v,
        )
        bus_support_needed = (
            source_support_needed or observation.v_bus_v < goal.bus_min_v
        )
        bus_support_integral_active = bus_support_integral_w > 0.0
        bus_support_trim_active = bus_support_trim_w > 0.0
        source_has_charge_headroom = (
            observation.source_available
            and max_safe_charge_w > 0.0
            and source_overload_w <= 0.0
            and not source_support_active
            and observation.v_bus_v >= goal.bus_min_v
        )
        charge_needed = (
            observation.soc_pct < goal.soc_min_pct
            and source_has_charge_headroom
            and not bus_support_needed
        )
        soc_dump_needed = observation.soc_pct > goal.soc_max_pct
        normal_hold = (
            goal.soc_min_pct <= observation.soc_pct <= goal.soc_max_pct
            and goal.bus_min_v <= observation.v_bus_v <= goal.bus_max_v
            and not bus_support_needed
            and not soc_dump_needed
        )
        live_bus_support_w = min(
            max(0.0, bus_support_target_w),
            max(0.0, max_safe_discharge_w),
            max(0.0, self.max_command_abs_w),
        )
        if (
            bus_support_needed
            and observation.soc_pct > goal.soc_min_hard_pct
            and live_bus_support_w > 0.0
        ):
            example_text = (
                "Current applicable example:\n"
                f"bus_support_needed=true, bus_support_target_w={live_bus_support_w:.3f} -> "
                "{\"mode\":\"DISCHARGE\",\"p_batt_cmd_w\":"
                f"{live_bus_support_w:.3f},"
                "\"reason\":\"bus below target; battery supports bus\"}\n"
                "Do not answer HOLD while bus_support_needed=true or bus_status=LOW.\n"
            )
        elif charge_needed:
            live_charge_w = min(100.0, max(0.0, max_safe_charge_w))
            example_text = (
                "Current applicable example:\n"
                "charge_needed=true -> "
                "{\"mode\":\"CHARGE\",\"p_batt_cmd_w\":"
                f"{-live_charge_w:.3f},"
                "\"reason\":\"SOC below target and source has charging headroom\"}\n"
            )
        elif normal_hold:
            example_text = (
                "Current applicable example:\n"
                "normal_hold=true -> "
                "{\"mode\":\"HOLD\",\"p_batt_cmd_w\":0,"
                "\"reason\":\"SOC and bus are inside target band\"}\n"
            )
        else:
            example_text = (
                "Current applicable example:\n"
                "Use the highest-priority true decision boolean below. "
                "Do not copy an example for a false condition.\n"
            )

        return [
            {
                "role": "system",
                "content": (
                    "You are the research LLM controller for a simulated "
                    "battery/load-bus digital twin. "
                    "Reply with exactly one JSON object and nothing else: "
                    "keys must be mode, p_batt_cmd_w, and reason. "
                    "Allowed modes: CHARGE, HOLD, DISCHARGE, SAFE. "
                    "Negative p_batt_cmd_w charges the battery. "
                    "Positive p_batt_cmd_w discharges into the bus. "
                    f"Use |p_batt_cmd_w| <= {self.max_command_abs_w:.0f} W. "
                    "Never copy the state or these rules into your answer. "
                    "You are responsible for choosing the mode; the runner "
                    "only clips unsafe magnitude. The source normally supplies "
                    "the load; load_consumption_w by itself is not a reason to "
                    "discharge the battery."
                ),
            },
            {
                "role": "user",
                "content": (
                    example_text
                    + "\n"
                    + "Rules in priority order:\n"
                    "1. If faults are active, choose SAFE.\n"
                    "2. If Vbus is below bus_min, regulate bus voltage: "
                    "DISCHARGE using the current bus_support_target_w from "
                    "State, not merely source_deficit_w or "
                    "source_support_target_w, but not more than "
                    "max_safe_discharge_w, if SOC is above soc_min_hard.\n"
                    "3. If source_support_needed=true and Vbus is not below "
                    "bus_min, support the source. If "
                    "bus_voltage_support_active=true, use the current "
                    "bus_support_target_w from State for smooth voltage "
                    "regulation; do not substitute a canned round number. "
                    "If bus_support_integral_active=true, also use "
                    "bus_support_target_w because it includes bus-support "
                    "memory. If bus_support_trim_active=true, also use "
                    "bus_support_target_w because it includes learned support "
                    "trim and anti-chatter target shaping. Otherwise use "
                    "source_support_target_w, "
                    "but not more than max_safe_discharge_w, if SOC is above "
                    "soc_min_hard.\n"
                    "4. If SOC is below soc_min and source has headroom "
                    "(source_available=true, max_safe_charge_w>0, "
                    "source_overload_w=0), CHARGE about "
                    "min(100 W, max_safe_charge_w).\n"
                    "5. If SOC is below soc_min but max_safe_charge_w<=0 and "
                    "bus_support_needed=false, choose HOLD and wait for source "
                    "headroom or a real bus-support condition.\n"
                    "6. If Vbus is above bus_max and SOC is below soc_max, "
                    "CHARGE about 100 W.\n"
                    "7. If SOC is above soc_max, DISCHARGE modestly, not more "
                    "than max_safe_discharge_w.\n"
                    "8. If SOC and Vbus are inside their target bands and "
                    "source_overload_w=0, choose HOLD with p_batt_cmd_w=0.\n"
                    "9. If source_can_sink_power=false, never exceed "
                    "max_safe_discharge_w.\n"
                    "Do not CHARGE when max_safe_charge_w<=0. "
                    "Do not CHARGE while source_support_active=true. "
                    "Never charge harder than max_safe_charge_w. "
                    "Do not DISCHARGE below soc_min unless supporting low/overloaded bus.\n"
                    "Do not DISCHARGE merely because load_consumption_w is nonzero; "
                    "the source is already serving the load when source_overload_w=0.\n"
                    "\n"
                    "Decision booleans:\n"
                    f"bus_support_needed={_bool_word(bus_support_needed)}\n"
                    f"charge_needed={_bool_word(charge_needed)}\n"
                    f"soc_dump_needed={_bool_word(soc_dump_needed)}\n"
                    f"normal_hold={_bool_word(normal_hold)}\n"
                    f"source_has_charge_headroom={_bool_word(source_has_charge_headroom)}\n"
                    f"source_support_needed={_bool_word(source_support_needed)}\n"
                    f"source_support_active={_bool_word(source_support_active)}\n"
                    f"bus_voltage_support_active={_bool_word(bus_voltage_support_active)}\n"
                    f"bus_support_integral_active={_bool_word(bus_support_integral_active)}\n"
                    f"bus_support_trim_active={_bool_word(bus_support_trim_active)}\n"
                    "\n"
                    "State:\n"
                    f"t_s={observation.sim_time_s:.3f}\n"
                    f"soc_pct={observation.soc_pct:.3f}\n"
                    f"soc_status={soc_status}\n"
                    f"soc_min_pct={goal.soc_min_pct:.3f}\n"
                    f"soc_max_pct={goal.soc_max_pct:.3f}\n"
                    f"soc_min_hard_pct={goal.soc_min_hard_pct:.3f}\n"
                    f"v_bus_v={observation.v_bus_v:.3f}\n"
                    f"bus_status={bus_status}\n"
                    f"bus_min_v={goal.bus_min_v:.3f}\n"
                    f"bus_max_v={goal.bus_max_v:.3f}\n"
                    f"bus_voltage_error_v={bus_voltage_error_v:.3f}\n"
                    f"bus_voltage_support_w={bus_voltage_support_w:.3f}\n"
                    f"bus_support_integral_w={bus_support_integral_w:.3f}\n"
                    f"bus_support_trim_w={bus_support_trim_w:.3f}\n"
                    f"bus_support_target_unslewed_w={bus_support_target_unslewed_w:.3f}\n"
                    f"bus_support_target_w={bus_support_target_w:.3f}\n"
                    f"load_consumption_w={load_consumption_w:.3f}\n"
                    f"p_source_w={observation.p_source_w:.3f}\n"
                    f"source_deficit_w={source_deficit_w:.3f}\n"
                    f"source_overload_w={source_overload_w:.3f}\n"
                    f"source_support_target_w={source_support_target_w:.3f}\n"
                    f"max_safe_charge_w={max_safe_charge_w:.3f}\n"
                    f"source_available={source_available}\n"
                    f"source_at_limit={source_at_limit}\n"
                    f"source_can_sink_power={source_can_sink}\n"
                    f"source_power_limit_w={_optional_float_word(observation.source_power_limit_w)}\n"
                    f"max_safe_discharge_w={max_safe_discharge_w:.3f}\n"
                    f"faults={faults}\n"
                    "\n"
                    "Return only the JSON decision object now. Use a real "
                    "reason, not the word 'short'."
                ),
            },
        ]

    def _build_safety_recovery_messages(
        self,
        *,
        observation: DTObservation,
        goal: DTGoal,
        safety_reason: str,
        attempt_index: int,
        max_attempts: int,
        recent_events: list[Any],
    ) -> list[dict[str, Any]]:
        load_consumption_w = observation.resolved_load_consumption_w()
        max_safe_discharge_w = (
            0.0
            if observation.max_safe_discharge_w is None
            else float(observation.max_safe_discharge_w)
        )
        if observation.max_safe_charge_w is None:
            max_safe_charge_w = (
                self.max_command_abs_w
                if observation.source_available and not observation.source_at_limit
                else 0.0
            )
        else:
            max_safe_charge_w = float(observation.max_safe_charge_w)
        active_faults = [
            name for name, is_active in observation.fault_flags.items() if is_active
        ]
        faults = ", ".join(active_faults) if active_faults else "none"
        source_deficit_w = _nonnegative_float_or_default(
            observation.extra.get("source_deficit_w"),
            _source_overload_w(observation),
        )
        bus_voltage_error_v = _nonnegative_float_or_default(
            observation.extra.get("bus_voltage_error_v"),
            max(0.0, goal.bus_nominal_v - observation.v_bus_v),
        )
        bus_support_target_w = _nonnegative_float_or_default(
            observation.extra.get("bus_support_target_w"),
            0.0,
        )
        source_support_needed = _optional_bool(
            observation.extra.get("source_support_needed")
        )
        if source_support_needed is None:
            source_support_needed = source_deficit_w > 0.0
        source_support_active = _optional_bool(
            observation.extra.get("source_support_active")
        )
        if source_support_active is None:
            source_support_active = source_support_needed
        recent_text = _recent_event_text(recent_events)

        return [
            {
                "role": "system",
                "content": (
                    "You are the safety-recovery arbiter for a simulated "
                    "battery/load-bus digital twin. A hard safety violation "
                    "has been detected. Decide whether one bounded recovery "
                    "command is reasonable or whether the mission must fully "
                    "safe-stop. Reply with exactly one JSON object and nothing "
                    "else. Keys must be mode, p_batt_cmd_w, and reason. "
                    "Allowed modes: CHARGE, HOLD, DISCHARGE, SAFE. SAFE means "
                    "declare full safety stop. HOLD means hold at 0 W and "
                    "recheck next tick. Negative p_batt_cmd_w charges; positive "
                    "p_batt_cmd_w discharges into the bus. "
                    f"Use |p_batt_cmd_w| <= {self.max_command_abs_w:.0f} W. "
                    "The Python guard layer will still clamp unsafe commands."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Safety recovery context:\n"
                    f"safety_reason={safety_reason}\n"
                    f"attempt_index={attempt_index}\n"
                    f"max_attempts={max_attempts}\n"
                    "\n"
                    "Recovery rules:\n"
                    "1. If telemetry/instrumentation is missing, invalid, or a "
                    "bridge/model fault is active, choose SAFE.\n"
                    "2. If the bus is below the hard minimum and SOC is above "
                    "the hard minimum, choose DISCHARGE using bus_support_target_w "
                    "or max_safe_discharge_w, whichever is smaller and positive.\n"
                    "3. If the bus is above the hard maximum and safe charge "
                    "headroom exists, choose CHARGE no harder than "
                    "max_safe_charge_w.\n"
                    "4. If SOC is at/over the hard maximum and safe discharge "
                    "headroom exists, choose DISCHARGE modestly.\n"
                    "5. If SOC is at/under the hard minimum and safe charge "
                    "headroom exists while the bus is not low, choose CHARGE "
                    "modestly. If the bus is also low or no charge headroom "
                    "exists, choose SAFE.\n"
                    "6. If the correct recovery is not clear, choose SAFE. "
                    "Do not gamble.\n"
                    "\n"
                    "Current state:\n"
                    f"t_s={observation.sim_time_s:.3f}\n"
                    f"soc_pct={observation.soc_pct:.3f}\n"
                    f"soc_min_hard_pct={goal.soc_min_hard_pct:.3f}\n"
                    f"soc_max_hard_pct={goal.soc_max_hard_pct:.3f}\n"
                    f"v_bus_v={observation.v_bus_v:.3f}\n"
                    f"bus_min_hard_v={goal.bus_min_hard_v:.3f}\n"
                    f"bus_max_hard_v={goal.bus_max_hard_v:.3f}\n"
                    f"bus_nominal_v={goal.bus_nominal_v:.3f}\n"
                    f"bus_voltage_error_v={bus_voltage_error_v:.3f}\n"
                    f"bus_support_target_w={bus_support_target_w:.3f}\n"
                    f"p_batt_w={observation.p_batt_w:.3f}\n"
                    f"p_load_w={observation.p_load_w:.3f}\n"
                    f"load_consumption_w={load_consumption_w:.3f}\n"
                    f"p_source_w={observation.p_source_w:.3f}\n"
                    f"source_deficit_w={source_deficit_w:.3f}\n"
                    f"source_support_needed={_bool_word(source_support_needed)}\n"
                    f"source_support_active={_bool_word(source_support_active)}\n"
                    f"source_available={_bool_word(observation.source_available)}\n"
                    f"source_at_limit={_bool_word(observation.source_at_limit)}\n"
                    f"source_can_sink_power={_bool_word(observation.source_can_sink_power)}\n"
                    f"source_power_limit_w={_optional_float_word(observation.source_power_limit_w)}\n"
                    f"max_safe_discharge_w={max_safe_discharge_w:.3f}\n"
                    f"max_safe_charge_w={max_safe_charge_w:.3f}\n"
                    f"faults={faults}\n"
                    "\n"
                    "Recent decisions:\n"
                    f"{recent_text}\n"
                    "\n"
                    "Return only the JSON recovery decision now. Example shape: "
                    "{\"mode\":\"DISCHARGE\",\"p_batt_cmd_w\":150,"
                    "\"reason\":\"bus hard-low but battery has safe discharge headroom\"}"
                ),
            },
        ]

    def _command_from_payload(self, payload: dict[str, Any]) -> DTCommand:
        if "mode" not in payload:
            echoed_keys = {
                "goal",
                "observation",
                "control_contract",
                "required_response_schema",
            }
            if echoed_keys.intersection(payload):
                raise ValueError("LLM echoed the prompt instead of returning a decision")
            raise ValueError("LLM response missing required key: mode")

        mode = str(payload.get("mode")).strip().upper()
        if mode not in {"CHARGE", "HOLD", "DISCHARGE", "SAFE"}:
            raise ValueError(f"invalid LLM mode: {mode}")

        reason = str(payload.get("reason", "LLM selected action")).strip()
        if not reason:
            reason = "LLM selected action"
        reason = f"LLM: {reason}"

        if mode == "SAFE":
            return DTCommand.safe(reason=reason)

        if "p_batt_cmd_w" not in payload:
            raise ValueError("LLM response missing required key: p_batt_cmd_w")

        raw_power = payload.get("p_batt_cmd_w")
        if isinstance(raw_power, str):
            raw_power = raw_power.strip()
        p_batt_cmd_w = float(raw_power)

        if mode == "CHARGE":
            return DTCommand.charge(p_batt_cmd_w, reason=reason)
        if mode == "DISCHARGE":
            return DTCommand.discharge(p_batt_cmd_w, reason=reason)

        return DTCommand.hold(reason=reason)

    def _raise_if_command_conflicts_with_rule_policy(
        self,
        command: DTCommand,
        fallback: DTCommand,
        observation: DTObservation,
        goal: DTGoal,
    ) -> None:
        command_mode = str(command.mode).upper()
        fallback_mode = str(fallback.mode).upper()

        if command_mode == fallback_mode:
            return

        if fallback_mode == "HOLD":
            if _recovery_needed(observation, goal):
                raise ValueError(
                    "LLM selected an action while deterministic policy selected "
                    "HOLD during a constrained recovery condition"
                )
            raise ValueError(
                "LLM selected an unnecessary action while deterministic policy "
                "selected HOLD inside the goal band"
            )

        raise ValueError(
            f"LLM selected {command.mode} while deterministic policy selected "
            f"{fallback.mode} "
            f"{fallback.p_batt_cmd_w:.3f} W"
        )

    @staticmethod
    def _parse_json_object(content: str) -> dict[str, Any]:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, flags=re.DOTALL)
            if match is None:
                raise
            payload = json.loads(match.group(0))

        if not isinstance(payload, dict):
            raise ValueError("LLM response was not a JSON object")
        return payload

    def _write_trace(self, event: str, payload: dict[str, Any]) -> None:
        if self.trace_path is None:
            return

        try:
            path = Path(self.trace_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "event": event,
                "model": self.model,
                "temperature": self.temperature,
                **payload,
            }
            with path.open("a", encoding="utf-8") as trace_file:
                trace_file.write(json.dumps(record, sort_keys=True) + "\n")
        except Exception:
            # Trace logging should never be allowed to destabilize control.
            return


def _safe_discharge_limit_w(observation: DTObservation) -> float | None:
    limit = observation.max_safe_discharge_w
    if limit is None:
        return None
    try:
        limit = float(limit)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(limit):
        return None
    return max(0.0, limit)


def _cap_to_safe_discharge(power_w: float, observation: DTObservation) -> float:
    requested_w = max(0.0, float(power_w))
    limit_w = _safe_discharge_limit_w(observation)
    if limit_w is None:
        return requested_w
    return min(requested_w, limit_w)


def _safe_charge_limit_w(observation: DTObservation) -> float | None:
    limit = observation.max_safe_charge_w
    if limit is None:
        if not observation.source_available or observation.source_at_limit:
            return 0.0
        return None
    try:
        limit = float(limit)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(limit):
        return None
    return max(0.0, limit)


def _cap_to_safe_charge(power_w: float, observation: DTObservation) -> float:
    requested_w = max(0.0, float(power_w))
    limit_w = _safe_charge_limit_w(observation)
    if limit_w is None:
        return requested_w
    return min(requested_w, limit_w)


def _source_overload_w(
    observation: DTObservation,
    margin_w: float = 25.0,
) -> float:
    extra_deficit_w = _finite_float_or_none(observation.extra.get("source_deficit_w"))
    if extra_deficit_w is not None:
        extra_deficit_w = max(0.0, extra_deficit_w)
        extra_support_needed = _optional_bool(
            observation.extra.get("source_support_needed")
        )
        if extra_support_needed is True:
            return extra_deficit_w
        if extra_support_needed is False:
            return 0.0
        if extra_deficit_w <= max(0.0, margin_w):
            return 0.0
        return extra_deficit_w

    load_consumption_w = observation.resolved_load_consumption_w()
    if load_consumption_w <= 0.0:
        return 0.0

    source_power_w = max(0.0, observation.p_source_w)
    source_limit_w = _positive_finite_float(observation.source_power_limit_w)
    if source_limit_w is not None:
        source_is_present = observation.source_available or source_power_w > 0.0
        if source_is_present:
            source_capacity_w = max(source_power_w, source_limit_w)
        else:
            source_capacity_w = source_power_w
        overload_w = load_consumption_w - source_capacity_w
    elif not observation.source_available or observation.source_at_limit:
        overload_w = load_consumption_w - source_power_w
    else:
        overload_w = 0.0

    if overload_w <= max(0.0, margin_w):
        return 0.0
    return overload_w


def _finite_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(resolved):
        return None
    return resolved


def _nonnegative_float_or_default(value: Any, default: float) -> float:
    resolved = _finite_float_or_none(value)
    if resolved is None:
        resolved = default
    return max(0.0, resolved)


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    return None


def _positive_finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(resolved) or resolved <= 0.0:
        return None
    return resolved


def _recovery_needed(observation: DTObservation, goal: DTGoal) -> bool:
    if any(observation.fault_flags.values()):
        return True
    if observation.soc_pct < goal.soc_min_pct:
        return True
    if observation.soc_pct > goal.soc_max_pct:
        return True
    if observation.v_bus_v < goal.bus_min_v:
        return True
    if observation.v_bus_v > goal.bus_max_v:
        return True
    return _source_overload_w(observation) > 0.0


def _band_status(value: float, lower: float, upper: float) -> str:
    if value < lower:
        return "LOW"
    if value > upper:
        return "HIGH"
    return "INSIDE"


def _bool_word(value: bool) -> str:
    return "true" if value else "false"


def _optional_float_word(value: float | None) -> str:
    if value is None:
        return "unknown"
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if not math.isfinite(resolved):
        return "unknown"
    return f"{resolved:.3f}"


def _recent_event_text(events: list[Any]) -> str:
    if not events:
        return "none"

    lines: list[str] = []
    for event in events[-5:]:
        obs = getattr(event, "observation", None)
        cmd = getattr(event, "command", None)
        policy_cmd = getattr(event, "policy_command", None)
        violations = getattr(event, "violations", [])
        if obs is None or cmd is None:
            continue
        policy_mode = getattr(policy_cmd, "mode", "none") if policy_cmd else "none"
        policy_power = (
            getattr(policy_cmd, "p_batt_cmd_w", 0.0) if policy_cmd else 0.0
        )
        lines.append(
            "- "
            f"t={obs.sim_time_s:.3f}s "
            f"soc={obs.soc_pct:.3f}% "
            f"vbus={obs.v_bus_v:.3f}V "
            f"policy={policy_mode}:{float(policy_power):.3f}W "
            f"applied={cmd.mode}:{cmd.p_batt_cmd_w:.3f}W "
            f"violations={'; '.join(violations) if violations else 'none'}"
        )

    return "\n".join(lines) if lines else "none"
