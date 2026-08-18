from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_PAGE_HEADER_PATTERN = re.compile(
    r"^[A-Z][A-Za-z0-9 .,&\-]{1,80}\b\d{4},\s*\d+,\s*\d+\s+\d+\s+of\s+\d+$"
)
_TABLE_SCENARIO_PATTERN = re.compile(r"^(MAR|MCAR|MNAR)\b")
_WHITESPACE_PATTERN = re.compile(r"[ \t]+")


@dataclass(slots=True)
class PresentationContent:
    raw_content: str
    display_content: str
    preview: str
    notes: List[str] = field(default_factory=list)


def present_retrieval_content(
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
    *,
    preview_length: int = 100,
) -> PresentationContent:
    metadata = metadata or {}
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    notes: List[str] = []

    lines = normalized.split("\n")
    lines, removed_headers = _remove_probable_headers_and_footers(lines)
    if removed_headers:
        notes.append("Removed probable page headers or footers from the display view.")

    display_content = _render_lines_for_display(lines)
    if display_content != normalized.strip():
        notes.append("Merged wrapped lines to improve readability.")

    if _looks_table_heavy(display_content):
        notes.append("This chunk appears table-heavy and may still look flattened in text mode.")

    preview = _build_preview(display_content, preview_length)
    return PresentationContent(
        raw_content=normalized,
        display_content=display_content,
        preview=preview,
        notes=notes,
    )


def build_context_chunk_detail_payload(chunk) -> Dict[str, Any]:
    presentation = present_retrieval_content(
        chunk.content,
        getattr(chunk, "metadata", None),
    )
    return {
        "source": getattr(chunk, "source", "Unknown source"),
        "score": getattr(chunk, "score", None),
        "display_content": presentation.display_content,
        "raw_content": presentation.raw_content,
        "presentation_notes": presentation.notes,
        "metadata": getattr(chunk, "metadata", {}),
    }


def build_search_match_detail_payload(match: Dict[str, Any]) -> Dict[str, Any]:
    presentation = present_retrieval_content(
        match.get("content", ""),
        match.get("metadata", {}),
    )
    return {
        "collection_name": match.get("collection_name"),
        "query": match.get("query"),
        "id": match.get("id"),
        "score": match.get("score"),
        "distance": match.get("distance"),
        "display_content": presentation.display_content,
        "raw_content": presentation.raw_content,
        "presentation_notes": presentation.notes,
        "metadata": match.get("metadata", {}),
    }


def render_detail_text(payload: Dict[str, Any]) -> str:
    lines: List[str] = []

    for label in ("source", "collection_name", "query", "id", "score", "distance"):
        value = payload.get(label)
        if value is None or value == "":
            continue
        pretty_label = label.replace("_", " ").title()
        lines.append(f"{pretty_label}: {value}")

    notes = payload.get("presentation_notes", [])
    if notes:
        lines.append("")
        lines.append("Presentation Notes:")
        for note in notes:
            lines.append(f"- {note}")

    display_content = payload.get("display_content", "").strip()
    if display_content:
        lines.append("")
        lines.append("Display Content:")
        lines.append(display_content)

    metadata = payload.get("metadata")
    if metadata:
        lines.append("")
        lines.append("Metadata:")
        lines.append(_format_metadata(metadata))

    raw_content = payload.get("raw_content", "").strip()
    if raw_content and raw_content != display_content:
        lines.append("")
        lines.append("Raw Content:")
        lines.append(raw_content)

    return "\n".join(lines).strip()


def _remove_probable_headers_and_footers(lines: List[str]) -> tuple[List[str], bool]:
    filtered_lines = []
    removed_any = False
    for line in lines:
        stripped = line.strip()
        if stripped and _PAGE_HEADER_PATTERN.match(stripped):
            removed_any = True
            continue
        filtered_lines.append(line)
    return filtered_lines, removed_any


def _render_lines_for_display(lines: List[str]) -> str:
    rendered_lines: List[str] = []
    for raw_line in lines:
        line = _WHITESPACE_PATTERN.sub(" ", raw_line).strip()
        if not line:
            if rendered_lines and rendered_lines[-1] != "":
                rendered_lines.append("")
            continue

        if not rendered_lines:
            rendered_lines.append(line)
            continue

        previous_line = rendered_lines[-1]
        if previous_line == "":
            rendered_lines.append(line)
            continue

        if _should_join_lines(previous_line, line):
            separator = "" if previous_line.endswith("-") else " "
            if previous_line.endswith("-"):
                previous_line = previous_line[:-1]
            rendered_lines[-1] = previous_line + separator + line
        else:
            rendered_lines.append(line)

    return "\n".join(rendered_lines).strip()


def _should_join_lines(previous_line: str, current_line: str) -> bool:
    if _is_probable_table_line(previous_line) or _is_probable_table_line(current_line):
        return False
    if current_line.startswith("("):
        return True
    if previous_line.endswith((".", "!", "?", ":", ";")):
        return False
    return True


def _is_probable_table_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("Table ") or stripped.startswith("Figure "):
        return False
    if _TABLE_SCENARIO_PATTERN.match(stripped):
        return True
    digit_count = sum(1 for char in stripped if char.isdigit())
    token_count = len(stripped.split())
    return digit_count >= 6 and token_count >= 4


def _looks_table_heavy(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    table_lines = sum(1 for line in lines if _is_probable_table_line(line))
    return table_lines >= max(3, len(lines) // 3)


def _build_preview(text: str, preview_length: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= preview_length:
        return normalized
    return normalized[: preview_length - 3].rstrip() + "..."


def _format_metadata(metadata: Dict[str, Any]) -> str:
    lines = []
    for key in sorted(metadata):
        lines.append(f"{key}: {metadata[key]}")
    return "\n".join(lines)
