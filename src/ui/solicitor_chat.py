"""Solicitor-facing Ask facade with authoritative application-state routing."""
from __future__ import annotations

import re

import streamlit as st
import ui.chat as base

from ui.solicitor_task_state import recommended_next_approved_task


def _normalise_question(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value).casefold()))


def _is_recommended_task_question(question: str) -> bool:
    prepared = _normalise_question(question)
    explicit = (
        "recommended next approved task",
        "next approved task",
        "recommended approved task",
        "recommended task for this matter",
        "what task should i work on next",
    )
    return any(phrase in prepared for phrase in explicit)


def _application_task_result(case_id: str) -> dict:
    task = recommended_next_approved_task(case_id)
    if task is None:
        answer = (
            "Case Operator currently has no READY approved task to recommend. "
            "Blocked and unavailable approved work remains preserved in Case Operator."
        )
    else:
        answer = "Recommended next approved task\n\n" + task.title
        if task.issue_name:
            answer += "\n\nRelated issue: " + task.issue_name
        if task.why_it_matters:
            answer += "\n\nWhy this matters / work to do: " + task.why_it_matters
    return {
        "answer": answer,
        "sources": [],
        "search_results": [],
        "application_state_answer": True,
        "application_state_authority": "Case Operator approved-task queue",
    }


def _coverage_is_contradictory(result: dict) -> bool:
    sources = result.get("sources")
    receipt = result.get("evidence_search_receipt")
    if not isinstance(sources, (list, tuple)) or not sources or receipt is None:
        return False
    counts = (
        base._field(receipt, "documents_completely_expanded", None),
        base._field(receipt, "pages_inspected", None),
        base._field(receipt, "chunks_inspected", None),
    )
    try:
        return all(int(value or 0) == 0 for value in counts)
    except (TypeError, ValueError):
        return False


def _show_sources(result: dict) -> None:
    sources = result.get("sources")
    if not isinstance(sources, (list, tuple)):
        sources = []
    st.divider()
    if result.get("evidence_search_receipt") is not None:
        st.subheader("📚 Inspected Evidence")
        st.caption(
            "Evidence inspected by the governed answer search; this is not the relied-upon subset."
        )
    else:
        st.subheader("📚 Evidence")
    for source in sources:
        if not isinstance(source, dict):
            continue
        with st.expander(base.build_evidence_heading(source)):
            document_label = source.get("source_label", "Unclassified evidence")
            chunk_label = source.get("chunk_source_label", "Unclassified evidence")
            semantic_label = source.get("semantic_source_label", chunk_label)
            primary_label = source.get("primary_source_label", "Unclassified source")
            provenance_method = source.get("chunk_provenance_method", "unknown")
            provenance_basis = source.get("provenance_basis", "unknown")
            provenance_confidence = source.get("provenance_confidence", "low")
            provenance_warning = source.get("provenance_warning", "")
            knowledge_signal = source.get("knowledge_signal_label", "No explicit knowledge indicator detected")
            st.caption(
                f"Semantic provenance: {semantic_label} · confidence: {provenance_confidence} · basis: {provenance_basis}"
            )
            st.caption(
                f"Retrieval provenance: {chunk_label} · {primary_label} · method: {provenance_method}"
            )
            st.caption(f"Knowledge/awareness signal: {knowledge_signal}")
            if provenance_warning:
                st.caption(f"Provenance caution: {provenance_warning}")
            if semantic_label != document_label:
                st.caption(f"Container classification: {document_label}")
            st.write(source.get("text", ""))


def _show_result(result: dict) -> None:
    st.subheader("📄 Answer")
    st.write(result.get("answer", ""))
    if result.get("application_state_answer"):
        st.info(
            "This answer comes from the authoritative Case Operator approved-task queue, "
            "not from document retrieval or model inference."
        )
        st.caption("Application-state authority: " + str(result.get("application_state_authority", "Case Operator")))
        return

    base._show_governed_answer_provenance(result)
    base._show_reference_findings(result)
    _show_sources(result)
    if _coverage_is_contradictory(result):
        st.divider()
        st.subheader("📊 Coverage")
        st.warning(
            "The search receipt reports zero inspected documents/pages/chunks while inspected evidence is displayed. "
            "Coverage counts are suppressed because the presentation is internally inconsistent; no zero-inspection conclusion should be drawn."
        )
    else:
        base._show_evidence_coverage(result)


def show_solicitor_chat(selected_documents, timeline_clicked, active_case_id: str | None = None):
    """Render Ask while routing explicit application-state questions deterministically."""
    if "last_question" not in st.session_state:
        st.session_state.last_question = ""
    if "last_result" not in st.session_state:
        st.session_state.last_result = None
    if "show_timeline" not in st.session_state:
        st.session_state.show_timeline = False
    if "last_result_case_id" not in st.session_state:
        st.session_state.last_result_case_id = active_case_id
    if st.session_state.last_result_case_id != active_case_id:
        st.session_state.last_question = ""
        st.session_state.last_result = None
        st.session_state.show_timeline = False
        st.session_state.pop(base._QUESTION_INPUT_KEY, None)
        st.session_state.last_result_case_id = active_case_id
    if timeline_clicked:
        st.session_state.show_timeline = True

    st.header("💬 AI Assistant")
    base._show_conversation_history(active_case_id)

    with base._question_form():
        question = base._question_text_area("Ask a legal question", key=base._QUESTION_INPUT_KEY)
        if base._question_form_submit_button("🔍 Ask"):
            if not question:
                st.warning("Please enter a question.")
                return

            submitted_question = question
            if active_case_id is not None and _is_recommended_task_question(question):
                result = _application_task_result(active_case_id)
            else:
                if active_case_id is not None and not selected_documents:
                    st.warning(
                        "The active case has no selected indexed documents. Assign or index documents before asking a case-specific question."
                    )
                    return
                if active_case_id is not None:
                    question = base.resolve_follow_up_question(
                        question,
                        base._history_for_case(active_case_id),
                        active_case_id=active_case_id,
                    )
                with st.spinner("Searching evidence..."):
                    result = base.ask_with_reference_findings(
                        question,
                        selected_documents,
                        case_id=active_case_id,
                    )

            st.session_state.last_question = submitted_question
            st.session_state.last_result = result
            st.session_state.last_result_case_id = active_case_id
            base._append_history_turn(
                question=submitted_question,
                result=result,
                active_case_id=active_case_id,
            )

    if st.session_state.last_result is not None:
        _show_result(st.session_state.last_result)

    if st.session_state.show_timeline:
        if st.session_state.last_result is None:
            st.info("Ask a question first to generate a timeline.")
            return
        search_results = st.session_state.last_result.get("search_results", [])
        events = base.extract_timeline_events(search_results)
        events = base.sort_events(events)
        st.divider()
        base.show_timeline(events)


__all__ = ["show_solicitor_chat", "_is_recommended_task_question", "_coverage_is_contradictory"]
