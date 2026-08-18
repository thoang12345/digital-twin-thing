from __future__ import annotations

from collections.abc import Callable
import csv
import time
from pathlib import Path

from Modules.Digital_Twins.backends import SimulationBackend
from Modules.Digital_Twins.constraints import CommandConstraintLayer
from Modules.Digital_Twins.policy import ControlPolicy, SocBandPolicy
from Modules.Digital_Twins.types import (
    DTCommand,
    DTGoal,
    DTObservation,
    MissionStatus,
    RunnerConfig,
    RunnerEvent,
    RunnerResult,
)

RunnerCheckpoint = Callable[[RunnerResult], None]


class AutonomousRunner:
    """Periodic supervisory runner for autonomous DT control."""

    def __init__(
        self,
        backend: SimulationBackend,
        goal: DTGoal | None = None,
        policy: ControlPolicy | None = None,
        config: RunnerConfig | None = None,
        on_checkpoint: RunnerCheckpoint | None = None,
    ) -> None:
        self.backend = backend
        self.goal = goal or DTGoal()
        self.policy = policy or SocBandPolicy()
        self.config = config or RunnerConfig()
        self.constraints = CommandConstraintLayer(self.goal, self.config)
        self.on_checkpoint = on_checkpoint

    def run(self) -> RunnerResult:
        events: list[RunnerEvent] = []
        stable_for_s = 0.0
        safety_recovery_attempts = 0

        try:
            observation = self.constraints.augment_observation(self.backend.reset())
            last_checked_time_s = observation.sim_time_s
            tick_index = 0

            while observation.sim_time_s < self.goal.max_sim_time_s:
                elapsed_since_last_check_s = max(
                    0.0, observation.sim_time_s - last_checked_time_s
                )
                last_checked_time_s = observation.sim_time_s
                in_startup_grace = observation.sim_time_s < self.config.startup_grace_s
                hard_violations = self._hard_violations(
                    observation,
                    allow_startup_transient=in_startup_grace,
                )
                soft_violations = self._soft_violations(observation)

                if hard_violations:
                    recovery_result = self._handle_hard_violation(
                        events=events,
                        tick_index=tick_index,
                        observation=observation,
                        hard_violations=hard_violations,
                        recovery_attempts=safety_recovery_attempts,
                    )
                    if recovery_result is not None:
                        return recovery_result

                    safety_recovery_attempts += 1
                    stable_for_s = 0.0
                    if self.config.real_time:
                        time.sleep(self.config.supervisor_period_s)
                    observation = self.constraints.augment_observation(
                        self.backend.advance(self.config.supervisor_period_s)
                    )
                    tick_index += 1
                    continue

                safety_recovery_attempts = 0

                if self._goal_satisfied(observation) and not soft_violations:
                    stable_for_s += elapsed_since_last_check_s
                    if stable_for_s >= self.goal.success_hold_s:
                        hold_command = DTCommand.hold(
                            reason="goal held for required duration"
                        )
                        event = RunnerEvent(
                            tick_index=tick_index,
                            observation=observation,
                            command=hold_command,
                            status=MissionStatus.SUCCEEDED,
                            policy_command=None,
                            violations=[],
                        )
                        events.append(event)
                        result = RunnerResult(
                            status=MissionStatus.SUCCEEDED,
                            reason="goal held for required duration",
                            events=events,
                            final_observation=observation,
                        )
                        self._checkpoint(result)
                        return result
                else:
                    stable_for_s = 0.0

                if in_startup_grace:
                    policy_command = DTCommand.hold(
                        reason=(
                            "startup grace period; holding battery command "
                            "while model settles"
                        )
                    )
                else:
                    policy_command = self.policy.choose_action(observation, self.goal)
                command = self.constraints.limit(policy_command, observation)
                self.backend.apply_command(command)
                event = RunnerEvent(
                    tick_index=tick_index,
                    observation=observation,
                    command=command,
                    status=MissionStatus.RUNNING,
                    policy_command=policy_command,
                    violations=soft_violations,
                )
                events.append(event)
                self._checkpoint(
                    RunnerResult(
                        status=MissionStatus.RUNNING,
                        reason="checkpoint after latest supervisor decision",
                        events=list(events),
                        final_observation=observation,
                    )
                )

                if self.config.real_time:
                    time.sleep(self.config.supervisor_period_s)

                observation = self.constraints.augment_observation(
                    self.backend.advance(self.config.supervisor_period_s)
                )
                tick_index += 1

            result = RunnerResult(
                status=MissionStatus.TIMED_OUT,
                reason="maximum simulation time reached before success criteria",
                events=events,
                final_observation=observation,
            )
            self._checkpoint(result)
            return result
        except Exception as exc:  # pragma: no cover - defensive handoff path
            result = RunnerResult(
                status=MissionStatus.FAILED,
                reason=f"{type(exc).__name__}: {exc}",
                events=events,
                final_observation=self._safe_observe(),
            )
            self._checkpoint(result)
            return result
        finally:
            self.backend.close()

    def _goal_satisfied(self, observation: DTObservation) -> bool:
        return (
            self.goal.soc_min_pct <= observation.soc_pct <= self.goal.soc_max_pct
            and self.goal.bus_min_v <= observation.v_bus_v <= self.goal.bus_max_v
        )

    def _soft_violations(self, observation: DTObservation) -> list[str]:
        violations: list[str] = []
        if observation.soc_pct < self.goal.soc_min_pct:
            violations.append(
                f"SOC {observation.soc_pct:.2f}% below target minimum "
                f"{self.goal.soc_min_pct:.2f}%"
            )
        if observation.soc_pct > self.goal.soc_max_pct:
            violations.append(
                f"SOC {observation.soc_pct:.2f}% above target maximum "
                f"{self.goal.soc_max_pct:.2f}%"
            )
        if observation.v_bus_v < self.goal.bus_min_v:
            violations.append(
                f"bus voltage {observation.v_bus_v:.2f} V below soft minimum "
                f"{self.goal.bus_min_v:.2f} V"
            )
        if observation.v_bus_v > self.goal.bus_max_v:
            violations.append(
                f"bus voltage {observation.v_bus_v:.2f} V above soft maximum "
                f"{self.goal.bus_max_v:.2f} V"
            )
        return violations

    def _hard_violations(
        self,
        observation: DTObservation,
        allow_startup_transient: bool = False,
    ) -> list[str]:
        violations: list[str] = []
        startup_tolerated_faults = {
            "bridge_missing_soc_pct",
            "bridge_missing_v_bus_v",
        }
        active_faults = [
            name
            for name, is_active in observation.fault_flags.items()
            if is_active
            and not (allow_startup_transient and name in startup_tolerated_faults)
        ]
        if active_faults:
            fault_message = f"active fault flags: {', '.join(active_faults)}"
            if observation.fault_flags.get("bridge_sim_failed"):
                bridge_error = observation.extra.get("bridge_error")
                if bridge_error:
                    fault_message += f"; bridge_error: {bridge_error}"
            violations.append(fault_message)
        if allow_startup_transient:
            return violations
        if observation.soc_pct <= self.goal.soc_min_hard_pct:
            violations.append(
                f"SOC {observation.soc_pct:.2f}% at/under hard minimum "
                f"{self.goal.soc_min_hard_pct:.2f}%"
            )
        if observation.soc_pct >= self.goal.soc_max_hard_pct:
            violations.append(
                f"SOC {observation.soc_pct:.2f}% at/over hard maximum "
                f"{self.goal.soc_max_hard_pct:.2f}%"
            )
        if observation.v_bus_v <= self.goal.bus_min_hard_v:
            violations.append(
                f"bus voltage {observation.v_bus_v:.2f} V at/under hard minimum "
                f"{self.goal.bus_min_hard_v:.2f} V"
            )
        if observation.v_bus_v >= self.goal.bus_max_hard_v:
            violations.append(
                f"bus voltage {observation.v_bus_v:.2f} V at/over hard maximum "
                f"{self.goal.bus_max_hard_v:.2f} V"
            )
        if (
            self.goal.max_abs_battery_current_a is not None
            and abs(observation.i_batt_a) >= self.goal.max_abs_battery_current_a
        ):
            violations.append(
                f"battery current {observation.i_batt_a:.2f} A exceeds hard limit "
                f"{self.goal.max_abs_battery_current_a:.2f} A"
            )
        return violations

    def _safe_observe(self) -> DTObservation | None:
        try:
            return self.constraints.augment_observation(self.backend.observe())
        except Exception:
            return None

    def _checkpoint(self, result: RunnerResult) -> None:
        if self.on_checkpoint is None:
            return
        self.on_checkpoint(result)

    def _handle_hard_violation(
        self,
        *,
        events: list[RunnerEvent],
        tick_index: int,
        observation: DTObservation,
        hard_violations: list[str],
        recovery_attempts: int,
    ) -> RunnerResult | None:
        reason = "; ".join(hard_violations)
        if not self._safety_recovery_allowed(hard_violations):
            return self._safety_stop(
                events=events,
                tick_index=tick_index,
                observation=observation,
                reason=reason,
                violations=hard_violations,
                policy_command=None,
            )

        max_attempts = max(0, int(self.config.safety_recovery_attempts))
        if recovery_attempts >= max_attempts:
            return self._safety_stop(
                events=events,
                tick_index=tick_index,
                observation=observation,
                reason=(
                    f"{reason}; safety recovery attempts exhausted "
                    f"({recovery_attempts}/{max_attempts})"
                ),
                violations=hard_violations,
                policy_command=None,
            )

        safe_hold = DTCommand.safe(f"safety recovery arbitration: {reason}")
        self.backend.apply_command(safe_hold)

        recovery_attempt_number = recovery_attempts + 1
        try:
            recovery_policy_command = self._choose_safety_recovery_action(
                observation=observation,
                safety_reason=reason,
                attempt_index=recovery_attempt_number,
                max_attempts=max_attempts,
                recent_events=events[-5:],
            )
        except Exception as exc:
            return self._safety_stop(
                events=events,
                tick_index=tick_index,
                observation=observation,
                reason=(
                    f"{reason}; safety recovery policy failed: "
                    f"{type(exc).__name__}: {exc}"
                ),
                violations=hard_violations,
                policy_command=safe_hold,
            )

        if not recovery_policy_command.enable or recovery_policy_command.mode == "SAFE":
            return self._safety_stop(
                events=events,
                tick_index=tick_index,
                observation=observation,
                reason=(
                    f"{reason}; safety recovery declared full safe stop: "
                    f"{recovery_policy_command.reason}"
                ),
                violations=hard_violations,
                policy_command=recovery_policy_command,
            )

        recovery_command = self.constraints.limit(recovery_policy_command, observation)
        if not recovery_command.enable or recovery_command.mode == "SAFE":
            return self._safety_stop(
                events=events,
                tick_index=tick_index,
                observation=observation,
                reason=(
                    f"{reason}; safety recovery command was rejected by "
                    f"deterministic constraints: {recovery_command.reason}"
                ),
                violations=hard_violations,
                policy_command=recovery_policy_command,
            )

        self.backend.apply_command(recovery_command)
        event = RunnerEvent(
            tick_index=tick_index,
            observation=observation,
            command=recovery_command,
            status=MissionStatus.RECOVERING,
            policy_command=recovery_policy_command,
            violations=hard_violations,
        )
        events.append(event)
        self._checkpoint(
            RunnerResult(
                status=MissionStatus.RECOVERING,
                reason=(
                    f"safety recovery attempt "
                    f"{recovery_attempt_number}/{max_attempts}: {reason}"
                ),
                events=list(events),
                final_observation=observation,
            )
        )
        return None

    def _choose_safety_recovery_action(
        self,
        *,
        observation: DTObservation,
        safety_reason: str,
        attempt_index: int,
        max_attempts: int,
        recent_events: list[RunnerEvent],
    ) -> DTCommand:
        chooser = getattr(self.policy, "choose_safety_recovery_action", None)
        if chooser is None:
            return DTCommand.safe(
                reason=(
                    "safety recovery requested, but selected policy does not "
                    "support recovery arbitration"
                )
            )
        return chooser(
            observation,
            self.goal,
            safety_reason,
            attempt_index=attempt_index,
            max_attempts=max_attempts,
            recent_events=recent_events,
        )

    def _safety_recovery_allowed(self, hard_violations: list[str]) -> bool:
        if not self.config.safety_recovery_enabled:
            return False
        return not any(
            self._hard_violation_is_unrecoverable(violation)
            for violation in hard_violations
        )

    @staticmethod
    def _hard_violation_is_unrecoverable(violation: str) -> bool:
        normalized = violation.lower()
        unrecoverable_markers = (
            "fault flags",
            "bridge_",
            "missing",
            "invalid",
            "nan",
            "inf",
            "current",
        )
        return any(marker in normalized for marker in unrecoverable_markers)

    def _safety_stop(
        self,
        *,
        events: list[RunnerEvent],
        tick_index: int,
        observation: DTObservation,
        reason: str,
        violations: list[str],
        policy_command: DTCommand | None,
    ) -> RunnerResult:
        safe_command = DTCommand.safe(reason)
        self.backend.apply_command(safe_command)
        event = RunnerEvent(
            tick_index=tick_index,
            observation=observation,
            command=safe_command,
            status=MissionStatus.SAFETY_STOPPED,
            policy_command=policy_command,
            violations=violations,
        )
        events.append(event)
        result = RunnerResult(
            status=MissionStatus.SAFETY_STOPPED,
            reason=reason,
            events=events,
            final_observation=observation,
        )
        self._checkpoint(result)
        return result


