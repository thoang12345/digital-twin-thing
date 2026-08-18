from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from Modules.RAG.query_expansion import IntentAwareQueryExpander
from Modules.RAG.reranker import HeuristicSearchReranker


@dataclass(slots=True)
class SearchPipelineResult:
    query: str
    intent: str
    expanded_queries: List[str] = field(default_factory=list)
    matches: List[Dict[str, Any]] = field(default_factory=list)


class IntentAwareSearchPipeline:
    def __init__(
        self,
        *,
        expander: IntentAwareQueryExpander | None = None,
        reranker: HeuristicSearchReranker | None = None,
        candidate_multiplier: int = 2,
        min_candidates: int = 6,
    ) -> None:
        self.expander = expander or IntentAwareQueryExpander()
        self.reranker = reranker or HeuristicSearchReranker()
        self.candidate_multiplier = candidate_multiplier
        self.min_candidates = min_candidates

    def search(
        self,
        collection,
        *,
        query: str,
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> SearchPipelineResult:
        expansion = self.expander.expand(query)
        candidate_limit = max(top_k * self.candidate_multiplier, self.min_candidates)
        merged_matches: Dict[str, Dict[str, Any]] = {}

        for variant in expansion.variants:
            raw_results = collection.query(
                query_texts=[variant.text],
                n_results=candidate_limit,
                where=where,
                include=["documents", "metadatas", "distances"],
            )

            ids = raw_results.get("ids", [[]])[0]
            documents = raw_results.get("documents", [[]])[0]
            metadatas = raw_results.get("metadatas", [[]])[0]
            distances = raw_results.get("distances", [[]])[0]

            for doc_id, document, metadata, distance in zip(
                ids,
                documents,
                metadatas,
                distances,
            ):
                base_score = self._distance_to_score(distance)
                weighted_score = (base_score or 0.0) * variant.weight
                entry = merged_matches.setdefault(
                    doc_id,
                    {
                        "id": doc_id,
                        "content": document,
                        "metadata": metadata or {},
                        "distance": distance,
                        "score": base_score,
                        "_aggregate_score": weighted_score,
                        "_matched_variants": [variant.text],
                    },
                )

                if weighted_score > entry.get("_aggregate_score", 0.0):
                    entry["content"] = document
                    entry["metadata"] = metadata or {}
                    entry["distance"] = distance
                    entry["score"] = base_score
                    entry["_aggregate_score"] = weighted_score

                if variant.text not in entry["_matched_variants"]:
                    entry["_matched_variants"].append(variant.text)

        reranked_matches = self.reranker.rerank(
            query=query,
            expansion=expansion,
            candidates=list(merged_matches.values()),
        )

        final_matches: List[Dict[str, Any]] = []
        for match in reranked_matches[:top_k]:
            metadata = dict(match.get("metadata") or {})
            metadata["retrievalIntent"] = expansion.intent
            metadata["matchedVariants"] = match.pop("_matched_variants", [])
            metadata["baseScore"] = match.pop("_base_score", match.get("score"))
            metadata["rerankNotes"] = match.pop("_rerank_notes", [])

            final_matches.append(
                {
                    "id": match["id"],
                    "content": match["content"],
                    "metadata": metadata,
                    "distance": match["distance"],
                    "score": match.pop("_rerank_score", match.get("score")),
                }
            )

        return SearchPipelineResult(
            query=query,
            intent=expansion.intent,
            expanded_queries=[variant.text for variant in expansion.variants],
            matches=final_matches,
        )

    @staticmethod
    def _distance_to_score(distance: Optional[float]) -> Optional[float]:
        if distance is None:
            return None
        return 1 / (1 + distance)
