"""Streamlit chat interface for LegalRAG Pro."""

from __future__ import annotations

import streamlit as st

from evidence_display import build_evidence_heading
from features.timeline import extract_timeline_events, sort_events
from evidence_reference_bridge import ask_with_reference_findings
from follow_up_context import resolve_follow_up_question
from ui.timeline import show_timeline


def _show_reference_findings(result: dict) -> None:
    warning = result.get("evidence_reference_resolution_warning")
    payload = result.get("evidence_reference_resolution")

    if warning:
        st.warning(str(warning))
        return
    if not isinstance(payload, dict):
        return

    receipt = payload.get("receipt")
    findings = payload.get("findings")
    if not isinstance(receipt, dict) or not isinstance(findings, list) or not findings:
        return

    st.divider()
    st.subheader("🔗 Referenced Evidence")
    st.caption(
        "Reference-resolution coverage: "
        f"{receipt.get('documents_completely_expanded', 0)}/"
        f"{len(receipt.get('searched_document_ids', []))} governed documents · "
        "whole case corpus complete: "
        f"{'yes' if receipt.get('case_corpus_complete') else 'no'}"
    )

    for index, finding in enumerate(findings, start=1):
        if not isinstance(finding, dict):
            continue
        status = str(finding.get("status", "UNRESOLVED_REFERENCE"))
        reference_text = str(finding.get("reference_text", ""))
        with st.expander(f"Reference {index} — {status}", expanded=False):
            st.text(f"Referenced item: {reference_text}")
            st.text(f"Status: {status}")
            matched_docs = finding.get("matched_document_ids") or []
            matched_keys = finding.get("matched_evidence_keys") or []
            st.text(
                "Matched governed document IDs: "
                + (", ".join(str(value) for value in matched_docs) if matched_docs else "none")
            )
            st.text(
                "Matched governed evidence keys: "
                + (", ".join(str(value) for value in matched_keys) if matched_keys else "none")
            )
            st.text(f"Deterministic basis: {finding.get('basis', '')}")

    if receipt.get("case_corpus_complete"):
        st.caption(
            "POSSIBLE_REFERENCED_BUT_NOT_LOCATED means no governed match was found "
            "after complete case-corpus inspection; it does not prove the item never existed."
        )


def _field(payload, name: str, default=None):
    """Read one presentation field from a mapping or immutable receipt object."""
    if isinstance(payload, dict):
        return payload.get(name, default)
    return getattr(payload, name, default)


def _display_value(value):
    """Return the serial display value of an enum-like presentation field."""
    return getattr(value, "value", value)


def _show_governed_answer_provenance(result: dict) -> None:
    """Render only already-validated B15 statement/reliance metadata."""
    if result.get("analytical_authority_mode") != "applied":
        return

    bindings = result.get("answer_statement_bindings")
    relied_evidence_keys = result.get("relied_evidence_keys")
    if (
        not isinstance(bindings, list)
        or not bindings
        or not isinstance(relied_evidence_keys, list)
        or any(not isinstance(binding, dict) for binding in bindings)
        or any(not isinstance(key, str) or not key for key in relied_evidence_keys)
    ):
        return

    for binding in bindings:
        refs = binding.get("source_proposition_refs")
        evidence_keys = binding.get("evidence_keys")
        if (
            not isinstance(binding.get("statement_id"), str)
            or not isinstance(binding.get("text"), str)
            or not isinstance(binding.get("source_status"), str)
            or not isinstance(refs, list)
            or not refs
            or any(not isinstance(ref, dict) for ref in refs)
            or not isinstance(evidence_keys, list)
            or not evidence_keys
            or any(not isinstance(key, str) or not key for key in evidence_keys)
        ):
            return

    st.divider()
    st.subheader("🧭 Governed Answer Provenance")
    authority_id = result.get("analytical_authority_id")
    activation_id = result.get("analytical_activation_id")
    reason = result.get("analytical_authority_reason")
    st.caption(
        "Analytical authority: applied"
        + (f" · authority: {authority_id}" if authority_id else "")
        + (f" · activation: {activation_id}" if activation_id else "")
    )
    if reason:
        st.caption(f"Authority routing: {reason}")

    for index, binding in enumerate(bindings, start=1):
        source_status = binding["source_status"]
        with st.expander(
            f"Validated statement {index} — {source_status}",
            expanded=False,
        ):
            st.text(f"Statement ID: {binding['statement_id']}")
            st.write(binding["text"])
            st.text(f"Frozen source status: {source_status}")
            st.text("Source proposition coordinates:")
            for ref in binding["source_proposition_refs"]:
                st.text(
                    "- "
                    f"{ref.get('issue_analysis_id', '')} / "
                    f"{ref.get('element_id', '')} / "
                    f"proposition {ref.get('source_proposition_index', '')}"
                )
            st.text("Exact relied evidence keys for this statement:")
            for evidence_key in binding["evidence_keys"]:
                st.text(f"- {evidence_key}")

    st.caption(
        "Exact relied-upon evidence keys from validated B15 bindings; "
        "not inferred from inspected sources or answer text."
    )
    for evidence_key in relied_evidence_keys:
        st.text(f"Relied evidence: {evidence_key}")


