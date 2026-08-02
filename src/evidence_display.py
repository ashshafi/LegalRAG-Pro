"""User-facing formatting for LegalRAG evidence provenance."""

from __future__ import annotations

from typing import Any


def build_evidence_heading(source: dict[str, Any]) -> str:
    """Return an always-visible Evidence panel heading with provenance.

    Chunk provenance is shown first because mixed/composite PDFs can contain
    material authored by a different source from the container-level
    classification. The container classification is appended only when it
    differs from the chunk provenance.
    """

    file_name = str(source.get("file") or "Unknown document")
    page = source.get("page", "?")
    chunk_label = str(
        source.get("chunk_source_label") or "Unclassified evidence"
    )
    document_label = str(
        source.get("source_label") or "Unclassified evidence"
    )

    heading = f"📄 {file_name} — Page {page} | {chunk_label}"
    if document_label != chunk_label:
        heading += f" | container: {document_label}"
    return heading
