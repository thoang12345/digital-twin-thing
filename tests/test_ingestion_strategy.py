import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from Modules.Ingestion.analyzer import DocumentAnalyzer
from Modules.Ingestion.docling_ingester import ParsedDocument, ParsedDocumentChunk
from Modules.Ingestion.selector import ParseStrategySelector
from Modules.Ingestion.service import SmartDocumentIngestor
from Modules.Ingestion.types import DocumentProfile, ParsePlan, RuntimeCapabilities


class FakePdfAnalyzer(DocumentAnalyzer):
    def __init__(self, page_texts):
        self.page_texts = page_texts

    def _extract_pdf_page_texts(self, path: Path):
        return list(self.page_texts)


class FakeCapabilitiesProbe:
    def __init__(self, capabilities):
        self.capabilities = capabilities

    def detect(self):
        return self.capabilities


class FakeSelector:
    def __init__(self, plan):
        self.plan = plan

    def select(self, profile, capabilities):
        return self.plan


class FakeTextIngester:
    def parse_file_as_text(self, file_path, source=None, document_id=None):
        return ParsedDocument(
            document_id=document_id or "doc-1",
            source=source or Path(file_path).name,
            file_name=Path(file_path).name,
            file_path=str(file_path),
            parser_name="text_engine",
            content="text result",
            page_count=3,
            chunks=[
                ParsedDocumentChunk(
                    chunk_id=f"{document_id}:chunk:0000",
                    content="text result",
                    metadata={},
                )
            ],
        )


class FakeDoclingIngester:
    def __init__(self, should_fail=False, parser_name="docling_engine"):
        self.should_fail = should_fail
        self.parser_name = parser_name

    def parse_file_with_docling(self, file_path, source=None, document_id=None):
        if self.should_fail:
            raise RuntimeError("docling failed")
        return ParsedDocument(
            document_id=document_id or "doc-1",
            source=source or Path(file_path).name,
            file_name=Path(file_path).name,
            file_path=str(file_path),
            parser_name=self.parser_name,
            content="docling result",
            page_count=3,
            chunks=[
                ParsedDocumentChunk(
                    chunk_id=f"{document_id}:chunk:0000",
                    content="docling result",
                    metadata={},
                )
            ],
        )


