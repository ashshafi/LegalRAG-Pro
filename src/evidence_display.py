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
    semantic_label = str(
        source.get("semantic_source_label") or chunk_label
    )
    confidence = str(source.get("provenance_confidence") or "").strip()
    basis = str(source.get("provenance_basis") or "").strip().replace("_", " ")
    document_label = str(
        source.get("source_label") or "Unclassified evidence"
    )

    heading = f"📄 {file_name} — Page {page} | {semantic_label}"
    if confidence and basis:
        heading += f" | provenance: {confidence} ({basis})"
    elif confidence:
        heading += f" | provenance: {confidence}"
    if document_label != semantic_label:
        heading += f" | container: {document_label}"
    return heading
