from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(slots=True)
class ParseWarning:
    code: str
    message: str


@dataclass(slots=True)
class PageProfile:
    page_number: int
    extractable_text_chars: int
    word_count: int
    text_density: float
    likely_scanned: bool
    table_candidate: bool
    image_heavy: bool
    parse_confidence: float


@dataclass(slots=True)
class DocumentProfile:
    file_path: str
    file_type: str
    file_size_mb: float
    page_count: Optional[int]
    sampled_page_count: int
    analyzer_name: str
    text_page_ratio: float
    ocr_candidate_ratio: float
    table_ratio: float
    born_digital_score: float
    mixed_content: bool
    memory_risk: str
    page_profiles: List[PageProfile] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass(slots=True)
class RuntimeCapabilities:
    docling_import_available: bool
    local_docling_model_cache_available: bool
    pdf_text_extractor_available: bool
    docx_support_available: bool
    tokenizer_fallback_available: bool
    notes: List[str] = field(default_factory=list)


@dataclass(slots=True)
class ParsePlan:
    strategy_name: str
    primary_mode: str
    fallback_order: List[str]
    reason: str
    docling_profile: Optional[str] = None
    warnings: List[ParseWarning] = field(default_factory=list)
