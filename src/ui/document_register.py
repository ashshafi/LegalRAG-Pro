"""Read-only Streamlit register of governed case documents."""

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
_FAILURE_TEXT = "The governed document register could not be loaded safely."
_NO_MATCH_TEXT = "No governed documents match that filename filter."


def _matches_filename(entry: DocumentCatalogEntry, query: str) -> bool:
    """Return whether a literal case-insensitive filename filter matches."""

    needle = query.strip().casefold()
    if not needle:
        return True
    return needle in entry.original_filename.casefold()


def _entry_line(entry: DocumentCatalogEntry) -> str:
    """Return one inert compact provenance-register row."""

    methods = ", ".join(entry.extraction_methods) or "none"
    return (
        f"{entry.original_filename} | "
        f"pages: {entry.page_count} | "
        f"chunks: {entry.evidence_chunk_count} | "
        f"methods: {methods} | "
        f"doc: {entry.source_document_instance_id[:8]} | "
        f"sha256: {entry.original_blob_sha256[:12]}"
    )


def show_document_register(
    active_case_id: str | None,
    *,
    catalog_service: CatalogService = list_case_documents,
) -> None:
    """Render a read-only governed document register for the active case."""

    if active_case_id is None or not active_case_id.strip():
        return

    try:
        entries = catalog_service(active_case_id)
    except DocumentCatalogError:
        st.sidebar.error(_FAILURE_TEXT)
        return

    with st.sidebar.expander("📋 Governed document register", expanded=False):
        if not entries:
            st.info(_EMPTY_TEXT)
            return

        query = st.text_input(
            "Filter by filename",
            key=f"u7_document_register_filter::{active_case_id}",
        )
        filtered = tuple(
            entry for entry in entries if _matches_filename(entry, query)
        )

        if query.strip():
            noun = "document" if len(entries) == 1 else "documents"
            st.caption(
                f"Showing {len(filtered)} of {len(entries)} governed {noun}"
            )
        else:
            noun = "document" if len(entries) == 1 else "documents"
            st.caption(f"{len(entries)} governed {noun}")

        if not filtered:
            st.info(_NO_MATCH_TEXT)
            return

        for entry in filtered:
            st.text(_entry_line(entry))


__all__ = ["show_document_register"]
