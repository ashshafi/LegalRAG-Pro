"""Tests for case-management document-listing helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from case_management.document_context import document_names_from_metadatas  # noqa: E402


class DocumentListingTests(unittest.TestCase):
    def test_returns_sorted_unique_filenames(self) -> None:
        names = document_names_from_metadatas(
            [
                {"file": "ET3.pdf", "case_id": "case-a"},
                {"file": "ET1.pdf", "case_id": "case-a"},
                {"file": "ET1.pdf", "case_id": "case-a"},
            ]
        )
        self.assertEqual(names, ["ET1.pdf", "ET3.pdf"])

    def test_ignores_empty_metadata_rows(self) -> None:
        names = document_names_from_metadatas(
            [None, {}, {"page": 1}, {"file": ""}, {"file": "Order.pdf"}]
        )
        self.assertEqual(names, ["Order.pdf"])


if __name__ == "__main__":
    unittest.main()
