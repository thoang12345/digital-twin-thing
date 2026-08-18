import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from Modules.RAG.benchmarking import (
    BenchmarkCase,
    BenchmarkExpectation,
    BenchmarkSuite,
    RetrievalBenchmarkRunner,
    format_benchmark_detailed_report,
    format_benchmark_report,
    load_benchmark_suite,
)


class FakeSearchClient:
    def __init__(self, results_by_query):
        self.results_by_query = results_by_query

    def query_collection(self, collection_name, query, top_k=5):
        payload = self.results_by_query[query]
        return {
            "collection_name": collection_name,
            "query": query,
            "intent": payload.get("intent", "general"),
            "expanded_queries": payload.get("expanded_queries", [query]),
            "matches": payload["matches"][:top_k],
        }


class RetrievalBenchmarkRunnerTests(unittest.TestCase):
    def test_runner_computes_hit_rates_and_mrr(self):
        suite = BenchmarkSuite(
            name="unit_suite",
            collection_name="docs",
            cases=[
                BenchmarkCase(
                    id="case_1",
                    query="what is an MoE",
                    expectation=BenchmarkExpectation(
                        acceptable_doc_names=["systems-14-00048-v3"],
                        required_phrases=["gating network"],
                    ),
                ),
                BenchmarkCase(
                    id="case_2",
                    query="what does RAG stand for",
                    expectation=BenchmarkExpectation(
                        acceptable_ids=["doc2"],
                    ),
                ),
            ],
        )
        client = FakeSearchClient(
            {
                "what is an MoE": {
                    "intent": "definition",
                    "matches": [
                        {
                            "id": "paper_chunk",
                            "content": "The model uses a gating network and expert models.",
                            "metadata": {"docName": "systems-14-00048-v3", "chunkNum": 4},
                            "distance": 1.1,
                            "score": 0.62,
                        }
                    ],
                },
                "what does RAG stand for": {
                    "intent": "definition",
                    "matches": [
                        {
                            "id": "other_doc",
                            "content": "Not the right answer.",
                            "metadata": {"docName": "other"},
                            "distance": 1.5,
                            "score": 0.40,
                        },
                        {
                            "id": "doc2",
                            "content": "RAG stands for retrieval-augmented generation.",
                            "metadata": {"docName": "seed_rag"},
                            "distance": 1.7,
                            "score": 0.37,
                        },
                    ],
                },
            }
        )

        report = RetrievalBenchmarkRunner().run_suite(suite=suite, search_client=client)

        self.assertEqual(report.total_cases, 2)
        self.assertAlmostEqual(report.hit_at_1, 0.5)
        self.assertAlmostEqual(report.hit_at_3, 1.0)
        self.assertAlmostEqual(report.mrr, 0.75)
        self.assertEqual(report.case_results[0].first_relevant_rank, 1)
        self.assertEqual(report.case_results[1].first_relevant_rank, 2)
        self.assertEqual(len(report.case_results[0].retrieved_matches), 1)
        self.assertTrue(report.case_results[0].retrieved_matches[0].is_relevant)
        self.assertEqual(
            report.case_results[1].retrieved_matches[1].display_content,
            "RAG stands for retrieval-augmented generation.",
        )

    def test_loader_reads_suite_json(self):
        payload = {
            "name": "loader_suite",
            "collection_name": "docs",
            "cases": [
                {
                    "id": "case_1",
                    "query": "what is an MoE",
                    "expect": {
                        "acceptable_doc_names": ["systems-14-00048-v3"],
                        "required_phrases": ["gating network"],
                    },
                }
            ],
        }

        with TemporaryDirectory() as tmp_dir:
            suite_path = Path(tmp_dir) / "suite.json"
            suite_path.write_text(json.dumps(payload), encoding="utf-8")
            suite = load_benchmark_suite(suite_path)

        self.assertEqual(suite.name, "loader_suite")
        self.assertEqual(suite.collection_name, "docs")
        self.assertEqual(len(suite.cases), 1)
        self.assertEqual(suite.cases[0].expectation.required_phrases, ["gating network"])

    def test_report_formatter_includes_summary_metrics(self):
        suite = BenchmarkSuite(
            name="unit_suite",
            collection_name="docs",
            cases=[],
        )
        report = RetrievalBenchmarkRunner().run_suite(
            suite=suite,
            search_client=FakeSearchClient({}),
        )

        text = format_benchmark_report(report)

        self.assertIn("Hit@1", text)
        self.assertIn("MRR", text)

    def test_detailed_report_includes_retrieved_content(self):
        suite = BenchmarkSuite(
            name="unit_suite",
            collection_name="docs",
            cases=[
                BenchmarkCase(
                    id="case_1",
                    query="what is an MoE",
                    description="Find the MoE definition chunk.",
                    expectation=BenchmarkExpectation(
                        acceptable_doc_names=["systems-14-00048-v3"],
                        required_phrases=["gating network"],
                    ),
                ),
            ],
        )
        client = FakeSearchClient(
            {
                "what is an MoE": {
                    "intent": "definition",
                    "expanded_queries": ["what is an moe", "what is a mixture of experts"],
                    "matches": [
                        {
                            "id": "paper_chunk",
                            "content": "Systems 2026, 14, 48 4 of 23\r\nThe model uses a gating network and expert models.",
                            "metadata": {"docName": "systems-14-00048-v3", "chunkNum": 4},
                            "distance": 1.1,
                            "score": 0.62,
                        }
                    ],
                },
            }
        )

        report = RetrievalBenchmarkRunner().run_suite(suite=suite, search_client=client)
        text = format_benchmark_detailed_report(report)

        self.assertIn("Retrieved Matches By Case", text)
        self.assertIn("Match ID: paper_chunk", text)
        self.assertIn("The model uses a gating network and expert models.", text)
        self.assertIn("Expanded Queries: what is an moe, what is a mixture of experts", text)


if __name__ == "__main__":
    unittest.main()
