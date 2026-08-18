import unittest
from tempfile import TemporaryDirectory

from Modules.Digital_Twins.tool_runner import run_autonomous_DT
from Modules.Tools.dt_state import DTStateManager
from Modules.Tools.tool_catalog import build_default_toolset


class FakeChromaTools:
    def search_DT_info(self, query):
        return {"query": query, "matches": []}

    def find_DT_by_output(self, output_name):
        return {"query": output_name, "matches": []}

    def find_DT_by_input(self, input_name):
        return {"query": input_name, "matches": []}

    def search_long_term_memory(self, query):
        return {"query": query, "matches": []}


class AutonomousDtToolTests(unittest.TestCase):
    def test_run_autonomous_dt_tool_mock_backend(self):
        with TemporaryDirectory() as tmpdir:
            result = run_autonomous_DT(
                backend="mock",
                policy="heuristic",
                max_sim_seconds=5.0,
                tick_seconds=1.0,
                success_hold_seconds=999.0,
                output_dir=tmpdir,
                run_label="unit_test",
            )

        self.assertEqual(result["tool"], "run_autonomous_DT")
        self.assertEqual(result["backend"], "mock")
        self.assertEqual(result["policy"], "heuristic")
        self.assertEqual(result["status"], "timed_out")
        self.assertIsNotNone(result["final_observation"])
        self.assertIn("report", result["artifacts"])
        self.assertGreaterEqual(result["event_count"], 1)

    def test_default_toolset_registers_autonomous_dt_tool(self):
        tools, registry = build_default_toolset(
            DTStateManager(),
            FakeChromaTools(),
        )

        tool_names = [tool["function"]["name"] for tool in tools]

        self.assertIn("run_autonomous_DT", tool_names)
        self.assertIn("run_autonomous_DT", registry)


if __name__ == "__main__":
    unittest.main()
