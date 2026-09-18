"""Streamlit sidebar for case-scoped documents and matter-workspace navigation."""

from __future__ import annotations
from authentication import current_user_identity
from case_management import CaseRepository

import logging

import streamlit as st

from ui.matter_overview import set_matter_overview_view

from document_upload import DocumentUploadError, upload_case_pdf
from ui.matter_source_import import show_matter_source_import

LOGGER = logging.getLogger(__name__)


def _show_case_upload(active_case_id: str | None, docs: list[str]) -> None:
    """Display the case-aware PDF upload control."""
    st.subheader("➕ Add document")
    if active_case_id is None:
        st.caption(
            "Create or select a matter before uploading a PDF."
        )
        return

    nonce = int(st.session_state.get("case_upload_nonce", 0))
    uploaded_file = st.file_uploader(
        "Upload PDF",
        type=["pdf"],
        key=f"case_pdf_upload_{active_case_id}_{nonce}",
    )
    if uploaded_file is None:
        return
    if uploaded_file.name in docs:
        st.warning(
            "A document with this filename is already indexed in the active matter."
        )
        return
    size_mb = uploaded_file.size / (1024 * 1024)
    st.caption(
        f"{uploaded_file.name} · {size_mb:.2f} MB · will be indexed to the active matter"
    )
    if not st.button(
        "📥 Upload and Index",
        key=f"index_case_pdf_{active_case_id}_{nonce}",
        width="stretch",
    ):
        return
    try:
        with st.sidebar:
            with st.spinner("Uploading and indexing PDF..."):
                access = CaseRepository().require_access(current_user_identity(), active_case_id)
                result = upload_case_pdf(
                    filename=uploaded_file.name,
                    content=uploaded_file.getvalue(),
                    case_id=active_case_id,
                    access=access,
                )
    except DocumentUploadError as exc:
        st.error(str(exc))
        return
    except Exception:
        LOGGER.exception("Unexpected error during case-aware PDF upload.")
        st.error(
            "The document could not be uploaded. Check the application log for details."
        )
        return
    st.success(
        f"Indexed {result.filename} ({result.chunks_indexed} chunks)."
    )
    # A new uploader key clears the completed upload on rerun.
    st.session_state["case_upload_nonce"] = nonce + 1
    st.rerun()


def show_sidebar(
    active_case_id: str | None = None,
    *,
    reports_available: bool = False,
):
    """Render secondary matter controls and document context only."""
    from document_manager import get_documents

    try:
        docs = get_documents(active_case_id)
    except Exception:
        LOGGER.exception("Unable to load indexed document metadata.")
        docs = []
        st.sidebar.warning("Indexed documents could not be loaded.")

    st.sidebar.caption("MATTER TOOLS")
    finance_clicked = st.sidebar.button(
        "Finance",
        use_container_width=True,
        disabled=active_case_id is None,
        type="primary" if st.session_state.get("m55_main_view") == "finance" else "secondary",
    )
    if finance_clicked:
        set_matter_overview_view(st.session_state, False)
        st.session_state["ppr3_legal_issue_dashboard_view"] = False
        st.session_state["u8_evidence_inspection_view"] = False
        st.session_state["m7_source_evidence_view"] = False
        st.session_state["m6_workspace_view"] = None
        st.session_state["ux_d2_documents_view"] = False
        st.session_state["ux_d2_drafts_view"] = False
        st.session_state.pop("case_operator_workspace_case_id", None)
        st.session_state.pop("mw1_task_workspace_case_id", None)
        st.session_state["m55_main_view"] = "finance"
        st.rerun()

    selected_documents: list[str] = []
    with st.sidebar.expander("Documents in context", expanded=False):
        if active_case_id is not None and not docs:
            st.info("No indexed documents are assigned to this matter yet.")
        elif not docs:
            st.info("No indexed documents found.")
        for filename in docs:
            if st.checkbox(filename, value=True, key=f"document_{active_case_id or 'legacy'}_{filename}"):
                selected_documents.append(filename)

    st.sidebar.caption("Matter navigation is in the solicitor bar above the working page.")
    if active_case_id is not None:
        st.sidebar.caption(f"{len(docs)} document(s) in this matter")
    show_matter_source_import(active_case_id)
    return selected_documents, False
