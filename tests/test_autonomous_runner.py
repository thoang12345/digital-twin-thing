import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from Modules.Digital_Twins.backends import MockBatteryBusBackend, SimulinkBackend
from Modules.Digital_Twins.constraints import CommandConstraintLayer
from Modules.Digital_Twins.policy import LLMControlPolicy, SocBandPolicy
from Modules.Digital_Twins.reporting import write_mission_report
from Modules.Digital_Twins.runner import AutonomousRunner
from Modules.Digital_Twins.types import (
    DTCommand,
    DTGoal,
    DTObservation,
    MissionStatus,
    RunnerConfig,
)


class FakeMatlabEngine:
    def __init__(self):
        self.paths = []
        self.commands = []
        self.closed = False

    def addpath(self, path, nargout=0):
        self.paths.append(path)

    def dt_bridge_init(
        self,
        model_name,
        model_path,
        p_batt_cmd_variable,
        enable_variable,
        mode_variable,
        nargout=1,
    ):
        return json.dumps(
            {
                "sim_time_s": 0.0,
                "soc_pct": 55.0,
                "v_bus_v": 400.0,
                "v_batt_v": 300.0,
                "i_batt_a": 0.0,
                "p_batt_w": 0.0,
                "p_load_w": 2500.0,
                "p_source_w": 2500.0,
                "source_at_limit": False,
                "source_available": True,
                "fault_flags": {},
                "extra": {
                    "model_name": model_name,
                    "model_path": model_path,
                    "p_batt_cmd_variable": p_batt_cmd_variable,
                    "enable_variable": enable_variable,
                    "mode_variable": mode_variable,
                },
            }
        )

    def dt_bridge_apply_command(
        self,
        p_batt_cmd_w,
        enable_cmd,
        mode_cmd,
        reason,
        nargout=0,
    ):
        self.commands.append((p_batt_cmd_w, enable_cmd, mode_cmd, reason))

    def dt_bridge_step(self, seconds, nargout=1):
        return json.dumps(
            {
                "sim_time_s": seconds,
                "soc_pct": 54.9,
                "v_bus_v": 399.0,
                "v_batt_v": 300.0,
                "i_batt_a": 1.0,
                "p_batt_w": 300.0,
                "p_load_w": 2500.0,
                "p_source_w": 2200.0,
                "source_at_limit": False,
                "source_available": True,
                "fault_flags": {},
                "extra": {},
            }
        )

    def dt_bridge_observe(self, nargout=1):
        return self.dt_bridge_step(0.0)

    def dt_bridge_close(self, nargout=0):
        self.closed = True


class FakeChatCompletions:
    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self.content),
                )
            ]
        )


class FakeLLMClient:
    def __init__(self, content=None, error=None):
        self.chat = SimpleNamespace(
            completions=FakeChatCompletions(content=content, error=error)
        )


class FixedDischargePolicy:
    def __init__(self, power_w):
        self.power_w = power_w

    def choose_action(self, observation, goal):
        return DTCommand.discharge(self.power_w, reason="unit test requested discharge")


class FixedChargePolicy:
    def __init__(self, power_w):
        self.power_w = power_w

    def choose_action(self, observation, goal):
        return DTCommand.charge(self.power_w, reason="unit test requested charge")


class FixedSafetyRecoveryPolicy:
    def __init__(self, command):
        self.command = command
        self.recovery_calls = []

    def choose_action(self, observation, goal):
        return DTCommand.hold(reason="ordinary policy should not run during hard violation")

    def choose_safety_recovery_action(
        self,
        observation,
        goal,
        safety_reason,
        *,
        attempt_index,
        max_attempts,
        recent_events,
    ):
        self.recovery_calls.append(
            {
                "observation": observation,
                "safety_reason": safety_reason,
                "attempt_index": attempt_index,
                "max_attempts": max_attempts,
                "recent_events": list(recent_events),
            }
        )
        return self.command


class SequenceBackend:
    def __init__(self, observations):
        self.observations = list(observations)
        self.index = 0
        self.commands = []
        self.closed = False

    def reset(self):
        self.index = 0
        return self.observations[0]

    def observe(self):
        return self.observations[self.index]

    def apply_command(self, command):
        self.commands.append(command)

    def advance(self, seconds):
        self.index = min(self.index + 1, len(self.observations) - 1)
        return self.observations[self.index]

    def close(self):
        self.closed = True


