"""Unit tests for Sprint 2.1 case management persistence."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from case_management.models import Case  # noqa: E402
from case_management.repository import CaseNotFoundError, CaseRepository  # noqa: E402


class CaseModelTests(unittest.TestCase):
    def test_create_generates_unique_ids(self) -> None:
        first = Case.create("Shafi v CACI Ltd")
        second = Case.create("Shafi v CACI Ltd")

        self.assertNotEqual(first.case_id, second.case_id)

    def test_case_name_must_not_be_empty(self) -> None:
        with self.assertRaises(ValueError):
            Case.create("   ")

    def test_optional_text_is_normalised(self) -> None:
        case = Case.create(
            "  Shafi v CACI Ltd  ",
            case_number="  2207441/2025  ",
            claimant="   ",
        )

        self.assertEqual(case.name, "Shafi v CACI Ltd")
        self.assertEqual(case.case_number, "2207441/2025")
        self.assertIsNone(case.claimant)


    def test_updated_can_clear_optional_fields(self) -> None:
        original = Case.create(
            "Case A",
            case_number="123",
            claimant="Claimant",
        )

        changed = original.updated(
            case_number="",
            claimant="",
        )

        self.assertIsNone(changed.case_number)
        self.assertIsNone(changed.claimant)


class CaseRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "nested" / "cases.sqlite3"
        self.repository = CaseRepository(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_repository_creates_missing_parent_directory_and_database(self) -> None:
        self.assertTrue(self.db_path.exists())

    def test_create_and_get_round_trip(self) -> None:
        case = Case.create(
            "Shafi v CACI Ltd",
            case_number="2207441/2025",
            claimant="Arshad Shafi",
            respondent="CACI Ltd",
        )

        self.repository.create(case)
        stored = self.repository.get(case.case_id)

        self.assertEqual(stored, case)

    def test_list_all_returns_persisted_cases(self) -> None:
        first = Case.create("Case A")
        second = Case.create("Case B")
        self.repository.create(first)
        self.repository.create(second)

        stored_ids = {case.case_id for case in self.repository.list_all()}

        self.assertEqual(stored_ids, {first.case_id, second.case_id})

    def test_duplicate_internal_id_is_rejected(self) -> None:
        case = Case.create("Case A")
        self.repository.create(case)

        with self.assertRaises(ValueError):
            self.repository.create(case)

    def test_update_persists_changes(self) -> None:
        original = Case.create("Original name")
        self.repository.create(original)
        changed = original.updated(
            name="Updated name",
            case_number="2207441/2025",
            respondent="CACI Ltd",
        )

        self.repository.update(changed)

        self.assertEqual(self.repository.get(original.case_id), changed)

    def test_update_missing_case_raises(self) -> None:
        case = Case.create("Missing")

        with self.assertRaises(CaseNotFoundError):
            self.repository.update(case)

    def test_delete_removes_metadata_only(self) -> None:
        case = Case.create("Case A")
        self.repository.create(case)

        self.assertTrue(self.repository.delete(case.case_id))
        self.assertIsNone(self.repository.get(case.case_id))
        self.assertFalse(self.repository.delete(case.case_id))


if __name__ == "__main__":
    unittest.main()
