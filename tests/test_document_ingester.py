import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from Modules.Ingestion.docling_ingester import DocumentIngestor


class FakePdfDocumentIngestor(DocumentIngestor):
    def _convert_pdf_to_markdown(self, path: Path):
        markdown = (
            "<!-- PAGE 1 -->\n"
            "# Overview\n\n"
            "The first page introduces the system.\n\n"
            "<!-- PAGE 2 -->\n"
            "## Details\n\n"
            "The second page explains the model."
        )
        return markdown, 2


class DocumentIngestorTests(unittest.TestCase):
    def test_parse_text_file_returns_single_chunk_with_metadata(self):
        ingester = DocumentIngestor()

        with TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "notes.txt"
            file_path.write_text("simple text entry", encoding="utf-8")

            result = ingester.parse_file(
                file_path=file_path,
                source="manual",
                document_id="doc-1",
            )

        self.assertEqual(result.parser_name, "text")
        self.assertEqual(result.page_count, None)
        self.assertEqual(len(result.chunks), 1)
        self.assertEqual(result.chunks[0].chunk_id, "doc-1:chunk:0000")
        self.assertEqual(result.chunks[0].metadata["source"], "manual")
        self.assertEqual(result.chunks[0].metadata["docName"], "notes")
        self.assertEqual(result.chunks[0].metadata["chunkCount"], 1)

    def test_parse_markdown_tracks_header_metadata(self):
        ingester = DocumentIngestor()

        with TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "paper.md"
            file_path.write_text(
                "# Summary\n\nThis section should retain its heading metadata.",
                encoding="utf-8",
            )

            result = ingester.parse_file(
                file_path=file_path,
                document_id="paper-1",
            )

        self.assertEqual(result.parser_name, "markdown_text")
        self.assertEqual(len(result.chunks), 1)
        self.assertIn("Summary", result.chunks[0].metadata["headers"])

    def test_parse_pdf_uses_page_markers_for_metadata(self):
        ingester = FakePdfDocumentIngestor()

        with TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "sample.pdf"
            file_path.write_bytes(b"%PDF-1.4\n")

            result = ingester.parse_file(
                file_path=file_path,
                document_id="pdf-1",
            )

        self.assertEqual(result.parser_name, "docling_pdf")
        self.assertEqual(result.page_count, 2)
        self.assertGreaterEqual(len(result.chunks), 2)
        page_starts = {chunk.metadata.get("pageStart") for chunk in result.chunks}
        self.assertIn(1, page_starts)
        self.assertIn(2, page_starts)


if __name__ == "__main__":
    unittest.main()
