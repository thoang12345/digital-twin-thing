from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb

from Modules.Ingestion.service import SmartDocumentIngestor
from Modules.adapters.retrieval_presentation import present_retrieval_content


@dataclass(slots=True)
class BenchmarkDocumentSpec:
    id: str
    type: str
    text: Optional[str] = None
    path: Optional[str] = None
    source: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BenchmarkExpectation:
    acceptable_ids: List[str] = field(default_factory=list)
    acceptable_doc_names: List[str] = field(default_factory=list)
    acceptable_chunk_nums: List[int] = field(default_factory=list)
    required_phrases: List[str] = field(default_factory=list)
    any_phrases: List[str] = field(default_factory=list)


@dataclass(slots=True)
class BenchmarkCase:
    id: str
    query: str
    top_k: int = 5
    description: str = ""
    category: str = "general"
    expectation: BenchmarkExpectation = field(default_factory=BenchmarkExpectation)


@dataclass(slots=True)
class BenchmarkSuite:
    name: str
    collection_name: str
    documents: List[BenchmarkDocumentSpec] = field(default_factory=list)
    cases: List[BenchmarkCase] = field(default_factory=list)


@dataclass(slots=True)
class BenchmarkRetrievedMatch:
    rank: int
    id: Optional[str]
    score: Optional[float]
    distance: Optional[float]
    is_relevant: bool
    display_content: str
    raw_content: str
    presentation_notes: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BenchmarkCaseResult:
    id: str
    query: str
    category: str
    description: str
    top_k: int
    matched: bool
    first_relevant_rank: Optional[int]
    reciprocal_rank: float
    top_match_id: Optional[str]
    relevant_match_id: Optional[str]
    intent: Optional[str]
    expanded_queries: List[str] = field(default_factory=list)
    retrieved_matches: List[BenchmarkRetrievedMatch] = field(default_factory=list)


@dataclass(slots=True)
class BenchmarkReport:
    suite_name: str
    collection_name: str
    total_cases: int
    hit_at_1: float
    hit_at_3: float
    hit_at_5: float
    mrr: float
    case_results: List[BenchmarkCaseResult] = field(default_factory=list)


@dataclass(slots=True)
class BenchmarkCategorySummary:
    category: str
    total_cases: int
    hit_at_1: float
    hit_at_3: float
    hit_at_5: float
    mrr: float


class BenchmarkCorpusBuilder:
    def __init__(
        self,
        *,
        persist_directory: str,
        collection_name: str,
        document_ingester: SmartDocumentIngestor | None = None,
    ) -> None:
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.document_ingester = document_ingester or SmartDocumentIngestor()
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def build(self, suite: BenchmarkSuite, base_path: Path) -> None:
        for document in suite.documents:
            if document.type == "text":
                self._add_text_document(document)
                continue
            if document.type == "file":
                self._add_file_document(document, base_path=base_path)
                continue
            raise ValueError(f"Unsupported benchmark document type: {document.type}")

    def _add_text_document(self, document: BenchmarkDocumentSpec) -> None:
        text = (document.text or "").strip()
        if not text:
            raise ValueError(f"Benchmark text document '{document.id}' is empty.")
        metadata = {
            "source": document.source or document.id,
            "docName": document.metadata.get("docName", document.id),
            "documentName": document.metadata.get("documentName", document.id),
            "benchmarkDocument": True,
            **document.metadata,
        }
        self.collection.upsert(
            ids=[document.id],
            documents=[text],
            metadatas=[metadata],
        )

    def _add_file_document(self, document: BenchmarkDocumentSpec, *, base_path: Path) -> None:
        if not document.path:
            raise ValueError(f"Benchmark file document '{document.id}' is missing a path.")
        resolved_path = resolve_relative_path(base_path, document.path)
        parsed_document = self.document_ingester.parse_file(
            file_path=resolved_path,
            source=document.source or document.path,
            document_id=document.id,
        )
        for chunk in parsed_document.chunks:
            chunk.metadata["benchmarkDocument"] = True
            chunk.metadata["benchmarkDocumentId"] = document.id
            chunk.metadata.update(document.metadata)
        self.collection.upsert(
            ids=[chunk.chunk_id for chunk in parsed_document.chunks],
            documents=[chunk.content for chunk in parsed_document.chunks],
            metadatas=[chunk.metadata for chunk in parsed_document.chunks],
        )


