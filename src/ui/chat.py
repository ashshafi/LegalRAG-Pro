"""Streamlit chat interface for LegalRAG Pro."""

from __future__ import annotations

import streamlit as st

from features.timeline import extract_timeline_events, sort_events
from legalrag import ask
from ui.timeline import show_timeline


def show_chat(
    selected_documents,
    timeline_clicked,
    active_case_id: str | None = None,
):
    """Render the legal assistant and keep results scoped to the active case."""

    if "last_question" not in st.session_state:
        st.session_state.last_question = ""

    if "last_result" not in st.session_state:
        st.session_state.last_result = None

    if "show_timeline" not in st.session_state:
        st.session_state.show_timeline = False

    if "last_result_case_id" not in st.session_state:
        st.session_state.last_result_case_id = active_case_id

    if st.session_state.last_result_case_id != active_case_id:
        st.session_state.last_result = None
        st.session_state.show_timeline = False
        st.session_state.last_result_case_id = active_case_id

    if timeline_clicked:
        st.session_state.show_timeline = True

    st.header("💬 AI Assistant")

    question = st.text_input(
        "Ask a legal question",
        value=st.session_state.last_question,
    )

    if st.button("🔍 Ask"):
        if not question:
            st.warning("Please enter a question.")
            return

        if active_case_id is not None and not selected_documents:
            st.warning(
                "The active case has no selected indexed documents. "
                "Assign or index documents before asking a case-specific question."
            )
            return

        with st.spinner("Searching evidence..."):
            result = ask(
                question,
                selected_documents,
                case_id=active_case_id,
            )

        st.session_state.last_question = question
        st.session_state.last_result = result
        st.session_state.last_result_case_id = active_case_id

    if st.session_state.last_result is not None:
        result = st.session_state.last_result

        st.subheader("📄 Answer")
        st.write(result["answer"])

        st.divider()
        st.subheader("📚 Evidence")

        for source in result["sources"]:
            with st.expander(
                f"📄 {source['file']} — Page {source['page']}"
            ):
                st.write(source["text"])

    if st.session_state.show_timeline:
        if st.session_state.last_result is None:
            st.info("Ask a question first to generate a timeline.")
            return

        events = extract_timeline_events(
            st.session_state.last_result["search_results"]
        )
        events = sort_events(events)

        st.divider()
        show_timeline(events)
