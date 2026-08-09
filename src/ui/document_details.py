"""Read-only Streamlit viewer for governed document provenance."""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from document_catalog import (
    DocumentCatalogEntry,
    DocumentCatalogError,
    list_case_documents,
)


CatalogService = Callable[[str], tuple[DocumentCatalogEntry, ...]]

_EMPTY_TEXT = "No governed documents are available for this case."
_FAILURE_TEXT = "Document details could not be loaded safely."


def _option_label(entry: DocumentCatalogEntry) -> str:
    """Return an unambiguous inert selector label."""

    return (
        f"{entry.original_filename} "
        f"· {entry.source_document_instance_id[:8]}"
    )


def show_document_details(
    active_case_id: str | None,
    *,
    catalog_service: CatalogService = list_case_documents,
) -> None:
    """Render read-only immutable provenance details for the active case."""

    if active_case_id is None or not active_case_id.strip():
        return

    try:
        entries = catalog_service(active_case_id)
    except DocumentCatalogError:
        st.sidebar.error(_FAILURE_TEXT)
        return

    with st.sidebar.expander("🔎 Document details", expanded=False):
        if not entries:
            st.info(_EMPTY_TEXT)
            return

        selected = st.selectbox(
            "Document",
            options=entries,
            format_func=_option_label,
            key=f"u6_document_details::{active_case_id}",
        )

        st.text(f"Filename: {selected.original_filename}")
        st.text(f"Media type: {selected.media_type}")
        st.text(f"Pages: {selected.page_count}")
        st.text(f"Evidence chunks: {selected.evidence_chunk_count}")
        st.text(f"Original size: {selected.original_byte_length:,} bytes")
        st.text(
            "Source document ID: "
            f"{selected.source_document_instance_id}"
        )
        st.text(
            "Original SHA-256: "
            f"{selected.original_blob_sha256}"
        )
        st.text(f"Source snapshot ID: {selected.source_snapshot_id}")
        st.text(
            "Extraction profile: "
            f"{selected.extraction_profile_id}"
        )
        st.text(
            "Chunking profile: "
            f"{selected.chunking_profile_id}"
        )
        st.text(
            "Extraction methods: "
            + ", ".join(selected.extraction_methods)
        )


__all__ = ["show_document_details"]
