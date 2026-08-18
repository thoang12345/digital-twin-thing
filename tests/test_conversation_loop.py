import unittest
from types import SimpleNamespace

from Modules.Core.conversationloop import ConversationLoop
from Modules.Core.types import ContextChunk
from Modules.Tools.Tool_loop import ToolLoopResult


class FakePromptBuilder:
    def build_payload(self, user_query, rag_matches, chat_memory):
        return [
            {"role": "system", "content": "system"},
            {"role": "user", "content": user_query},
        ]


class FakeToolLoopRunner:
    def run(self, initial_messages):
        return ToolLoopResult(
            final_response="done",
            finished=True,
            rounds_used=1,
            messages=initial_messages,
            tool_trace=[],
            error=None,
        )


class FakeChatMemory:
    def __init__(self):
        self.messages = []

    def get_messages(self):
        return list(self.messages)

    def add_user_message(self, content):
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content):
        self.messages.append({"role": "assistant", "content": content})


class FakeRetriever:
    def search(self, query, top_k):
        return SimpleNamespace(
            matches=[
                SimpleNamespace(
                    id="doc-1",
                    content=f"rag for {query}",
                    score=0.9,
                    metadata={"source": "unit-test"},
                )
            ]
        )


class ConversationLoopTests(unittest.TestCase):
    def test_turn_result_contains_rag_matches(self):
        chat_memory = FakeChatMemory()
        loop = ConversationLoop(
            prompt_builder=FakePromptBuilder(),
            tool_loop_runner=FakeToolLoopRunner(),
            chat_memory=chat_memory,
            rag_retriever=FakeRetriever(),
            rag_adapter=lambda result: [
                ContextChunk(
                    content=result.matches[0].content,
                    source=result.matches[0].metadata["source"],
                    score=result.matches[0].score,
                    metadata=result.matches[0].metadata,
                )
            ],
        )

        result = loop.run_turn("hello")

        self.assertEqual(result["final_response"], "done")
        self.assertEqual(len(result["rag_matches"]), 1)
        self.assertEqual(result["rag_matches"][0].source, "unit-test")


if __name__ == "__main__":
    unittest.main()
