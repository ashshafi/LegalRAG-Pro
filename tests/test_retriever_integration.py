"""Integration tests for Sprint 2.2 retrieval quality wiring."""

from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


class _FakeEmbeddings:
    def create(self, **_kwargs: object) -> object:
        return types.SimpleNamespace(
            data=[types.SimpleNamespace(embedding=[0.1, 0.2])]
        )


class _FakeCollection:
    def __init__(self) -> None:
        self.query_kwargs: dict[str, object] | None = None

    def query(self, **kwargs: object) -> dict[str, object]:
        self.query_kwargs = kwargs
        return {
            "ids": [["id-0", "id-1", "id-2"]],
            "documents": [[
                "Witness statement first chunk.",
                "Witness statement second chunk.",
                "Employer email evidence.",
            ]],
            "metadatas": [[
                {"file": "Witness.pdf", "page": 2, "case_id": "case-a"},
                {"file": "Witness.pdf", "page": 2, "case_id": "case-a"},
                {"file": "Employer.pdf", "page": 1, "case_id": "case-a"},
            ]],
            "distances": [[0.1, 0.2, 0.3]],
        }


class RetrieverIntegrationTests(unittest.TestCase):
    def test_case_filter_is_applied_before_quality_filtering(self) -> None:
        fake_collection = _FakeCollection()
        fake_config = types.ModuleType("config")
        fake_config.collection = fake_collection
        fake_config.openai_client = types.SimpleNamespace(
            embeddings=_FakeEmbeddings()
        )

        fake_query_expander = types.ModuleType("query_expander")
        fake_query_expander.expand_query = lambda question: question

        sys.modules.pop("retriever", None)
        try:
            with patch.dict(
                sys.modules,
                {
                    "config": fake_config,
                    "query_expander": fake_query_expander,
                },
            ):
                retriever = importlib.import_module("retriever")
                results = retriever.retrieve(
                    "What happened?",
                    n_results=2,
                    case_id="case-a",
                )
        finally:
            sys.modules.pop("retriever", None)

        self.assertIsNotNone(fake_collection.query_kwargs)
        assert fake_collection.query_kwargs is not None
        self.assertEqual(fake_collection.query_kwargs["where"], {"case_id": "case-a"})
        self.assertEqual(fake_collection.query_kwargs["n_results"], 8)
        self.assertEqual(results["ids"][0], ["id-0", "id-2"])
        self.assertEqual(
            {metadata["case_id"] for metadata in results["metadatas"][0]},
            {"case-a"},
        )

    def test_retrieval_adds_source_classification_before_return(self) -> None:
        class ClassifiedCollection:
            def __init__(self) -> None:
                self.query_kwargs: dict[str, object] | None = None

            def query(self, **kwargs: object) -> dict[str, object]:
                self.query_kwargs = kwargs
                return {
                    "ids": [["id-0", "id-1"]],
                    "documents": [[
                        "I am the Claimant in these proceedings.",
                        "We are writing regarding your employment with the Company.",
                    ]],
                    "metadatas": [[
                        {
                            "file": "Supplementary Witness Statement.pdf",
                            "page": 1,
                            "case_id": "case-a",
                        },
                        {
                            "file": "HR letter.pdf",
                            "page": 1,
                            "case_id": "case-a",
                        },
                    ]],
                    "distances": [[0.1, 0.2]],
                }

        fake_collection = ClassifiedCollection()
        fake_config = types.ModuleType("config")
        fake_config.collection = fake_collection
        fake_config.openai_client = types.SimpleNamespace(
            embeddings=_FakeEmbeddings()
        )

        fake_query_expander = types.ModuleType("query_expander")
        fake_query_expander.expand_query = lambda question: question

        sys.modules.pop("retriever", None)
        try:
            with patch.dict(
                sys.modules,
                {
                    "config": fake_config,
                    "query_expander": fake_query_expander,
                },
            ):
                retriever = importlib.import_module("retriever")
                results = retriever.retrieve(
                    "What happened?",
                    n_results=2,
                    case_id="case-a",
                )
        finally:
            sys.modules.pop("retriever", None)

        self.assertEqual(
            results["metadatas"][0][0]["evidence_source_type"],
            "claimant_witness_statement",
        )
        self.assertEqual(
            results["metadatas"][0][0]["evidence_source_label"],
            "Claimant evidence",
        )
        self.assertEqual(
            results["metadatas"][0][1]["evidence_source_label"],
            "Employer evidence",
        )
        self.assertEqual(
            fake_collection.query_kwargs["where"],
            {"case_id": "case-a"},
        )

    def test_chunk_provenance_and_primary_reranking_are_applied_after_case_scope(self) -> None:
        class ProvenanceCollection:
            def __init__(self) -> None:
                self.query_kwargs: dict[str, object] | None = None

            def query(self, **kwargs: object) -> dict[str, object]:
                self.query_kwargs = kwargs
                return {
                    "ids": [["witness-1", "witness-2", "h4-employer"]],
                    "documents": [[
                        "Witness statement paragraph about employer knowledge.",
                        "Witness statement paragraph about later events.",
                        (
                            "From: HR Director\n"
                            "To: Unum Claims\n"
                            "We are writing regarding your employment and "
                            "the proposed return-to-work arrangements."
                        ),
                    ]],
                    "metadatas": [[
                        {
                            "file": "Witness Statement.pdf",
                            "page": 1,
                            "case_id": "case-a",
                        },
                        {
                            "file": "Witness Statement.pdf",
                            "page": 2,
                            "case_id": "case-a",
                        },
                        {
                            "file": "Appendix H4 - Unum correspondence.pdf",
                            "page": 3,
                            "case_id": "case-a",
                        },
                    ]],
                    "distances": [[0.10, 0.11, 0.12]],
                }

        fake_collection = ProvenanceCollection()
        fake_config = types.ModuleType("config")
        fake_config.collection = fake_collection
        fake_config.openai_client = types.SimpleNamespace(
            embeddings=_FakeEmbeddings()
        )

        fake_query_expander = types.ModuleType("query_expander")
        fake_query_expander.expand_query = lambda question: question

        sys.modules.pop("retriever", None)
        try:
            with patch.dict(
                sys.modules,
                {
                    "config": fake_config,
                    "query_expander": fake_query_expander,
                },
            ):
                retriever = importlib.import_module("retriever")
                results = retriever.retrieve(
                    "What did the employer know?",
                    n_results=3,
                    case_id="case-a",
                )
        finally:
            sys.modules.pop("retriever", None)

        self.assertIsNotNone(fake_collection.query_kwargs)
        assert fake_collection.query_kwargs is not None
        self.assertEqual(fake_collection.query_kwargs["where"], {"case_id": "case-a"})
        self.assertEqual(results["ids"][0], ["witness-1", "h4-employer", "witness-2"])

        h4_metadata = results["metadatas"][0][1]
        self.assertEqual(h4_metadata["evidence_source_type"], "insurer_record")
        self.assertEqual(h4_metadata["chunk_source_type"], "employer_record")
        self.assertEqual(h4_metadata["retrieval_original_rank"], 3)
        self.assertEqual(h4_metadata["retrieval_rerank_rank"], 2)
        self.assertEqual(h4_metadata["case_id"], "case-a")


if __name__ == "__main__":
    unittest.main()
