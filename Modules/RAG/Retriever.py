from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import chromadb

from Modules.RAG.search_pipeline import IntentAwareSearchPipeline


@dataclass(slots=True)
class Document:
    id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SearchMatch:
    id: str
    content: str
    score: Optional[float]
    distance: Optional[float]
    metadata: Dict[str, Any]


@dataclass(slots=True)
class SearchResult:
    query: str
    matches: List[SearchMatch]


class ChromaRAGRetriever:
    def __init__(
        self,
        collection_name: str = "rag_collection",
        persist_directory: str = "./chroma_db",
        search_pipeline: IntentAwareSearchPipeline | None = None,
    ):
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.client.get_or_create_collection(name=collection_name)
        self.search_pipeline = search_pipeline or IntentAwareSearchPipeline()

    def add_documents(self, documents: List[Document]) -> None:
        if not documents:
            return

        ids = [doc.id for doc in documents]
        contents = [doc.content for doc in documents]
        metadatas = [doc.metadata for doc in documents]

        self.collection.upsert(
            ids=ids,
            documents=contents,
            metadatas=metadatas,
        )

    def search(
        self,
        query: str,
        top_k: int = 3,
        where: Optional[Dict[str, Any]] = None,
    ) -> SearchResult:
        pipeline_result = self.search_pipeline.search(
            self.collection,
            query=query,
            top_k=top_k,
            where=where,
        )

        matches: List[SearchMatch] = []
        for match in pipeline_result.matches:
            matches.append(
                SearchMatch(
                    id=match["id"],
                    content=match["content"],
                    metadata=match["metadata"] or {},
                    distance=match["distance"],
                    score=match["score"],
                )
            )

        return SearchResult(query=query, matches=matches)

    @staticmethod
    def _distance_to_score(distance: Optional[float]) -> Optional[float]:
        if distance is None:
            return None
        return 1 / (1 + distance)
