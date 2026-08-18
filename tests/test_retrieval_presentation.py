import unittest
from types import SimpleNamespace

from Modules.adapters.retrieval_presentation import (
    build_context_chunk_detail_payload,
    build_search_match_detail_payload,
    present_retrieval_content,
    render_detail_text,
)


class RetrievalPresentationTests(unittest.TestCase):
    def test_presentation_removes_probable_page_header_and_merges_lines(self):
        raw_content = (
            "Systems 2026, 14, 48 16 of 23\r\n"
            "further confirms the stability of MoE's performance and underscores its robustness to\r\n"
            "random missingness.\r\n"
            "Table 3. Comparative imputation performance of the baseline and the proposed\r\n"
            "SG-MoE model.\r\n"
        )

        result = present_retrieval_content(raw_content, {"pageCount": 23})

        self.assertNotIn("16 of 23", result.display_content)
        self.assertIn(
            "underscores its robustness to random missingness.",
            result.display_content,
        )
        self.assertIn(
            "baseline and the proposed SG-MoE model.",
            result.display_content,
        )
        self.assertGreaterEqual(len(result.notes), 1)

    def test_presentation_keeps_table_rows_separate(self):
        raw_content = (
            "Scenario Rate MAE RMSE\n"
            "MAR 0.1 6.385 10.507\n"
            "MAR 0.3 6.505 10.652\n"
            "MCAR 0.1 6.070 10.240\n"
        )

        result = present_retrieval_content(raw_content)

        self.assertIn("MAR 0.1 6.385 10.507\nMAR 0.3 6.505 10.652", result.display_content)
        self.assertIn("table-heavy", " ".join(result.notes).lower())

    def test_context_chunk_payload_and_detail_text_use_display_content(self):
        chunk = SimpleNamespace(
            source="doc-a",
            score=0.8,
            content="Systems 2026, 14, 48 16 of 23\nWrapped line\ncontinues here.",
            metadata={"parser": "pypdf_fallback"},
        )

        payload = build_context_chunk_detail_payload(chunk)
        detail_text = render_detail_text(payload)

        self.assertIn("Display Content:", detail_text)
        self.assertIn("Wrapped line continues here.", detail_text)
        self.assertIn("Metadata:", detail_text)
        self.assertIn("parser: pypdf_fallback", detail_text)

    def test_search_match_payload_keeps_raw_content_section_when_changed(self):
        match = {
            "collection_name": "docs",
            "query": "MoE framework",
            "id": "chunk-1",
            "score": 0.5,
            "distance": 1.2,
            "content": "Systems 2026, 14, 48 16 of 23\nBody line one\nline two.",
            "metadata": {"chunkNum": 1},
        }

        payload = build_search_match_detail_payload(match)
        detail_text = render_detail_text(payload)

        self.assertIn("Collection Name: docs", detail_text)
        self.assertIn("Query: MoE framework", detail_text)
        self.assertIn("Raw Content:", detail_text)
        self.assertIn("Body line one line two.", detail_text)


if __name__ == "__main__":
    unittest.main()