def make_capabilities(**overrides):
    base = RuntimeCapabilities(
        docling_import_available=True,
        local_docling_model_cache_available=True,
        pdf_text_extractor_available=True,
        docx_support_available=True,
        tokenizer_fallback_available=True,
        notes=[],
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def make_profile(**overrides):
    base = DocumentProfile(
        file_path="sample.pdf",
        file_type="pdf",
        file_size_mb=2.0,
        page_count=10,
        sampled_page_count=10,
        analyzer_name="test",
        text_page_ratio=0.9,
        ocr_candidate_ratio=0.0,
        table_ratio=0.0,
        born_digital_score=0.95,
        mixed_content=False,
        memory_risk="low",
        page_profiles=[],
        notes=[],
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


class DocumentAnalyzerTests(unittest.TestCase):
    def test_pdf_analyzer_marks_born_digital_document(self):
        analyzer = FakePdfAnalyzer(
            [
                "A" * 900,
                "B" * 850,
                "C" * 920,
            ]
        )

        with TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "sample.pdf"
            file_path.write_bytes(b"%PDF-1.4\n")
            profile = analyzer.analyze(file_path)

        self.assertEqual(profile.page_count, 3)
        self.assertEqual(profile.text_page_ratio, 1.0)
        self.assertEqual(profile.ocr_candidate_ratio, 0.0)
        self.assertEqual(profile.memory_risk, "low")

    def test_pdf_analyzer_marks_mixed_content(self):
        analyzer = FakePdfAnalyzer(
            [
                "A" * 900,
                "",
                "B" * 80,
            ]
        )

        with TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "sample.pdf"
            file_path.write_bytes(b"%PDF-1.4\n")
            profile = analyzer.analyze(file_path)

        self.assertTrue(profile.mixed_content)
        self.assertGreater(profile.ocr_candidate_ratio, 0.0)


class ParseStrategySelectorTests(unittest.TestCase):
    def test_selector_prefers_text_only_for_born_digital_pdf(self):
        selector = ParseStrategySelector()
        plan = selector.select(make_profile(), make_capabilities())

        self.assertEqual(plan.strategy_name, "text_only")
        self.assertEqual(plan.primary_mode, "text_only")

    def test_selector_prefers_docling_full_for_scanned_pdf(self):
        selector = ParseStrategySelector()
        plan = selector.select(
            make_profile(
                text_page_ratio=0.1,
                ocr_candidate_ratio=0.8,
                born_digital_score=0.2,
                mixed_content=False,
            ),
            make_capabilities(),
        )

        self.assertEqual(plan.strategy_name, "docling_full")
        self.assertEqual(plan.primary_mode, "docling_full")

    def test_selector_uses_hybrid_for_mixed_pdf(self):
        selector = ParseStrategySelector()
        plan = selector.select(
            make_profile(
                text_page_ratio=0.6,
                ocr_candidate_ratio=0.3,
                born_digital_score=0.58,
                mixed_content=True,
            ),
            make_capabilities(),
        )

        self.assertEqual(plan.strategy_name, "hybrid")
        self.assertIn(plan.primary_mode, {"docling_light", "text_only"})

    def test_selector_falls_back_to_text_when_docling_cache_missing(self):
        selector = ParseStrategySelector()
        plan = selector.select(
            make_profile(
                text_page_ratio=0.5,
                ocr_candidate_ratio=0.4,
                mixed_content=False,
            ),
            make_capabilities(local_docling_model_cache_available=False),
        )

        self.assertEqual(plan.primary_mode, "text_only")


class SmartDocumentIngestorTests(unittest.TestCase):
    def test_smart_ingester_attaches_strategy_metadata(self):
        plan = ParsePlan(
            strategy_name="text_only",
            primary_mode="text_only",
            fallback_order=[],
            reason="Born-digital PDF detected.",
        )
        ingester = SmartDocumentIngestor(
            analyzer=FakePdfAnalyzer(["A" * 900]),
            selector=FakeSelector(plan),
            capabilities_probe=FakeCapabilitiesProbe(make_capabilities()),
            text_ingester=FakeTextIngester(),
            docling_light_ingester=FakeDoclingIngester(),
            docling_full_ingester=FakeDoclingIngester(),
        )

        with TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "sample.pdf"
            file_path.write_bytes(b"%PDF-1.4\n")
            result = ingester.parse_file(file_path, document_id="pdf-1")

        self.assertEqual(result.strategy_name, "text_only")
        self.assertEqual(result.selected_mode, "text_only")
        self.assertFalse(result.fallback_used)
        self.assertEqual(result.chunks[0].metadata["strategy"], "text_only")

    def test_smart_ingester_uses_fallback_mode_when_primary_fails(self):
        plan = ParsePlan(
            strategy_name="hybrid",
            primary_mode="docling_light",
            fallback_order=["text_only"],
            reason="Mixed-content PDF detected.",
        )
        ingester = SmartDocumentIngestor(
            analyzer=FakePdfAnalyzer(["A" * 900, ""]),
            selector=FakeSelector(plan),
            capabilities_probe=FakeCapabilitiesProbe(make_capabilities()),
            text_ingester=FakeTextIngester(),
            docling_light_ingester=FakeDoclingIngester(should_fail=True),
            docling_full_ingester=FakeDoclingIngester(),
        )

        with TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "sample.pdf"
            file_path.write_bytes(b"%PDF-1.4\n")
            result = ingester.parse_file(file_path, document_id="pdf-2")

        self.assertEqual(result.selected_mode, "text_only")
        self.assertTrue(result.fallback_used)
        self.assertEqual(result.mode_errors, ["docling_light: docling failed"])


if __name__ == "__main__":
    unittest.main()