class AutonomousRunnerTests(unittest.TestCase):
    def test_observation_derives_positive_load_consumption_from_signed_load_power(self):
        observation = DTObservation(
            sim_time_s=0.0,
            soc_pct=55.0,
            v_bus_v=400.0,
            p_load_w=-200.0,
        )

        payload = observation.to_dict()

        self.assertEqual(payload["p_load_w"], -200.0)
        self.assertEqual(payload["load_consumption_w"], 200.0)
        self.assertFalse(payload["source_can_sink_power"])

    def test_runner_succeeds_when_goal_is_held(self):
        backend = MockBatteryBusBackend(initial_soc_pct=55.0)
        runner = AutonomousRunner(
            backend=backend,
            goal=DTGoal(success_hold_s=10.0, max_sim_time_s=30.0),
            config=RunnerConfig(supervisor_period_s=5.0, startup_grace_s=0.0),
        )

        result = runner.run()

        self.assertEqual(result.status, MissionStatus.SUCCEEDED)
        self.assertGreaterEqual(len(result.events), 1)
        self.assertEqual(result.events[0].command.mode, "HOLD")

    def test_policy_charges_when_soc_is_below_target(self):
        backend = MockBatteryBusBackend(initial_soc_pct=35.0)
        runner = AutonomousRunner(
            backend=backend,
            goal=DTGoal(soc_min_pct=40.0, success_hold_s=10.0, max_sim_time_s=10.0),
            policy=SocBandPolicy(charge_power_w=100.0),
            config=RunnerConfig(supervisor_period_s=5.0, startup_grace_s=0.0),
        )

        result = runner.run()

        self.assertEqual(result.events[0].command.mode, "CHARGE")
        self.assertLess(result.events[0].command.p_batt_cmd_w, 0.0)

    def test_policy_preemptively_supports_bus_when_source_is_overloaded(self):
        policy = SocBandPolicy(bus_support_power_w=150.0)
        observation = DTObservation(
            sim_time_s=100.0,
            soc_pct=15.0,
            v_bus_v=400.0,
            p_batt_w=0.0,
            p_load_w=-900.0,
            p_source_w=500.0,
            max_safe_discharge_w=475.0,
            source_at_limit=True,
            source_available=True,
        )

        command = policy.choose_action(observation, DTGoal(soc_min_pct=40.0))

        self.assertEqual(command.mode, "DISCHARGE")
        self.assertAlmostEqual(command.p_batt_cmd_w, 400.0)
        self.assertIn("source is overloaded", command.reason)

    def test_policy_holds_when_load_is_only_at_known_source_limit(self):
        policy = SocBandPolicy(bus_support_power_w=150.0)
        observation = DTObservation(
            sim_time_s=100.0,
            soc_pct=15.0,
            v_bus_v=400.0,
            p_batt_w=0.0,
            p_load_w=-500.0,
            p_source_w=500.0,
            source_power_limit_w=500.0,
            max_safe_charge_w=0.0,
            source_at_limit=True,
            source_available=False,
        )

        command = policy.choose_action(observation, DTGoal(soc_min_pct=40.0))

        self.assertEqual(command.mode, "HOLD")
        self.assertIn("SOC is low", command.reason)

    def test_policy_uses_source_limit_for_overload_even_if_flag_lags(self):
        policy = SocBandPolicy(bus_support_power_w=150.0)
        observation = DTObservation(
            sim_time_s=100.0,
            soc_pct=15.0,
            v_bus_v=400.0,
            p_batt_w=0.0,
            p_load_w=-900.0,
            p_source_w=500.0,
            source_power_limit_w=500.0,
            max_safe_discharge_w=475.0,
            source_at_limit=False,
            source_available=True,
        )

        command = policy.choose_action(observation, DTGoal(soc_min_pct=40.0))

        self.assertEqual(command.mode, "DISCHARGE")
        self.assertAlmostEqual(command.p_batt_cmd_w, 400.0)

    def test_runner_safety_stops_on_hard_soc_violation(self):
        backend = MockBatteryBusBackend(initial_soc_pct=5.0)
        runner = AutonomousRunner(
            backend=backend,
            goal=DTGoal(soc_min_hard_pct=10.0),
            config=RunnerConfig(supervisor_period_s=5.0, startup_grace_s=0.0),
        )

        result = runner.run()

        self.assertEqual(result.status, MissionStatus.SAFETY_STOPPED)
        self.assertEqual(result.events[0].command.mode, "SAFE")

    def test_runner_default_still_immediate_safety_stops_on_hard_voltage(self):
        backend = SequenceBackend(
            [
                DTObservation(sim_time_s=0.0, soc_pct=55.0, v_bus_v=300.0),
                DTObservation(sim_time_s=1.0, soc_pct=55.0, v_bus_v=400.0),
            ]
        )
        policy = FixedSafetyRecoveryPolicy(DTCommand.discharge(100.0))
        runner = AutonomousRunner(
            backend=backend,
            goal=DTGoal(bus_nominal_v=400.0, max_sim_time_s=10.0),
            policy=policy,
            config=RunnerConfig(supervisor_period_s=1.0, startup_grace_s=0.0),
        )

        result = runner.run()

        self.assertEqual(result.status, MissionStatus.SAFETY_STOPPED)
        self.assertEqual(result.events[0].command.mode, "SAFE")
        self.assertEqual(policy.recovery_calls, [])

    def test_runner_uses_safety_recovery_for_recoverable_hard_voltage(self):
        backend = SequenceBackend(
            [
                DTObservation(
                    sim_time_s=0.0,
                    soc_pct=55.0,
                    v_bus_v=300.0,
                    p_load_w=300.0,
                    p_source_w=250.0,
                    max_safe_discharge_w=250.0,
                ),
                DTObservation(
                    sim_time_s=1.0,
                    soc_pct=55.0,
                    v_bus_v=400.0,
                    p_load_w=300.0,
                    p_source_w=300.0,
                ),
                DTObservation(
                    sim_time_s=2.0,
                    soc_pct=55.0,
                    v_bus_v=400.0,
                    p_load_w=300.0,
                    p_source_w=300.0,
                ),
            ]
        )
        policy = FixedSafetyRecoveryPolicy(
            DTCommand.discharge(100.0, reason="unit test recovery")
        )
        runner = AutonomousRunner(
            backend=backend,
            goal=DTGoal(
                bus_nominal_v=400.0,
                success_hold_s=1.0,
                max_sim_time_s=10.0,
            ),
            policy=policy,
            config=RunnerConfig(
                supervisor_period_s=1.0,
                startup_grace_s=0.0,
                max_p_batt_step_w=500.0,
                safety_recovery_enabled=True,
                safety_recovery_attempts=2,
            ),
        )

        result = runner.run()

        self.assertEqual(result.events[0].status, MissionStatus.RECOVERING)
        self.assertEqual(result.events[0].command.mode, "DISCHARGE")
        self.assertEqual(result.events[0].policy_command.mode, "DISCHARGE")
        self.assertEqual(len(policy.recovery_calls), 1)
        self.assertIn("bus voltage", policy.recovery_calls[0]["safety_reason"])
        self.assertEqual(policy.recovery_calls[0]["attempt_index"], 1)
        self.assertEqual(result.status, MissionStatus.SUCCEEDED)

    def test_runner_exhausts_safety_recovery_attempts(self):
        backend = SequenceBackend(
            [
                DTObservation(sim_time_s=0.0, soc_pct=55.0, v_bus_v=300.0),
                DTObservation(sim_time_s=1.0, soc_pct=55.0, v_bus_v=300.0),
                DTObservation(sim_time_s=2.0, soc_pct=55.0, v_bus_v=300.0),
            ]
        )
        policy = FixedSafetyRecoveryPolicy(
            DTCommand.hold(reason="unit test hold and recheck")
        )
        runner = AutonomousRunner(
            backend=backend,
            goal=DTGoal(bus_nominal_v=400.0, max_sim_time_s=10.0),
            policy=policy,
            config=RunnerConfig(
                supervisor_period_s=1.0,
                startup_grace_s=0.0,
                safety_recovery_enabled=True,
                safety_recovery_attempts=1,
            ),
        )

        result = runner.run()

        self.assertEqual(result.status, MissionStatus.SAFETY_STOPPED)
        self.assertEqual(result.events[0].status, MissionStatus.RECOVERING)
        self.assertEqual(result.events[-1].status, MissionStatus.SAFETY_STOPPED)
        self.assertIn("attempts exhausted", result.reason)

    def test_runner_does_not_recover_instrumentation_faults(self):
        backend = SequenceBackend(
            [
                DTObservation(
                    sim_time_s=0.0,
                    soc_pct=55.0,
                    v_bus_v=400.0,
                    fault_flags={"bridge_sim_failed": True},
                    extra={"bridge_error": "unit test bridge failure"},
                )
            ]
        )
        policy = FixedSafetyRecoveryPolicy(DTCommand.hold())
        runner = AutonomousRunner(
            backend=backend,
            goal=DTGoal(max_sim_time_s=10.0),
            policy=policy,
            config=RunnerConfig(
                supervisor_period_s=1.0,
                startup_grace_s=0.0,
                safety_recovery_enabled=True,
                safety_recovery_attempts=2,
            ),
        )

        result = runner.run()

        self.assertEqual(result.status, MissionStatus.SAFETY_STOPPED)
        self.assertEqual(result.events[0].command.mode, "SAFE")
        self.assertEqual(policy.recovery_calls, [])

    def test_runner_caps_discharge_to_prevent_source_backfeed(self):
        backend = MockBatteryBusBackend(
            initial_soc_pct=55.0,
            load_power_w=200.0,
            source_power_limit_w=300.0,
        )
        runner = AutonomousRunner(
            backend=backend,
            goal=DTGoal(success_hold_s=999.0, max_sim_time_s=1.0),
            policy=FixedDischargePolicy(500.0),
            config=RunnerConfig(
                supervisor_period_s=1.0,
                startup_grace_s=0.0,
                max_p_batt_abs_w=500.0,
                max_p_batt_step_w=500.0,
                source_power_margin_w=25.0,
            ),
        )

        result = runner.run()

        self.assertEqual(result.events[0].command.mode, "DISCHARGE")
        self.assertAlmostEqual(result.events[0].command.p_batt_cmd_w, 175.0)
        self.assertAlmostEqual(result.events[0].observation.max_safe_discharge_w, 175.0)
        self.assertIn("no-backfeed guard capped", result.events[0].command.reason)

    def test_runner_blocks_discretionary_discharge_below_soc_target(self):
        backend = MockBatteryBusBackend(
            initial_soc_pct=15.0,
            load_power_w=200.0,
            source_power_limit_w=300.0,
        )
        runner = AutonomousRunner(
            backend=backend,
            goal=DTGoal(soc_min_pct=40.0, success_hold_s=999.0, max_sim_time_s=1.0),
            policy=FixedDischargePolicy(200.0),
            config=RunnerConfig(
                supervisor_period_s=1.0,
                startup_grace_s=0.0,
                max_p_batt_abs_w=500.0,
                max_p_batt_step_w=500.0,
            ),
        )

        result = runner.run()

        self.assertEqual(result.events[0].policy_command.mode, "DISCHARGE")
        self.assertEqual(result.events[0].policy_command.p_batt_cmd_w, 200.0)
        self.assertEqual(result.events[0].command.mode, "HOLD")
        self.assertEqual(result.events[0].command.p_batt_cmd_w, 0.0)
        self.assertIn("blocked discharge", result.events[0].constraint_note())
        self.assertIn("blocked discharge because SOC is below", result.events[0].command.reason)

    def test_runner_allows_low_soc_discharge_for_real_source_deficit(self):
        backend = MockBatteryBusBackend(
            initial_soc_pct=15.0,
            load_power_w=600.0,
            source_power_limit_w=500.0,
        )
        runner = AutonomousRunner(
            backend=backend,
            goal=DTGoal(soc_min_pct=40.0, success_hold_s=999.0, max_sim_time_s=1.0),
            policy=FixedDischargePolicy(300.0),
            config=RunnerConfig(
                supervisor_period_s=1.0,
                startup_grace_s=0.0,
                max_p_batt_abs_w=500.0,
                max_p_batt_step_w=500.0,
                source_power_limit_w=500.0,
                source_support_entry_margin_w=5.0,
            ),
        )

        result = runner.run()
        observation = result.events[0].observation

        self.assertEqual(result.events[0].policy_command.mode, "DISCHARGE")
        self.assertEqual(result.events[0].command.mode, "DISCHARGE")
        self.assertAlmostEqual(result.events[0].command.p_batt_cmd_w, 100.0)
        self.assertAlmostEqual(observation.extra["source_deficit_w"], 100.0)
        self.assertTrue(observation.extra["source_support_needed"])
        self.assertIn("low-SOC source-support guard capped", result.events[0].constraint_note())

    def test_bus_support_target_uses_voltage_error_when_bus_is_low(self):
        constraints = CommandConstraintLayer(
            goal=DTGoal(soc_min_pct=40.0, bus_nominal_v=400.0),
            config=RunnerConfig(
                max_p_batt_abs_w=500.0,
                source_power_limit_w=500.0,
                bus_support_min_w=150.0,
                bus_support_gain_w_per_v=5.0,
            ),
        )

        observation = constraints.augment_observation(
            DTObservation(
                sim_time_s=102.0,
                soc_pct=15.0,
                v_bus_v=346.0,
                p_load_w=519.0,
                p_source_w=500.0,
            )
        )

        self.assertAlmostEqual(observation.extra["source_deficit_w"], 19.0)
        self.assertAlmostEqual(observation.extra["bus_voltage_error_v"], 54.0)
        self.assertAlmostEqual(observation.extra["bus_voltage_support_w"], 270.0)
        self.assertAlmostEqual(observation.extra["bus_support_target_w"], 289.0)

    def test_bus_support_target_adds_voltage_error_before_soft_min(self):
        constraints = CommandConstraintLayer(
            goal=DTGoal(soc_min_pct=40.0, bus_nominal_v=400.0),
            config=RunnerConfig(
                max_p_batt_abs_w=500.0,
                source_power_limit_w=500.0,
                bus_support_min_w=150.0,
                bus_support_gain_w_per_v=5.0,
            ),
        )

        observation = constraints.augment_observation(
            DTObservation(
                sim_time_s=120.0,
                soc_pct=15.0,
                v_bus_v=390.0,
                p_load_w=585.0,
                p_source_w=500.0,
            )
        )

        self.assertAlmostEqual(observation.extra["source_deficit_w"], 85.0)
        self.assertAlmostEqual(observation.extra["bus_voltage_error_v"], 10.0)
        self.assertAlmostEqual(observation.extra["bus_voltage_support_w"], 50.0)
        self.assertTrue(observation.extra["bus_voltage_support_active"])
        self.assertAlmostEqual(observation.extra["bus_support_target_w"], 135.0)

    def test_low_soc_cap_uses_bus_support_target_before_soft_min(self):
        constraints = CommandConstraintLayer(
            goal=DTGoal(soc_min_pct=40.0, bus_nominal_v=400.0),
            config=RunnerConfig(
                max_p_batt_abs_w=500.0,
                max_p_batt_step_w=500.0,
                source_power_limit_w=500.0,
                bus_support_min_w=150.0,
                bus_support_gain_w_per_v=5.0,
            ),
        )
        observation = constraints.augment_observation(
            DTObservation(
                sim_time_s=120.0,
                soc_pct=15.0,
                v_bus_v=390.0,
                p_load_w=585.0,
                p_source_w=500.0,
            )
        )

        command = constraints.limit(
            DTCommand.discharge(300.0, reason="unit test requested smooth support"),
            observation,
        )

        self.assertAlmostEqual(observation.extra["source_support_target_w"], 85.0)
        self.assertAlmostEqual(observation.extra["bus_support_target_w"], 135.0)
        self.assertEqual(command.mode, "DISCHARGE")
        self.assertAlmostEqual(command.p_batt_cmd_w, 135.0)
        self.assertIn("low-SOC bus-support guard capped", command.reason)

    def test_bus_support_target_uses_source_deficit_when_bus_is_healthy(self):
        constraints = CommandConstraintLayer(
            goal=DTGoal(soc_min_pct=40.0, bus_nominal_v=400.0),
            config=RunnerConfig(
                max_p_batt_abs_w=500.0,
                source_power_limit_w=500.0,
                bus_support_min_w=150.0,
                bus_support_gain_w_per_v=5.0,
            ),
        )

        observation = constraints.augment_observation(
            DTObservation(
                sim_time_s=100.0,
                soc_pct=15.0,
                v_bus_v=400.0,
                p_load_w=600.0,
                p_source_w=500.0,
            )
        )

        self.assertAlmostEqual(observation.extra["source_deficit_w"], 100.0)
        self.assertAlmostEqual(observation.extra["bus_voltage_error_v"], 0.0)
        self.assertAlmostEqual(observation.extra["bus_support_target_w"], 100.0)

    def test_bus_support_integral_accumulates_when_enabled(self):
        constraints = CommandConstraintLayer(
            goal=DTGoal(soc_min_pct=40.0, bus_nominal_v=400.0),
            config=RunnerConfig(
                supervisor_period_s=1.0,
                max_p_batt_abs_w=500.0,
                source_power_limit_w=500.0,
                bus_support_min_w=150.0,
                bus_support_gain_w_per_v=5.0,
                bus_support_integral_gain_w_per_v_s=1.0,
                bus_support_integral_max_w=20.0,
                bus_support_integral_leak_per_s=0.0,
                bus_support_integral_deadband_v=0.0,
            ),
        )

        first = constraints.augment_observation(
            DTObservation(
                sim_time_s=120.0,
                soc_pct=15.0,
                v_bus_v=390.0,
                p_load_w=585.0,
                p_source_w=500.0,
            )
        )
        second = constraints.augment_observation(
            DTObservation(
                sim_time_s=121.0,
                soc_pct=15.0,
                v_bus_v=390.0,
                p_load_w=585.0,
                p_source_w=500.0,
            )
        )

        self.assertAlmostEqual(first.extra["bus_support_integral_w"], 0.0)
        self.assertAlmostEqual(first.extra["bus_support_target_w"], 135.0)
        self.assertAlmostEqual(second.extra["bus_support_integral_error_v"], 10.0)
        self.assertAlmostEqual(second.extra["bus_support_integral_v_s"], 10.0)
        self.assertAlmostEqual(second.extra["bus_support_integral_w"], 10.0)
        self.assertAlmostEqual(second.extra["bus_support_target_w"], 145.0)

    def test_bus_support_integral_leaks_when_bus_recovers(self):
        constraints = CommandConstraintLayer(
            goal=DTGoal(soc_min_pct=40.0, bus_nominal_v=400.0),
            config=RunnerConfig(
                supervisor_period_s=1.0,
                max_p_batt_abs_w=500.0,
                source_power_limit_w=500.0,
                bus_support_gain_w_per_v=5.0,
                bus_support_integral_gain_w_per_v_s=1.0,
                bus_support_integral_max_w=20.0,
                bus_support_integral_leak_per_s=0.5,
                bus_support_integral_deadband_v=0.0,
            ),
        )
        constraints.augment_observation(
            DTObservation(
                sim_time_s=120.0,
                soc_pct=15.0,
                v_bus_v=390.0,
                p_load_w=585.0,
                p_source_w=500.0,
            )
        )
        constraints.augment_observation(
            DTObservation(
                sim_time_s=121.0,
                soc_pct=15.0,
                v_bus_v=390.0,
                p_load_w=585.0,
                p_source_w=500.0,
            )
        )

        recovered = constraints.augment_observation(
            DTObservation(
                sim_time_s=122.0,
                soc_pct=15.0,
                v_bus_v=400.0,
                p_load_w=600.0,
                p_source_w=500.0,
            )
        )

        self.assertFalse(recovered.extra["bus_voltage_support_active"])
        self.assertTrue(recovered.extra["bus_support_integral_context_active"])
        self.assertAlmostEqual(recovered.extra["bus_support_integral_w"], 5.0)
        self.assertAlmostEqual(recovered.extra["bus_support_target_w"], 105.0)

    def test_bus_support_integral_does_not_leak_while_error_persists(self):
        constraints = CommandConstraintLayer(
            goal=DTGoal(soc_min_pct=40.0, bus_nominal_v=400.0),
            config=RunnerConfig(
                supervisor_period_s=1.0,
                max_p_batt_abs_w=500.0,
                source_power_limit_w=500.0,
                bus_support_gain_w_per_v=5.0,
                bus_support_integral_gain_w_per_v_s=1.0,
                bus_support_integral_max_w=20.0,
                bus_support_integral_leak_per_s=0.5,
                bus_support_integral_deadband_v=0.0,
            ),
        )
        for sim_time_s in (120.0, 121.0):
            constraints.augment_observation(
                DTObservation(
                    sim_time_s=sim_time_s,
                    soc_pct=15.0,
                    v_bus_v=390.0,
                    p_load_w=585.0,
                    p_source_w=500.0,
                )
            )

        still_low = constraints.augment_observation(
            DTObservation(
                sim_time_s=122.0,
                soc_pct=15.0,
                v_bus_v=390.0,
                p_load_w=585.0,
                p_source_w=500.0,
            )
        )

        self.assertAlmostEqual(still_low.extra["bus_support_integral_w"], 20.0)
        self.assertAlmostEqual(still_low.extra["bus_support_target_w"], 155.0)

    def test_bus_support_trim_accumulates_slow_support_offset(self):
        constraints = CommandConstraintLayer(
            goal=DTGoal(soc_min_pct=40.0, bus_nominal_v=400.0),
            config=RunnerConfig(
                supervisor_period_s=1.0,
                max_p_batt_abs_w=500.0,
                source_power_limit_w=500.0,
                bus_support_gain_w_per_v=3.0,
                bus_support_trim_gain_w_per_v_s=1.0,
                bus_support_trim_max_w=10.0,
                bus_support_trim_deadband_v=0.0,
            ),
        )
        first = constraints.augment_observation(
            DTObservation(
                sim_time_s=120.0,
                soc_pct=15.0,
                v_bus_v=399.0,
                p_load_w=600.0,
                p_source_w=500.0,
            )
        )
        second = constraints.augment_observation(
            DTObservation(
                sim_time_s=121.0,
                soc_pct=15.0,
                v_bus_v=399.0,
                p_load_w=600.0,
                p_source_w=500.0,
            )
        )

        self.assertAlmostEqual(first.extra["bus_support_trim_w"], 0.0)
        self.assertAlmostEqual(first.extra["bus_support_target_w"], 103.0)
        self.assertAlmostEqual(second.extra["bus_support_trim_error_v"], 1.0)
        self.assertAlmostEqual(second.extra["bus_support_trim_w"], 1.0)
        self.assertAlmostEqual(second.extra["bus_support_target_w"], 104.0)

    def test_bus_support_trim_decays_when_source_has_slack(self):
        constraints = CommandConstraintLayer(
            goal=DTGoal(soc_min_pct=40.0, bus_nominal_v=400.0),
            config=RunnerConfig(
                supervisor_period_s=1.0,
                max_p_batt_abs_w=500.0,
                source_power_limit_w=500.0,
                bus_support_gain_w_per_v=0.0,
                bus_support_trim_gain_w_per_v_s=2.0,
                bus_support_trim_max_w=10.0,
                bus_support_trim_decay_w_per_s=1.0,
                bus_support_trim_deadband_v=0.0,
                bus_support_trim_source_slack_deadband_w=2.0,
            ),
        )
        constraints.augment_observation(
            DTObservation(
                sim_time_s=120.0,
                soc_pct=15.0,
                v_bus_v=399.0,
                p_load_w=600.0,
                p_source_w=500.0,
            )
        )
        accumulated = constraints.augment_observation(
            DTObservation(
                sim_time_s=121.0,
                soc_pct=15.0,
                v_bus_v=399.0,
                p_load_w=600.0,
                p_source_w=500.0,
            )
        )
        recovered_with_slack = constraints.augment_observation(
            DTObservation(
                sim_time_s=122.0,
                soc_pct=15.0,
                v_bus_v=400.0,
                p_load_w=600.0,
                p_source_w=490.0,
            )
        )

        self.assertAlmostEqual(accumulated.extra["bus_support_trim_w"], 2.0)
        self.assertAlmostEqual(
            recovered_with_slack.extra["bus_support_trim_source_slack_w"],
            10.0,
        )
        self.assertAlmostEqual(recovered_with_slack.extra["bus_support_trim_w"], 1.0)
        self.assertAlmostEqual(
            recovered_with_slack.extra["bus_support_target_w"],
            101.0,
        )

    def test_bus_support_target_down_slew_prevents_abrupt_drop(self):
        constraints = CommandConstraintLayer(
            goal=DTGoal(soc_min_pct=40.0, bus_nominal_v=400.0),
            config=RunnerConfig(
                supervisor_period_s=1.0,
                max_p_batt_abs_w=500.0,
                source_power_limit_w=500.0,
                bus_support_gain_w_per_v=0.0,
                bus_support_target_slew_down_w_per_s=2.0,
            ),
        )
        high_target = constraints.augment_observation(
            DTObservation(
                sim_time_s=120.0,
                soc_pct=15.0,
                v_bus_v=400.0,
                p_load_w=610.0,
                p_source_w=500.0,
            )
        )
        lower_target = constraints.augment_observation(
            DTObservation(
                sim_time_s=121.0,
                soc_pct=15.0,
                v_bus_v=400.0,
                p_load_w=600.0,
                p_source_w=500.0,
            )
        )

        self.assertAlmostEqual(high_target.extra["bus_support_target_w"], 110.0)
        self.assertAlmostEqual(
            lower_target.extra["bus_support_target_unslewed_w"],
            100.0,
        )
        self.assertTrue(lower_target.extra["bus_support_target_slew_active"])
        self.assertAlmostEqual(lower_target.extra["bus_support_target_w"], 108.0)

    def test_runner_does_not_source_deficit_cap_when_bus_is_low(self):
        constraints = CommandConstraintLayer(
            goal=DTGoal(soc_min_pct=40.0, bus_nominal_v=400.0),
            config=RunnerConfig(
                max_p_batt_abs_w=500.0,
                max_p_batt_step_w=500.0,
                source_power_limit_w=500.0,
                source_support_entry_margin_w=5.0,
            ),
        )
        observation = constraints.augment_observation(
            DTObservation(
                sim_time_s=102.0,
                soc_pct=15.0,
                v_bus_v=346.0,
                p_load_w=519.0,
                p_source_w=500.0,
            )
        )

        command = constraints.limit(
            DTCommand.discharge(400.0, reason="unit test requested bus support"),
            observation,
        )

        self.assertAlmostEqual(observation.extra["source_deficit_w"], 19.0)
        self.assertGreater(observation.extra["bus_support_target_w"], 250.0)
        self.assertTrue(observation.extra["source_support_needed"])
        self.assertEqual(command.mode, "DISCHARGE")
        self.assertAlmostEqual(command.p_batt_cmd_w, 400.0)
        self.assertNotIn("low-SOC source-support guard capped", command.reason)

    def test_runner_does_not_treat_source_at_limit_as_source_deficit(self):
        backend = MockBatteryBusBackend(
            initial_soc_pct=15.0,
            load_power_w=500.0,
            source_power_limit_w=500.0,
        )
        runner = AutonomousRunner(
            backend=backend,
            goal=DTGoal(soc_min_pct=40.0, success_hold_s=999.0, max_sim_time_s=1.0),
            policy=FixedDischargePolicy(200.0),
            config=RunnerConfig(
                supervisor_period_s=1.0,
                startup_grace_s=0.0,
                max_p_batt_abs_w=500.0,
                max_p_batt_step_w=500.0,
                source_power_limit_w=500.0,
            ),
        )

        result = runner.run()
        observation = result.events[0].observation

        self.assertEqual(result.events[0].command.mode, "HOLD")
        self.assertEqual(result.events[0].command.p_batt_cmd_w, 0.0)
        self.assertEqual(observation.extra["source_deficit_w"], 0.0)
        self.assertFalse(observation.extra["source_support_needed"])
        self.assertIn("blocked discharge", result.events[0].constraint_note())

    def test_source_support_latch_waits_for_clear_deficit_and_recovered_bus(self):
        constraints = CommandConstraintLayer(
            goal=DTGoal(soc_min_pct=40.0, bus_nominal_v=400.0),
            config=RunnerConfig(
                source_power_limit_w=500.0,
                source_support_entry_margin_w=5.0,
                source_support_clear_margin_w=1.0,
                source_support_bus_hysteresis_v=5.0,
                source_support_hold_s=3.0,
            ),
        )

        overload = constraints.augment_observation(
            DTObservation(
                sim_time_s=0.0,
                soc_pct=15.0,
                v_bus_v=400.0,
                p_load_w=600.0,
                p_source_w=500.0,
            )
        )
        low_bus_clear_deficit = constraints.augment_observation(
            DTObservation(
                sim_time_s=1.0,
                soc_pct=15.0,
                v_bus_v=384.0,
                p_load_w=500.0,
                p_source_w=500.0,
            )
        )
        first_recovered = constraints.augment_observation(
            DTObservation(
                sim_time_s=2.0,
                soc_pct=15.0,
                v_bus_v=400.0,
                p_load_w=500.0,
                p_source_w=500.0,
            )
        )
        still_holding = constraints.augment_observation(
            DTObservation(
                sim_time_s=4.0,
                soc_pct=15.0,
                v_bus_v=400.0,
                p_load_w=500.0,
                p_source_w=500.0,
            )
        )
        cleared = constraints.augment_observation(
            DTObservation(
                sim_time_s=5.0,
                soc_pct=15.0,
                v_bus_v=400.0,
                p_load_w=500.0,
                p_source_w=500.0,
            )
        )

        self.assertTrue(overload.extra["source_support_active"])
        self.assertTrue(low_bus_clear_deficit.extra["source_support_active"])
        self.assertTrue(first_recovered.extra["source_support_active"])
        self.assertTrue(still_holding.extra["source_support_active"])
        self.assertFalse(cleared.extra["source_support_active"])

    def test_source_support_latch_blocks_charge_during_recovery(self):
        constraints = CommandConstraintLayer(
            goal=DTGoal(soc_min_pct=40.0, bus_nominal_v=400.0),
            config=RunnerConfig(
                source_power_limit_w=500.0,
                source_support_entry_margin_w=5.0,
                source_support_hold_s=3.0,
            ),
        )
        constraints.augment_observation(
            DTObservation(
                sim_time_s=0.0,
                soc_pct=15.0,
                v_bus_v=400.0,
                p_load_w=600.0,
                p_source_w=500.0,
            )
        )
        recovery_observation = constraints.augment_observation(
            DTObservation(
                sim_time_s=1.0,
                soc_pct=15.0,
                v_bus_v=400.0,
                p_load_w=200.0,
                p_source_w=200.0,
            )
        )

        command = constraints.limit(
            DTCommand.charge(100.0, reason="unit test requested charge"),
            recovery_observation,
        )

        self.assertTrue(recovery_observation.extra["source_support_active"])
        self.assertEqual(command.mode, "HOLD")
        self.assertIn("source-support recovery", command.reason)

    def test_runner_blocks_charge_when_source_has_no_headroom(self):
        backend = MockBatteryBusBackend(
            initial_soc_pct=35.0,
            load_power_w=3000.0,
            source_power_limit_w=3000.0,
        )
        runner = AutonomousRunner(
            backend=backend,
            goal=DTGoal(soc_min_pct=40.0, success_hold_s=999.0, max_sim_time_s=1.0),
            policy=FixedChargePolicy(200.0),
            config=RunnerConfig(
                supervisor_period_s=1.0,
                startup_grace_s=0.0,
                max_p_batt_abs_w=500.0,
                max_p_batt_step_w=500.0,
                charge_power_margin_w=25.0,
            ),
        )

        result = runner.run()

        self.assertEqual(result.events[0].command.mode, "HOLD")
        self.assertEqual(result.events[0].command.p_batt_cmd_w, 0.0)
        self.assertEqual(result.events[0].observation.max_safe_charge_w, 0.0)
        self.assertIn("no source headroom", result.events[0].command.reason)

    def test_runner_derates_charge_to_available_source_headroom(self):
        backend = MockBatteryBusBackend(
            initial_soc_pct=35.0,
            load_power_w=2900.0,
            source_power_limit_w=3000.0,
        )
        runner = AutonomousRunner(
            backend=backend,
            goal=DTGoal(soc_min_pct=40.0, success_hold_s=999.0, max_sim_time_s=1.0),
            policy=FixedChargePolicy(500.0),
            config=RunnerConfig(
                supervisor_period_s=1.0,
                startup_grace_s=0.0,
                max_p_batt_abs_w=500.0,
                max_p_batt_step_w=500.0,
                charge_power_margin_w=25.0,
            ),
        )

        result = runner.run()

        self.assertEqual(result.events[0].command.mode, "CHARGE")
        self.assertAlmostEqual(result.events[0].command.p_batt_cmd_w, -75.0)
        self.assertAlmostEqual(result.events[0].observation.max_safe_charge_w, 75.0)
        self.assertIn("charge headroom guard capped", result.events[0].command.reason)

    def test_charge_headroom_ignores_headroom_created_by_battery_discharge(self):
        constraints = CommandConstraintLayer(
            goal=DTGoal(bus_nominal_v=400.0),
            config=RunnerConfig(
                max_p_batt_abs_w=500.0,
                max_p_batt_step_w=500.0,
                source_power_limit_w=3000.0,
                charge_power_margin_w=25.0,
            ),
        )
        observation = constraints.augment_observation(
            DTObservation(
                sim_time_s=10.0,
                soc_pct=35.0,
                v_bus_v=400.0,
                p_batt_w=500.0,
                p_load_w=3000.0,
                p_source_w=2500.0,
                source_at_limit=False,
            )
        )

        command = constraints.limit(
            DTCommand.charge(100.0, reason="unit test requested charge"),
            observation,
        )

        self.assertEqual(observation.max_safe_charge_w, 0.0)
        self.assertEqual(command.mode, "HOLD")
        self.assertEqual(command.p_batt_cmd_w, 0.0)
        self.assertIn("no source headroom", command.reason)

    def test_post_discharge_support_hold_blocks_immediate_charge_restart(self):
        constraints = CommandConstraintLayer(
            goal=DTGoal(bus_nominal_v=400.0),
            config=RunnerConfig(
                max_p_batt_abs_w=500.0,
                max_p_batt_step_w=500.0,
                source_power_limit_w=3000.0,
                charge_power_margin_w=25.0,
                post_discharge_charge_hold_s=10.0,
            ),
        )
        support_observation = constraints.augment_observation(
            DTObservation(
                sim_time_s=0.0,
                soc_pct=35.0,
                v_bus_v=379.0,
                p_batt_w=0.0,
                p_load_w=3100.0,
                p_source_w=3000.0,
                source_at_limit=True,
            )
        )
        charge_observation = constraints.augment_observation(
            DTObservation(
                sim_time_s=5.0,
                soc_pct=35.0,
                v_bus_v=400.0,
                p_batt_w=0.0,
                p_load_w=2800.0,
                p_source_w=2800.0,
                source_at_limit=False,
            )
        )

        support_command = constraints.limit(
            DTCommand.discharge(200.0, reason="unit test requested support"),
            support_observation,
        )
        charge_command = constraints.limit(
            DTCommand.charge(100.0, reason="unit test requested charge"),
            charge_observation,
        )

        self.assertEqual(support_command.mode, "DISCHARGE")
        self.assertEqual(charge_observation.max_safe_charge_w, 175.0)
        self.assertEqual(charge_command.mode, "HOLD")
        self.assertEqual(charge_command.p_batt_cmd_w, 0.0)
        self.assertIn("battery discharged", charge_command.reason)

    def test_charge_recovery_hold_prevents_immediate_restart_after_bus_sag(self):
        constraints = CommandConstraintLayer(
            goal=DTGoal(bus_nominal_v=400.0),
            config=RunnerConfig(
                max_p_batt_abs_w=500.0,
                max_p_batt_step_w=500.0,
                source_power_limit_w=3000.0,
                charge_power_margin_w=25.0,
                charge_bus_hysteresis_v=5.0,
                charge_recovery_hold_s=10.0,
            ),
        )
        initial_observation = constraints.augment_observation(
            DTObservation(
                sim_time_s=0.0,
                soc_pct=35.0,
                v_bus_v=400.0,
                p_batt_w=0.0,
                p_load_w=2500.0,
                p_source_w=2500.0,
            )
        )
        low_bus_observation = constraints.augment_observation(
            DTObservation(
                sim_time_s=5.0,
                soc_pct=35.0,
                v_bus_v=379.0,
                p_batt_w=-100.0,
                p_load_w=3000.0,
                p_source_w=3000.0,
                source_at_limit=True,
            )
        )
        cooldown_observation = constraints.augment_observation(
            DTObservation(
                sim_time_s=10.0,
                soc_pct=35.0,
                v_bus_v=400.0,
                p_batt_w=0.0,
                p_load_w=2500.0,
                p_source_w=2500.0,
            )
        )

        initial_command = constraints.limit(
            DTCommand.charge(100.0, reason="unit test requested charge"),
            initial_observation,
        )
        blocked_command = constraints.limit(
            DTCommand.charge(100.0, reason="unit test requested charge"),
            low_bus_observation,
        )
        cooldown_command = constraints.limit(
            DTCommand.charge(100.0, reason="unit test requested charge"),
            cooldown_observation,
        )

        self.assertEqual(initial_command.mode, "CHARGE")
        self.assertAlmostEqual(initial_command.p_batt_cmd_w, -100.0)
        self.assertEqual(blocked_command.mode, "HOLD")
        self.assertIn("bus voltage is below", blocked_command.reason)
        self.assertEqual(cooldown_command.mode, "HOLD")
        self.assertIn("charge recovery hold active", cooldown_command.reason)

    def test_simulink_backend_uses_matlab_bridge_contract(self):
        fake_engine = FakeMatlabEngine()
        backend = SimulinkBackend(
            model_name="DT_enviroment",
            model_path="DT_enviroment.slx",
            matlab_engine=fake_engine,
        )

        initial = backend.reset()
        backend.apply_command(DTCommand.discharge(125.0, reason="unit test"))
        stepped = backend.advance(5.0)
        backend.close()

        self.assertEqual(initial.soc_pct, 55.0)
        self.assertEqual(stepped.sim_time_s, 5.0)
        self.assertEqual(fake_engine.commands[-1][0], 125.0)
        self.assertEqual(fake_engine.commands[-1][1], 1.0)
        self.assertEqual(fake_engine.commands[-1][2], "DISCHARGE")
        self.assertTrue(fake_engine.closed)

    def test_llm_policy_converts_model_json_to_command(self):
        client = FakeLLMClient(
            content=json.dumps(
                {
                    "mode": "CHARGE",
                    "p_batt_cmd_w": 100.0,
                    "reason": "SOC below target and source has spare capacity",
                }
            )
        )
        policy = LLMControlPolicy(client=client, model="unit-test-model")
        observation = MockBatteryBusBackend(initial_soc_pct=35.0).reset()

        command = policy.choose_action(observation, DTGoal(soc_min_pct=40.0))

        self.assertEqual(command.mode, "CHARGE")
        self.assertLess(command.p_batt_cmd_w, 0.0)
        self.assertIn("SOC below target", command.reason)
        self.assertEqual(policy.attempted_calls, 1)
        self.assertEqual(policy.successful_calls, 1)
        self.assertEqual(policy.fallback_calls, 0)

    def test_llm_policy_falls_back_to_heuristic_on_error(self):
        client = FakeLLMClient(error=RuntimeError("model unavailable"))
        policy = LLMControlPolicy(client=client, model="unit-test-model")
        observation = MockBatteryBusBackend(initial_soc_pct=35.0).reset()

        command = policy.choose_action(observation, DTGoal(soc_min_pct=40.0))

        self.assertEqual(command.mode, "CHARGE")
        self.assertIn("LLM policy fallback", command.reason)
        self.assertEqual(policy.attempted_calls, 1)
        self.assertEqual(policy.successful_calls, 0)
        self.assertEqual(policy.fallback_calls, 1)

    def test_llm_policy_rejects_prompt_echo_and_falls_back(self):
        client = FakeLLMClient(
            content=json.dumps(
                {
                    "goal": {"soc_min_pct": 40.0},
                    "observation": {"soc_pct": 35.0},
                    "required_response_schema": {
                        "mode": "CHARGE | HOLD | DISCHARGE | SAFE",
                        "p_batt_cmd_w": "number in watts",
                    },
                }
            )
        )
        policy = LLMControlPolicy(client=client, model="unit-test-model")
        observation = MockBatteryBusBackend(initial_soc_pct=35.0).reset()

        command = policy.choose_action(observation, DTGoal(soc_min_pct=40.0))

        self.assertEqual(command.mode, "CHARGE")
        self.assertIn("echoed the prompt", command.reason)
        self.assertEqual(policy.attempted_calls, 1)
        self.assertEqual(policy.successful_calls, 0)
        self.assertEqual(policy.fallback_calls, 1)

    def test_llm_policy_research_mode_allows_model_mode_without_rule_gate(self):
        client = FakeLLMClient(
            content=json.dumps(
                {
                    "mode": "CHARGE",
                    "p_batt_cmd_w": 1500.0,
                    "reason": "model wants to charge",
                }
            )
        )
        policy = LLMControlPolicy(client=client, model="unit-test-model")
        observation = MockBatteryBusBackend(initial_soc_pct=55.0).reset()

        command = policy.choose_action(observation, DTGoal())

        self.assertEqual(command.mode, "CHARGE")
        self.assertEqual(command.p_batt_cmd_w, -1500.0)
        self.assertEqual(policy.successful_calls, 1)
        self.assertEqual(policy.fallback_calls, 0)

    def test_llm_mode_gate_falls_back_when_hold_ignores_low_soc_recovery(self):
        client = FakeLLMClient(
            content=json.dumps(
                {
                    "mode": "HOLD",
                    "p_batt_cmd_w": 0.0,
                    "reason": "short",
                }
            )
        )
        policy = LLMControlPolicy(client=client, model="unit-test-model", mode_gate=True)
        observation = MockBatteryBusBackend(initial_soc_pct=35.0).reset()

        command = policy.choose_action(observation, DTGoal(soc_min_pct=40.0))

        self.assertEqual(command.mode, "CHARGE")
        self.assertIn("LLM selected HOLD while deterministic policy selected CHARGE", command.reason)
        self.assertEqual(policy.attempted_calls, 1)
        self.assertEqual(policy.successful_calls, 0)
        self.assertEqual(policy.fallback_calls, 1)

    def test_llm_mode_gate_falls_back_when_action_is_unneeded_inside_goal_band(self):
        client = FakeLLMClient(
            content=json.dumps(
                {
                    "mode": "CHARGE",
                    "p_batt_cmd_w": 1500.0,
                    "reason": "short",
                }
            )
        )
        policy = LLMControlPolicy(client=client, model="unit-test-model", mode_gate=True)
        observation = MockBatteryBusBackend(initial_soc_pct=55.0).reset()

        command = policy.choose_action(observation, DTGoal())

        self.assertEqual(command.mode, "HOLD")
        self.assertEqual(command.p_batt_cmd_w, 0.0)
        self.assertIn("unnecessary action", command.reason)
        self.assertEqual(policy.successful_calls, 0)
        self.assertEqual(policy.fallback_calls, 1)

    def test_llm_mode_gate_falls_back_when_hold_ignores_source_overload(self):
        client = FakeLLMClient(
            content=json.dumps(
                {
                    "mode": "HOLD",
                    "p_batt_cmd_w": 0.0,
                    "reason": "short",
                }
            )
        )
        policy = LLMControlPolicy(client=client, model="unit-test-model", mode_gate=True)
        observation = DTObservation(
            sim_time_s=100.0,
            soc_pct=15.0,
            v_bus_v=400.0,
            p_batt_w=0.0,
            p_load_w=-900.0,
            p_source_w=500.0,
            max_safe_discharge_w=475.0,
            source_at_limit=True,
            source_available=True,
        )

        command = policy.choose_action(observation, DTGoal(soc_min_pct=40.0))

        self.assertEqual(command.mode, "DISCHARGE")
        self.assertAlmostEqual(command.p_batt_cmd_w, 400.0)
        self.assertIn("deterministic policy selected DISCHARGE", command.reason)
        self.assertEqual(policy.successful_calls, 0)
        self.assertEqual(policy.fallback_calls, 1)

    def test_llm_policy_writes_trace_log(self):
        client = FakeLLMClient(
            content=json.dumps(
                {
                    "mode": "HOLD",
                    "p_batt_cmd_w": 0.0,
                    "reason": "system is already inside the goal band",
                }
            )
        )
        observation = MockBatteryBusBackend(initial_soc_pct=55.0).reset()

        with TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "llm_trace.jsonl"
            policy = LLMControlPolicy(
                client=client,
                model="unit-test-model",
                trace_path=trace_path,
            )
            command = policy.choose_action(observation, DTGoal())
            records = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(command.mode, "HOLD")
        self.assertEqual([record["event"] for record in records], ["request", "response"])
        self.assertEqual(records[0]["model"], "unit-test-model")
        self.assertIn("load_consumption_w", records[0]["messages"][1]["content"])
        self.assertIn("source_deficit_w", records[0]["messages"][1]["content"])
        self.assertIn("source_support_needed", records[0]["messages"][1]["content"])
        self.assertIn("bus_support_target_w", records[0]["messages"][1]["content"])
        self.assertIn("bus_support_integral_w", records[0]["messages"][1]["content"])
        self.assertIn("bus_support_trim_w", records[0]["messages"][1]["content"])
        self.assertIn(
            "bus_support_target_unslewed_w",
            records[0]["messages"][1]["content"],
        )
        self.assertIn("Current applicable example", records[0]["messages"][1]["content"])
        self.assertIn("normal_hold=true ->", records[0]["messages"][1]["content"])
        self.assertNotIn("bus_support_target_w=300", records[0]["messages"][1]["content"])
        self.assertIn("bus_voltage_support_active", records[0]["messages"][1]["content"])
        self.assertIn("Return only the JSON decision object", records[0]["messages"][1]["content"])
        self.assertEqual(client.chat.completions.calls[0]["max_tokens"], 120)

    def test_llm_policy_safety_recovery_prompt_returns_command(self):
        client = FakeLLMClient(
            content=json.dumps(
                {
                    "mode": "DISCHARGE",
                    "p_batt_cmd_w": 150.0,
                    "reason": "bus hard-low but battery has discharge headroom",
                }
            )
        )
        observation = DTObservation(
            sim_time_s=10.0,
            soc_pct=55.0,
            v_bus_v=300.0,
            p_load_w=300.0,
            p_source_w=250.0,
            max_safe_discharge_w=250.0,
        )

        with TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "llm_trace.jsonl"
            policy = LLMControlPolicy(
                client=client,
                model="unit-test-model",
                trace_path=trace_path,
            )
            command = policy.choose_safety_recovery_action(
                observation,
                DTGoal(bus_nominal_v=400.0),
                "bus voltage 300.00 V at/under hard minimum 320.00 V",
                attempt_index=1,
                max_attempts=2,
                recent_events=[],
            )
            records = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(command.mode, "DISCHARGE")
        self.assertEqual(command.p_batt_cmd_w, 150.0)
        self.assertEqual(policy.safety_recovery_attempted_calls, 1)
        self.assertEqual(policy.safety_recovery_successful_calls, 1)
        self.assertEqual([record["event"] for record in records], ["safety_recovery_request", "safety_recovery_response"])
        self.assertIn("Safety recovery context", records[0]["messages"][1]["content"])
        self.assertIn("safety_reason=bus voltage", records[0]["messages"][1]["content"])

    def test_llm_policy_uses_live_bus_support_example_when_bus_is_low(self):
        client = FakeLLMClient(
            content=json.dumps(
                {
                    "mode": "HOLD",
                    "p_batt_cmd_w": 0.0,
                    "reason": "unit test response ignored",
                }
            )
        )
        observation = DTObservation(
            sim_time_s=125.0,
            soc_pct=15.0,
            v_bus_v=333.333333,
            p_batt_w=0.0,
            p_load_w=-500.0,
            p_source_w=500.0,
            max_safe_charge_w=0.0,
            max_safe_discharge_w=500.0,
            source_at_limit=True,
            source_available=False,
            source_can_sink_power=False,
            source_power_limit_w=500.0,
            extra={
                "bus_support_target_w": 333.333333,
                "bus_voltage_support_active": True,
                "source_support_needed": False,
                "source_support_active": True,
                "source_support_target_w": 0.0,
            },
        )

        with TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "llm_trace.jsonl"
            policy = LLMControlPolicy(
                client=client,
                model="unit-test-model",
                trace_path=trace_path,
            )
            policy.choose_action(observation, DTGoal())
            records = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
            ]

        prompt = records[0]["messages"][1]["content"]
        self.assertIn("bus_support_needed=true, bus_support_target_w=333.333", prompt)
        self.assertIn('"mode":"DISCHARGE"', prompt)
        self.assertIn('"p_batt_cmd_w":333.333', prompt)
        self.assertIn("Do not answer HOLD while bus_support_needed=true", prompt)
        self.assertNotIn("normal_hold=true ->", prompt)
        self.assertNotIn("bus_support_target_w=300", prompt)

    def test_startup_grace_holds_instead_of_safety_stopping(self):
        backend = MockBatteryBusBackend(initial_soc_pct=55.0, bus_nominal_v=100.0)
        runner = AutonomousRunner(
            backend=backend,
            goal=DTGoal(
                bus_nominal_v=400.0,
                success_hold_s=10.0,
                max_sim_time_s=5.0,
            ),
            config=RunnerConfig(supervisor_period_s=1.0, startup_grace_s=2.0),
        )

        result = runner.run()

        self.assertEqual(result.events[0].status, MissionStatus.RUNNING)
        self.assertEqual(result.events[0].command.mode, "HOLD")
        self.assertIn("startup grace", result.events[0].command.reason)

    def test_runner_emits_running_checkpoints_before_terminal_result(self):
        checkpoints = []
        backend = MockBatteryBusBackend(initial_soc_pct=55.0)
        runner = AutonomousRunner(
            backend=backend,
            goal=DTGoal(success_hold_s=999.0, max_sim_time_s=2.0),
            config=RunnerConfig(supervisor_period_s=1.0, startup_grace_s=0.0),
            on_checkpoint=checkpoints.append,
        )

        result = runner.run()

        self.assertEqual(result.status, MissionStatus.TIMED_OUT)
        self.assertGreaterEqual(len(checkpoints), 2)
        self.assertEqual(checkpoints[0].status, MissionStatus.RUNNING)
        self.assertEqual(checkpoints[0].final_observation.sim_time_s, 0.0)
        self.assertEqual(checkpoints[-1].status, MissionStatus.TIMED_OUT)
        self.assertEqual(checkpoints[-1].final_observation.sim_time_s, 2.0)

    def test_mission_report_is_written(self):
        backend = MockBatteryBusBackend(initial_soc_pct=55.0)
        goal = DTGoal(success_hold_s=5.0, max_sim_time_s=10.0)
        runner = AutonomousRunner(
            backend=backend,
            goal=goal,
            config=RunnerConfig(supervisor_period_s=5.0, startup_grace_s=0.0),
        )
        result = runner.run()

        with TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "mission_report.md"
            write_mission_report(result, goal, report_path)
            content = report_path.read_text(encoding="utf-8")

        self.assertIn("# Autonomous DT Mission Report", content)
        self.assertIn("## Decision timeline", content)
        self.assertIn("Policy/LLM Mode", content)
        self.assertIn("Applied Mode", content)
        self.assertIn("Python adjustment", content)
        self.assertIn("Bus support target", content)
        self.assertIn("Recent bus voltage ripple", content)


if __name__ == "__main__":
    unittest.main()
