import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from Modules.Ingestion.docling_ingester import ParsedDocument, ParsedDocumentChunk
from Modules.RAG.search_pipeline import SearchPipelineResult
from Modules.Tools.search_tools import ChromaToolSearch


class FakeCountCollection:
    def __init__(self, count_value):
        self._count_value = count_value

    def count(self):
        return self._count_value


class FakeWritableCollection(FakeCountCollection):
    def __init__(self, count_value=0):
        super().__init__(count_value)
        self.upsert_calls = []

    def upsert(self, **kwargs):
        self.upsert_calls.append(kwargs)
        self._count_value += len(kwargs.get("ids", []))


class FakeClientDb:
    def list_collections(self):
        return [SimpleNamespace(name="Zeta"), SimpleNamespace(name="alpha")]

    def get_or_create_collection(self, name):
        counts = {"Zeta": 3, "alpha": 7}
        return FakeCountCollection(counts[name])


class FakeWritableClientDb:
    def __init__(self):
        self.collections = {}

    def get_or_create_collection(self, name):
        return self.collections.setdefault(name, FakeWritableCollection())

    def list_collections(self):
        return [SimpleNamespace(name=name) for name in self.collections.keys()]

    def delete_collection(self, name):
        self.collections.pop(name, None)


class FakeDocumentIngester:
    def parse_file(self, file_path, source=None, document_id=None):
        return ParsedDocument(
            document_id=document_id or "doc-1",
            source=source or "sample.txt",
            file_name="sample.txt",
            file_path=str(file_path),
            parser_name="fake_parser",
            content="chunk one\nchunk two",
            page_count=2,
            chunks=[
                ParsedDocumentChunk(
                    chunk_id=f"{document_id}:chunk:0000",
                    content="chunk one",
                    metadata={"docName": "sample", "chunkNum": 0, "pageStart": 1},
                ),
                ParsedDocumentChunk(
                    chunk_id=f"{document_id}:chunk:0001",
                    content="chunk two",
                    metadata={"docName": "sample", "chunkNum": 1, "pageStart": 2},
                ),
            ],
        )


class FakeSearchPipeline:
    def search(self, collection, *, query, top_k=5, where=None):
        return SearchPipelineResult(
            query=query,
            intent="definition",
            expanded_queries=[query, "mixture of experts"],
            matches=[
                {
                    "id": "1",
                    "content": "hello",
                    "metadata": {"docName": "doc-a"},
                    "distance": 1.2,
                    "score": 0.61,
                }
            ],
        )


class ChromaToolSearchTests(unittest.TestCase):
    def test_list_collections_returns_sorted_names_and_counts(self):
        browser = ChromaToolSearch.__new__(ChromaToolSearch)
        browser.clientdb = FakeClientDb()

        result = browser.list_collections()

        self.assertEqual(
            result,
            [
                {"name": "alpha", "count": 7},
                {"name": "Zeta", "count": 3},
            ],
        )

    def test_query_collection_wraps_search_results(self):
        browser = ChromaToolSearch.__new__(ChromaToolSearch)
        browser.clientdb = FakeWritableClientDb()
        browser.search_pipeline = FakeSearchPipeline()

        result = browser.query_collection("docs", "hello", top_k=4)

        self.assertEqual(result["collection_name"], "docs")
        self.assertEqual(result["query"], "hello")
        self.assertEqual(result["intent"], "definition")
        self.assertIn("mixture of experts", result["expanded_queries"])
        self.assertEqual(len(result["matches"]), 1)

    def test_add_text_entry_upserts_document(self):
        browser = ChromaToolSearch.__new__(ChromaToolSearch)
        browser.clientdb = FakeWritableClientDb()

        result = browser.add_text_entry("notes", "hello world", source="manual")

        collection = browser.clientdb.get_or_create_collection("notes")
        self.assertEqual(result["collection_name"], "notes")
        self.assertEqual(result["source"], "manual")
        self.assertEqual(len(collection.upsert_calls), 1)
        self.assertEqual(collection.upsert_calls[0]["documents"], ["hello world"])

    def test_ingest_file_reads_text_and_upserts_document(self):
        browser = ChromaToolSearch.__new__(ChromaToolSearch)
        browser.clientdb = FakeWritableClientDb()
        browser.document_ingester = FakeDocumentIngester()

        with TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "sample.txt"
            file_path.write_text("file content", encoding="utf-8")

            result = browser.ingest_file("docs", str(file_path), source="sample")

        collection = browser.clientdb.get_or_create_collection("docs")
        self.assertEqual(result["collection_name"], "docs")
        self.assertEqual(result["file_name"], "sample.txt")
        self.assertEqual(result["chunk_count"], 2)
        self.assertEqual(result["parser"], "fake_parser")
        self.assertEqual(result["strategy"], "auto")
        self.assertEqual(len(collection.upsert_calls), 1)
        self.assertEqual(collection.upsert_calls[0]["documents"], ["chunk one", "chunk two"])
        self.assertEqual(
            collection.upsert_calls[0]["ids"],
            [result["document_id"] + ":chunk:0000", result["document_id"] + ":chunk:0001"],
        )

    def test_clear_collection_recreates_empty_collection(self):
        browser = ChromaToolSearch.__new__(ChromaToolSearch)
        browser.clientdb = FakeWritableClientDb()
        browser.add_text_entry("docs", "hello world", source="manual")

        result = browser.clear_collection("docs")

        self.assertEqual(result["collection_name"], "docs")
        self.assertEqual(result["status"], "cleared")
        self.assertEqual(result["deleted_count"], 1)
        self.assertEqual(browser.clientdb.get_or_create_collection("docs").count(), 0)

    def test_delete_collection_removes_existing_collection(self):
        browser = ChromaToolSearch.__new__(ChromaToolSearch)
        browser.clientdb = FakeWritableClientDb()
        browser.add_text_entry("docs", "hello world", source="manual")

        result = browser.delete_collection("docs")

        self.assertEqual(result["collection_name"], "docs")
        self.assertEqual(result["status"], "deleted")
        self.assertEqual(result["deleted_count"], 1)
        self.assertNotIn("docs", browser.clientdb.collections)

    def test_ingest_directory_processes_supported_files(self):
        browser = ChromaToolSearch.__new__(ChromaToolSearch)
        browser.clientdb = FakeWritableClientDb()
        browser.document_ingester = FakeDocumentIngester()
        browser.search_pipeline = FakeSearchPipeline()

        with TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            (base / "a.txt").write_text("file a", encoding="utf-8")
            (base / "b.md").write_text("file b", encoding="utf-8")
            (base / "ignore.png").write_text("not supported", encoding="utf-8")

            result = browser.ingest_directory("docs", str(base))

        self.assertEqual(result["collection_name"], "docs")
        self.assertEqual(result["file_count"], 2)
        self.assertEqual(result["ingested_count"], 2)
        self.assertEqual(result["failed_count"], 0)
        self.assertGreaterEqual(result["total_chunks"], 4)


if __name__ == "__main__":
    unittest.main()