class RetrievalBenchmarkRunner:
    def run_suite(
        self,
        *,
        suite: BenchmarkSuite,
        search_client,
    ) -> BenchmarkReport:
        case_results: List[BenchmarkCaseResult] = []

        for case in suite.cases:
            result = search_client.query_collection(
                suite.collection_name,
                case.query,
                top_k=case.top_k,
            )
            retrieved_matches: List[BenchmarkRetrievedMatch] = []
            first_rank = None
            relevant_match_id = None
            for index, match in enumerate(result.get("matches", []), start=1):
                is_relevant = self._is_relevant_match(match, case.expectation)
                presentation = present_retrieval_content(
                    match.get("content", ""),
                    match.get("metadata", {}),
                )
                retrieved_matches.append(
                    BenchmarkRetrievedMatch(
                        rank=index,
                        id=match.get("id"),
                        score=match.get("score"),
                        distance=match.get("distance"),
                        is_relevant=is_relevant,
                        display_content=presentation.display_content,
                        raw_content=presentation.raw_content,
                        presentation_notes=presentation.notes,
                        metadata=match.get("metadata", {}),
                    )
                )
                if is_relevant and first_rank is None:
                    first_rank = index
                    relevant_match_id = match.get("id")

            matched = first_rank is not None
            reciprocal_rank = 0.0 if first_rank is None else 1.0 / first_rank
            top_match_id = result.get("matches", [{}])[0].get("id") if result.get("matches") else None

            case_results.append(
                BenchmarkCaseResult(
                    id=case.id,
                    query=case.query,
                    category=case.category,
                    description=case.description,
                    top_k=case.top_k,
                    matched=matched,
                    first_relevant_rank=first_rank,
                    reciprocal_rank=reciprocal_rank,
                    top_match_id=top_match_id,
                    relevant_match_id=relevant_match_id,
                    intent=result.get("intent"),
                    expanded_queries=result.get("expanded_queries", []),
                    retrieved_matches=retrieved_matches,
                )
            )

        total_cases = len(case_results)
        hit_at_1 = self._compute_hit_at_k(case_results, 1)
        hit_at_3 = self._compute_hit_at_k(case_results, 3)
        hit_at_5 = self._compute_hit_at_k(case_results, 5)
        mrr = 0.0 if not total_cases else sum(item.reciprocal_rank for item in case_results) / total_cases

        return BenchmarkReport(
            suite_name=suite.name,
            collection_name=suite.collection_name,
            total_cases=total_cases,
            hit_at_1=hit_at_1,
            hit_at_3=hit_at_3,
            hit_at_5=hit_at_5,
            mrr=mrr,
            case_results=case_results,
        )

    def summarize_by_category(
        self,
        report: BenchmarkReport,
    ) -> List[BenchmarkCategorySummary]:
        grouped: Dict[str, List[BenchmarkCaseResult]] = {}
        for item in report.case_results:
            grouped.setdefault(item.category, []).append(item)

        summaries = []
        for category, items in sorted(grouped.items()):
            total_cases = len(items)
            hit_at_1 = self._compute_hit_at_k(items, 1)
            hit_at_3 = self._compute_hit_at_k(items, 3)
            hit_at_5 = self._compute_hit_at_k(items, 5)
            mrr = 0.0 if not total_cases else sum(item.reciprocal_rank for item in items) / total_cases
            summaries.append(
                BenchmarkCategorySummary(
                    category=category,
                    total_cases=total_cases,
                    hit_at_1=hit_at_1,
                    hit_at_3=hit_at_3,
                    hit_at_5=hit_at_5,
                    mrr=mrr,
                )
            )
        return summaries

    def _is_relevant_match(
        self,
        match: Dict[str, Any],
        expectation: BenchmarkExpectation,
    ) -> bool:
        metadata = match.get("metadata") or {}
        content = normalize_text(match.get("content", ""))
        doc_name = str(
            metadata.get("docName")
            or metadata.get("documentName")
            or metadata.get("benchmarkDocumentId")
            or ""
        )
        chunk_num = metadata.get("chunkNum")

        if expectation.acceptable_ids and match.get("id") not in expectation.acceptable_ids:
            return False
        if expectation.acceptable_doc_names and doc_name not in expectation.acceptable_doc_names:
            return False
        if expectation.acceptable_chunk_nums and chunk_num not in expectation.acceptable_chunk_nums:
            return False
        if expectation.required_phrases:
            if not all(normalize_text(phrase) in content for phrase in expectation.required_phrases):
                return False
        if expectation.any_phrases:
            if not any(normalize_text(phrase) in content for phrase in expectation.any_phrases):
                return False
        return True

    @staticmethod
    def _compute_hit_at_k(case_results: List[BenchmarkCaseResult], k: int) -> float:
        if not case_results:
            return 0.0
        hits = sum(
            1
            for item in case_results
            if item.first_relevant_rank is not None and item.first_relevant_rank <= k
        )
        return hits / len(case_results)


