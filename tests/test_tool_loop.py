import unittest
from types import SimpleNamespace

from Modules.Tools.Tool_loop import ToolLoopRunner


class FakeCompletions:
    def __init__(self, messages):
        self._messages = list(messages)

    def create(self, **_kwargs):
        message = self._messages.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    def __init__(self, messages):
        self.chat = SimpleNamespace(completions=FakeCompletions(messages))


class RaisingCompletions:
    def create(self, **_kwargs):
        raise RuntimeError("backend offline")


class RaisingClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=RaisingCompletions())


class ToolLoopRunnerTests(unittest.TestCase):
    def test_finish_tool_completes_the_loop(self):
        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(
                name="finish",
                arguments='{"final_response": "done"}',
            ),
        )
        message = SimpleNamespace(content="", tool_calls=[tool_call])
        runner = ToolLoopRunner(
            client=FakeClient([message]),
            model="fake-model",
            tools=[],
            tool_registry={
                "finish": lambda final_response: {"final_response": final_response}
            },
        )

        result = runner.run([{"role": "system", "content": "hello"}])

        self.assertTrue(result.finished)
        self.assertEqual(result.final_response, "done")
        self.assertEqual(result.tool_trace[0].tool_name, "finish")

    def test_plain_assistant_content_can_return_without_tools(self):
        message = SimpleNamespace(content="plain answer", tool_calls=[])
        runner = ToolLoopRunner(
            client=FakeClient([message]),
            model="fake-model",
            tools=[],
            tool_registry={},
            require_tool_choice=False,
        )

        result = runner.run([{"role": "system", "content": "hello"}])

        self.assertTrue(result.finished)
        self.assertEqual(result.final_response, "plain answer")

    def test_client_failure_returns_a_structured_error(self):
        runner = ToolLoopRunner(
            client=RaisingClient(),
            model="fake-model",
            tools=[],
            tool_registry={},
        )

        result = runner.run([{"role": "system", "content": "hello"}])

        self.assertFalse(result.finished)
        self.assertIn("backend offline", result.error)

    def test_event_callback_receives_tool_events(self):
        recorded_events = []
        tool_call = SimpleNamespace(
            id="call-1",
            function=SimpleNamespace(
                name="finish",
                arguments='{"final_response": "done"}',
            ),
        )
        message = SimpleNamespace(content="", tool_calls=[tool_call])
        runner = ToolLoopRunner(
            client=FakeClient([message]),
            model="fake-model",
            tools=[],
            tool_registry={
                "finish": lambda final_response: {"final_response": final_response}
            },
            event_callback=recorded_events.append,
        )

        result = runner.run([{"role": "system", "content": "hello"}])

        self.assertTrue(result.finished)
        self.assertIn("round_started", [event["type"] for event in recorded_events])
        self.assertIn("tool_finished", [event["type"] for event in recorded_events])


if __name__ == "__main__":
    unittest.main()
