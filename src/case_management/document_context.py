"""Helpers for associating indexed document chunks with legal cases."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

CASE_ID_METADATA_KEY: Final[str] = "case_id"
LEGACY_CASE_ID: Final[str] = "__legacy__"


def normalise_case_id(case_id: str | None) -> str | None:
    """Return a trimmed case ID, or ``None`` for legacy/global indexing."""

    if case_id is None:
        return None

    cleaned = case_id.strip()
    return cleaned or None


def build_chunk_metadata(
    *,
    pdf_path: str | Path,
    page_number: int,
    chunk_number: int,
    case_id: str | None = None,
    evidence_source_type: str | None = None,
    evidence_source_label: str | None = None,
    evidence_classification_method: str | None = None,
) -> dict[str, str | int]:
    """Build Chroma metadata for one document chunk.

    Existing metadata keys remain unchanged for backwards compatibility.
    ``case_id`` and evidence-source fields are added only when their respective
    case-aware/evidence-aware ingestion values are supplied.
    """

    path = Path(pdf_path)
    metadata: dict[str, str | int] = {
        "file": path.name,
        "page": page_number,
        "chunk": chunk_number,
    }

    cleaned_case_id = normalise_case_id(case_id)
    if cleaned_case_id is not None:
        metadata[CASE_ID_METADATA_KEY] = cleaned_case_id

    if evidence_source_type:
        metadata["evidence_source_type"] = evidence_source_type
    if evidence_source_label:
        metadata["evidence_source_label"] = evidence_source_label
    if evidence_classification_method:
        metadata["evidence_classification_method"] = (
            evidence_classification_method
        )

    return metadata


def build_document_id(
    *,
    pdf_path: str | Path,
    page_number: int,
    chunk_number: int,
    case_id: str | None = None,
) -> str:
    """Build a stable Chroma ID for a chunk.

    Legacy/global ingestion preserves the historical ID format. Case-aware
    ingestion prefixes the ID with a filesystem-safe form of ``case_id`` so
    two cases can index identically named PDFs without Chroma ID collisions.
    """

    path = Path(pdf_path)
    legacy_id = f"{path.stem}_{page_number}_{chunk_number}"

    cleaned_case_id = normalise_case_id(case_id)
    if cleaned_case_id is None:
        return legacy_id

    safe_case_id = re.sub(r"[^A-Za-z0-9._-]+", "_", cleaned_case_id)
    return f"{safe_case_id}__{legacy_id}"

def document_names_from_metadatas(
    metadatas: list[dict[str, object] | None],
) -> list[str]:
    """Return sorted unique filenames from Chroma metadata rows."""

    return sorted(
        {
            str(metadata["file"])
            for metadata in metadatas
            if metadata and metadata.get("file")
        }
    )
