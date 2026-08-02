"""Tests for bounded primary-source evidence reranking."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from evidence_reranking import (  # noqa: E402
    RETRIEVAL_ORIGINAL_RANK_KEY,
    RETRIEVAL_PROMOTION_KEY,
    RETRIEVAL_RERANK_RANK_KEY,
    rerank_for_primary_sources,
)


def _results(tiers: list[int]) -> dict[str, object]:
    count = len(tiers)
    return {
        "ids": [[f"id-{index}" for index in range(count)]],
        "documents": [[f"Evidence {index}" for index in range(count)]],
        "metadatas": [[
            {
                "file": f"Doc-{index}.pdf",
                "page": 1,
                "case_id": "case-a",
                "primary_source_tier": tier,
            }
            for index, tier in enumerate(tiers)
        ]],
        "distances": [[0.1 + index / 100 for index in range(count)]],
    }


class EvidenceRerankingTests(unittest.TestCase):
    def test_top_vector_result_is_never_displaced(self) -> None:
        results = _results([1, 4, 4])

        reranked = rerank_for_primary_sources(results)

        self.assertEqual(reranked["ids"][0][0], "id-0")

    def test_nearby_primary_record_can_move_above_testimonial_source(self) -> None:
        results = _results([1, 1, 4, 1])

        reranked = rerank_for_primary_sources(results)

        self.assertEqual(reranked["ids"][0][:3], ["id-0", "id-2", "id-1"])

    def test_far_primary_record_receives_only_bounded_promotion(self) -> None:
        results = _results([1] * 10 + [4])

        reranked = rerank_for_primary_sources(results)

        new_position = reranked["ids"][0].index("id-10") + 1
        self.assertGreaterEqual(new_position, 7)

    def test_direct_party_correspondence_gets_smaller_bounded_preference(self) -> None:
        results = _results([1, 1, 3, 1, 1])

        reranked = rerank_for_primary_sources(results)

        self.assertEqual(reranked["ids"][0][:3], ["id-0", "id-2", "id-1"])

    def test_result_fields_remain_aligned(self) -> None:
        results = _results([1, 1, 4])

        reranked = rerank_for_primary_sources(results)

        self.assertEqual(reranked["ids"][0], ["id-0", "id-2", "id-1"])
        self.assertEqual(
            reranked["distances"][0],
            [0.1, 0.12000000000000001, 0.11],
        )
        self.assertEqual(
            [metadata["file"] for metadata in reranked["metadatas"][0]],
            ["Doc-0.pdf", "Doc-2.pdf", "Doc-1.pdf"],
        )

    def test_case_metadata_is_preserved(self) -> None:
        reranked = rerank_for_primary_sources(_results([1, 4, 1]))

        self.assertEqual(
            {metadata["case_id"] for metadata in reranked["metadatas"][0]},
            {"case-a"},
        )

    def test_reranking_metadata_records_original_and_new_rank(self) -> None:
        reranked = rerank_for_primary_sources(_results([1, 1, 4]))
        metadata_by_id = dict(
            zip(reranked["ids"][0], reranked["metadatas"][0], strict=True)
        )

        promoted = metadata_by_id["id-2"]
        self.assertEqual(promoted[RETRIEVAL_ORIGINAL_RANK_KEY], 3)
        self.assertEqual(promoted[RETRIEVAL_RERANK_RANK_KEY], 2)
        self.assertEqual(promoted[RETRIEVAL_PROMOTION_KEY], 1)


if __name__ == "__main__":
    unittest.main()