def _show_evidence_coverage(result: dict) -> None:
    """Render the existing U8 search receipt as coverage, never as reliance."""
    receipt = result.get("evidence_search_receipt")
    if receipt is None:
        return

    st.divider()
    st.subheader("📊 Coverage")
    st.caption(
        "Governed evidence-search coverage. This records what was inspected; "
        "it does not identify what the answer relied upon."
    )
    st.text(
        "Search mode: "
        f"{_display_value(_field(receipt, 'search_mode', 'unknown'))}"
        " · completion: "
        f"{_display_value(_field(receipt, 'completion', 'unknown'))}"
        " · whole case corpus complete: "
        f"{'yes' if _field(receipt, 'case_corpus_complete', False) else 'no'}"
    )
    st.text(
        "Inspected: "
        f"{_field(receipt, 'documents_completely_expanded', '?')} documents · "
        f"{_field(receipt, 'pages_inspected', '?')} pages · "
        f"{_field(receipt, 'chunks_inspected', '?')} chunks"
    )
    st.text(
        "Case corpus: "
        f"{_field(receipt, 'case_document_count', '?')} documents · "
        f"{_field(receipt, 'case_page_count', '?')} pages · "
        f"{_field(receipt, 'case_chunk_count', '?')} chunks"
    )
    st.text(
        "Negative-finding scope: "
        f"{_display_value(_field(receipt, 'negative_finding_scope', 'none'))}"
        " · permitted: "
        f"{'yes' if _field(receipt, 'negative_finding_permitted', False) else 'no'}"
    )


_CHAT_HISTORY_KEY = "conversation_turn_history"
_NO_ACTIVE_CASE_HISTORY_KEY = "__no_active_case__"
_QUESTION_INPUT_KEY = "legal_question_input"


def _history_scope_key(active_case_id: str | None) -> str:
    """Return the session-local history partition for the active case."""
    if isinstance(active_case_id, str) and active_case_id:
        return active_case_id
    return _NO_ACTIVE_CASE_HISTORY_KEY


def _valid_history_turn(turn) -> bool:
    """Return whether a stored presentation turn has the minimum safe shape."""
    if not isinstance(turn, dict):
        return False
    question = turn.get("question")
    result = turn.get("result")
    return (
        isinstance(question, str)
        and bool(question)
        and isinstance(result, dict)
        and "answer" in result
    )


def _history_store() -> dict[str, list[dict]]:
    """Return validated session-local history storage, failing closed if malformed."""
    store = st.session_state.get(_CHAT_HISTORY_KEY)
    if not isinstance(store, dict):
        store = {}
        st.session_state[_CHAT_HISTORY_KEY] = store
    return store


def _history_for_case(active_case_id: str | None) -> list[dict]:
    """Return only valid turns for the active case without cross-case fallback."""
    store = _history_store()
    scope_key = _history_scope_key(active_case_id)
    turns = store.get(scope_key)
    if turns is None:
        return []
    if not isinstance(turns, list) or any(not _valid_history_turn(turn) for turn in turns):
        store[scope_key] = []
        return []
    return turns


