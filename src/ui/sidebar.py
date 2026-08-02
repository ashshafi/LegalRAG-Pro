"""Streamlit sidebar for case-scoped documents and tribunal tools."""

from __future__ import annotations

import logging

import streamlit as st

LOGGER = logging.getLogger(__name__)


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
            "Use 'Assign legacy documents' above or index a PDF for this case."
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
