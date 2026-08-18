import tkinter as tk
import unittest
from types import SimpleNamespace

from Modules.GUI.app import AssistantGuiApp


class GenericDtGuiTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is unavailable: {exc}")
        self.root.withdraw()
        conversation = SimpleNamespace(
            available_tools=[],
            database_browser=None,
            tool_loop_runner=SimpleNamespace(tools=[]),
        )
        self.app = AssistantGuiApp(self.root, conversation)
        self.root.update_idletasks()

    def tearDown(self):
        if hasattr(self, "root"):
            self.root.destroy()

    def test_defaults_target_current_runner_and_model(self):
        self.assertEqual(self.app.dt_backend_var.get(), "udp")
        self.assertEqual(self.app.dt_policy_var.get(), "llm")
        self.assertTrue(self.app.dt_runner_path_var.get().endswith("run_dt_runner.py"))
        self.assertTrue(
            self.app.dt_model_path_var.get().endswith(
                "DT_enviroment_state_machine_llm_udp.slx"
            )
        )
        self.assertFalse(self.app.dt_llm_strict_var.get())
        model_inputs = self.app.dt_model_inputs_text.get("1.0", "end")
        self.assertIn("--max-p-batt 480", model_inputs)
        self.assertIn("--source-power-limit 500", model_inputs)

        tab_names = [
            self.app.dt_settings_notebook.tab(tab_id, "text")
            for tab_id in self.app.dt_settings_notebook.tabs()
        ]
        self.assertEqual(tab_names, ["Run", "Model Inputs", "Connection", "Agent"])

    def test_gui_command_requests_structured_live_events(self):
        command = self.app._build_dt_command()

        self.assertIn("--emit-gui-events", command)
        self.assertIn("--llm-command-limit", command)
        self.assertIn("--source-power-limit", command)

    def test_model_specific_arguments_are_appended_without_gui_interpretation(self):
        self.app.dt_model_inputs_text.delete("1.0", "end")
        self.app.dt_model_inputs_text.insert(
            "1.0",
            "# custom model\n--plant-gain 2.5\n--scenario \"high load\"",
        )

        command = self.app._build_dt_command()

        self.assertEqual(command[-4:], ["--plant-gain", "2.5", "--scenario", "high load"])

    def test_live_event_uses_generic_control_path_summaries(self):
        self.app._handle_dt_live_event(
            {
                "request_summary": "OPEN valve to 30%",
                "runner_output_summary": "OPEN limited to 20%",
                "local_control_summary": "PRESSURE_REGULATION",
                "feedback_summary": "Flow = 4.2 L/s",
                "telemetry_summary": "t=50 s  pressure=200 kPa",
                "interface_note": "rate limit applied",
            }
        )

        self.assertEqual(self.app.dt_supervisor_request_var.get(), "OPEN valve to 30%")
        self.assertEqual(self.app.dt_guarded_intent_var.get(), "OPEN limited to 20%")
        self.assertEqual(self.app.dt_local_state_var.get(), "PRESSURE_REGULATION")
        self.assertEqual(self.app.dt_measured_power_var.get(), "Flow = 4.2 L/s")
        self.assertIn("pressure=200 kPa", self.app.dt_telemetry_var.get())
        self.assertIn("rate limit applied", self.app.dt_adjustment_var.get())


if __name__ == "__main__":
    unittest.main()
