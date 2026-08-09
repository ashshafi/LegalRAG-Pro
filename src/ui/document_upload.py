"""Case-scoped Streamlit UI for governed PDF ingestion."""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from document_upload import (
    DocumentUploadError,
    DocumentUploadResult,
    upload_case_pdf,
)

UploadService = Callable[..., DocumentUploadResult]

_NO_ACTIVE_CASE_TEXT = "Select or create a case to add documents."
_NO_FILE_TEXT = "Choose a PDF document before adding it."
_PROGRESS_TEXT = "Adding document and verifying evidence…"
_SUCCESS_TEXT = "Document added to the selected case."
_REUSE_TEXT = "An identical existing PDF was safely reused for the selected case."
_FAILURE_TEXT = (
    "The document could not be added. No existing document was overwritten. "
    "Check that the file is a valid PDF and try again. If a different PDF "
    "with the same filename already exists, use a distinct filename. "
    "You may safely retry the same PDF."
)


def show_document_upload(
    active_case_id: str | None,
    *,
    upload_service: UploadService = upload_case_pdf,
) -> None:
    """Render governed single-PDF upload controls for the active case."""
    if active_case_id is None or not active_case_id.strip():
        st.sidebar.info(_NO_ACTIVE_CASE_TEXT)
        return

    form_key = f"u3_document_upload_form::{active_case_id}"
    uploader_key = f"u3_document_upload_file::{active_case_id}"

    with st.sidebar.expander("➕ Add document", expanded=False):
        with st.form(form_key, clear_on_submit=True):
            uploaded_file = st.file_uploader(
                "PDF document",
                type=["pdf"],
                accept_multiple_files=False,
                key=uploader_key,
            )
            submitted = st.form_submit_button(
                "Add document to case",
                use_container_width=True,
            )

        if not submitted:
            return
        if uploaded_file is None:
            st.info(_NO_FILE_TEXT)
            return

        content = uploaded_file.getvalue()

        try:
            with st.spinner(_PROGRESS_TEXT):
                result = upload_service(
                    filename=uploaded_file.name,
                    content=content,
                    case_id=active_case_id,
                )
        except DocumentUploadError:
            st.error(_FAILURE_TEXT)
            return

        if result.reused_existing_file:
            st.success(_REUSE_TEXT)
        else:
            st.success(_SUCCESS_TEXT)

        st.text(f"Document: {result.filename}")
