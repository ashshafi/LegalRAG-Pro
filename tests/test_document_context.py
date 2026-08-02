"""Tests for Sprint 2.1 case-aware document ingestion metadata."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from case_management.document_context import (  # noqa: E402
    build_chunk_metadata,
    build_document_id,
    normalise_case_id,
)


class DocumentContextTests(unittest.TestCase):
    def test_legacy_metadata_shape_is_unchanged(self) -> None:
        metadata = build_chunk_metadata(
            pdf_path="docs/ET1.pdf",
            page_number=2,
            chunk_number=3,
        )

        self.assertEqual(
            metadata,
            {"file": "ET1.pdf", "page": 2, "chunk": 3},
        )

    def test_case_aware_metadata_includes_case_id(self) -> None:
        metadata = build_chunk_metadata(
            pdf_path="docs/ET1.pdf",
            page_number=2,
            chunk_number=3,
            case_id=" case-123 ",
        )

        self.assertEqual(metadata["case_id"], "case-123")
        self.assertEqual(metadata["file"], "ET1.pdf")

    def test_evidence_source_metadata_is_added_only_when_supplied(self) -> None:
        metadata = build_chunk_metadata(
            pdf_path="docs/Medical.pdf",
            page_number=4,
            chunk_number=1,
            case_id="case-a",
            evidence_source_type="independent_medical",
            evidence_source_label="Independent medical evidence",
            evidence_classification_method="automatic",
        )

        self.assertEqual(metadata["evidence_source_type"], "independent_medical")
        self.assertEqual(
            metadata["evidence_source_label"],
            "Independent medical evidence",
        )
        self.assertEqual(
            metadata["evidence_classification_method"],
            "automatic",
        )

    def test_legacy_document_id_is_unchanged(self) -> None:
        document_id = build_document_id(
            pdf_path="docs/ET1.pdf",
            page_number=2,
            chunk_number=3,
        )

        self.assertEqual(document_id, "ET1_2_3")

    def test_case_aware_document_ids_do_not_collide_across_cases(self) -> None:
        first = build_document_id(
            pdf_path="docs/ET1.pdf",
            page_number=2,
            chunk_number=3,
            case_id="case-a",
        )
        second = build_document_id(
            pdf_path="docs/ET1.pdf",
            page_number=2,
            chunk_number=3,
            case_id="case-b",
        )

        self.assertNotEqual(first, second)
        self.assertTrue(first.endswith("__ET1_2_3"))
        self.assertTrue(second.endswith("__ET1_2_3"))

    def test_blank_case_id_uses_legacy_behaviour(self) -> None:
        self.assertIsNone(normalise_case_id("   "))
        metadata = build_chunk_metadata(
            pdf_path="ET1.pdf",
            page_number=1,
            chunk_number=0,
            case_id="   ",
        )
        self.assertNotIn("case_id", metadata)

    def test_case_id_is_sanitised_for_document_id_only(self) -> None:
        document_id = build_document_id(
            pdf_path="Order.pdf",
            page_number=1,
            chunk_number=0,
            case_id="case / 123",
        )
        metadata = build_chunk_metadata(
            pdf_path="Order.pdf",
            page_number=1,
            chunk_number=0,
            case_id="case / 123",
        )

        self.assertEqual(document_id, "case_123__Order_1_0")
        self.assertEqual(metadata["case_id"], "case / 123")


if __name__ == "__main__":
    unittest.main()
