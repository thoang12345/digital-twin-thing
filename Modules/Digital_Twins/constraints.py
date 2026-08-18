from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Any

from Modules.Digital_Twins.types import (
    DTCommand,
    DTGoal,
    DTObservation,
    RunnerConfig,
)


_VOLTAGE_ERROR_EPSILON = 1e-6


@dataclass(slots=True)
class GuardedPower:
    p_batt_cmd_w: float
    reasons: list[str]
    bypass_rate_limit: bool = False


class CommandConstraintLayer:
    """Deterministic guard layer between policy intent and plant command.

    Policies, including the LLM policy, propose a supervisory intent. This
    layer owns the physics-adjacent constraints: command clipping, charge and
    discharge headroom, anti-chatter charge cooldowns, and command ramping.
    """

    def __init__(self, goal: DTGoal, config: RunnerConfig) -> None:
        self.goal = goal
        self.config = config
        self._last_p_batt_cmd_w = 0.0
        self._charge_blocked_until_s = 0.0
        self._last_charge_block_reason = ""
        self._source_support_active = False
        self._source_support_clear_since_s: float | None = None
        self._bus_support_integral_v_s = 0.0
        self._bus_support_integral_w = 0.0
        self._bus_support_integral_error_v = 0.0
        self._bus_support_integral_context_active = False
        self._bus_support_integral_last_time_s: float | None = None
        self._bus_support_trim_w = 0.0
        self._bus_support_trim_error_v = 0.0
        self._bus_support_trim_source_slack_w = 0.0
        self._bus_support_trim_last_time_s: float | None = None
        self._bus_support_target_w = 0.0
        self._bus_support_target_unslewed_w = 0.0
        self._bus_support_target_slew_active = False
        self._bus_support_target_last_time_s: float | None = None

    def augment_observation(self, observation: DTObservation) -> DTObservation:
        load_consumption_w = observation.resolved_load_consumption_w()
        max_safe_discharge_w = self.max_safe_discharge_w(observation)
        max_safe_charge_w = self.max_safe_charge_w(observation)
        source_power_limit_w = self._source_power_limit_w(observation)
        source_deficit_w = self.source_deficit_w(observation)
        source_support_needed = self._source_support_needed(source_deficit_w)
        source_support_active = self._update_source_support_latch(
            observation,
            source_deficit_w,
            source_support_needed,
        )
        source_support_target_w = self._source_support_target_w(source_deficit_w)
        bus_voltage_error_v = self._bus_voltage_error_v(observation)
        bus_voltage_support_w = self._bus_voltage_support_w(bus_voltage_error_v)
        bus_voltage_support_active = self._bus_voltage_support_active(
            observation,
            source_deficit_w,
        )
        bus_support_trim_w = self._update_bus_support_trim(
            observation,
            source_deficit_w=source_deficit_w,
            max_safe_discharge_w=max_safe_discharge_w,
        )
        bus_support_integral_w = self._update_bus_support_integral(
            observation,
            source_deficit_w=source_deficit_w,
            max_safe_discharge_w=max_safe_discharge_w,
        )
        bus_support_target_unslewed_w = self.bus_support_target_w(
            observation,
            source_deficit_w=source_deficit_w,
            max_safe_discharge_w=max_safe_discharge_w,
        )
        bus_support_target_w = self._update_bus_support_target_slew(
            observation,
            target_w=bus_support_target_unslewed_w,
            source_deficit_w=source_deficit_w,
            max_safe_discharge_w=max_safe_discharge_w,
        )
        extra = dict(observation.extra)
        extra.update(
            {
                "load_consumption_w": load_consumption_w,
                "max_safe_discharge_w": max_safe_discharge_w,
                "max_safe_charge_w": max_safe_charge_w,
                "source_power_limit_w": source_power_limit_w,
                "source_deficit_w": source_deficit_w,
                "source_support_needed": source_support_needed,
                "source_support_active": source_support_active,
                "source_support_target_w": source_support_target_w,
                "bus_voltage_error_v": bus_voltage_error_v,
                "bus_voltage_support_w": bus_voltage_support_w,
                "bus_voltage_support_active": bus_voltage_support_active,
                "bus_support_integral_error_v": self._bus_support_integral_error_v,
                "bus_support_integral_v_s": self._bus_support_integral_v_s,
                "bus_support_integral_w": bus_support_integral_w,
                "bus_support_integral_context_active": (
                    self._bus_support_integral_context_active
                ),
                "bus_support_integral_gain_w_per_v_s": (
                    self.config.bus_support_integral_gain_w_per_v_s
                ),
                "bus_support_integral_max_w": (
                    self.config.bus_support_integral_max_w
                ),
                "bus_support_integral_leak_per_s": (
                    self.config.bus_support_integral_leak_per_s
                ),
                "bus_support_integral_deadband_v": (
                    self.config.bus_support_integral_deadband_v
                ),
                "bus_support_trim_error_v": self._bus_support_trim_error_v,
                "bus_support_trim_source_slack_w": (
                    self._bus_support_trim_source_slack_w
                ),
                "bus_support_trim_w": bus_support_trim_w,
                "bus_support_trim_gain_w_per_v_s": (
                    self.config.bus_support_trim_gain_w_per_v_s
                ),
                "bus_support_trim_max_w": self.config.bus_support_trim_max_w,
                "bus_support_trim_decay_w_per_s": (
                    self.config.bus_support_trim_decay_w_per_s
                ),
                "bus_support_trim_deadband_v": (
                    self.config.bus_support_trim_deadband_v
                ),
                "bus_support_trim_source_slack_deadband_w": (
                    self.config.bus_support_trim_source_slack_deadband_w
                ),
                "bus_support_target_unslewed_w": bus_support_target_unslewed_w,
                "bus_support_target_slew_active": (
                    self._bus_support_target_slew_active
                ),
                "bus_support_target_slew_down_w_per_s": (
                    self.config.bus_support_target_slew_down_w_per_s
                ),
                "bus_support_target_w": bus_support_target_w,
                "bus_support_min_w": self.config.bus_support_min_w,
                "bus_support_gain_w_per_v": self.config.bus_support_gain_w_per_v,
                "source_support_entry_margin_w": (
                    self.config.source_support_entry_margin_w
                ),
                "source_support_clear_margin_w": (
                    self.config.source_support_clear_margin_w
                ),
                "source_support_bus_hysteresis_v": (
                    self.config.source_support_bus_hysteresis_v
                ),
                "source_support_hold_s": self.config.source_support_hold_s,
                "source_backfeed_guard_enabled": (
                    self.config.prevent_source_backfeed
                    and not observation.source_can_sink_power
                ),
                "source_min_power_w": self.config.source_min_power_w,
                "source_power_margin_w": self.config.source_power_margin_w,
                "charge_headroom_guard_enabled": (
                    self.config.prevent_charge_without_source_headroom
                ),
                "charge_power_margin_w": self.config.charge_power_margin_w,
                "charge_resume_bus_v": self._charge_resume_bus_v(),
                "charge_blocked_until_s": self._charge_blocked_until_s,
                "post_discharge_charge_hold_s": (
                    self.config.post_discharge_charge_hold_s
                ),
                "block_discharge_below_soc_min": (
                    self.config.block_discharge_below_soc_min
                ),
                "allow_source_support_below_soc_min": (
                    self.config.allow_source_support_below_soc_min
                ),
            }
        )
        return replace(
            observation,
            load_consumption_w=load_consumption_w,
            max_safe_discharge_w=max_safe_discharge_w,
            max_safe_charge_w=max_safe_charge_w,
            source_power_limit_w=source_power_limit_w,
            extra=extra,
        )

    def limit(self, command: DTCommand, observation: DTObservation) -> DTCommand:
        if not command.enable:
            self._last_p_batt_cmd_w = 0.0
            return DTCommand.safe(command.reason)

        clipped, clip_reasons = self._clip_to_absolute_limit(command.p_batt_cmd_w)
        guarded = self._apply_physical_guards(clipped, observation)
        guarded.reasons[:0] = clip_reasons
        limited, rate_limited = self._rate_limit(
            guarded.p_batt_cmd_w,
            bypass=guarded.bypass_rate_limit,
        )

        reason = self._append_limit_reason(
            command.reason,
            guarded.reasons,
            rate_limited=rate_limited,
            guarded_w=guarded.p_batt_cmd_w,
            limited_w=limited,
        )

        return DTCommand(
            mode=self._mode_for_power(command.mode, limited),
            p_batt_cmd_w=limited,
            enable=command.enable,
            reason=reason,
        )

    def max_safe_discharge_w(self, observation: DTObservation) -> float:
        if not self.config.prevent_source_backfeed or observation.source_can_sink_power:
            return abs(self.config.max_p_batt_abs_w)

        explicit_limit = _optional_finite_float(observation.max_safe_discharge_w)
        if explicit_limit is not None:
            return self._clamp_to_abs_limit(explicit_limit)

        load_consumption_w = observation.resolved_load_consumption_w()
        source_reserve_w = 0.0
        if observation.source_available:
            source_reserve_w = (
                max(0.0, self.config.source_min_power_w)
                + max(0.0, self.config.source_power_margin_w)
            )
        load_based_limit_w = load_consumption_w - source_reserve_w

        balance_based_limit_w = math.inf
        if math.isfinite(observation.p_batt_w) and math.isfinite(
            observation.p_source_w
        ):
            current_discharge_w = max(0.0, observation.p_batt_w)
            reducible_source_w = max(0.0, observation.p_source_w - source_reserve_w)
            balance_based_limit_w = current_discharge_w + reducible_source_w

        candidate_limit_w = min(load_based_limit_w, balance_based_limit_w)
        if not math.isfinite(candidate_limit_w):
            candidate_limit_w = load_based_limit_w
        if not math.isfinite(candidate_limit_w):
            candidate_limit_w = 0.0

        return self._clamp_to_abs_limit(candidate_limit_w)

    def max_safe_charge_w(self, observation: DTObservation) -> float:
        if not self.config.prevent_charge_without_source_headroom:
            return abs(self.config.max_p_batt_abs_w)

        if not observation.source_available:
            return 0.0

        source_limit_w = self._source_power_limit_w(observation)
        if source_limit_w is not None:
            load_consumption_w = observation.resolved_load_consumption_w()
            if load_consumption_w > 0.0 and math.isfinite(load_consumption_w):
                candidate_limit_w = (
                    source_limit_w
                    - load_consumption_w
                    - max(0.0, self.config.charge_power_margin_w)
                )
            elif math.isfinite(observation.p_source_w):
                current_charge_w = max(0.0, -observation.p_batt_w)
                candidate_limit_w = (
                    source_limit_w
                    - max(0.0, observation.p_source_w)
                    + current_charge_w
                    - max(0.0, self.config.charge_power_margin_w)
                )
            else:
                candidate_limit_w = 0.0
            return self._clamp_to_abs_limit(candidate_limit_w)

        if observation.source_at_limit:
            return 0.0

        return abs(self.config.max_p_batt_abs_w)

    def source_deficit_w(self, observation: DTObservation) -> float:
        """Return load demand that cannot be covered by the source capacity."""

        load_consumption_w = observation.resolved_load_consumption_w()
        if load_consumption_w <= 0.0 or not math.isfinite(load_consumption_w):
            return 0.0

        source_power_w = max(0.0, _finite_or_zero(observation.p_source_w))
        source_limit_w = self._source_power_limit_w(observation)
        if source_limit_w is not None:
            source_is_present = observation.source_available or source_power_w > 0.0
            if source_is_present:
                source_capacity_w = max(source_power_w, source_limit_w)
            else:
                source_capacity_w = source_power_w
        elif observation.source_at_limit or not observation.source_available:
            source_capacity_w = source_power_w
        else:
            return 0.0

        return max(0.0, load_consumption_w - source_capacity_w)

    def bus_support_target_w(
        self,
        observation: DTObservation,
        *,
        source_deficit_w: float | None = None,
        max_safe_discharge_w: float | None = None,
    ) -> float:
        """Return a discharge target for regulating a low bus voltage."""

        if source_deficit_w is None:
            source_deficit_w = self.source_deficit_w(observation)
        if max_safe_discharge_w is None:
            max_safe_discharge_w = self.max_safe_discharge_w(observation)

        if not self._bus_support_context_active(observation, source_deficit_w):
            return min(
                self._source_support_target_w(source_deficit_w),
                max(0.0, max_safe_discharge_w),
            )

        voltage_support_w = 0.0
        if self._bus_voltage_support_active(observation, source_deficit_w):
            voltage_support_w = self._bus_voltage_support_w(
                self._bus_voltage_error_v(observation)
            )
        target_w = (
            source_deficit_w
            + voltage_support_w
            + self._bus_support_trim_w
            + self._bus_support_integral_w
        )
        if self._bus_below_soft_min(observation):
            target_w = max(target_w, max(0.0, self.config.bus_support_min_w))
        return min(
            self._clamp_to_abs_limit(target_w),
            max(0.0, max_safe_discharge_w),
        )

    def _apply_physical_guards(
        self,
        requested_p_batt_w: float,
        observation: DTObservation,
    ) -> GuardedPower:
        if requested_p_batt_w > 0.0:
            return self._apply_discharge_guards(requested_p_batt_w, observation)
        if requested_p_batt_w < 0.0:
            return self._apply_charge_guards(requested_p_batt_w, observation)
        return GuardedPower(0.0, [])

    def _apply_discharge_guards(
        self,
        requested_p_batt_w: float,
        observation: DTObservation,
    ) -> GuardedPower:
        limited = requested_p_batt_w
        reasons: list[str] = []
        bypass_rate_limit = False

        bus_needs_emergency_support = self._bus_below_soft_min(observation)
        source_deficit_w = self.source_deficit_w(observation)
        source_support_target_w = self._source_support_target_w(source_deficit_w)
        bus_voltage_support_active = self._bus_voltage_support_active(
            observation,
            source_deficit_w,
        )
        bus_support_context_active = self._bus_support_context_active(
            observation,
            source_deficit_w,
        )
        low_soc_support_cap_w = source_support_target_w
        if bus_support_context_active:
            observed_target_w = _optional_finite_float(
                observation.extra.get("bus_support_target_w")
            )
            if observed_target_w is not None:
                low_soc_support_cap_w = observed_target_w
            else:
                low_soc_support_cap_w = self.bus_support_target_w(
                    observation,
                    source_deficit_w=source_deficit_w,
                )
        source_support_allowed = (
            self.config.allow_source_support_below_soc_min
            and low_soc_support_cap_w > 0.0
            and (
                self._source_support_active
                or self._source_support_needed(source_deficit_w)
            )
        )
        if (
            self.config.block_discharge_below_soc_min
            and observation.soc_pct <= self.goal.soc_min_pct
            and not bus_needs_emergency_support
            and not source_support_allowed
        ):
            limited = 0.0
            bypass_rate_limit = True
            reasons.append(
                "blocked discharge because SOC is below the target minimum "
                f"({observation.soc_pct:.2f}% <= {self.goal.soc_min_pct:.2f}%) "
                "and neither bus voltage nor source overload requires support"
            )

        if (
            limited > low_soc_support_cap_w
            and source_support_allowed
            and observation.soc_pct <= self.goal.soc_min_pct
            and not bus_needs_emergency_support
        ):
            limited = low_soc_support_cap_w
            if (
                bus_voltage_support_active
                or self._bus_support_integral_w > 0.0
                or self._bus_support_trim_w > 0.0
            ):
                reasons.append(
                    "low-SOC bus-support guard capped discharge to "
                    f"{low_soc_support_cap_w:.3f} W "
                    f"(source deficit {source_deficit_w:.3f} W, "
                    f"bus voltage {observation.v_bus_v:.3f} V)"
                )
            else:
                reasons.append(
                    "low-SOC source-support guard capped discharge to "
                    f"{low_soc_support_cap_w:.3f} W "
                    f"(source deficit {source_deficit_w:.3f} W)"
                )

        if (
            limited > 0.0
            and self.config.prevent_source_backfeed
            and not observation.source_can_sink_power
        ):
            max_safe_discharge_w = self.max_safe_discharge_w(observation)
            if limited > max_safe_discharge_w:
                limited = max_safe_discharge_w
                bypass_rate_limit = True
                reasons.append(
                    "no-backfeed guard capped discharge to "
                    f"{max_safe_discharge_w:.3f} W "
                    f"(load consumption {observation.resolved_load_consumption_w():.3f} W, "
                    f"source margin {self.config.source_power_margin_w:.3f} W)"
                )

        support_reason = self._discharge_support_reason(limited, observation)
        if support_reason:
            self._suspend_charge(
                observation,
                support_reason,
                hold_s=self.config.post_discharge_charge_hold_s,
            )

        return GuardedPower(limited, reasons, bypass_rate_limit)

    def _apply_charge_guards(
        self,
        requested_p_batt_w: float,
        observation: DTObservation,
    ) -> GuardedPower:
        requested_charge_w = abs(requested_p_batt_w)
        reasons: list[str] = []

        if observation.v_bus_v < self.goal.bus_min_v:
            reason = (
                "blocked charge because bus voltage is below the soft minimum "
                f"({observation.v_bus_v:.2f} V < {self.goal.bus_min_v:.2f} V)"
            )
            self._suspend_charge(observation, reason)
            return GuardedPower(0.0, [reason], bypass_rate_limit=True)

        recovery_reason = self._charge_recovery_reason(observation)
        if recovery_reason:
            return GuardedPower(0.0, [recovery_reason], bypass_rate_limit=True)

        if self._source_support_active:
            reason = (
                "blocked charge because source-support recovery is active; "
                "waiting for source deficit to clear and bus voltage to recover"
            )
            return GuardedPower(0.0, [reason], bypass_rate_limit=True)

        max_safe_charge_w = self.max_safe_charge_w(observation)
        if max_safe_charge_w <= 0.0:
            reason = (
                "blocked charge because no source headroom is available "
                f"(safe charge cap {max_safe_charge_w:.3f} W)"
            )
            self._suspend_charge(observation, reason)
            return GuardedPower(0.0, [reason], bypass_rate_limit=True)

        if requested_charge_w > max_safe_charge_w:
            limited_charge_w = max_safe_charge_w
            bypass_rate_limit = self._last_p_batt_cmd_w < -limited_charge_w
            reasons.append(
                "charge headroom guard capped charge to "
                f"{limited_charge_w:.3f} W "
                f"(source margin {self.config.charge_power_margin_w:.3f} W)"
            )
            return GuardedPower(
                -limited_charge_w,
                reasons,
                bypass_rate_limit=bypass_rate_limit,
            )

        return GuardedPower(requested_p_batt_w, reasons)

    def _clip_to_absolute_limit(self, requested_p_batt_w: float) -> tuple[float, list[str]]:
        max_abs_w = abs(self.config.max_p_batt_abs_w)
        clipped = max(-max_abs_w, min(max_abs_w, requested_p_batt_w))
        if math.isclose(clipped, requested_p_batt_w, abs_tol=1e-9):
            return clipped, []
        return clipped, [
            "absolute battery command limit clipped request from "
            f"{requested_p_batt_w:.3f} W to {clipped:.3f} W"
        ]

    def _rate_limit(self, target_p_batt_w: float, *, bypass: bool) -> tuple[float, bool]:
        if bypass:
            self._last_p_batt_cmd_w = target_p_batt_w
            return target_p_batt_w, False

        max_step = abs(self.config.max_p_batt_step_w)
        delta = max(
            -max_step,
            min(max_step, target_p_batt_w - self._last_p_batt_cmd_w),
        )
        limited = self._last_p_batt_cmd_w + delta
        rate_limited = not math.isclose(limited, target_p_batt_w, abs_tol=1e-9)
        self._last_p_batt_cmd_w = limited
        return limited, rate_limited

    def _suspend_charge(
        self,
        observation: DTObservation,
        reason: str,
        *,
        hold_s: float | None = None,
    ) -> None:
        now_s = _finite_or_zero(observation.sim_time_s)
        resolved_hold_s = (
            self.config.charge_recovery_hold_s if hold_s is None else hold_s
        )
        resolved_hold_s = max(0.0, resolved_hold_s)
        self._charge_blocked_until_s = max(
            self._charge_blocked_until_s,
            now_s + resolved_hold_s,
        )
        self._last_charge_block_reason = reason

    def _charge_recovery_reason(self, observation: DTObservation) -> str:
        if self._charge_blocked_until_s <= 0.0:
            return ""

        now_s = _finite_or_zero(observation.sim_time_s)
        remaining_s = self._charge_blocked_until_s - now_s
        if remaining_s > 1e-9:
            return (
                "charge recovery hold active for "
                f"{remaining_s:.3f} more seconds after "
                f"{self._last_charge_block_reason}"
            )

        resume_bus_v = self._charge_resume_bus_v()
        if observation.v_bus_v < resume_bus_v:
            return (
                "charge recovery waiting for bus voltage to recover above "
                f"{resume_bus_v:.2f} V after {self._last_charge_block_reason}"
            )

        self._charge_blocked_until_s = 0.0
        self._last_charge_block_reason = ""
        return ""

    def _charge_resume_bus_v(self) -> float:
        return self.goal.bus_min_v + max(0.0, self.config.charge_bus_hysteresis_v)

    def _discharge_support_reason(
        self,
        p_batt_cmd_w: float,
        observation: DTObservation,
    ) -> str:
        if p_batt_cmd_w <= 0.0:
            return ""
        if observation.v_bus_v < self.goal.bus_min_v:
            return (
                "battery discharged for bus-voltage support; charging is "
                "temporarily locked out to avoid using battery-created headroom"
            )
        if observation.source_at_limit:
            return (
                "battery discharged while source was at its limit; charging is "
                "temporarily locked out to avoid using battery-created headroom"
            )

        source_limit_w = self._source_power_limit_w(observation)
        if source_limit_w is None:
            return ""

        load_consumption_w = observation.resolved_load_consumption_w()
        margin_w = max(0.0, self.config.charge_power_margin_w)
        true_charge_headroom_w = source_limit_w - load_consumption_w - margin_w
        if true_charge_headroom_w <= 0.0:
            return (
                "battery discharged while true source charge headroom was zero; "
                "charging is temporarily locked out to avoid using "
                "battery-created headroom"
            )
        return ""

    def _source_support_needed(self, source_deficit_w: float) -> bool:
        if not self.config.allow_source_support_below_soc_min:
            return False
        return source_deficit_w > max(0.0, self.config.source_support_entry_margin_w)

    def _source_support_target_w(self, source_deficit_w: float) -> float:
        if not self.config.allow_source_support_below_soc_min:
            return 0.0
        return self._clamp_to_abs_limit(source_deficit_w)

    def _bus_voltage_error_v(self, observation: DTObservation) -> float:
        if not math.isfinite(observation.v_bus_v):
            return 0.0
        return max(0.0, self.goal.bus_nominal_v - observation.v_bus_v)

    def _bus_voltage_support_w(self, bus_voltage_error_v: float) -> float:
        gain_w_per_v = max(0.0, self.config.bus_support_gain_w_per_v)
        return max(0.0, bus_voltage_error_v) * gain_w_per_v

    def _update_bus_support_trim(
        self,
        observation: DTObservation,
        *,
        source_deficit_w: float,
        max_safe_discharge_w: float,
    ) -> float:
        gain_w_per_v_s = max(0.0, self.config.bus_support_trim_gain_w_per_v_s)
        max_trim_w = max(0.0, self.config.bus_support_trim_max_w)
        context_active = self._bus_support_context_active(
            observation,
            source_deficit_w,
        )
        now_s = _finite_or_zero(observation.sim_time_s)
        dt_s = self._elapsed_seconds(
            now_s,
            self._bus_support_trim_last_time_s,
        )
        self._bus_support_trim_last_time_s = now_s
        self._bus_support_trim_source_slack_w = self._source_slack_w(observation)

        if gain_w_per_v_s <= 0.0 or max_trim_w <= 0.0 or not context_active:
            self._bus_support_trim_w = 0.0
            self._bus_support_trim_error_v = 0.0
            return 0.0

        deadband_v = max(0.0, self.config.bus_support_trim_deadband_v)
        if math.isfinite(observation.v_bus_v):
            trim_error_v = max(
                0.0,
                self.goal.bus_nominal_v - deadband_v - observation.v_bus_v,
            )
        else:
            trim_error_v = 0.0
        self._bus_support_trim_error_v = trim_error_v

        voltage_support_w = 0.0
        if self._bus_voltage_support_active(observation, source_deficit_w):
            voltage_support_w = self._bus_voltage_support_w(
                self._bus_voltage_error_v(observation)
            )
        base_target_w = source_deficit_w + voltage_support_w
        available_trim_w = max(
            0.0,
            min(
                max_trim_w,
                max(0.0, max_safe_discharge_w) - base_target_w,
                self._clamp_to_abs_limit(max_trim_w + base_target_w)
                - base_target_w,
            ),
        )

        if trim_error_v > _VOLTAGE_ERROR_EPSILON and dt_s > 0.0:
            if base_target_w + self._bus_support_trim_w < max_safe_discharge_w:
                self._bus_support_trim_w += trim_error_v * gain_w_per_v_s * dt_s
        else:
            slack_deadband_w = max(
                0.0,
                self.config.bus_support_trim_source_slack_deadband_w,
            )
            excess_source_slack_w = max(
                0.0,
                self._bus_support_trim_source_slack_w - slack_deadband_w,
            )
            decay_w_per_s = max(0.0, self.config.bus_support_trim_decay_w_per_s)
            if excess_source_slack_w > 0.0 and decay_w_per_s > 0.0 and dt_s > 0.0:
                self._bus_support_trim_w -= decay_w_per_s * dt_s

        self._bus_support_trim_w = max(
            0.0,
            min(self._bus_support_trim_w, max_trim_w, available_trim_w),
        )
        return self._bus_support_trim_w

    def _update_bus_support_integral(
        self,
        observation: DTObservation,
        *,
        source_deficit_w: float,
        max_safe_discharge_w: float,
    ) -> float:
        gain_w_per_v_s = max(
            0.0,
            self.config.bus_support_integral_gain_w_per_v_s,
        )
        max_integral_w = max(0.0, self.config.bus_support_integral_max_w)
        context_active = self._bus_support_context_active(
            observation,
            source_deficit_w,
        )
        now_s = _finite_or_zero(observation.sim_time_s)
        if self._bus_support_integral_last_time_s is None:
            dt_s = 0.0
        else:
            dt_s = now_s - self._bus_support_integral_last_time_s
            if not math.isfinite(dt_s) or dt_s < 0.0:
                dt_s = 0.0
        max_dt_s = max(1.0, self.config.supervisor_period_s * 5.0)
        dt_s = min(dt_s, max_dt_s)
        self._bus_support_integral_last_time_s = now_s
        self._bus_support_integral_context_active = context_active

        if gain_w_per_v_s <= 0.0 or max_integral_w <= 0.0 or not context_active:
            self._bus_support_integral_v_s = 0.0
            self._bus_support_integral_w = 0.0
            self._bus_support_integral_error_v = 0.0
            return 0.0

        deadband_v = max(0.0, self.config.bus_support_integral_deadband_v)
        if math.isfinite(observation.v_bus_v):
            integral_error_v = max(
                0.0,
                self.goal.bus_nominal_v - deadband_v - observation.v_bus_v,
            )
        else:
            integral_error_v = 0.0
        self._bus_support_integral_error_v = integral_error_v

        leak_per_s = max(0.0, self.config.bus_support_integral_leak_per_s)
        if (
            leak_per_s > 0.0
            and dt_s > 0.0
            and integral_error_v <= _VOLTAGE_ERROR_EPSILON
        ):
            self._bus_support_integral_v_s *= max(0.0, 1.0 - leak_per_s * dt_s)

        voltage_support_w = 0.0
        if self._bus_voltage_support_active(observation, source_deficit_w):
            voltage_support_w = self._bus_voltage_support_w(
                self._bus_voltage_error_v(observation)
            )
        base_target_w = source_deficit_w + voltage_support_w + self._bus_support_trim_w
        max_output_w = min(
            self._clamp_to_abs_limit(max_integral_w + base_target_w),
            max(0.0, max_safe_discharge_w),
        )
        if (
            integral_error_v > 0.0
            and dt_s > 0.0
            and base_target_w < max_output_w
        ):
            self._bus_support_integral_v_s += integral_error_v * dt_s

        max_integral_v_s = max_integral_w / gain_w_per_v_s
        self._bus_support_integral_v_s = max(
            0.0,
            min(self._bus_support_integral_v_s, max_integral_v_s),
        )
        available_integral_w = max(0.0, max_output_w - base_target_w)
        self._bus_support_integral_w = min(
            max_integral_w,
            self._bus_support_integral_v_s * gain_w_per_v_s,
            available_integral_w,
        )
        return self._bus_support_integral_w

    def _update_bus_support_target_slew(
        self,
        observation: DTObservation,
        *,
        target_w: float,
        source_deficit_w: float,
        max_safe_discharge_w: float,
    ) -> float:
        context_active = self._bus_support_context_active(
            observation,
            source_deficit_w,
        )
        bounded_target_w = min(
            self._clamp_to_abs_limit(target_w),
            max(0.0, max_safe_discharge_w),
        )
        self._bus_support_target_unslewed_w = bounded_target_w

        now_s = _finite_or_zero(observation.sim_time_s)
        dt_s = self._elapsed_seconds(
            now_s,
            self._bus_support_target_last_time_s,
        )
        self._bus_support_target_last_time_s = now_s

        slew_down_w_per_s = max(
            0.0,
            self.config.bus_support_target_slew_down_w_per_s,
        )
        if (
            not context_active
            or slew_down_w_per_s <= 0.0
            or self._bus_support_target_w <= 0.0
            or bounded_target_w >= self._bus_support_target_w
        ):
            slewed_target_w = bounded_target_w
        else:
            max_drop_w = slew_down_w_per_s * max(0.0, dt_s)
            slewed_target_w = max(
                bounded_target_w,
                self._bus_support_target_w - max_drop_w,
            )

        self._bus_support_target_slew_active = (
            slewed_target_w > bounded_target_w + 1e-9
        )
        self._bus_support_target_w = min(
            self._clamp_to_abs_limit(slewed_target_w),
            max(0.0, max_safe_discharge_w),
        )
        return self._bus_support_target_w

    def _bus_voltage_support_active(
        self,
        observation: DTObservation,
        source_deficit_w: float,
    ) -> bool:
        if not math.isfinite(observation.v_bus_v):
            return False
        if observation.v_bus_v >= self.goal.bus_nominal_v:
            return False
        if self._bus_below_soft_min(observation):
            return True
        return self._source_support_active or self._source_support_needed(
            source_deficit_w
        )

    def _bus_support_context_active(
        self,
        observation: DTObservation,
        source_deficit_w: float,
    ) -> bool:
        if not math.isfinite(observation.v_bus_v):
            return False
        if self._bus_below_soft_min(observation):
            return True
        return self._source_support_active or self._source_support_needed(
            source_deficit_w
        )

    def _bus_below_soft_min(self, observation: DTObservation) -> bool:
        return (
            math.isfinite(observation.v_bus_v)
            and observation.v_bus_v < self.goal.bus_min_v
        )

    def _update_source_support_latch(
        self,
        observation: DTObservation,
        source_deficit_w: float,
        source_support_needed: bool,
    ) -> bool:
        if not self.config.allow_source_support_below_soc_min:
            self._source_support_active = False
            self._source_support_clear_since_s = None
            return False

        if source_support_needed:
            self._source_support_active = True
            self._source_support_clear_since_s = None
            return True

        if not self._source_support_active:
            return False

        deficit_clear = source_deficit_w <= max(
            0.0,
            self.config.source_support_clear_margin_w,
        )
        bus_recovered = observation.v_bus_v >= (
            self.goal.bus_min_v
            + max(0.0, self.config.source_support_bus_hysteresis_v)
        )
        if not deficit_clear or not bus_recovered:
            self._source_support_clear_since_s = None
            return True

        now_s = _finite_or_zero(observation.sim_time_s)
        if self._source_support_clear_since_s is None:
            self._source_support_clear_since_s = now_s
            return True

        if now_s - self._source_support_clear_since_s < max(
            0.0,
            self.config.source_support_hold_s,
        ):
            return True

        self._source_support_active = False
        self._source_support_clear_since_s = None
        return False

    def _source_slack_w(self, observation: DTObservation) -> float:
        source_limit_w = self._source_power_limit_w(observation)
        if source_limit_w is None or not math.isfinite(observation.p_source_w):
            return 0.0
        source_power_w = max(0.0, observation.p_source_w)
        return max(0.0, source_limit_w - source_power_w)

    def _elapsed_seconds(self, now_s: float, previous_s: float | None) -> float:
        if previous_s is None:
            return 0.0
        dt_s = now_s - previous_s
        if not math.isfinite(dt_s) or dt_s < 0.0:
            return 0.0
        max_dt_s = max(1.0, self.config.supervisor_period_s * 5.0)
        return min(dt_s, max_dt_s)

    def _source_power_limit_w(self, observation: DTObservation) -> float | None:
        for value in (
            observation.source_power_limit_w,
            self.config.source_power_limit_w,
            observation.extra.get("source_power_limit_w"),
            observation.extra.get("source_limit_w"),
            observation.extra.get("p_source_limit_w"),
        ):
            finite_value = _optional_finite_float(value)
            if finite_value is not None and finite_value > 0.0:
                return finite_value
        return None

    def _clamp_to_abs_limit(self, value: float) -> float:
        if not math.isfinite(value):
            return 0.0
        return max(0.0, min(abs(self.config.max_p_batt_abs_w), value))

    @staticmethod
    def _mode_for_power(original_mode: str, p_batt_cmd_w: float) -> str:
        if p_batt_cmd_w > 0.0:
            return "DISCHARGE"
        if p_batt_cmd_w < 0.0:
            return "CHARGE"
        if str(original_mode).strip().upper() == "SAFE":
            return "SAFE"
        return "HOLD"

    @staticmethod
    def _append_limit_reason(
        original_reason: str,
        guard_reasons: list[str],
        *,
        rate_limited: bool,
        guarded_w: float,
        limited_w: float,
    ) -> str:
        reason_parts = [original_reason] if original_reason else []
        reason_parts.extend(guard_reasons)
        if rate_limited:
            reason_parts.append(
                "rate limit moved command toward "
                f"{guarded_w:.3f} W; applied {limited_w:.3f} W this tick"
            )
        return "; ".join(reason_parts)


def _optional_finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(resolved):
        return None
    return resolved


def _finite_or_zero(value: Any) -> float:
    resolved = _optional_finite_float(value)
    return resolved if resolved is not None else 0.0
