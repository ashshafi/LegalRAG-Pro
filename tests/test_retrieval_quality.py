"""Tests for Sprint 2.2 retrieval duplicate suppression and diversification."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from retrieval_quality import (  # noqa: E402
    improve_retrieval_results,
    overfetch_count,
)


def _results(
    documents: list[str],
    metadatas: list[dict[str, object]],
) -> dict[str, object]:
    """Build a representative single-query Chroma response for tests."""

    count = len(documents)
    return {
        "ids": [[f"id-{index}" for index in range(count)]],
        "documents": [documents],
        "metadatas": [metadatas],
        "distances": [[index / 100 for index in range(count)]],
        "embeddings": None,
        "included": ["metadatas", "documents", "distances"],
    }


class RetrievalQualityTests(unittest.TestCase):
    def test_overfetches_four_times_requested_results(self) -> None:
        self.assertEqual(overfetch_count(10), 40)

    def test_overfetch_rejects_non_positive_result_count(self) -> None:
        with self.assertRaises(ValueError):
            overfetch_count(0)

    def test_exact_duplicate_text_is_suppressed(self) -> None:
        results = _results(
            ["Same evidence", "Same   evidence", "Different evidence"],
            [
                {"file": "A.pdf", "page": 1, "case_id": "case-a"},
                {"file": "B.pdf", "page": 2, "case_id": "case-a"},
                {"file": "C.pdf", "page": 3, "case_id": "case-a"},
            ],
        )

        filtered = improve_retrieval_results(results, n_results=10)

        self.assertEqual(
            filtered["documents"][0],
            ["Same evidence", "Different evidence"],
        )

    def test_near_duplicate_text_is_suppressed(self) -> None:
        base = (
            "CACI wrote to the claimant on 12 May 2005 and discussed the "
            "proposed working arrangements and occupational health advice."
        )
        near_duplicate = base.replace("12 May 2005", "13 May 2005")
        results = _results(
            [base, near_duplicate, "Independent medical evidence."],
            [
                {"file": "A.pdf", "page": 1},
                {"file": "A.pdf", "page": 2},
                {"file": "C.pdf", "page": 3},
            ],
        )

        filtered = improve_retrieval_results(results, n_results=10)

        self.assertEqual(len(filtered["documents"][0]), 2)
        self.assertIn("Independent medical evidence.", filtered["documents"][0])

    def test_near_identical_text_from_different_documents_is_preserved(self) -> None:
        base = (
            "The employer confirmed that occupational health advice would be "
            "obtained before decisions were made about working arrangements."
        )
        near_duplicate = base.replace("confirmed", "stated")
        results = _results(
            [base, near_duplicate],
            [
                {"file": "Employer.pdf", "page": 1},
                {"file": "Insurer.pdf", "page": 4},
            ],
        )

        filtered = improve_retrieval_results(results, n_results=10)

        self.assertEqual(len(filtered["documents"][0]), 2)

    def test_only_one_chunk_per_document_page_is_returned(self) -> None:
        results = _results(
            [
                "Witness statement chunk one.",
                "Witness statement chunk two with different wording.",
                "Employer email.",
            ],
            [
                {"file": "Witness.pdf", "page": 2},
                {"file": "Witness.pdf", "page": 2},
                {"file": "Employer.pdf", "page": 1},
            ],
        )

        filtered = improve_retrieval_results(results, n_results=10)

        self.assertEqual(filtered["ids"][0], ["id-0", "id-2"])

    def test_first_pass_limits_dominant_document_to_two_results(self) -> None:
        results = _results(
            [
                "Witness page one.",
                "Witness page two.",
                "Witness page three.",
                "Employer email.",
                "Medical record.",
            ],
            [
                {"file": "Witness.pdf", "page": 1},
                {"file": "Witness.pdf", "page": 2},
                {"file": "Witness.pdf", "page": 3},
                {"file": "Employer.pdf", "page": 1},
                {"file": "Medical.pdf", "page": 1},
            ],
        )

        filtered = improve_retrieval_results(results, n_results=4)

        self.assertEqual(
            filtered["ids"][0],
            ["id-0", "id-1", "id-3", "id-4"],
        )

    def test_document_cap_relaxes_when_more_results_are_needed(self) -> None:
        results = _results(
            ["Page one.", "Page two.", "Page three."],
            [
                {"file": "Only.pdf", "page": 1},
                {"file": "Only.pdf", "page": 2},
                {"file": "Only.pdf", "page": 3},
            ],
        )

        filtered = improve_retrieval_results(results, n_results=3)

        self.assertEqual(filtered["ids"][0], ["id-0", "id-1", "id-2"])

    def test_case_metadata_is_preserved_unchanged(self) -> None:
        results = _results(
            ["Employer evidence.", "Medical evidence."],
            [
                {"file": "Employer.pdf", "page": 1, "case_id": "case-a"},
                {"file": "Medical.pdf", "page": 2, "case_id": "case-a"},
            ],
        )

        filtered = improve_retrieval_results(results, n_results=10)

        self.assertEqual(
            [metadata["case_id"] for metadata in filtered["metadatas"][0]],
            ["case-a", "case-a"],
        )

    def test_result_fields_stay_aligned_after_filtering(self) -> None:
        results = _results(
            ["Duplicate", "Duplicate", "Independent"],
            [
                {"file": "A.pdf", "page": 1},
                {"file": "B.pdf", "page": 1},
                {"file": "C.pdf", "page": 1},
            ],
        )

        filtered = improve_retrieval_results(results, n_results=10)

        self.assertEqual(filtered["ids"][0], ["id-0", "id-2"])
        self.assertEqual(filtered["distances"][0], [0.0, 0.02])
        self.assertEqual(len(filtered["metadatas"][0]), 2)
        self.assertEqual(
            filtered["included"],
            ["metadatas", "documents", "distances"],
        )


if __name__ == "__main__":
    unittest.main()
