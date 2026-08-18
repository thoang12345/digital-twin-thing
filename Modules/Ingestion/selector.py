from __future__ import annotations

from Modules.Ingestion.types import DocumentProfile, ParsePlan, ParseWarning, RuntimeCapabilities


class ParseStrategySelector:
    def select(
        self,
        profile: DocumentProfile,
        capabilities: RuntimeCapabilities,
    ) -> ParsePlan:
        if profile.file_type != "pdf":
            return ParsePlan(
                strategy_name="text_only",
                primary_mode="text_only",
                fallback_order=[],
                reason="Non-PDF documents use the lightweight text-oriented ingest path.",
            )

        docling_ready = (
            capabilities.docling_import_available
            and capabilities.local_docling_model_cache_available
        )
        warnings = []

        if not capabilities.pdf_text_extractor_available and not capabilities.docling_import_available:
            warnings.append(
                ParseWarning(
                    code="no_pdf_parser",
                    message="No local PDF text extractor or Docling import was detected.",
                )
            )

        if profile.text_page_ratio >= 0.85 and profile.ocr_candidate_ratio <= 0.10:
            return ParsePlan(
                strategy_name="text_only",
                primary_mode="text_only",
                fallback_order=self._fallbacks_for_text(docling_ready, profile.memory_risk),
                reason="The PDF looks born-digital with strong extractable text across most pages.",
                warnings=warnings,
            )

        if profile.mixed_content:
            primary_mode = "text_only"
            fallback_order = []
            docling_profile = None
            reason = "The PDF mixes strong text pages with OCR-like pages, so a conservative hybrid plan is safer."

            if docling_ready and profile.memory_risk != "high":
                primary_mode = "docling_light"
                fallback_order = ["text_only"]
                docling_profile = "light"
                reason = "The PDF mixes clean text and OCR-like pages, so a light Docling pass with text fallback is the best balance."
            elif not docling_ready:
                warnings.append(
                    ParseWarning(
                        code="docling_cache_unconfirmed",
                        message="Local Docling model cache was not confirmed, so hybrid routing is falling back to text mode.",
                    )
                )

            return ParsePlan(
                strategy_name="hybrid",
                primary_mode=primary_mode,
                fallback_order=fallback_order,
                reason=reason,
                docling_profile=docling_profile,
                warnings=warnings,
            )

        if (
            profile.ocr_candidate_ratio >= 0.60
            and docling_ready
            and profile.memory_risk != "high"
        ):
            return ParsePlan(
                strategy_name="docling_full",
                primary_mode="docling_full",
                fallback_order=["docling_light", "text_only"],
                reason="Most pages appear OCR-dependent, so the full Docling pipeline is justified.",
                docling_profile="full",
                warnings=warnings,
            )

        if (
            profile.text_page_ratio >= 0.70
            and profile.ocr_candidate_ratio <= 0.20
            and docling_ready
            and profile.memory_risk != "high"
        ):
            return ParsePlan(
                strategy_name="docling_light",
                primary_mode="docling_light",
                fallback_order=["text_only"],
                reason="The PDF has strong extractable text and low OCR pressure, so a light Docling pass should preserve structure without heavy OCR.",
                docling_profile="light",
                warnings=warnings,
            )

        if not docling_ready:
            warnings.append(
                ParseWarning(
                    code="docling_cache_unconfirmed",
                    message="Local Docling model cache was not confirmed, so the selector is defaulting to text mode.",
                )
            )
            return ParsePlan(
                strategy_name="text_only",
                primary_mode="text_only",
                fallback_order=[],
                reason="Docling is not confidently available locally, so the selector is using the safe text path.",
                warnings=warnings,
            )

        primary_mode = "docling_light"
        fallback_order = ["text_only"]
        docling_profile = "light"
        reason = "The PDF may benefit from structural parsing, but the selector is keeping the Docling profile light."

        if profile.memory_risk == "high":
            primary_mode = "text_only"
            fallback_order = ["docling_light"]
            docling_profile = None
            reason = "The document looks expensive to parse, so text mode is the safer first pass."

        return ParsePlan(
            strategy_name="docling_light" if primary_mode == "docling_light" else "text_only",
            primary_mode=primary_mode,
            fallback_order=fallback_order,
            reason=reason,
            docling_profile=docling_profile,
            warnings=warnings,
        )

    @staticmethod
    def _fallbacks_for_text(docling_ready: bool, memory_risk: str) -> list[str]:
        if docling_ready and memory_risk == "low":
            return ["docling_light"]
        return []
