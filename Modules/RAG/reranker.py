from __future__ import annotations

import re
from typing import Any, Dict, List

from Modules.RAG.query_expansion import QueryExpansionResult, normalize_for_matching

_TABLE_METRIC_PATTERN = re.compile(r"\b(mae|rmse|smape|p value|pvalue|mcar|mar|mnar)\b")
_DEFINITION_PHRASES = (
    "is a",
    "is an",
    "refers to",
    "defined as",
    "consists of",
    "core component",
    "set of",
    "gating network",
    "expert models",
)
_FRONT_MATTER_PHRASES = (
    "academic editor",
    "received",
    "revised",
    "accepted",
    "published",
    "copyright",
    "licensee",
    "creative commons attribution",
    "open access article",
)


class HeuristicSearchReranker:
    def rerank(
        self,
        *,
        query: str,
        expansion: QueryExpansionResult,
        candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        reranked: List[Dict[str, Any]] = []
        for candidate in candidates:
            reranked.append(
                self._score_candidate(
                    candidate=candidate,
                    expansion=expansion,
                )
            )

        reranked.sort(
            key=lambda item: (
                item["_rerank_score"],
                item.get("_base_score", item.get("score") or 0.0),
            ),
            reverse=True,
        )
        return reranked

    def _score_candidate(
        self,
        *,
        candidate: Dict[str, Any],
        expansion: QueryExpansionResult,
    ) -> Dict[str, Any]:
        content = candidate.get("content", "")
        metadata = candidate.get("metadata") or {}
        normalized_content = normalize_for_matching(content)
        base_score = candidate.get("_aggregate_score", candidate.get("score") or 0.0)
        rerank_score = base_score
        notes: List[str] = []

        if expansion.alias_terms and any(
            normalize_for_matching(alias) in normalized_content for alias in expansion.alias_terms
        ):
            rerank_score += 0.08
            notes.append("Alias phrase matched content.")

        if expansion.intent == "definition":
            if any(phrase in normalized_content for phrase in _DEFINITION_PHRASES):
                rerank_score += 0.12
                notes.append("Definition-style phrasing detected.")

            chunk_num = metadata.get("chunkNum")
            if isinstance(chunk_num, int):
                if chunk_num <= 5:
                    rerank_score += 0.08
                    notes.append("Early-document chunk boosted for definitional intent.")
                elif chunk_num >= 12:
                    rerank_score -= 0.04
                    notes.append("Later chunk slightly penalized for definitional intent.")

            if self._looks_table_heavy(content):
                rerank_score -= 0.18
                notes.append("Table-heavy chunk penalized for definitional intent.")

            if "figure " in normalized_content:
                rerank_score -= 0.05
                notes.append("Figure-heavy chunk penalized for definitional intent.")

            if any(phrase in normalized_content for phrase in _FRONT_MATTER_PHRASES):
                rerank_score -= 0.14
                notes.append("Front-matter chunk penalized for definitional intent.")

        elif expansion.intent == "performance":
            if self._looks_table_heavy(content):
                rerank_score += 0.06
                notes.append("Table-heavy chunk boosted for performance intent.")

        candidate["_base_score"] = candidate.get("score")
        candidate["_rerank_score"] = max(0.0, min(1.0, rerank_score))
        candidate["_rerank_notes"] = notes
        return candidate

    @staticmethod
    def _looks_table_heavy(content: str) -> bool:
        lowered = normalize_for_matching(content)
        metric_hits = len(_TABLE_METRIC_PATTERN.findall(lowered))
        line_count = len([line for line in content.splitlines() if line.strip()])
        digit_count = sum(char.isdigit() for char in content)
        return metric_hits >= 3 or (digit_count >= 25 and line_count >= 6)