def load_benchmark_suite(path: str | Path) -> BenchmarkSuite:
    suite_path = Path(path)
    payload = json.loads(suite_path.read_text(encoding="utf-8"))

    documents = [
        BenchmarkDocumentSpec(
            id=document["id"],
            type=document["type"],
            text=document.get("text"),
            path=document.get("path"),
            source=document.get("source"),
            metadata=document.get("metadata", {}),
        )
        for document in payload.get("documents", [])
    ]

    cases = []
    for case in payload.get("cases", []):
        expectation_payload = case.get("expect", {})
        cases.append(
            BenchmarkCase(
                id=case["id"],
                query=case["query"],
                top_k=case.get("top_k", 5),
                description=case.get("description", ""),
                category=case.get("category", "general"),
                expectation=BenchmarkExpectation(
                    acceptable_ids=expectation_payload.get("acceptable_ids", []),
                    acceptable_doc_names=expectation_payload.get("acceptable_doc_names", []),
                    acceptable_chunk_nums=expectation_payload.get("acceptable_chunk_nums", []),
                    required_phrases=expectation_payload.get("required_phrases", []),
                    any_phrases=expectation_payload.get("any_phrases", []),
                ),
            )
        )

    return BenchmarkSuite(
        name=payload["name"],
        collection_name=payload["collection_name"],
        documents=documents,
        cases=cases,
    )


def format_benchmark_report(report: BenchmarkReport) -> str:
    runner = RetrievalBenchmarkRunner()
    category_summaries = runner.summarize_by_category(report)
    hit_1_count = sum(
        1
        for item in report.case_results
        if item.first_relevant_rank is not None and item.first_relevant_rank <= 1
    )
    hit_3_count = sum(
        1
        for item in report.case_results
        if item.first_relevant_rank is not None and item.first_relevant_rank <= 3
    )
    hit_5_count = sum(
        1
        for item in report.case_results
        if item.first_relevant_rank is not None and item.first_relevant_rank <= 5
    )
    lines = [
        f"Suite: {report.suite_name}",
        f"Collection: {report.collection_name}",
        f"Total Cases: {report.total_cases}",
        f"Hit@1: {report.hit_at_1:.3f} ({hit_1_count}/{report.total_cases})",
        "  Meaning: how often the first result was relevant.",
        f"Hit@3: {report.hit_at_3:.3f} ({hit_3_count}/{report.total_cases})",
        "  Meaning: how often at least one relevant result appeared in the top 3.",
        f"Hit@5: {report.hit_at_5:.3f} ({hit_5_count}/{report.total_cases})",
        "  Meaning: how often at least one relevant result appeared in the top 5.",
        f"MRR: {report.mrr:.3f}",
        "  Meaning: average reward for ranking relevant results earlier.",
        "",
        "Category Summary:",
    ]
    for summary in category_summaries:
        lines.append(
            f"- {summary.category}: cases={summary.total_cases} "
            f"Hit@1={summary.hit_at_1:.3f} Hit@3={summary.hit_at_3:.3f} "
            f"Hit@5={summary.hit_at_5:.3f} MRR={summary.mrr:.3f}"
        )
    lines.extend(
        [
            "",
        "Case Results:",
        ]
    )
    for item in report.case_results:
        status = "PASS" if item.matched else "FAIL"
        lines.append(
            f"- [{status}] {item.id} ({item.category}) rank={item.first_relevant_rank} "
            f"top_match={item.top_match_id} relevant_match={item.relevant_match_id} intent={item.intent}"
        )
        lines.append(f"  Query: {item.query}")
        if item.description:
            lines.append(f"  Goal: {item.description}")
    return "\n".join(lines)


def format_benchmark_detailed_report(report: BenchmarkReport) -> str:
    lines = [
        format_benchmark_report(report),
        "",
        "Retrieved Matches By Case:",
    ]

    for item in report.case_results:
        status = "PASS" if item.matched else "FAIL"
        lines.extend(
            [
                "",
                f"=== {item.id} [{status}] ===",
                f"Category: {item.category}",
                f"Query: {item.query}",
                f"Goal: {item.description or 'No description provided.'}",
                f"Intent: {item.intent or 'unknown'}",
                f"First Relevant Rank: {item.first_relevant_rank}",
                f"Expanded Queries: {', '.join(item.expanded_queries) if item.expanded_queries else '(none)'}",
                f"Retrieved Matches: {len(item.retrieved_matches)}",
            ]
        )

        if not item.retrieved_matches:
            lines.append("No matches were returned for this query.")
            continue

        for match in item.retrieved_matches:
            metadata = match.metadata or {}
            doc_name = (
                metadata.get("docName")
                or metadata.get("documentName")
                or metadata.get("benchmarkDocumentId")
                or "unknown"
            )
            lines.extend(
                [
                    "",
                    f"--- Rank {match.rank} ---",
                    f"Relevant: {'yes' if match.is_relevant else 'no'}",
                    f"Match ID: {match.id}",
                    f"Document: {doc_name}",
                    f"Chunk Num: {metadata.get('chunkNum', 'n/a')}",
                    f"Score: {match.score}",
                    f"Distance: {match.distance}",
                ]
            )
            if match.presentation_notes:
                lines.append("Presentation Notes:")
                for note in match.presentation_notes:
                    lines.append(f"- {note}")
            lines.extend(
                [
                    "Content:",
                    match.display_content or "(empty)",
                ]
            )

    return "\n".join(lines)


def normalize_text(value: str) -> str:
    return " ".join(value.lower().replace("’", "'").replace("‘", "'").split())


def resolve_relative_path(base_path: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return (base_path / candidate).resolve()