def _append_history_turn(
    *,
    question: str,
    result: dict,
    active_case_id: str | None,
) -> None:
    """Append one completed governed turn to presentation-only session history."""
    if not question or not isinstance(result, dict) or "answer" not in result:
        return
    store = _history_store()
    scope_key = _history_scope_key(active_case_id)
    turns = _history_for_case(active_case_id)
    if scope_key not in store:
        store[scope_key] = turns
    turns.append({"question": question, "result": result})


def _show_conversation_history(active_case_id: str | None) -> None:
    """Render prior completed turns without using them as answer context."""
    turns = _history_for_case(active_case_id)
    if not turns:
        return

    current_result = None
    if (
        st.session_state.get("last_result_case_id") == active_case_id
        and st.session_state.get("last_result") is not None
    ):
        current_result = st.session_state.get("last_result")

    visible_turns = turns
    if current_result is not None and turns[-1].get("result") is current_result:
        visible_turns = turns[:-1]
    if not visible_turns:
        return

    st.subheader("🗂 Conversation History")
    st.caption(
        "Session-local history for this case only. Prior completed turns are not legal or "
        "evidential authority; their rendered results are presentation-only. For an active "
        "case, a bounded same-case excerpt may be used only to resolve a context-dependent "
        "follow-up into a standalone current question. That question then follows the normal "
        "governed answer/retrieval path; prior-result metadata, evidence, provenance, and "
        "authority are not inherited."
    )
    for index, turn in enumerate(visible_turns, start=1):
        with st.expander(f"Turn {index} — {turn['question']}", expanded=False):
            st.text("Question:")
            st.write(turn["question"])
            st.text("Answer:")
            st.write(turn["result"]["answer"])



def _question_form():
    form = getattr(st, "form", None)
    if form is None:
        from contextlib import nullcontext
        return nullcontext()
    return form(key="assistant_question_form", clear_on_submit=False)


def _question_text_area(label, **kwargs):
    text_area = getattr(st, "text_area", None)
    if text_area is not None:
        return text_area(label, **kwargs)
    return st.text_input(label, **kwargs)


def _question_form_submit_button(label):
    submit = getattr(st, "form_submit_button", None)
    if submit is not None:
        return submit(label)
    return st.button(label)


def _receipt_field(receipt, name: str, default=None):
    if isinstance(receipt, dict):
        return receipt.get(name, default)
    return getattr(receipt, name, default)


def _enum_value(value):
    return getattr(value, "value", value)


