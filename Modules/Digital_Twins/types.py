from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any


class MissionStatus(str, Enum):
    """Terminal and non-terminal states for an autonomous DT mission."""

    RUNNING = "running"
    RECOVERING = "recovering"
    SUCCEEDED = "succeeded"
    TIMED_OUT = "timed_out"
    SAFETY_STOPPED = "safety_stopped"
    FAILED = "failed"


@dataclass(slots=True)
class DTGoal:
    """Goal contract for the battery/load-bus autonomous runner.

    The first mission is intentionally modest: keep state of charge inside a
    desired band while keeping the bus voltage inside a soft tolerance. Hard
    limits are kept separate so the runner can stop deterministically before
    an LLM/policy has a chance to make the situation worse.
    """

    soc_min_pct: float = 40.0
    soc_max_pct: float = 80.0
    bus_nominal_v: float = 400.0
    bus_tolerance_pct: float = 0.05
    bus_hard_tolerance_pct: float = 0.20
    success_hold_s: float = 60.0
    max_sim_time_s: float = 600.0
    soc_min_hard_pct: float = 10.0
    soc_max_hard_pct: float = 95.0
    max_abs_battery_current_a: float | None = None

    @property
    def bus_min_v(self) -> float:
        return self.bus_nominal_v * (1.0 - self.bus_tolerance_pct)

    @property
    def bus_max_v(self) -> float:
        return self.bus_nominal_v * (1.0 + self.bus_tolerance_pct)

    @property
    def bus_min_hard_v(self) -> float:
        return self.bus_nominal_v * (1.0 - self.bus_hard_tolerance_pct)

    @property
    def bus_max_hard_v(self) -> float:
        return self.bus_nominal_v * (1.0 + self.bus_hard_tolerance_pct)


@dataclass(slots=True)
class DTObservation:
    """Compact state snapshot exposed to the autonomous runner."""

    sim_time_s: float
    soc_pct: float
    v_bus_v: float
    v_batt_v: float = 0.0
    i_batt_a: float = 0.0
    p_batt_w: float = 0.0
    p_load_w: float = 0.0
    p_source_w: float = 0.0
    load_consumption_w: float | None = None
    max_safe_discharge_w: float | None = None
    max_safe_charge_w: float | None = None
    source_power_limit_w: float | None = None
    source_can_sink_power: bool = False
    source_at_limit: bool = False
    source_available: bool = True
    fault_flags: dict[str, bool] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def resolved_load_consumption_w(self) -> float:
        """Return positive load consumption regardless of raw sensor polarity.

        Some Simulink electrical measurements report load power as negative
        because the sensor reference direction points into the bus. The raw
        ``p_load_w`` value is preserved for debugging, while this derived value
        gives policies a stable "how much load can absorb battery power?"
        quantity.
        """

        if self.load_consumption_w is not None:
            try:
                value = float(self.load_consumption_w)
            except (TypeError, ValueError):
                return 0.0
            return value if math.isfinite(value) and value > 0.0 else 0.0

        try:
            raw_load_w = float(self.p_load_w)
        except (TypeError, ValueError):
            return 0.0
        if not math.isfinite(raw_load_w):
            return 0.0
        return abs(raw_load_w)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sim_time_s": self.sim_time_s,
            "soc_pct": self.soc_pct,
            "v_bus_v": self.v_bus_v,
            "v_batt_v": self.v_batt_v,
            "i_batt_a": self.i_batt_a,
            "p_batt_w": self.p_batt_w,
            "p_load_w": self.p_load_w,
            "load_consumption_w": self.resolved_load_consumption_w(),
            "p_source_w": self.p_source_w,
            "max_safe_discharge_w": self.max_safe_discharge_w,
            "max_safe_charge_w": self.max_safe_charge_w,
            "source_power_limit_w": self.source_power_limit_w,
            "source_can_sink_power": self.source_can_sink_power,
            "source_at_limit": self.source_at_limit,
            "source_available": self.source_available,
            "fault_flags": dict(self.fault_flags),
            "extra": dict(self.extra),
        }


