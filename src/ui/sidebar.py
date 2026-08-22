"""Streamlit sidebar for case-scoped documents and matter-workspace navigation."""

from __future__ import annotations

import logging

import streamlit as st

from ui.matter_overview import set_matter_overview_view

from document_upload import DocumentUploadError, upload_case_pdf

LOGGER = logging.getLogger(__name__)


def _show_case_upload(active_case_id: str | None, docs: list[str]) -> None:
    """Display the case-aware PDF upload control."""
    st.sidebar.subheader("➕ Add document")
    if active_case_id is None:
        st.sidebar.caption(
            "Create or select a matter before uploading a PDF."
        )
        return

    nonce = int(st.session_state.get("case_upload_nonce", 0))
    uploaded_file = st.sidebar.file_uploader(
        "Upload PDF",
        type=["pdf"],
        key=f"case_pdf_upload_{active_case_id}_{nonce}",
    )
    if uploaded_file is None:
        return
    if uploaded_file.name in docs:
        st.sidebar.warning(
            "A document with this filename is already indexed in the active matter."
        )
        return
    size_mb = uploaded_file.size / (1024 * 1024)
    st.sidebar.caption(
        f"{uploaded_file.name} · {size_mb:.2f} MB · will be indexed to the active matter"
    )
    if not st.sidebar.button(
        "📥 Upload and Index",
        key=f"index_case_pdf_{active_case_id}_{nonce}",
        use_container_width=True,
    ):
        return
    try:
        with st.sidebar:
            with st.spinner("Uploading and indexing PDF..."):
                result = upload_case_pdf(
                    filename=uploaded_file.name,
                    content=uploaded_file.getvalue(),
                    case_id=active_case_id,
                )
    except DocumentUploadError as exc:
        st.sidebar.error(str(exc))
        return
    except Exception:
        LOGGER.exception("Unexpected error during case-aware PDF upload.")
        st.sidebar.error(
            "The document could not be uploaded. Check the application log for details."
        )
        return
    st.sidebar.success(
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
    """Display document selection and matter-workspace navigation.
    When a case is active, only documents indexed/assigned to that case are
    displayed. With no active case the historic global document listing remains
    available for backwards compatibility.
    """
    st.sidebar.caption("MATTER")
    overview_clicked = st.sidebar.button(
        "▣ Overview",
        use_container_width=True,
        disabled=active_case_id is None,
        help=(
            None
            if active_case_id is not None
            else "Select or create a matter to open its overview."
        ),
    )
    if overview_clicked:
        set_matter_overview_view(st.session_state, True)
        st.session_state["u8_evidence_inspection_view"] = False
        st.session_state["ppr3_legal_issue_dashboard_view"] = False
        st.session_state["m7_source_evidence_view"] = False
        st.session_state["m6_workspace_view"] = None
        st.session_state["m55_main_view"] = "assistant"

    st.sidebar.title("📚 Documents")

    try:
        from document_manager import get_documents
        docs = get_documents(active_case_id)
    except Exception:
        LOGGER.exception("Unable to load indexed document metadata.")
        docs = []
        st.sidebar.warning("Indexed documents could not be loaded.")
    selected_documents: list[str] = []
    if active_case_id is not None and not docs:
        st.sidebar.info(
            "No documents are assigned to this matter yet. "
            "Assign a legacy document above or upload a new PDF below."
        )
    elif not docs:
        st.sidebar.info("No indexed documents found.")
    for filename in docs:
        if st.sidebar.checkbox(
            filename,
            value=True,
            key=f"document_{active_case_id or 'legacy'}_{filename}",
        ):
            selected_documents.append(filename)
    st.sidebar.divider()
    _show_case_upload(active_case_id, docs)

    st.sidebar.divider()
    st.sidebar.caption("CASE INTELLIGENCE")

    tools_disabled = active_case_id is not None and not docs
    timeline_clicked = st.sidebar.button(
        "🕒 Chronology",
        use_container_width=True,
        disabled=tools_disabled,
    )
    if timeline_clicked:
        st.session_state["m7_source_evidence_view"] = False
        st.session_state["m6_workspace_view"] = None
        st.session_state["m55_main_view"] = "assistant"

    evidence_clicked = st.sidebar.button(
        "🔎 Evidence",
        use_container_width=True,
        disabled=not reports_available,
    )
    people_clicked = st.sidebar.button(
        "👥 People",
        use_container_width=True,
        disabled=not reports_available,
    )
    if evidence_clicked:
        st.session_state["m7_source_evidence_view"] = False
        st.session_state["m6_workspace_view"] = "evidence"
    if people_clicked:
        st.session_state["m7_source_evidence_view"] = False
        st.session_state["m6_workspace_view"] = "people"

    dashboard_clicked = st.sidebar.button(
        "⚖️ Legal Issues",
        use_container_width=True,
        disabled=active_case_id is None,
        help=(
            None
            if active_case_id is not None
            else "An active matter is required for Legal Issues."
        ),
    )
    if dashboard_clicked:
        set_matter_overview_view(st.session_state, False)
        st.session_state["ppr3_legal_issue_dashboard_view"] = True
        st.session_state["u8_evidence_inspection_view"] = False
        st.session_state["m7_source_evidence_view"] = False
        st.session_state["m6_workspace_view"] = None
        st.session_state["m55_main_view"] = "assistant"

    st.sidebar.divider()
    st.sidebar.caption("LEGAL WORK")

    workspace_clicked = st.sidebar.button(
        "🧠 Analysis",
        use_container_width=True,
        disabled=not reports_available,
        help=(
            None
            if reports_available
            else "A validated frozen report projection is required for the active matter."
        ),
    )
    if workspace_clicked:
        st.session_state["m7_source_evidence_view"] = False
        st.session_state["m6_workspace_view"] = "traceability"

    assistant_clicked = st.sidebar.button(
        "💬 Assistant",
        use_container_width=True,
        disabled=active_case_id is None,
    )
    if assistant_clicked:
        st.session_state["u8_evidence_inspection_view"] = False
        st.session_state["m7_source_evidence_view"] = False
        st.session_state["m6_workspace_view"] = None
        st.session_state["m55_main_view"] = "assistant"

    st.sidebar.button(
        "✍ Drafting",
        use_container_width=True,
        disabled=True,
        help="Planned legal-work capability; not active in PPR4-M3.",
    )

    reports_clicked = st.sidebar.button(
        "📄 Reports",
        use_container_width=True,
        disabled=not reports_available,
        help=(
            None
            if reports_available
            else "A validated frozen report projection is required for the active matter."
        ),
    )
    if reports_clicked:
        st.session_state["m7_source_evidence_view"] = False
        st.session_state["m6_workspace_view"] = None
        st.session_state["m55_main_view"] = "reports"

    st.sidebar.divider()
    st.sidebar.caption("AUDIT")

    source_evidence_clicked = st.sidebar.button(
        "🔗 Sources & Provenance",
        use_container_width=True,
        disabled=not reports_available,
        help=(
            None
            if reports_available
            else "A validated frozen report projection is required for the active matter."
        ),
    )
    if source_evidence_clicked:
        st.session_state["m7_source_evidence_view"] = True
        st.session_state["m6_workspace_view"] = None
        st.session_state["m55_main_view"] = "assistant"

    st.sidebar.button(
        "🛡 Audit Trail",
        use_container_width=True,
        disabled=True,
        help="Planned consolidated audit presentation; not active in PPR4-M3.",
    )

    if (
        timeline_clicked
        or workspace_clicked
        or evidence_clicked
        or people_clicked
        or assistant_clicked
        or source_evidence_clicked
        or reports_clicked
    ):
        set_matter_overview_view(st.session_state, False)
        st.session_state["ppr3_legal_issue_dashboard_view"] = False

    st.sidebar.divider()
    st.sidebar.title("📊 Status")
    if active_case_id is not None:
        st.sidebar.info(f"{len(docs)} document(s) in active matter")
    else:
        st.sidebar.info(f"{len(docs)} document(s) indexed")

    return selected_documents, timeline_clicked
