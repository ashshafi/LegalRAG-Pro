"""Tests for safe legacy-document assignment."""

from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from case_management.migration import (  # noqa: E402
    apply_legacy_assignment,
    build_legacy_assignment_plan,
    list_legacy_documents,
)


class FakeCollection:
    def __init__(self) -> None:
        self.rows = {
            "ET1_1_0": {"file": "ET1.pdf", "page": 1, "chunk": 0},
            "ET1_1_1": {"file": "ET1.pdf", "page": 1, "chunk": 1},
            "other": {
                "file": "Other.pdf",
                "page": 1,
                "chunk": 0,
                "case_id": "case-b",
            },
        }
        self.update_calls = []

    def get(self, where=None, include=None):
        items = list(self.rows.items())
        if where and "file" in where:
            items = [
                (chunk_id, metadata)
                for chunk_id, metadata in items
                if metadata.get("file") == where["file"]
            ]
        return {
            "ids": [chunk_id for chunk_id, _ in items],
            "metadatas": [deepcopy(metadata) for _, metadata in items],
        }

    def update(self, *, ids, metadatas):
        self.update_calls.append((list(ids), deepcopy(metadatas)))
        for chunk_id, metadata in zip(ids, metadatas, strict=True):
            self.rows[chunk_id] = deepcopy(metadata)


class LegacyMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.collection = FakeCollection()

    def test_lists_only_documents_with_unassigned_chunks(self) -> None:
        self.assertEqual(
            list_legacy_documents(self.collection),
            ["ET1.pdf"],
        )

    def test_preview_does_not_modify_collection(self) -> None:
        before = deepcopy(self.collection.rows)

        plan = build_legacy_assignment_plan(
            self.collection,
            filename="ET1.pdf",
            case_id="case-a",
        )

        self.assertEqual(plan.chunk_count, 2)
        self.assertEqual(self.collection.rows, before)
        self.assertEqual(self.collection.update_calls, [])

    def test_plan_assigns_only_previously_unassigned_chunks(self) -> None:
        plan = build_legacy_assignment_plan(
            self.collection,
            filename="Other.pdf",
            case_id="case-a",
        )

        self.assertEqual(plan.chunk_count, 0)

    def test_apply_updates_metadata_without_embeddings_or_documents(self) -> None:
        plan = build_legacy_assignment_plan(
            self.collection,
            filename="ET1.pdf",
            case_id="case-a",
        )

        count = apply_legacy_assignment(self.collection, plan)

        self.assertEqual(count, 2)
        ids, metadatas = self.collection.update_calls[0]
        self.assertEqual(ids, ["ET1_1_0", "ET1_1_1"])
        self.assertTrue(all(m["case_id"] == "case-a" for m in metadatas))

    def test_assignment_does_not_move_existing_case_chunks(self) -> None:
        plan = build_legacy_assignment_plan(
            self.collection,
            filename="Other.pdf",
            case_id="case-a",
        )
        apply_legacy_assignment(self.collection, plan)

        self.assertEqual(
            self.collection.rows["other"]["case_id"],
            "case-b",
        )
        self.assertEqual(self.collection.update_calls, [])

    def test_empty_target_case_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_legacy_assignment_plan(
                self.collection,
                filename="ET1.pdf",
                case_id="   ",
            )


if __name__ == "__main__":
    unittest.main()
