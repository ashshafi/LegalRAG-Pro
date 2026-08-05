"""Case-aware PDF upload service for LegalRAG Pro."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import uuid4

from case_management.document_context import normalise_case_id

LOGGER = logging.getLogger(__name__)

Indexer = Callable[..., int]


class DocumentUploadError(RuntimeError):
    """Raised when an uploaded PDF cannot be safely stored or indexed."""


@dataclass(frozen=True, slots=True)
class DocumentUploadResult:
    """Outcome of a successful case-aware document upload."""

    filename: str
    path: Path
    chunks_indexed: int
    reused_existing_file: bool


def _normalise_filename(filename: str) -> str:
    """Return a safe plain filename and reject path traversal."""

    cleaned = filename.strip()
    if not cleaned:
        raise DocumentUploadError("The uploaded file has no filename.")

    if "/" in cleaned or "\\" in cleaned:
        raise DocumentUploadError(
            "The uploaded filename contains a path. Please rename the PDF and try again."
        )

    if Path(cleaned).suffix.lower() != ".pdf":
        raise DocumentUploadError("Only PDF files can be uploaded.")

    return cleaned


def _looks_like_pdf(content: bytes) -> bool:
    """Return whether the uploaded bytes contain a PDF header near the start."""

    return bool(content) and b"%PDF-" in content[:1024]


def _write_atomically(path: Path, content: bytes) -> None:
    """Write bytes atomically so interrupted uploads do not leave partial PDFs."""

    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.uploading")
    try:
        temp_path.write_bytes(content)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def upload_case_pdf(
    *,
    filename: str,
    content: bytes,
    case_id: str,
    docs_folder: str | Path = "docs",
    indexer: Indexer | None = None,
) -> DocumentUploadResult:
    """Store and index one uploaded PDF for a specific legal case.

    Args:
        filename: Original uploaded filename.
        content: Raw uploaded PDF bytes.
        case_id: Stable internal UUID of the active case.
        docs_folder: LegalRAG document storage directory.
        indexer: Optional injected index function for tests. Production uses
            :func:`source_evidence.ingestion.index_case_pdf_source_bound`.

    Returns:
        Details of the saved and indexed document.

    Raises:
        DocumentUploadError: If validation, storage, or indexing fails.
    """

    cleaned_case_id = normalise_case_id(case_id)
    if cleaned_case_id is None:
        raise DocumentUploadError(
            "Select or create an active case before uploading a document."
        )

    safe_filename = _normalise_filename(filename)

    if not _looks_like_pdf(content):
        raise DocumentUploadError(
            "The selected file does not appear to be a valid PDF."
        )

    storage_dir = Path(docs_folder)
    storage_dir.mkdir(parents=True, exist_ok=True)
    save_path = storage_dir / safe_filename

    reused_existing_file = False
    created_new_file = False

    if save_path.exists():
        existing_content = save_path.read_bytes()
        if existing_content != content:
            raise DocumentUploadError(
                f"A different file named '{safe_filename}' already exists in the "
                "LegalRAG docs folder. Rename the PDF before uploading it so the "
                "existing source document is not overwritten."
            )
        reused_existing_file = True
    else:
        try:
            _write_atomically(save_path, content)
            created_new_file = True
        except OSError as exc:
            LOGGER.exception("Unable to save uploaded PDF %s.", safe_filename)
            raise DocumentUploadError(
                f"Could not save '{safe_filename}' to the LegalRAG docs folder."
            ) from exc

    try:
        if indexer is None:
            # Import lazily so unit tests do not initialise OpenAI/Chroma just by
            # importing this service.
            from source_evidence.identity import sha256_bytes
            from source_evidence.ingestion import index_case_pdf_source_bound

            chunks_indexed = int(
                index_case_pdf_source_bound(
                    save_path,
                    case_id=cleaned_case_id,
                    expected_original_sha256=sha256_bytes(content),
                )
            )
        else:
            # Preserve the frozen injected-indexer contract exactly.
            chunks_indexed = int(indexer(save_path, case_id=cleaned_case_id))
    except Exception as exc:
        LOGGER.exception(
            "Indexing failed for uploaded PDF %s in case %s.",
            safe_filename,
            cleaned_case_id,
        )
        if created_new_file:
            save_path.unlink(missing_ok=True)
        raise DocumentUploadError(
            f"'{safe_filename}' was not indexed. The upload has been rolled back."
        ) from exc

    if chunks_indexed <= 0:
        if created_new_file:
            save_path.unlink(missing_ok=True)
        raise DocumentUploadError(
            f"No searchable text could be indexed from '{safe_filename}'."
        )

    LOGGER.info(
        "Uploaded and indexed %s for case %s (%s chunks).",
        safe_filename,
        cleaned_case_id,
        chunks_indexed,
    )

    return DocumentUploadResult(
        filename=safe_filename,
        path=save_path,
        chunks_indexed=chunks_indexed,
        reused_existing_file=reused_existing_file,
    )
