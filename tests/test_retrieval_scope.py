"""Tests for Sprint 2.1 case-isolated retrieval scope."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from case_management.retrieval_scope import build_retrieval_filter  # noqa: E402


class RetrievalScopeTests(unittest.TestCase):
    def test_active_case_always_adds_case_filter(self) -> None:
        where = build_retrieval_filter(case_id="case-a")

        self.assertEqual(where, {"case_id": "case-a"})

    def test_case_and_document_filters_are_combined_with_and(self) -> None:
        where = build_retrieval_filter(
            case_id="case-a",
            selected_documents=["ET1.pdf", "ET3.pdf"],
        )

        self.assertEqual(
            where,
            {
                "$and": [
                    {"case_id": "case-a"},
                    {"file": {"$in": ["ET1.pdf", "ET3.pdf"]}},
                ]
            },
        )

    def test_case_a_filter_cannot_match_case_b(self) -> None:
        where_a = build_retrieval_filter(
            case_id="case-a",
            selected_documents=["ET1.pdf"],
        )
        where_b = build_retrieval_filter(
            case_id="case-b",
            selected_documents=["ET1.pdf"],
        )

        self.assertNotEqual(where_a, where_b)
        self.assertIn({"case_id": "case-a"}, where_a["$and"])
        self.assertNotIn({"case_id": "case-b"}, where_a["$and"])

    def test_missing_case_preserves_legacy_global_filter(self) -> None:
        where = build_retrieval_filter(
            case_id=None,
            selected_documents=["ET1.pdf"],
        )

        self.assertEqual(where, {"file": {"$in": ["ET1.pdf"]}})

    def test_missing_case_and_documents_preserves_global_query(self) -> None:
        self.assertIsNone(
            build_retrieval_filter(case_id=None, selected_documents=None)
        )

    def test_blank_case_id_uses_legacy_path(self) -> None:
        self.assertIsNone(
            build_retrieval_filter(case_id="   ", selected_documents=[])
        )


if __name__ == "__main__":
    unittest.main()
