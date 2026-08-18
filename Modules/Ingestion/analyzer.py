from __future__ import annotations

import re
from pathlib import Path
from typing import List

from Modules.Ingestion.types import DocumentProfile, PageProfile

_WHITESPACE_PATTERN = re.compile(r"\s+")
_DIGIT_PATTERN = re.compile(r"\d")


class DocumentAnalyzer:
    def analyze(self, file_path: str | Path) -> DocumentProfile:
        path = Path(file_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not path.is_file():
            raise ValueError(f"Path is not a file: {path}")

        file_type = path.suffix.lower().lstrip(".") or "unknown"
        file_size_mb = round(path.stat().st_size / (1024 * 1024), 3)

        if file_type == "pdf":
            return self._analyze_pdf(path, file_type=file_type, file_size_mb=file_size_mb)

        notes = ["Non-PDF file: using lightweight text-oriented ingest heuristics."]
        return DocumentProfile(
            file_path=str(path),
            file_type=file_type,
            file_size_mb=file_size_mb,
            page_count=None,
            sampled_page_count=0,
            analyzer_name="document_analyzer",
            text_page_ratio=1.0,
            ocr_candidate_ratio=0.0,
            table_ratio=0.0,
            born_digital_score=1.0,
            mixed_content=False,
            memory_risk="low",
            notes=notes,
        )

    def _analyze_pdf(
        self,
        path: Path,
        *,
        file_type: str,
        file_size_mb: float,
    ) -> DocumentProfile:
        page_texts = self._extract_pdf_page_texts(path)
        page_profiles: List[PageProfile] = []
        strong_text_pages = 0
        ocr_candidate_pages = 0
        table_candidate_pages = 0

        for page_number, raw_text in enumerate(page_texts, start=1):
            normalized_text = self._normalize_text(raw_text)
            char_count = len(normalized_text)
            word_count = len(normalized_text.split()) if normalized_text else 0
            likely_scanned = char_count < 80
            table_candidate = self._looks_table_like(raw_text)
            image_heavy = char_count < 40
            parse_confidence = min(1.0, char_count / 800) if char_count else 0.0
            text_density = round(char_count / max(word_count, 1), 3) if char_count else 0.0

            if char_count >= 600:
                strong_text_pages += 1
            if likely_scanned:
                ocr_candidate_pages += 1
            if table_candidate:
                table_candidate_pages += 1

            page_profiles.append(
                PageProfile(
                    page_number=page_number,
                    extractable_text_chars=char_count,
                    word_count=word_count,
                    text_density=text_density,
                    likely_scanned=likely_scanned,
                    table_candidate=table_candidate,
                    image_heavy=image_heavy,
                    parse_confidence=round(parse_confidence, 3),
                )
            )

        page_count = len(page_profiles)
        text_page_ratio = round(strong_text_pages / page_count, 3) if page_count else 0.0
        ocr_candidate_ratio = round(ocr_candidate_pages / page_count, 3) if page_count else 0.0
        table_ratio = round(table_candidate_pages / page_count, 3) if page_count else 0.0
        born_digital_score = round(
            max(0.0, (text_page_ratio * 0.8) + ((1 - ocr_candidate_ratio) * 0.2)),
            3,
        )
        mixed_content = strong_text_pages > 0 and ocr_candidate_pages > 0
        memory_risk = self._estimate_memory_risk(page_count=page_count, file_size_mb=file_size_mb)

        notes = []
        if mixed_content:
            notes.append("Mixed-content PDF detected: some pages have strong text while others look OCR-dependent.")
        if table_ratio >= 0.3:
            notes.append("A notable share of pages appear table-heavy.")
        if ocr_candidate_ratio == 0.0:
            notes.append("All sampled pages have extractable text.")

        return DocumentProfile(
            file_path=str(path),
            file_type=file_type,
            file_size_mb=file_size_mb,
            page_count=page_count,
            sampled_page_count=page_count,
            analyzer_name="document_analyzer",
            text_page_ratio=text_page_ratio,
            ocr_candidate_ratio=ocr_candidate_ratio,
            table_ratio=table_ratio,
            born_digital_score=born_digital_score,
            mixed_content=mixed_content,
            memory_risk=memory_risk,
            page_profiles=page_profiles,
            notes=notes,
        )

    def _extract_pdf_page_texts(self, path: Path) -> List[str]:
        try:
            import pypdfium2 as pdfium
        except ImportError as exc:
            raise RuntimeError(
                "Document analysis for PDFs requires pypdfium2 in the environment."
            ) from exc

        pdf = pdfium.PdfDocument(str(path))
        page_texts = []
        for page_index in range(len(pdf)):
            text_page = pdf[page_index].get_textpage()
            page_texts.append(text_page.get_text_range() or "")
        return page_texts

    @staticmethod
    def _normalize_text(text: str) -> str:
        return _WHITESPACE_PATTERN.sub(" ", text).strip()

    @staticmethod
    def _looks_table_like(text: str) -> bool:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) < 4:
            return False

        digit_lines = sum(1 for line in lines if _DIGIT_PATTERN.search(line))
        spaced_lines = sum(1 for line in lines if "  " in line or "\t" in line)
        short_lines = sum(1 for line in lines if len(line.split()) <= 6)

        return (
            digit_lines / len(lines) >= 0.35
            and (spaced_lines / len(lines) >= 0.15 or short_lines / len(lines) >= 0.5)
        )

    @staticmethod
    def _estimate_memory_risk(*, page_count: int, file_size_mb: float) -> str:
        if page_count > 40 or file_size_mb > 20:
            return "high"
        if page_count > 20 or file_size_mb > 10:
            return "medium"
        return "low"
