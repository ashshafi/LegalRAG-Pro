"""Streamlit sidebar for case-scoped documents and tribunal tools."""

from __future__ import annotations

import logging

import streamlit as st

from document_upload import DocumentUploadError, upload_case_pdf

LOGGER = logging.getLogger(__name__)


def _show_case_upload(active_case_id: str | None, docs: list[str]) -> None:
    """Display the case-aware PDF upload control."""

    st.sidebar.subheader("➕ Add document")

    if active_case_id is None:
        st.sidebar.caption(
            "Create or select a case before uploading a PDF."
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
            "A document with this filename is already indexed in the active case."
        )
        return

    size_mb = uploaded_file.size / (1024 * 1024)
    st.sidebar.caption(
        f"{uploaded_file.name} · {size_mb:.2f} MB · will be indexed to the active case"
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


def show_sidebar(active_case_id: str | None = None):
    """Display document selection and tribunal tools.

    When a case is active, only documents indexed/assigned to that case are
    displayed. With no active case the historic global document listing remains
    available for backwards compatibility.
    """

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
            "No documents are assigned to this case yet. "
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
    st.sidebar.title("⚖ Tribunal Tools")

    tools_disabled = active_case_id is not None and not docs

    timeline_clicked = st.sidebar.button(
        "📅 Timeline",
        use_container_width=True,
        disabled=tools_disabled,
    )

    st.sidebar.button(
        "📚 Evidence Explorer",
        use_container_width=True,
        disabled=tools_disabled,
    )

    st.sidebar.button(
        "👤 People Explorer",
        use_container_width=True,
        disabled=tools_disabled,
    )

    st.sidebar.button(
        "📑 Compare Documents",
        use_container_width=True,
        disabled=tools_disabled,
    )

    st.sidebar.button(
        "📄 Reports",
        use_container_width=True,
        disabled=tools_disabled,
    )

    st.sidebar.divider()
    st.sidebar.title("📊 Status")

    st.sidebar.success("OpenAI Connected")
    st.sidebar.success("Chroma Connected")

    if active_case_id is not None:
        st.sidebar.info(f"{len(docs)} document(s) in active case")
    else:
        st.sidebar.info(f"{len(docs)} document(s) indexed")

    return selected_documents, timeline_clicked
