import unittest
from types import SimpleNamespace

from Modules.adapters.rag_adapters import search_result_to_context_chunks


class RagAdapterTests(unittest.TestCase):
    def test_adapter_keeps_all_matches(self):
        search_result = SimpleNamespace(
            matches=[
                SimpleNamespace(
                    id="1",
                    content="First chunk",
                    score=0.8,
                    metadata={"source": "doc-a"},
                ),
                SimpleNamespace(
                    id="2",
                    content="Second chunk",
                    score=0.7,
                    metadata={"source": "doc-b"},
                ),
            ]
        )

        chunks = search_result_to_context_chunks(search_result)

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].source, "doc-a")
        self.assertEqual(chunks[1].source, "doc-b")


if __name__ == "__main__":
    unittest.main()
