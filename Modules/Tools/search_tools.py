from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import chromadb

from Modules.RAG.search_pipeline import IntentAwareSearchPipeline
from Modules.Ingestion.service import SmartDocumentIngestor


class ChromaToolSearch:
    SUPPORTED_INGEST_EXTENSIONS = {
        ".txt",
        ".md",
        ".markdown",
        ".json",
        ".csv",
        ".py",
        ".pdf",
        ".docx",
    }

    def __init__(
        self,
        persist_directory: str = "./chroma_db",
        digital_twin_collection: str = "DTMs",
        long_term_memory_collection: str = "LTM",
        document_ingester: Optional[SmartDocumentIngestor] = None,
        search_pipeline: Optional[IntentAwareSearchPipeline] = None,
    ):
        self.clientdb = chromadb.PersistentClient(path=persist_directory)
        self.digital_twin_collection = digital_twin_collection
        self.long_term_memory_collection = long_term_memory_collection
        self.document_ingester = document_ingester or SmartDocumentIngestor()
        self.search_pipeline = search_pipeline or IntentAwareSearchPipeline()

    def search_collection(
        self,
        collection_name: str,
        query: str,
        top_k: int = 2,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        collection = self.clientdb.get_or_create_collection(name=collection_name)
        results = collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        matches = []
        for doc_id, document, metadata, distance in zip(
            ids,
            documents,
            metadatas,
            distances,
        ):
            matches.append(
                {
                    "id": doc_id,
                    "content": document,
                    "metadata": metadata or {},
                    "distance": distance,
                    "score": self._distance_to_score(distance),
                }
            )

        return matches

    def list_collections(self) -> List[Dict[str, Any]]:
        collections = []
        for collection in self.clientdb.list_collections():
            name = getattr(collection, "name", str(collection))
            try:
                count = self.clientdb.get_or_create_collection(name=name).count()
            except Exception:
                count = None
            collections.append({"name": name, "count": count})

        collections.sort(key=lambda item: item["name"].lower())
        return collections

    def clear_collection(self, collection_name: str) -> Dict[str, Any]:
        resolved_name = self._normalize_collection_name(collection_name)
        deleted_count = 0

        if self._collection_exists(resolved_name):
            deleted_count = self.clientdb.get_or_create_collection(
                name=resolved_name
            ).count()
            self.clientdb.delete_collection(name=resolved_name)

        self.clientdb.get_or_create_collection(name=resolved_name)
        return {
            "collection_name": resolved_name,
            "status": "cleared",
            "deleted_count": deleted_count,
        }

    def delete_collection(self, collection_name: str) -> Dict[str, Any]:
        resolved_name = self._normalize_collection_name(collection_name)
        if not self._collection_exists(resolved_name):
            raise ValueError(f"Collection '{resolved_name}' does not exist.")

        deleted_count = self.clientdb.get_or_create_collection(name=resolved_name).count()
        self.clientdb.delete_collection(name=resolved_name)
        return {
            "collection_name": resolved_name,
            "status": "deleted",
            "deleted_count": deleted_count,
        }

    def query_collection(
        self,
        collection_name: str,
        query: str,
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        collection = self.clientdb.get_or_create_collection(name=collection_name)
        pipeline_result = self._get_search_pipeline().search(
            collection,
            query=query,
            top_k=top_k,
            where=where,
        )
        return {
            "collection_name": collection_name,
            "query": query,
            "intent": pipeline_result.intent,
            "expanded_queries": pipeline_result.expanded_queries,
            "matches": pipeline_result.matches,
        }

    def add_text_entry(
        self,
        collection_name: str,
        text: str,
        source: Optional[str] = None,
        document_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        cleaned_text = text.strip()
        if not cleaned_text:
            raise ValueError("Text entry cannot be empty.")

        collection = self.clientdb.get_or_create_collection(name=collection_name)
        resolved_document_id = document_id or str(uuid4())
        metadata = {
            "source": source or "manual_entry",
            "ingest_type": "manual_text",
        }
        collection.upsert(
            ids=[resolved_document_id],
            documents=[cleaned_text],
            metadatas=[metadata],
        )
        return {
            "collection_name": collection_name,
            "document_id": resolved_document_id,
            "source": metadata["source"],
            "characters": len(cleaned_text),
            "ingest_type": metadata["ingest_type"],
        }

    def ingest_file(
        self,
        collection_name: str,
        file_path: str,
        source: Optional[str] = None,
        document_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        collection = self.clientdb.get_or_create_collection(name=collection_name)
        resolved_document_id = document_id or str(uuid4())
        parsed_document = self._get_document_ingester().parse_file(
            file_path=file_path,
            source=source,
            document_id=resolved_document_id,
        )
        collection.upsert(
            ids=[chunk.chunk_id for chunk in parsed_document.chunks],
            documents=[chunk.content for chunk in parsed_document.chunks],
            metadatas=[chunk.metadata for chunk in parsed_document.chunks],
        )
        return {
            "collection_name": collection_name,
            "document_id": resolved_document_id,
            "source": parsed_document.source,
            "file_name": parsed_document.file_name,
            "file_path": parsed_document.file_path,
            "characters": len(parsed_document.content),
            "chunk_count": len(parsed_document.chunks),
            "page_count": parsed_document.page_count,
            "parser": parsed_document.parser_name,
            "strategy": parsed_document.strategy_name,
            "selected_mode": parsed_document.selected_mode,
            "selection_reason": parsed_document.selection_reason,
            "fallback_used": parsed_document.fallback_used,
            "warnings": parsed_document.warnings,
            "analysis": parsed_document.analysis,
            "ingest_type": "file_chunks",
        }

    def ingest_directory(
        self,
        collection_name: str,
        directory_path: str,
        *,
        recursive: bool = False,
    ) -> Dict[str, Any]:
        resolved_collection_name = self._normalize_collection_name(collection_name)
        path = Path(directory_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Directory not found: {path}")
        if not path.is_dir():
            raise ValueError(f"Path is not a directory: {path}")

        iterator = path.rglob("*") if recursive else path.iterdir()
        file_paths = sorted(
            candidate
            for candidate in iterator
            if candidate.is_file()
            and candidate.suffix.lower() in self.SUPPORTED_INGEST_EXTENSIONS
        )
        if not file_paths:
            raise ValueError(
                "No supported files were found in the selected directory."
            )

        ingested_files = []
        failed_files = []
        total_chunks = 0
        total_characters = 0

        for file_path in file_paths:
            try:
                result = self.ingest_file(
                    collection_name=resolved_collection_name,
                    file_path=str(file_path),
                    source=file_path.name,
                )
            except Exception as exc:
                failed_files.append(
                    {
                        "file_name": file_path.name,
                        "file_path": str(file_path),
                        "error": str(exc),
                    }
                )
                continue

            total_chunks += int(result.get("chunk_count", 0) or 0)
            total_characters += int(result.get("characters", 0) or 0)
            ingested_files.append(
                {
                    "file_name": result.get("file_name"),
                    "file_path": result.get("file_path"),
                    "document_id": result.get("document_id"),
                    "chunk_count": result.get("chunk_count"),
                    "parser": result.get("parser"),
                    "strategy": result.get("strategy"),
                    "selected_mode": result.get("selected_mode"),
                    "fallback_used": result.get("fallback_used"),
                }
            )

        return {
            "collection_name": resolved_collection_name,
            "directory_path": str(path),
            "recursive": recursive,
            "file_count": len(file_paths),
            "ingested_count": len(ingested_files),
            "failed_count": len(failed_files),
            "total_chunks": total_chunks,
            "total_characters": total_characters,
            "ingested_files": ingested_files,
            "failed_files": failed_files,
            "ingest_type": "directory_files",
        }

    def search_DT_info(self, query: str) -> dict:
        matches = self.search_collection(
            collection_name=self.digital_twin_collection,
            query=query,
            top_k=3,
        )
        return {
            "tool": "search_DT_info",
            "query": query,
            "matches": matches,
        }

    def find_DT_by_output(self, output_name: str) -> dict:
        matches = self.search_collection(
            collection_name=self.digital_twin_collection,
            query=output_name,
            top_k=3,
            where={"outputs": output_name},
        )
        return {
            "tool": "find_DT_by_output",
            "query": output_name,
            "matches": matches,
        }

    def find_DT_by_input(self, input_name: str) -> dict:
        matches = self.search_collection(
            collection_name=self.digital_twin_collection,
            query=input_name,
            top_k=3,
            where={"inputs": input_name},
        )
        return {
            "tool": "find_DT_by_input",
            "query": input_name,
            "matches": matches,
        }

    def search_long_term_memory(self, query: str) -> dict:
        matches = self.search_collection(
            collection_name=self.long_term_memory_collection,
            query=query,
            top_k=3,
        )
        return {
            "tool": "search_long_term_memory",
            "query": query,
            "matches": matches,
        }

    @staticmethod
    def _distance_to_score(distance: Optional[float]) -> Optional[float]:
        if distance is None:
            return None
        return 1 / (1 + distance)

    def _get_document_ingester(self) -> SmartDocumentIngestor:
        ingester = getattr(self, "document_ingester", None)
        if ingester is None:
            ingester = SmartDocumentIngestor()
            self.document_ingester = ingester
        return ingester

    def _get_search_pipeline(self) -> IntentAwareSearchPipeline:
        pipeline = getattr(self, "search_pipeline", None)
        if pipeline is None:
            pipeline = IntentAwareSearchPipeline()
            self.search_pipeline = pipeline
        return pipeline

    def _collection_exists(self, collection_name: str) -> bool:
        return any(
            getattr(collection, "name", str(collection)) == collection_name
            for collection in self.clientdb.list_collections()
        )

    @staticmethod
    def _normalize_collection_name(collection_name: str) -> str:
        resolved_name = collection_name.strip()
        if not resolved_name:
            raise ValueError("Collection name cannot be empty.")
        return resolved_name