@dataclass(slots=True)
class DTCommand:
    """Command contract sent from the runner into the DT model."""

    mode: str = "HOLD"
    p_batt_cmd_w: float = 0.0
    enable: bool = True
    reason: str = ""

    @classmethod
    def charge(cls, p_batt_cmd_w: float, reason: str = "") -> "DTCommand":
        return cls(mode="CHARGE", p_batt_cmd_w=-abs(p_batt_cmd_w), reason=reason)

    @classmethod
    def discharge(cls, p_batt_cmd_w: float, reason: str = "") -> "DTCommand":
        return cls(
            mode="DISCHARGE",
            p_batt_cmd_w=abs(p_batt_cmd_w),
            reason=reason,
        )

    @classmethod
    def hold(cls, reason: str = "") -> "DTCommand":
        return cls(mode="HOLD", p_batt_cmd_w=0.0, reason=reason)

    @classmethod
    def safe(cls, reason: str = "") -> "DTCommand":
        return cls(mode="SAFE", p_batt_cmd_w=0.0, enable=False, reason=reason)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "p_batt_cmd_w": self.p_batt_cmd_w,
            "enable": self.enable,
            "reason": self.reason,
        }


@dataclass(slots=True)
class RunnerConfig:
    """Execution settings for the supervisory runner."""

    supervisor_period_s: float = 5.0
    startup_grace_s: float = 1.0
    max_p_batt_abs_w: float = 500.0
    max_p_batt_step_w: float = 100.0
    prevent_source_backfeed: bool = True
    source_min_power_w: float = 0.0
    source_power_margin_w: float = 25.0
    source_power_limit_w: float | None = None
    prevent_charge_without_source_headroom: bool = True
    charge_power_margin_w: float = 25.0
    charge_bus_hysteresis_v: float = 5.0
    charge_recovery_hold_s: float = 10.0
    post_discharge_charge_hold_s: float = 10.0
    block_discharge_below_soc_min: bool = True
    allow_source_support_below_soc_min: bool = True
    source_support_entry_margin_w: float = 5.0
    source_support_clear_margin_w: float = 1.0
    source_support_bus_hysteresis_v: float = 5.0
    source_support_hold_s: float = 3.0
    bus_support_min_w: float = 150.0
    bus_support_gain_w_per_v: float = 5.0
    bus_support_integral_gain_w_per_v_s: float = 0.0
    bus_support_integral_max_w: float = 20.0
    bus_support_integral_leak_per_s: float = 0.25
    bus_support_integral_deadband_v: float = 0.25
    bus_support_trim_gain_w_per_v_s: float = 0.0
    bus_support_trim_max_w: float = 12.0
    bus_support_trim_decay_w_per_s: float = 0.25
    bus_support_trim_deadband_v: float = 0.25
    bus_support_trim_source_slack_deadband_w: float = 2.0
    bus_support_target_slew_down_w_per_s: float = 0.0
    safety_recovery_enabled: bool = False
    safety_recovery_attempts: int = 2
    real_time: bool = False


@dataclass(slots=True)
class RunnerEvent:
    """One supervisory decision made by the runner."""

    tick_index: int
    observation: DTObservation
    command: DTCommand
    status: MissionStatus
    policy_command: DTCommand | None = None
    violations: list[str] = field(default_factory=list)

    def constraint_note(self) -> str:
        """Describe how deterministic constraints changed the policy command."""

        if self.policy_command is None:
            return ""

        same_mode = self.policy_command.mode == self.command.mode
        same_enable = self.policy_command.enable == self.command.enable
        same_power = abs(
            self.policy_command.p_batt_cmd_w - self.command.p_batt_cmd_w
        ) < 1e-9
        if same_mode and same_enable and same_power:
            return "none"

        policy_reason = self.policy_command.reason
        applied_reason = self.command.reason
        if policy_reason and applied_reason.startswith(policy_reason + "; "):
            return applied_reason[len(policy_reason) + 2 :]
        if applied_reason and applied_reason != policy_reason:
            return applied_reason
        return "modified by deterministic constraints"


@dataclass(slots=True)
class RunnerResult:
    """Final mission result and audit trail."""

    status: MissionStatus
    reason: str
    events: list[RunnerEvent] = field(default_factory=list)
    final_observation: DTObservation | None = None
