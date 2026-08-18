import unittest

from Modules.RAG.query_expansion import IntentAwareQueryExpander
from Modules.RAG.reranker import HeuristicSearchReranker
from Modules.RAG.search_pipeline import IntentAwareSearchPipeline, SearchPipelineResult


class FakeCollection:
    def __init__(self, query_to_results):
        self.query_to_results = query_to_results

    def query(self, query_texts, n_results, where=None, include=None):
        query = query_texts[0]
        result = self.query_to_results.get(
            query,
            {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]},
        )
        return result


class FakeSearchPipeline:
    def __init__(self, result):
        self.result = result

    def search(self, collection, *, query, top_k=5, where=None):
        return self.result


class QueryExpansionTests(unittest.TestCase):
    def test_definition_query_expands_moe_aliases(self):
        expander = IntentAwareQueryExpander()

        result = expander.expand("what is an MoE")

        self.assertEqual(result.intent, "definition")
        texts = [variant.text for variant in result.variants]
        self.assertIn("mixture of experts", texts)
        self.assertIn("what is a mixture of experts", texts)
        self.assertIn("definition of mixture of experts", texts)


class SearchPipelineTests(unittest.TestCase):
    def test_definition_reranking_promotes_definition_chunk_over_table_chunk(self):
        collection = FakeCollection(
            {
                "what is an MoE": {
                    "ids": [["table_chunk", "definition_chunk"]],
                    "documents": [[
                        "Table 3. Comparative performance of the SG-MoE model. MAE RMSE sMAPE MAR MCAR MNAR.",
                        "The core component of the proposed framework is the Spatially Gated Mixture-of-Experts model. It consists of a gating network and a set of expert models.",
                    ]],
                    "metadatas": [[
                        {"chunkNum": 14, "docName": "paper"},
                        {"chunkNum": 4, "docName": "paper"},
                    ]],
                    "distances": [[1.35, 1.62]],
                },
                "mixture of experts": {
                    "ids": [["definition_chunk"]],
                    "documents": [[
                        "The core component of the proposed framework is the Spatially Gated Mixture-of-Experts model. It consists of a gating network and a set of expert models.",
                    ]],
                    "metadatas": [[
                        {"chunkNum": 4, "docName": "paper"},
                    ]],
                    "distances": [[1.55]],
                },
                "mixture-of-experts": {
                    "ids": [["definition_chunk"]],
                    "documents": [[
                        "The core component of the proposed framework is the Spatially Gated Mixture-of-Experts model. It consists of a gating network and a set of expert models.",
                    ]],
                    "metadatas": [[
                        {"chunkNum": 4, "docName": "paper"},
                    ]],
                    "distances": [[1.58]],
                },
                "what is a mixture of experts": {
                    "ids": [["definition_chunk"]],
                    "documents": [[
                        "The core component of the proposed framework is the Spatially Gated Mixture-of-Experts model. It consists of a gating network and a set of expert models.",
                    ]],
                    "metadatas": [[
                        {"chunkNum": 4, "docName": "paper"},
                    ]],
                    "distances": [[1.50]],
                },
                "definition of mixture of experts": {
                    "ids": [["definition_chunk"]],
                    "documents": [[
                        "The core component of the proposed framework is the Spatially Gated Mixture-of-Experts model. It consists of a gating network and a set of expert models.",
                    ]],
                    "metadatas": [[
                        {"chunkNum": 4, "docName": "paper"},
                    ]],
                    "distances": [[1.49]],
                },
                "mixture of experts model": {
                    "ids": [["definition_chunk"]],
                    "documents": [[
                        "The core component of the proposed framework is the Spatially Gated Mixture-of-Experts model. It consists of a gating network and a set of expert models.",
                    ]],
                    "metadatas": [[
                        {"chunkNum": 4, "docName": "paper"},
                    ]],
                    "distances": [[1.47]],
                },
            }
        )

        pipeline = IntentAwareSearchPipeline()
        result = pipeline.search(collection, query="what is an MoE", top_k=3)

        self.assertEqual(result.intent, "definition")
        self.assertEqual(result.matches[0]["id"], "definition_chunk")
        self.assertIn("Alias phrase matched content.", result.matches[0]["metadata"]["rerankNotes"])


if __name__ == "__main__":
    unittest.main()