def _show_new_ai_finding_provenance_summary(result: dict) -> None:
    """Render compact solicitor-facing provenance for a New AI Finding."""

    if not result.get("new_ai_finding"):
        return

    st.divider()
    st.subheader("Sources & provenance")
    st.caption(
        "Source documents and page references used in this provisional finding "
        "are identified inline in the answer above."
    )

    receipt = result.get("evidence_search_receipt")
    if receipt is not None:
        mode = _enum_value(_receipt_field(receipt, "search_mode", "unknown"))
        documents = _receipt_field(receipt, "documents_inspected", None)
        if documents is None:
            documents = _receipt_field(receipt, "documents_completely_expanded", 0)
        pages = _receipt_field(receipt, "pages_inspected", 0)
        chunks = _receipt_field(receipt, "chunks_inspected", 0)
        corpus_complete = bool(_receipt_field(receipt, "case_corpus_complete", False))
        st.caption(
            "Inspection scope: "
            f"{documents} document(s) ? {pages} page(s) ? {chunks} chunk(s) "
            f"? mode: {mode} ? whole case corpus complete: "
            f"{'yes' if corpus_complete else 'no'}"
        )

    payload = result.get("evidence_reference_resolution")
    if isinstance(payload, dict):
        findings = payload.get("findings")
        if isinstance(findings, list) and findings:
            counts: dict[str, int] = {}
            for finding in findings:
                if not isinstance(finding, dict):
                    continue
                status = str(finding.get("status", "UNRESOLVED_REFERENCE"))
                counts[status] = counts.get(status, 0) + 1
            if counts:
                summary = " ? ".join(
                    f"{status.replace('_', ' ').title()}: {count}"
                    for status, count in sorted(counts.items())
                )
                st.caption(f"Reference-resolution summary: {summary}")

    warning = result.get("evidence_reference_resolution_warning")
    if warning:
        st.warning(str(warning))

    st.info(
        "Full inspected-evidence, reference-resolution and technical provenance "
        "detail is available under Sources & Provenance in the Audit section."
    )


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
        st.session_state.last_question = ""
        st.session_state.last_result = None
        st.session_state.show_timeline = False
        st.session_state.pop(_QUESTION_INPUT_KEY, None)
        st.session_state.last_result_case_id = active_case_id

    if timeline_clicked:
        st.session_state.show_timeline = True

    st.header("💬 AI Assistant")

    _show_conversation_history(active_case_id)

    with _question_form():
        question = _question_text_area(
            "Ask a legal question",
            key=_QUESTION_INPUT_KEY,
        )

        if _question_form_submit_button("🔍 Ask"):
            if not question:
                st.warning("Please enter a question.")
                return

            if active_case_id is not None and not selected_documents:
                st.warning(
                    "The active case has no selected indexed documents. "
                    "Assign or index documents before asking a case-specific question."
                )
                return

            submitted_question = question
            if active_case_id is not None:
                question = resolve_follow_up_question(
                    question,
                    _history_for_case(active_case_id),
                    active_case_id=active_case_id,
                )

            with st.spinner("Searching evidence..."):
                result = ask_with_reference_findings(
                    question,
                    selected_documents,
                    case_id=active_case_id,
                )

            st.session_state.last_question = submitted_question
            st.session_state.last_result = result
            st.session_state.last_result_case_id = active_case_id
            _append_history_turn(
                question=submitted_question,
                result=result,
                active_case_id=active_case_id,
            )

    if st.session_state.last_result is not None:
        result = st.session_state.last_result

        st.subheader("📄 Answer")
        st.write(result["answer"])

        if result.get("new_ai_finding"):
            _show_new_ai_finding_provenance_summary(result)
        else:
            _show_governed_answer_provenance(result)

            _show_reference_findings(result)

            st.divider()
            if result.get("evidence_search_receipt") is not None:
                st.subheader("📚 Inspected Evidence")
                st.caption(
                    "Evidence inspected by the governed U8 answer search; "
                    "this is not the relied-upon subset."
                )
            else:
                st.subheader("📚 Evidence")

            for source in result["sources"]:
                with st.expander(build_evidence_heading(source)):
                    document_label = source.get(
                        "source_label",
                        "Unclassified evidence",
                    )
                    chunk_label = source.get(
                        "chunk_source_label",
                        "Unclassified evidence",
                    )
                    semantic_label = source.get(
                        "semantic_source_label",
                        chunk_label,
                    )
                    primary_label = source.get(
                        "primary_source_label",
                        "Unclassified source",
                    )
                    provenance_method = source.get(
                        "chunk_provenance_method",
                        "unknown",
                    )
                    provenance_basis = source.get("provenance_basis", "unknown")
                    provenance_confidence = source.get("provenance_confidence", "low")
                    provenance_warning = source.get("provenance_warning", "")
                    knowledge_signal = source.get(
                        "knowledge_signal_label",
                        "No explicit knowledge indicator detected",
                    )
                    st.caption(
                        f"Semantic provenance: {semantic_label} "
                        f"· confidence: {provenance_confidence} "
                        f"· basis: {provenance_basis}"
                    )
                    st.caption(
                        f"Retrieval provenance: {chunk_label} "
                        f"· {primary_label} "
                        f"· method: {provenance_method}"
                    )
                    st.caption(f"Knowledge/awareness signal: {knowledge_signal}")
                    if provenance_warning:
                        st.caption(f"Provenance caution: {provenance_warning}")
                    if semantic_label != document_label:
                        st.caption(
                            f"Container classification: {document_label}"
                        )
                    st.write(source["text"])

            _show_evidence_coverage(result)

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
