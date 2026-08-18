from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

from Modules.Ingestion.analyzer import DocumentAnalyzer
from Modules.Ingestion.capabilities import RuntimeCapabilitiesProbe
from Modules.Ingestion.docling_ingester import DocumentIngestor, PdfPipelineConfig, ParsedDocument
from Modules.Ingestion.selector import ParseStrategySelector
from Modules.Ingestion.types import DocumentProfile, ParsePlan, RuntimeCapabilities


class SmartDocumentIngestor:
    def __init__(
        self,
        *,
        analyzer: DocumentAnalyzer | None = None,
        selector: ParseStrategySelector | None = None,
        capabilities_probe: RuntimeCapabilitiesProbe | None = None,
        text_ingester: DocumentIngestor | None = None,
        docling_light_ingester: DocumentIngestor | None = None,
        docling_full_ingester: DocumentIngestor | None = None,
    ) -> None:
        self.analyzer = analyzer or DocumentAnalyzer()
        self.selector = selector or ParseStrategySelector()
        self.capabilities_probe = capabilities_probe or RuntimeCapabilitiesProbe()
        self.text_ingester = text_ingester or DocumentIngestor()
        self.docling_light_ingester = docling_light_ingester or DocumentIngestor(
            pdf_config=PdfPipelineConfig(
                do_ocr=False,
                force_full_page_ocr=False,
                do_table_structure=False,
                images_scale=1.0,
                layout_batch_size=1,
                ocr_batch_size=1,
                table_batch_size=1,
            )
        )
        self.docling_full_ingester = docling_full_ingester or DocumentIngestor(
            pdf_config=PdfPipelineConfig(
                do_ocr=True,
                force_full_page_ocr=True,
                do_table_structure=True,
                images_scale=1.0,
                layout_batch_size=1,
                ocr_batch_size=1,
                table_batch_size=1,
            )
        )

    def parse_file(
        self,
        file_path: str | Path,
        *,
        source: Optional[str] = None,
        document_id: Optional[str] = None,
    ) -> ParsedDocument:
        path = Path(file_path).expanduser()
        capabilities = self.capabilities_probe.detect()
        profile = self.analyzer.analyze(path)
        plan = self.selector.select(profile, capabilities)

        errors: List[str] = []
        attempted_modes = [plan.primary_mode, *plan.fallback_order]
        used_mode = plan.primary_mode

        for index, mode in enumerate(attempted_modes):
            try:
                parsed_document = self._parse_with_mode(
                    mode=mode,
                    file_path=path,
                    source=source,
                    document_id=document_id,
                )
                used_mode = mode
                fallback_used = index > 0
                return self._annotate_result(
                    parsed_document=parsed_document,
                    plan=plan,
                    profile=profile,
                    capabilities=capabilities,
                    selected_mode=used_mode,
                    fallback_used=fallback_used,
                    errors=errors,
                )
            except Exception as exc:
                errors.append(f"{mode}: {exc}")

        raise RuntimeError(
            "Unable to parse the document with the selected ingest plan. "
            + " | ".join(errors)
        )

    def _parse_with_mode(
        self,
        *,
        mode: str,
        file_path: Path,
        source: Optional[str],
        document_id: Optional[str],
    ) -> ParsedDocument:
        if mode == "text_only":
            return self.text_ingester.parse_file_as_text(
                file_path=file_path,
                source=source,
                document_id=document_id,
            )
        if mode == "docling_light":
            return self.docling_light_ingester.parse_file_with_docling(
                file_path=file_path,
                source=source,
                document_id=document_id,
            )
        if mode == "docling_full":
            return self.docling_full_ingester.parse_file_with_docling(
                file_path=file_path,
                source=source,
                document_id=document_id,
            )
        raise ValueError(f"Unknown ingest mode: {mode}")

    def _annotate_result(
        self,
        *,
        parsed_document: ParsedDocument,
        plan: ParsePlan,
        profile: DocumentProfile,
        capabilities: RuntimeCapabilities,
        selected_mode: str,
        fallback_used: bool,
        errors: List[str],
    ) -> ParsedDocument:
        parsed_document.strategy_name = plan.strategy_name
        parsed_document.selected_mode = selected_mode
        parsed_document.selection_reason = plan.reason
        parsed_document.fallback_used = fallback_used
        parsed_document.analysis = asdict(profile)
        parsed_document.capabilities = asdict(capabilities)
        parsed_document.warnings = [warning.message for warning in plan.warnings]
        parsed_document.attempted_modes = [plan.primary_mode, *plan.fallback_order]
        parsed_document.mode_errors = errors

        for chunk in parsed_document.chunks:
            chunk.metadata["strategy"] = plan.strategy_name
            chunk.metadata["selectedMode"] = selected_mode
            chunk.metadata["selectionReason"] = plan.reason
            chunk.metadata["fallbackUsed"] = fallback_used
            chunk.metadata["memoryRisk"] = profile.memory_risk
            chunk.metadata["textPageRatio"] = profile.text_page_ratio
            chunk.metadata["ocrCandidateRatio"] = profile.ocr_candidate_ratio

        return parsed_document
