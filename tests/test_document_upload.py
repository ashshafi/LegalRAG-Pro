"""Tests for case-aware in-app PDF uploads."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from document_upload import DocumentUploadError, upload_case_pdf  # noqa: E402


PDF_BYTES = b"%PDF-1.7\n% LegalRAG test PDF\n"


class DocumentUploadTests(unittest.TestCase):
    """Verify validation, storage, case scoping, and rollback."""

    def test_upload_saves_pdf_and_passes_case_id_to_indexer(self) -> None:
        calls: list[tuple[Path, str | None]] = []

        def fake_indexer(path: Path, case_id: str | None = None) -> int:
            calls.append((Path(path), case_id))
            return 4

        with TemporaryDirectory() as temp_dir:
            result = upload_case_pdf(
                filename="ET1.pdf",
                content=PDF_BYTES,
                case_id=" case-123 ",
                docs_folder=temp_dir,
                indexer=fake_indexer,
            )

            saved_path = Path(temp_dir) / "ET1.pdf"
            self.assertTrue(saved_path.exists())
            self.assertEqual(saved_path.read_bytes(), PDF_BYTES)
            self.assertEqual(result.filename, "ET1.pdf")
            self.assertEqual(result.chunks_indexed, 4)
            self.assertFalse(result.reused_existing_file)
            self.assertEqual(calls, [(saved_path, "case-123")])

    def test_requires_active_case(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(
                DocumentUploadError,
                "active case",
            ):
                upload_case_pdf(
                    filename="ET1.pdf",
                    content=PDF_BYTES,
                    case_id=" ",
                    docs_folder=temp_dir,
                    indexer=lambda *_args, **_kwargs: 1,
                )

    def test_rejects_non_pdf_content(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(
                DocumentUploadError,
                "valid PDF",
            ):
                upload_case_pdf(
                    filename="fake.pdf",
                    content=b"this is not a pdf",
                    case_id="case-123",
                    docs_folder=temp_dir,
                    indexer=lambda *_args, **_kwargs: 1,
                )

    def test_does_not_overwrite_different_existing_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            existing = Path(temp_dir) / "ET1.pdf"
            existing.write_bytes(b"%PDF-1.4\nexisting\n")

            with self.assertRaisesRegex(
                DocumentUploadError,
                "different file",
            ):
                upload_case_pdf(
                    filename="ET1.pdf",
                    content=PDF_BYTES,
                    case_id="case-123",
                    docs_folder=temp_dir,
                    indexer=lambda *_args, **_kwargs: 1,
                )

            self.assertEqual(
                existing.read_bytes(),
                b"%PDF-1.4\nexisting\n",
            )

    def test_identical_existing_file_can_be_reused_for_another_case(self) -> None:
        calls: list[str | None] = []

        def fake_indexer(_path: Path, case_id: str | None = None) -> int:
            calls.append(case_id)
            return 2

        with TemporaryDirectory() as temp_dir:
            existing = Path(temp_dir) / "ET1.pdf"
            existing.write_bytes(PDF_BYTES)

            result = upload_case_pdf(
                filename="ET1.pdf",
                content=PDF_BYTES,
                case_id="case-b",
                docs_folder=temp_dir,
                indexer=fake_indexer,
            )

            self.assertTrue(result.reused_existing_file)
            self.assertEqual(calls, ["case-b"])
            self.assertEqual(existing.read_bytes(), PDF_BYTES)

    def test_new_file_is_removed_when_indexing_fails(self) -> None:
        def failing_indexer(_path: Path, case_id: str | None = None) -> int:
            raise RuntimeError(f"index failed for {case_id}")

        with TemporaryDirectory() as temp_dir:
            save_path = Path(temp_dir) / "ET1.pdf"

            with self.assertRaisesRegex(
                DocumentUploadError,
                "rolled back",
            ):
                upload_case_pdf(
                    filename="ET1.pdf",
                    content=PDF_BYTES,
                    case_id="case-123",
                    docs_folder=temp_dir,
                    indexer=failing_indexer,
                )

            self.assertFalse(save_path.exists())

    def test_zero_chunks_rolls_back_new_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            save_path = Path(temp_dir) / "blank.pdf"

            with self.assertRaisesRegex(
                DocumentUploadError,
                "No searchable text",
            ):
                upload_case_pdf(
                    filename="blank.pdf",
                    content=PDF_BYTES,
                    case_id="case-123",
                    docs_folder=temp_dir,
                    indexer=lambda *_args, **_kwargs: 0,
                )

            self.assertFalse(save_path.exists())


if __name__ == "__main__":
    unittest.main()
