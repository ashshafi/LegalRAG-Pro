"""Solicitor-facing governed Documents workspace for LegalRAG Pro R6."""

from __future__ import annotations
from authentication import current_user_identity
from case_management import CaseRepository

import logging
from typing import Any

import streamlit as st

from document_catalog import DocumentCatalogError, list_case_documents
from document_upload import DocumentUploadError, upload_case_pdf

from ui.solicitor_shell import DOCUMENT_UPLOAD_OPEN_KEY, INSPECTION_ORIGIN_KEY

LOGGER = logging.getLogger(__name__)
_FLASH_KEY = "ux_r5_document_upload_flash"
_PAGE_SIZE = 12


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _inspect_document(
    *,
    active_case_id: str,
    source_document_instance_id: str,
) -> None:
    st.session_state[INSPECTION_ORIGIN_KEY] = "Documents"
    st.session_state["ux_d2_documents_view"] = False
    st.session_state["u8_evidence_inspection_document_id"] = source_document_instance_id
    st.session_state["u8_evidence_inspection_view"] = True
    st.session_state["m7_source_evidence_view"] = False
    st.session_state["m6_workspace_view"] = None
    st.session_state["m55_main_view"] = "assistant"


def _show_upload(active_case_id: str, *, expanded: bool) -> None:
    with st.expander("Add document", expanded=expanded):
        st.caption(
            "Add one PDF to this matter. The existing governed ingestion service "
            "handles capture, indexing and source binding."
        )
        with st.form(
            f"ux_r5_document_upload_form::{active_case_id}",
            clear_on_submit=True,
        ):
            uploaded = st.file_uploader(
                "PDF document",
                type=["pdf"],
                accept_multiple_files=False,
                key=f"ux_r5_document_upload_file::{active_case_id}",
            )
            submitted = st.form_submit_button(
                "Add document to matter",
                type="primary",
                use_container_width=False,
            )

        if not submitted:
            return
        if uploaded is None:
            st.info("Choose a PDF document before adding it.")
            return

        try:
            content = uploaded.getvalue()
            with st.spinner("Adding document and verifying governed evidence…"):
                result = upload_case_pdf(
                    filename=uploaded.name,
                    content=content,
                    case_id=active_case_id,
                    access=CaseRepository().require_access(
                        current_user_identity(),
                        active_case_id,
                    ),
                )
        except DocumentUploadError as exc:
            st.error(str(exc))
            return
        except Exception:
            LOGGER.exception("Unexpected error in solicitor Documents upload.")
            st.error(
                "The document could not be added safely. No existing document "
                "has been overwritten."
            )
            return

        reused = bool(getattr(result, "reused_existing_file", False))
        filename = _clean(getattr(result, "filename", "")) or uploaded.name
        chunks = getattr(result, "chunks_indexed", None)
        if reused:
            message = f"{filename} was already present and was safely reused."
        elif chunks is not None:
            message = f"Added {filename} and indexed {chunks} evidence chunk(s)."
        else:
            message = f"Added {filename} to the matter."
        st.session_state[_FLASH_KEY] = message
        st.rerun()


def _document_card(active_case_id: str, entry: Any) -> None:
    filename = _clean(getattr(entry, "original_filename", "")) or "Document"
    source_id = _clean(getattr(entry, "source_document_instance_id", ""))
    pages = getattr(entry, "page_count", None)
    chunks = getattr(entry, "evidence_chunk_count", None)
    methods = tuple(getattr(entry, "extraction_methods", ()) or ())
    media = _clean(getattr(entry, "media_type", ""))
    sha = _clean(getattr(entry, "original_blob_sha256", ""))

    with st.container(border=True):
        left, right = st.columns([7, 1.5])
        with left:
            st.markdown("**" + filename + "**")
            facts: list[str] = []
            if pages is not None:
                facts.append(f"{pages} page(s)")
            if chunks is not None:
                facts.append(f"{chunks} evidence chunk(s)")
            if methods:
                facts.append("Extraction: " + ", ".join(str(item) for item in methods))
            if facts:
                st.caption(" · ".join(facts))
        with right:
            if source_id and st.button(
                "Inspect evidence",
                key=f"ux_r5_inspect::{active_case_id}::{source_id}",
                use_container_width=True,
            ):
                _inspect_document(
                    active_case_id=active_case_id,
                    source_document_instance_id=source_id,
                )
                st.rerun()

        with st.expander("Source details", expanded=False):
            if media:
                st.write("Media type: " + media)
            if source_id:
                st.write("Document instance: " + source_id)
            if sha:
                st.write("SHA-256: " + sha)


def show_documents_workspace(active_case_id: str | None) -> None:
    st.markdown('<div class="lr-page-heading">Documents</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="lr-page-lede">'
        "Governed source documents for this matter. Evidence inspection remains "
        "separate from the source-document register."
        "</div>",
        unsafe_allow_html=True,
    )

    if active_case_id is None or not str(active_case_id).strip():
        st.info("Select an active matter to view or add documents.")
        return

    flash = st.session_state.pop(_FLASH_KEY, None)
    if flash:
        st.success(str(flash))

    expanded = bool(st.session_state.pop(DOCUMENT_UPLOAD_OPEN_KEY, False))
    _show_upload(active_case_id, expanded=expanded)

    try:
        entries = tuple(list_case_documents(active_case_id))
    except DocumentCatalogError:
        st.error("The governed document register could not be loaded safely.")
        return
    except Exception:
        LOGGER.exception("Unexpected Documents register error.")
        st.error("The matter document register could not be loaded.")
        return

    st.markdown(
        f'<div class="lr-section-title">Matter documents '
        f'<span style="color:#667085;font-weight:500">({len(entries)})</span></div>',
        unsafe_allow_html=True,
    )

    if not entries:
        st.info("No governed documents are currently recorded for this matter.")
        return

    query = st.text_input(
        "Filter documents",
        key=f"ux_r5_document_filter::{active_case_id}",
        placeholder="Filter by filename",
        label_visibility="collapsed",
    )
    needle = query.strip().casefold()
    filtered = tuple(
        entry
        for entry in entries
        if not needle
        or needle in _clean(getattr(entry, "original_filename", "")).casefold()
    )

    if not filtered:
        st.info("No governed documents match that filename filter.")
        return

    page_key = f"ux_r6_document_page::{active_case_id}"
    total_pages = max(1, (len(filtered) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    current_page = int(st.session_state.get(page_key, 1) or 1)
    current_page = min(max(current_page, 1), total_pages)
    st.session_state[page_key] = current_page

    first = (current_page - 1) * _PAGE_SIZE
    page_entries = filtered[first:first + _PAGE_SIZE]
    st.caption(
        f"Showing {first + 1}-{first + len(page_entries)} of {len(filtered)} documents "
        f"· page {current_page} of {total_pages}"
    )

    prev_col, next_col, spacer = st.columns([1.0, 1.0, 5.0])
    with prev_col:
        if st.button(
            "Previous",
            key=f"ux_r6_documents_prev::{active_case_id}",
            disabled=current_page <= 1,
            use_container_width=True,
        ):
            st.session_state[page_key] = current_page - 1
            st.rerun()
    with next_col:
        if st.button(
            "Next",
            key=f"ux_r6_documents_next::{active_case_id}",
            disabled=current_page >= total_pages,
            use_container_width=True,
        ):
            st.session_state[page_key] = current_page + 1
            st.rerun()
    with spacer:
        st.empty()

    for entry in page_entries:
        _document_card(active_case_id, entry)


__all__ = ["show_documents_workspace"]
