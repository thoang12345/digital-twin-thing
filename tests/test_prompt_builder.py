import unittest

from Modules.Core.types import ContextChunk
from Modules.Prompt.prompt import PromptBuilder


class PromptBuilderTests(unittest.TestCase):
    def test_payload_uses_system_memory_and_user_message(self):
        builder = PromptBuilder(max_memory_messages=2, max_rag_chunks=2)
        rag_matches = [
            ContextChunk(content="Chunk one", source="doc-1", score=0.9),
        ]
        chat_memory = [
            {"role": "user", "content": "older user"},
            {"role": "assistant", "content": "older assistant"},
        ]

        messages = builder.build_payload(
            user_query="What is the status?",
            rag_matches=rag_matches,
            chat_memory=chat_memory,
        )

        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["content"], "older user")
        self.assertEqual(messages[2]["content"], "older assistant")
        self.assertEqual(messages[3]["role"], "user")
        self.assertIn("What is the status?", messages[3]["content"])
        self.assertIn("Chunk one", messages[3]["content"])


if __name__ == "__main__":
    unittest.main()
