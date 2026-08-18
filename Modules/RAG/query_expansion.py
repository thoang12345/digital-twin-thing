from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

_WHITESPACE_PATTERN = re.compile(r"\s+")
_NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass(slots=True)
class ExpandedQuery:
    text: str
    weight: float
    reason: str


@dataclass(slots=True)
class QueryExpansionResult:
    original_query: str
    normalized_query: str
    intent: str
    variants: List[ExpandedQuery] = field(default_factory=list)
    alias_terms: List[str] = field(default_factory=list)


class IntentAwareQueryExpander:
    DEFINITION_PATTERNS = (
        r"\bwhat is\b",
        r"\bwhat's\b",
        r"\bdefine\b",
        r"\bdefinition of\b",
        r"\bexplain\b",
        r"\bmeaning of\b",
    )
    COMPARISON_PATTERNS = (
        r"\bcompare\b",
        r"\bdifference\b",
        r"\bversus\b",
        r"\bvs\b",
    )
    PERFORMANCE_PATTERNS = (
        r"\bperformance\b",
        r"\bresults\b",
        r"\baccuracy\b",
        r"\brmse\b",
        r"\bmae\b",
        r"\bsmape\b",
        r"\bp-value\b",
    )

    ABBREVIATIONS = {
        "moe": ["mixture of experts", "mixture-of-experts"],
    }

    def expand(self, query: str) -> QueryExpansionResult:
        normalized_query = self._normalize_query(query)
        intent = self._detect_intent(normalized_query)
        alias_terms = self._expand_alias_terms(normalized_query)

        variants: List[ExpandedQuery] = []
        self._add_variant(variants, normalized_query, 1.0, "original")

        for alias in alias_terms:
            self._add_variant(variants, alias, 0.97, "alias")

        if intent == "definition":
            for alias in alias_terms:
                article = "an" if alias[:1].lower() in {"a", "e", "i", "o", "u"} else "a"
                self._add_variant(
                    variants,
                    f"what is {article} {alias}",
                    1.0,
                    "definition_rewrite",
                )
                self._add_variant(
                    variants,
                    f"definition of {alias}",
                    0.95,
                    "definition_rewrite",
                )
                self._add_variant(
                    variants,
                    f"{alias} model",
                    0.92,
                    "definition_focus",
                )

        if intent == "comparison":
            for alias in alias_terms:
                self._add_variant(
                    variants,
                    f"{alias} comparison",
                    0.93,
                    "comparison_focus",
                )

        if intent == "performance":
            for alias in alias_terms:
                self._add_variant(
                    variants,
                    f"{alias} performance",
                    0.94,
                    "performance_focus",
                )

        return QueryExpansionResult(
            original_query=query,
            normalized_query=normalized_query,
            intent=intent,
            variants=variants,
            alias_terms=alias_terms,
        )

    def _detect_intent(self, query: str) -> str:
        lowered = query.lower()
        if any(re.search(pattern, lowered) for pattern in self.DEFINITION_PATTERNS):
            return "definition"
        if any(re.search(pattern, lowered) for pattern in self.COMPARISON_PATTERNS):
            return "comparison"
        if any(re.search(pattern, lowered) for pattern in self.PERFORMANCE_PATTERNS):
            return "performance"
        return "general"

    def _expand_alias_terms(self, query: str) -> List[str]:
        alias_terms: List[str] = []
        for abbreviation, expansions in self.ABBREVIATIONS.items():
            if re.search(rf"\b{re.escape(abbreviation)}\b", query, flags=re.IGNORECASE):
                for expansion in expansions:
                    self._add_alias(alias_terms, expansion)

        normalized_query = normalize_for_matching(query)
        for expansions in self.ABBREVIATIONS.values():
            for expansion in expansions:
                if normalize_for_matching(expansion) in normalized_query:
                    self._add_alias(alias_terms, expansion)

        return alias_terms

    @staticmethod
    def _add_variant(
        variants: List[ExpandedQuery],
        text: str,
        weight: float,
        reason: str,
    ) -> None:
        cleaned = IntentAwareQueryExpander._normalize_query(text)
        if not cleaned:
            return
        if any(existing.text == cleaned for existing in variants):
            return
        variants.append(ExpandedQuery(text=cleaned, weight=weight, reason=reason))

    @staticmethod
    def _add_alias(alias_terms: List[str], alias: str) -> None:
        cleaned = IntentAwareQueryExpander._normalize_query(alias)
        if cleaned and cleaned not in alias_terms:
            alias_terms.append(cleaned)

    @staticmethod
    def _normalize_query(query: str) -> str:
        return _WHITESPACE_PATTERN.sub(" ", query).strip()


def normalize_for_matching(text: str) -> str:
    lowered = text.lower()
    lowered = lowered.replace("’", "'").replace("‘", "'")
    lowered = lowered.replace("–", "-").replace("—", "-")
    lowered = lowered.replace("?", " ")
    lowered = _NON_ALNUM_PATTERN.sub(" ", lowered)
    return _WHITESPACE_PATTERN.sub(" ", lowered).strip()
