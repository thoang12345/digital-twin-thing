import unittest

from Modules.Digital_Twins.gui_events import (
    DT_GUI_EVENT_PREFIX,
    build_dt_gui_event,
    format_dt_gui_event,
    local_state_name,
    parse_dt_gui_event,
)
from Modules.Digital_Twins.types import (
    DTCommand,
    DTObservation,
    MissionStatus,
    RunnerEvent,
    RunnerResult,
)


class DtGuiEventTests(unittest.TestCase):
    def _result(self) -> RunnerResult:
        observation = DTObservation(
            sim_time_s=50.0,
            soc_pct=15.01,
            v_bus_v=399.95,
            p_batt_w=25.0,
            p_load_w=500.0,
            p_source_w=475.0,
            extra={"state_code": 2.0},
        )
        policy_command = DTCommand.discharge(250.0, "LLM requests support")
        guarded_command = DTCommand.hold("discretionary discharge blocked")
        event = RunnerEvent(
            tick_index=5,
            observation=observation,
            command=guarded_command,
            status=MissionStatus.RUNNING,
            policy_command=policy_command,
        )
        return RunnerResult(
            status=MissionStatus.RUNNING,
            reason="mission running",
            events=[event],
            final_observation=observation,
        )

    def test_build_event_keeps_supervisor_guard_and_local_state_separate(self):
        payload = build_dt_gui_event(self._result())

        self.assertEqual(payload["supervisor_request"]["mode"], "DISCHARGE")
        self.assertEqual(payload["supervisor_request"]["p_batt_cmd_w"], 250.0)
        self.assertEqual(payload["guarded_udp_intent"]["mode"], "HOLD")
        self.assertEqual(payload["guarded_udp_intent"]["p_batt_cmd_w"], 0.0)
        self.assertEqual(payload["reported_local_state"], {"code": 2, "name": "BUS_SUPPORT"})
        self.assertEqual(payload["p_batt_measured_w"], 25.0)
        self.assertEqual(payload["python_adjustment"], "discretionary discharge blocked")
        self.assertEqual(payload["request_summary"], "DISCHARGE +250.0 W")
        self.assertEqual(payload["runner_output_summary"], "HOLD +0.0 W")
        self.assertEqual(payload["local_control_summary"], "BUS_SUPPORT [code 2]")
        self.assertEqual(payload["feedback_summary"], "P_batt = +25.0 W")

    def test_format_and_parse_round_trip(self):
        line = format_dt_gui_event(self._result())

        self.assertTrue(line.startswith(DT_GUI_EVENT_PREFIX))
        payload = parse_dt_gui_event(line)
        self.assertEqual(payload["schema"], "dt_gui_event_v1")
        self.assertEqual(payload["tick_index"], 5)
        self.assertEqual(payload["reported_local_state"]["name"], "BUS_SUPPORT")

    def test_parser_ignores_normal_console_output(self):
        self.assertIsNone(parse_dt_gui_event("Mission status: succeeded"))
        self.assertIsNone(parse_dt_gui_event(DT_GUI_EVENT_PREFIX + "not json"))

    def test_local_state_name_handles_missing_and_unknown_codes(self):
        self.assertEqual(local_state_name(None), "NOT_REPORTED")
        self.assertEqual(local_state_name(3.0), "SAFE_LOCAL")
        self.assertEqual(local_state_name(7), "UNKNOWN_7")


if __name__ == "__main__":
    unittest.main()