def write_runner_events_csv(events: list[RunnerEvent], output_path: str | Path) -> None:
    """Write the runner audit trail as a flat CSV file."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "tick_index",
        "status",
        "sim_time_s",
        "soc_pct",
        "v_bus_v",
        "v_batt_v",
        "i_batt_a",
        "p_batt_w",
        "p_load_w",
        "load_consumption_w",
        "p_source_w",
        "max_safe_discharge_w",
        "max_safe_charge_w",
        "source_power_limit_w",
        "source_deficit_w",
        "source_support_needed",
        "source_support_active",
        "source_support_target_w",
        "bus_voltage_error_v",
        "bus_voltage_support_w",
        "bus_voltage_support_active",
        "bus_support_integral_error_v",
        "bus_support_integral_v_s",
        "bus_support_integral_w",
        "bus_support_integral_context_active",
        "bus_support_trim_error_v",
        "bus_support_trim_source_slack_w",
        "bus_support_trim_w",
        "bus_support_target_unslewed_w",
        "bus_support_target_slew_active",
        "bus_support_target_w",
        "source_can_sink_power",
        "source_at_limit",
        "source_available",
        "fault_flags",
        "observation_extra",
        "policy_mode",
        "policy_p_batt_cmd_w",
        "policy_command_enable",
        "policy_command_reason",
        "command_mode",
        "p_batt_cmd_w",
        "command_enable",
        "command_reason",
        "constraint_note",
        "violations",
    ]
    tmp_path = path.with_name(f".{path.name}.tmp")
    with tmp_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for event in events:
            obs = event.observation
            policy_cmd = event.policy_command
            cmd = event.command
            writer.writerow(
                {
                    "tick_index": event.tick_index,
                    "status": event.status.value,
                    "sim_time_s": obs.sim_time_s,
                    "soc_pct": obs.soc_pct,
                    "v_bus_v": obs.v_bus_v,
                    "v_batt_v": obs.v_batt_v,
                    "i_batt_a": obs.i_batt_a,
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
                    "source_support_target_w": obs.extra.get(
                        "source_support_target_w"
                    ),
                    "bus_voltage_error_v": obs.extra.get("bus_voltage_error_v"),
                    "bus_voltage_support_w": obs.extra.get("bus_voltage_support_w"),
                    "bus_voltage_support_active": obs.extra.get(
                        "bus_voltage_support_active"
                    ),
                    "bus_support_integral_error_v": obs.extra.get(
                        "bus_support_integral_error_v"
                    ),
                    "bus_support_integral_v_s": obs.extra.get(
                        "bus_support_integral_v_s"
                    ),
                    "bus_support_integral_w": obs.extra.get(
                        "bus_support_integral_w"
                    ),
                    "bus_support_integral_context_active": obs.extra.get(
                        "bus_support_integral_context_active"
                    ),
                    "bus_support_trim_error_v": obs.extra.get(
                        "bus_support_trim_error_v"
                    ),
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
                    "source_can_sink_power": obs.source_can_sink_power,
                    "source_at_limit": obs.source_at_limit,
                    "source_available": obs.source_available,
                    "fault_flags": obs.fault_flags,
                    "observation_extra": obs.extra,
                    "policy_mode": policy_cmd.mode if policy_cmd else "",
                    "policy_p_batt_cmd_w": (
                        policy_cmd.p_batt_cmd_w if policy_cmd else ""
                    ),
                    "policy_command_enable": policy_cmd.enable if policy_cmd else "",
                    "policy_command_reason": policy_cmd.reason if policy_cmd else "",
                    "command_mode": cmd.mode,
                    "p_batt_cmd_w": cmd.p_batt_cmd_w,
                    "command_enable": cmd.enable,
                    "command_reason": cmd.reason,
                    "constraint_note": event.constraint_note(),
                    "violations": " | ".join(event.violations),
                }
            )
    tmp_path.replace(path)
