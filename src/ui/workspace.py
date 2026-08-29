"""Native read-only M6 interactive workspace over CaseReportProjection."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Iterable

import streamlit as st

from case_reporting.models import CaseReportProjection, StatusView
from case_reporting.validation import validate_case_report_projection
from workspace_index import (
    DocumentGroupKey,
    WorkspaceIndex,
    WorkspaceIndexError,
    WorkspaceObjectKey,
    build_workspace_index,
    literal_query_matches,
)

_INVALID_WORKSPACE_TEXT = (
    "The frozen report projection could not be validated for interactive navigation. "
    "The workspace has not been displayed."
)
_NO_CASE_TEXT = "Select an active case to use the interactive workspace."
_NO_PROJECTION_TEXT = "No frozen report projection is available for this case."
_EMPTY_FROZEN_TEXT = "None recorded in the frozen report projection."
_NO_FILTER_MATCH_TEXT = "No items match the current workspace filters."
_UNIQUE_ELEMENT_TEXT = "No unique element coordinate can be resolved from the frozen projection."
_VIEW_LABELS = {
    "traceability": "Exact Traceability",
    "evidence": "Evidence Explorer",
    "chronology": "Frozen Chronology",
    "people": "People / Participants Explorer",
    "comparison": "Projection Evidence-Use Comparison",
    "review": "Issue Review",
}
_VIEW_ORDER = tuple(_VIEW_LABELS)
_TRACE_LABELS = {
    "issue": "Issue",
    "element": "Element",
    "statement": "Statement",
    "finding": "Finding",
    "event": "Event",
    "assertion": "Event Assertion",
    "conflict": "Conflict",
    "gap": "Gap",
    "risk": "Risk",
    "question": "Priority Question",
    "citation": "Citation",
}
_TRACE_ORDER = tuple(_TRACE_LABELS)
_BINDING_KEYS = (
    "m6_workspace_case_id",
    "m6_workspace_projection_id",
    "m6_workspace_projection_payload_sha256",
    "m6_workspace_manifest_id",
)
_M6_KEYS = {
    "m6_workspace_case_id",
    "m6_workspace_projection_id",
    "m6_workspace_projection_payload_sha256",
    "m6_workspace_manifest_id",
    "m6_workspace_view",
    "m6_trace_kind",
    "m6_trace_query",
    "m6_trace_selected_key",
    "m6_evidence_query",
    "m6_evidence_documents",
    "m6_evidence_source_types",
    "m6_evidence_statuses",
    "m6_evidence_provenance_types",
    "m6_evidence_provenance_confidences",
    "m6_evidence_authors",
    "m6_evidence_parties",
    "m6_evidence_issue_ids",
    "m6_chronology_query",
    "m6_chronology_event_types",
    "m6_chronology_participants",
    "m6_chronology_occurrence_statuses",
    "m6_chronology_timing_statuses",
    "m6_chronology_confidences",
    "m6_chronology_issue_ids",
    "m6_people_query",
    "m6_people_contexts",
    "m6_people_selected_value",
    "m6_compare_left_key",
    "m6_compare_right_key",
}


def _defaults() -> dict[str, object]:
    return {
        "m6_workspace_view": None,
        "m6_trace_kind": "issue",
        "m6_trace_query": "",
        "m6_trace_selected_key": None,
        "m6_evidence_query": "",
        "m6_evidence_documents": [],
        "m6_evidence_source_types": [],
        "m6_evidence_statuses": [],
        "m6_evidence_provenance_types": [],
        "m6_evidence_provenance_confidences": [],
        "m6_evidence_authors": [],
        "m6_evidence_parties": [],
        "m6_evidence_issue_ids": [],
        "m6_chronology_query": "",
        "m6_chronology_event_types": [],
        "m6_chronology_participants": [],
        "m6_chronology_occurrence_statuses": [],
        "m6_chronology_timing_statuses": [],
        "m6_chronology_confidences": [],
        "m6_chronology_issue_ids": [],
        "m6_people_query": "",
        "m6_people_contexts": [],
        "m6_people_selected_value": None,
        "m6_compare_left_key": None,
        "m6_compare_right_key": None,
    }


def _binding(active_case_id: str | None, projection: CaseReportProjection | None) -> tuple[object, ...]:
    if projection is None:
        return active_case_id, None, None, None
    return (
        active_case_id,
        projection.report_projection_id,
        projection.projection_payload_sha256,
        projection.manifest.manifest_id,
    )


def synchronise_workspace_session_state(
    active_case_id: str | None,
    projection: CaseReportProjection | None,
) -> bool:
    """Bind transient M6 state to the exact frozen four-part projection identity."""

    current = _binding(active_case_id, projection)
    stored = tuple(st.session_state.get(key) for key in _BINDING_KEYS)
    changed = current != stored
    if changed:
        for key, value in zip(_BINDING_KEYS, current, strict=True):
            st.session_state[key] = value
        for key, value in _defaults().items():
            st.session_state[key] = value.copy() if isinstance(value, list) else value
    else:
        for key, value in _defaults().items():
            st.session_state.setdefault(key, value.copy() if isinstance(value, list) else value)
    if st.session_state.get("m6_workspace_view") not in {None, *_VIEW_ORDER}:
        st.session_state["m6_workspace_view"] = None
    if st.session_state.get("m6_trace_kind") not in _TRACE_ORDER:
        st.session_state["m6_trace_kind"] = "issue"
        st.session_state["m6_trace_selected_key"] = None
    return changed


def _text(label: str, value: object) -> None:
    if value is None:
        st.text(f"{label}: Not recorded in the frozen report projection.")
    else:
        st.text(f"{label}: {value}")


def _status(label: str, value: StatusView) -> None:
    st.text(label)
    _text("Raw value", value.raw_value)
    _text("Label", value.label)
    _text("Explanation", value.explanation)
    _text("Qualification code", value.qualification_code)


def _first_values(values: Iterable[object]) -> tuple[object, ...]:
    seen: set[object] = set()
    result: list[object] = []
    for value in values:
        if value is None or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


def _selected(key: str) -> set[object]:
    value = st.session_state.get(key, [])
    return set(value or ())


def _filter_count(shown: int, total: int, active: bool) -> None:
    st.caption(f"Showing {shown} of {total}")
    if active:
        st.caption("Filtered view")


def _reset_keys(keys: Iterable[str]) -> None:
    defaults = _defaults()
    for key in keys:
        value = defaults[key]
        st.session_state[key] = value.copy() if isinstance(value, list) else value


def _format_key(key: WorkspaceObjectKey) -> str:
    if key.secondary_id is None:
        return f"{_TRACE_LABELS[key.kind]} · {key.primary_id}"
    return f"{_TRACE_LABELS[key.kind]} · {key.primary_id} | {key.secondary_id}"


def _render_scalar_fields(value: object) -> None:
    """Render direct frozen dataclass fields as inert text without semantic rewriting."""

    if not is_dataclass(value):
        st.text(str(value))
        return
    for item in fields(value):
        field_value = getattr(value, item.name)
        if isinstance(field_value, StatusView):
            _status(item.name.replace("_", " ").title(), field_value)
            continue
        if isinstance(field_value, tuple) and field_value and is_dataclass(field_value[0]):
            _text(item.name.replace("_", " ").title(), field_value)
            continue
        if is_dataclass(field_value):
            _text(item.name.replace("_", " ").title(), repr(field_value))
            continue
        _text(item.name.replace("_", " ").title(), field_value)


def _trace_keys(index: WorkspaceIndex, kind: str) -> tuple[WorkspaceObjectKey, ...]:
    return {
        "issue": index.issue_keys,
        "element": index.element_keys,
        "statement": index.statement_keys,
        "finding": index.finding_keys,
        "event": index.event_keys,
        "assertion": index.assertion_keys,
        "conflict": index.conflict_keys,
        "gap": index.gap_keys,
        "risk": index.risk_keys,
        "question": index.question_keys,
        "citation": index.citation_keys,
    }[kind]


def _trace_search_values(key: WorkspaceObjectKey, value: object) -> tuple[object, ...]:
    kind = key.kind
    if kind == "issue":
        return (
            value.issue_analysis_id, value.issue_definition_id, value.issue_definition_version,
            value.issue_name, value.original_user_question, value.issue_summary,
            value.position_status.raw_value, value.position_status.label,
            value.confidence.raw_value, value.confidence.label,
        )
    if kind == "element":
        return (
            value.issue_analysis_id, value.element_id, value.element_name, value.legal_question,
            value.analysis_status.raw_value, value.analysis_status.label,
            value.analysis_confidence.raw_value, value.analysis_confidence.label,
            value.legal_significance, value.provisional_analysis, value.unresolved_matters,
        )
    if kind == "statement":
        return (value.report_statement_id, value.category, value.text, value.evidence_keys, value.citation_ids)
    if kind == "finding":
        return (
            value.finding_id, value.finding_type, value.scope, value.category, value.origin,
            value.analytical_bases, value.status.raw_value, value.status.label,
            value.confidence.raw_value, value.confidence.label, value.summary,
            value.controlled_explanation, value.issue_ids, value.related_finding_ids, value.citation_ids,
        )
    if kind == "event":
        return (
            value.event_id, value.description, value.normalized_event_core, value.event_type,
            value.participants, value.occurrence_status.raw_value, value.occurrence_status.label,
            value.timing_status.raw_value, value.timing_status.label, value.confidence.raw_value,
            value.confidence.label, value.citation_ids, value.related_issue_ids,
        )
    if kind == "assertion":
        return (
            value.event_id, value.assertion_id, value.description, value.issue_analysis_id,
            value.element_id, value.evidence_key, value.citation_id, value.source_proposition_index,
            value.occurrence_status.raw_value, value.occurrence_status.label,
            value.timing_status.raw_value, value.timing_status.label,
            value.confidence.raw_value, value.confidence.label, value.extraction_basis,
        )
    if kind == "conflict":
        return (
            value.conflict_id, value.conflict_type, value.scope, value.subject,
            value.status.raw_value, value.status.label, value.materiality.raw_value,
            value.materiality.label, value.related_issue_ids, value.citation_ids,
        )
    if kind == "gap":
        return (
            value.gap_id, value.gap_type, value.scope, value.issue_analysis_id, value.element_id,
            value.description, value.materiality.raw_value, value.materiality.label,
            value.unresolved_question, value.related_finding_ids, value.citation_ids,
        )
    if kind == "risk":
        return (
            value.risk_id, value.risk_type, value.scope, value.materiality.raw_value,
            value.materiality.label, value.description, value.classification_explanation,
            value.basis_finding_ids, value.conflict_ids, value.gap_ids, value.affected_issue_ids,
            value.citation_ids,
        )
    if kind == "question":
        return (
            value.question_id, value.question, value.priority.raw_value, value.priority.label,
            value.basis_type, value.affected_issue_ids, value.affected_element_ids,
            value.finding_ids, value.gap_ids, value.conflict_ids, value.citation_ids,
        )
    return _citation_search_values(value)


def _render_traceability(index: WorkspaceIndex) -> None:
    st.header("Exact Traceability")
    kind = st.selectbox(
        "Object type",
        options=_TRACE_ORDER,
        key="m6_trace_kind",
        format_func=lambda value: _TRACE_LABELS[value],
    )
    query = st.text_input("Literal search", key="m6_trace_query")
    keys = tuple(
        key for key in _trace_keys(index, kind)
        if literal_query_matches(query, _trace_search_values(key, index.object_by_key[key]))
    )
    _filter_count(len(keys), len(_trace_keys(index, kind)), bool(str(query).strip()))
    if not keys:
        st.info(_NO_FILTER_MATCH_TEXT)
        st.session_state["m6_trace_selected_key"] = None
        return
    selected = st.session_state.get("m6_trace_selected_key")
    if selected not in keys:
        st.session_state["m6_trace_selected_key"] = keys[0]
    selected = st.selectbox(
        "Frozen object",
        options=keys,
        key="m6_trace_selected_key",
        format_func=_format_key,
    )
    st.subheader(_format_key(selected))
    _render_scalar_fields(index.object_by_key[selected])
    st.subheader("Exact outgoing references")
    outgoing = index.outgoing[selected]
    if not outgoing:
        st.text(_EMPTY_FROZEN_TEXT)
    for field_name, target in outgoing:
        st.text(f"{field_name} → {_format_key(target)}")
        if st.button(f"Open target · {_format_key(target)} · {field_name}"):
            st.session_state["m6_trace_kind"] = target.kind
            st.session_state["m6_trace_selected_key"] = target
            st.rerun()
    if selected.kind == "question":
        unresolved = index.unresolved_priority_element_ids.get(selected.primary_id, ())
        for element_id in unresolved:
            st.text(f"Affected element ID: {element_id}")
            st.text(_UNIQUE_ELEMENT_TEXT)
    st.subheader("Referenced by")
    reverse = index.backlinks[selected]
    if not reverse:
        st.text(_EMPTY_FROZEN_TEXT)
    for backlink in reverse:
        st.text(f"{_format_key(backlink.source)} · {backlink.source_field}")
        if st.button(f"Open reference · {_format_key(backlink.source)} · {backlink.source_field}"):
            st.session_state["m6_trace_kind"] = backlink.source.kind
            st.session_state["m6_trace_selected_key"] = backlink.source
            st.rerun()



def _review_open_traceability(label: str, key: WorkspaceObjectKey, *, token: str) -> None:
    """Navigate to one already-indexed frozen object without changing analytical state."""

    if st.button(label, key=f"ierw_review_trace::{token}::{key.kind}::{key.primary_id}"):
        st.session_state["m6_trace_kind"] = key.kind
        st.session_state["m6_trace_selected_key"] = key
        st.session_state["m6_workspace_view"] = "traceability"
        st.rerun()


def _render_review_collection(
    index: WorkspaceIndex,
    heading: str,
    kind: str,
    primary_ids: tuple[str, ...],
) -> None:
    """Render exact frozen objects and offer only existing traceability navigation."""

    st.subheader(heading)
    if not primary_ids:
        st.text(_EMPTY_FROZEN_TEXT)
        return

    for ordinal, primary_id in enumerate(primary_ids, start=1):
        key = WorkspaceObjectKey(kind, primary_id)
        value = index.object_by_key.get(key)
        if value is None:
            raise WorkspaceIndexError(
                f"Issue Review references an unknown frozen {kind} object: {primary_id!r}."
            )
        st.text(_format_key(key))
        _render_scalar_fields(value)
        _review_open_traceability(
            f"Open in Exact Traceability · {_format_key(key)}",
            key,
            token=f"{heading}:{ordinal}",
        )


def _render_issue_review(index: WorkspaceIndex) -> None:
    """Compose one issue-centric read-only review from the frozen workspace index."""

    st.header("Issue Review")
    st.caption(
        "Read-only review of the validated frozen report projection. "
        "This view creates no analytical state and performs no retrieval."
    )

    issue_ids = tuple(key.primary_id for key in index.issue_keys)
    if not issue_ids:
        st.info("No frozen legal issues are available in this report projection.")
        st.session_state["ierw_review_issue_id"] = None
        return

    selected_issue_id = st.session_state.get("ierw_review_issue_id")
    if selected_issue_id not in issue_ids:
        st.session_state["ierw_review_issue_id"] = issue_ids[0]

    selected_issue_id = st.selectbox(
        "Frozen issue",
        options=issue_ids,
        key="ierw_review_issue_id",
        format_func=lambda value: index.issues_by_id[value].issue_name,
    )
    issue = index.issues_by_id[selected_issue_id]
    issue_key = WorkspaceObjectKey("issue", selected_issue_id)

    st.subheader(issue.issue_name)
    _text("Issue analysis ID", issue.issue_analysis_id)
    _text("Issue summary", issue.issue_summary)
    _status("Position status", issue.position_status)
    _status("Position confidence", issue.confidence)

    if st.button("Open issue in Exact Traceability", key="ierw_review_open_issue_trace"):
        st.session_state["m6_trace_kind"] = "issue"
        st.session_state["m6_trace_selected_key"] = issue_key
        st.session_state["m6_workspace_view"] = "traceability"
        st.rerun()

    if st.button("Review issue evidence", key="ierw_review_open_issue_evidence"):
        st.session_state["m6_evidence_issue_ids"] = [selected_issue_id]
        st.session_state["m6_workspace_view"] = "evidence"
        st.rerun()

    if st.button("Review issue chronology", key="ierw_review_open_issue_chronology"):
        st.session_state["m6_chronology_issue_ids"] = [selected_issue_id]
        st.session_state["m6_workspace_view"] = "chronology"
        st.rerun()

    direct_ids = tuple(finding.finding_id for finding in issue.direct_findings)
    higher_ids = tuple(finding.finding_id for finding in issue.higher_order_findings)
    question_ids = tuple(
        key.primary_id
        for key in index.question_keys
        if selected_issue_id in index.questions_by_id[key.primary_id].affected_issue_ids
    )

    _render_review_collection(index, "Direct Findings", "finding", direct_ids)
    _render_review_collection(index, "Higher-Order Findings", "finding", higher_ids)
    _render_review_collection(index, "Conflicts", "conflict", tuple(issue.conflict_ids))
    _render_review_collection(index, "Evidence Gaps", "gap", tuple(issue.gap_ids))
    _render_review_collection(index, "Risk Areas", "risk", tuple(issue.risk_ids))
    _render_review_collection(index, "Priority Questions", "question", question_ids)

def _citation_search_values(value) -> tuple[object, ...]:
    return (
        value.citation_id, value.evidence_key, value.citation, value.document_name,
        value.document_id, value.page, value.chunk_id, value.date, value.author, value.parties,
        value.source_type, value.evidence_status, value.provenance_type, value.provenance_basis,
        value.provenance_confidence, value.evidence_use_coordinates,
    )


def _document_label(value: DocumentGroupKey) -> str:
    suffix = value.document_id if value.document_id is not None else "no document ID"
    return f"{value.document_name} · {suffix}"


def _render_citation(index: WorkspaceIndex, citation) -> None:
    st.subheader(f"Citation · {citation.citation_id}")
    for label, value in (
        ("Evidence key", citation.evidence_key),
        ("Citation text", citation.citation),
        ("Document name", citation.document_name),
        ("Document ID", citation.document_id),
        ("Page", citation.page),
        ("Chunk ID", citation.chunk_id),
        ("Date", citation.date),
        ("Author", citation.author),
        ("Parties", citation.parties),
        ("Source type", citation.source_type),
        ("Evidence status", citation.evidence_status),
        ("Provenance type", citation.provenance_type),
        ("Provenance basis", citation.provenance_basis),
        ("Provenance confidence", citation.provenance_confidence),
        ("Evidence-use coordinates", citation.evidence_use_coordinates),
    ):
        _text(label, value)
    st.text("Referenced by")
    key = WorkspaceObjectKey("citation", citation.citation_id)
    backlinks = index.backlinks[key]
    if not backlinks:
        st.text(_EMPTY_FROZEN_TEXT)
    for backlink in backlinks:
        st.text(f"{_format_key(backlink.source)} · {backlink.source_field}")


def _render_evidence(index: WorkspaceIndex) -> None:
    st.header("Evidence Explorer")
    citations = tuple(index.citations_by_id[key.primary_id] for key in index.citation_keys)
    st.text_input("Literal search", key="m6_evidence_query")
    st.multiselect("Document group", index.document_group_keys, key="m6_evidence_documents", format_func=_document_label)
    st.multiselect("Source type", _first_values(item.source_type for item in citations), key="m6_evidence_source_types")
    st.multiselect("Evidence status", _first_values(item.evidence_status for item in citations), key="m6_evidence_statuses")
    st.multiselect("Provenance type", _first_values(item.provenance_type for item in citations), key="m6_evidence_provenance_types")
    st.multiselect("Provenance confidence", _first_values(item.provenance_confidence for item in citations), key="m6_evidence_provenance_confidences")
    st.multiselect("Author", _first_values(item.author for item in citations), key="m6_evidence_authors")
    st.multiselect("Party", _first_values(party for item in citations for party in item.parties), key="m6_evidence_parties")
    st.multiselect("Issue ID", _first_values(coord[0] for item in citations for coord in item.evidence_use_coordinates), key="m6_evidence_issue_ids")

    selected_documents = _selected("m6_evidence_documents")
    source_types = _selected("m6_evidence_source_types")
    statuses = _selected("m6_evidence_statuses")
    provenance_types = _selected("m6_evidence_provenance_types")
    provenance_confidences = _selected("m6_evidence_provenance_confidences")
    authors = _selected("m6_evidence_authors")
    parties = _selected("m6_evidence_parties")
    issue_ids = _selected("m6_evidence_issue_ids")
    query = str(st.session_state.get("m6_evidence_query", ""))

    def keep(item) -> bool:
        group = DocumentGroupKey(item.document_name, item.document_id)
        return (
            (not selected_documents or group in selected_documents)
            and (not source_types or item.source_type in source_types)
            and (not statuses or item.evidence_status in statuses)
            and (not provenance_types or item.provenance_type in provenance_types)
            and (not provenance_confidences or item.provenance_confidence in provenance_confidences)
            and (not authors or item.author in authors)
            and (not parties or bool(parties.intersection(item.parties)))
            and (not issue_ids or bool(issue_ids.intersection(coord[0] for coord in item.evidence_use_coordinates)))
            and literal_query_matches(query, _citation_search_values(item))
        )

    visible = tuple(item for item in citations if keep(item))
    active = any((selected_documents, source_types, statuses, provenance_types, provenance_confidences, authors, parties, issue_ids)) or bool(query.strip())
    _filter_count(len(visible), len(citations), active)
    if st.button("Reset filters"):
        _reset_keys(key for key in _M6_KEYS if key.startswith("m6_evidence_"))
        st.rerun()
    if not visible:
        st.info(_NO_FILTER_MATCH_TEXT if active else _EMPTY_FROZEN_TEXT)
        return
    for citation in visible:
        _render_citation(index, citation)


def _event_search_values(event) -> tuple[object, ...]:
    temporal = event.canonical_temporal_extent.display_text if event.canonical_temporal_extent is not None else None
    values: list[object] = [
        event.event_id, event.description, event.normalized_event_core, event.event_type, event.participants,
        event.occurrence_status.raw_value, event.occurrence_status.label, event.occurrence_status.explanation,
        event.occurrence_status.qualification_code, event.timing_status.raw_value, event.timing_status.label,
        event.timing_status.explanation, event.timing_status.qualification_code, event.confidence.raw_value,
        event.confidence.label, event.confidence.explanation, event.confidence.qualification_code, temporal,
        event.citation_ids, event.related_issue_ids, event.related_element_coordinates,
    ]
    for assertion in event.assertions:
        assertion_temporal = assertion.temporal_extent.display_text if assertion.temporal_extent is not None else None
        values.extend((
            assertion.assertion_id, assertion.description, assertion.issue_analysis_id, assertion.element_id,
            assertion.evidence_key, assertion.citation_id, assertion.source_proposition_index,
            assertion.occurrence_status.raw_value, assertion.occurrence_status.label,
            assertion.occurrence_status.explanation, assertion.occurrence_status.qualification_code,
            assertion.timing_status.raw_value, assertion.timing_status.label, assertion.timing_status.explanation,
            assertion.timing_status.qualification_code, assertion.confidence.raw_value, assertion.confidence.label,
            assertion.confidence.explanation, assertion.confidence.qualification_code, assertion_temporal,
            assertion.extraction_basis,
        ))
    return tuple(values)


def _render_chronology(index: WorkspaceIndex) -> None:
    st.header("Frozen Chronology")
    events = tuple(index.events_by_id[key.primary_id] for key in index.event_keys)
    st.text_input("Literal search", key="m6_chronology_query")
    st.multiselect("Event type", _first_values(item.event_type for item in events), key="m6_chronology_event_types")
    st.multiselect("Participant", _first_values(value for item in events for value in item.participants), key="m6_chronology_participants")
    st.multiselect("Occurrence raw status", _first_values(item.occurrence_status.raw_value for item in events), key="m6_chronology_occurrence_statuses")
    st.multiselect("Timing raw status", _first_values(item.timing_status.raw_value for item in events), key="m6_chronology_timing_statuses")
    st.multiselect("Confidence raw status", _first_values(item.confidence.raw_value for item in events), key="m6_chronology_confidences")
    st.multiselect("Related issue ID", _first_values(value for item in events for value in item.related_issue_ids), key="m6_chronology_issue_ids")
    query = str(st.session_state.get("m6_chronology_query", ""))
    event_types = _selected("m6_chronology_event_types")
    participants = _selected("m6_chronology_participants")
    occurrence = _selected("m6_chronology_occurrence_statuses")
    timing = _selected("m6_chronology_timing_statuses")
    confidence = _selected("m6_chronology_confidences")
    issues = _selected("m6_chronology_issue_ids")

    def keep(item) -> bool:
        return (
            (not event_types or item.event_type in event_types)
            and (not participants or bool(participants.intersection(item.participants)))
            and (not occurrence or item.occurrence_status.raw_value in occurrence)
            and (not timing or item.timing_status.raw_value in timing)
            and (not confidence or item.confidence.raw_value in confidence)
            and (not issues or bool(issues.intersection(item.related_issue_ids)))
            and literal_query_matches(query, _event_search_values(item))
        )

    visible = tuple(item for item in events if keep(item))
    active = any((event_types, participants, occurrence, timing, confidence, issues)) or bool(query.strip())
    _filter_count(len(visible), len(events), active)
    if st.button("Reset filters"):
        _reset_keys(key for key in _M6_KEYS if key.startswith("m6_chronology_"))
        st.rerun()
    if not visible:
        st.info(_NO_FILTER_MATCH_TEXT if active else _EMPTY_FROZEN_TEXT)
        return
    for event in visible:
        st.subheader(f"Event · {event.event_id}")
        _text("Description", event.description)
        _text("Normalised event core", event.normalized_event_core)
        _text("Event type", event.event_type)
        _text("Participants", event.participants)
        _status("Occurrence", event.occurrence_status)
        _status("Timing", event.timing_status)
        _status("Confidence", event.confidence)
        _text("Temporal extent", event.canonical_temporal_extent)
        _text("Citation IDs", event.citation_ids)
        _text("Related issue IDs", event.related_issue_ids)
        _text("Related element coordinates", event.related_element_coordinates)
        st.text("Event Assertions")
        if not event.assertions:
            st.text(_EMPTY_FROZEN_TEXT)
        for assertion in event.assertions:
            st.text(f"Assertion ID: {assertion.assertion_id}")
            _text("Description", assertion.description)
            _text("Issue analysis ID", assertion.issue_analysis_id)
            _text("Element ID", assertion.element_id)
            _text("Evidence key", assertion.evidence_key)
            _text("Citation ID", assertion.citation_id)
            _text("Source proposition index", assertion.source_proposition_index)
            _status("Occurrence", assertion.occurrence_status)
            _status("Timing", assertion.timing_status)
            _status("Confidence", assertion.confidence)
            _text("Temporal extent", assertion.temporal_extent)
            _text("Extraction basis", assertion.extraction_basis)


def _render_people(index: WorkspaceIndex) -> None:
    st.header("People / Participants Explorer")
    st.caption(
        "Names and party strings are grouped exactly as recorded in the frozen projection. "
        "No entity resolution, alias matching or person/organisation classification is performed."
    )
    st.text_input("Literal search", key="m6_people_query")
    contexts = (
        "case_header.claimant", "case_header.respondent", "event.participants",
        "citation.author", "citation.parties",
    )
    st.multiselect("Occurrence context", contexts, key="m6_people_contexts")
    query = str(st.session_state.get("m6_people_query", ""))
    selected_contexts = _selected("m6_people_contexts")
    visible = tuple(
        value for value in index.recorded_name_values
        if literal_query_matches(query, (value,))
        and (
            not selected_contexts
            or any(item.context in selected_contexts for item in index.recorded_names[value])
        )
    )
    active = bool(query.strip()) or bool(selected_contexts)
    _filter_count(len(visible), len(index.recorded_name_values), active)
    if st.button("Reset filters"):
        _reset_keys(("m6_people_query", "m6_people_contexts", "m6_people_selected_value"))
        st.rerun()
    if not visible:
        st.session_state["m6_people_selected_value"] = None
        st.info(_NO_FILTER_MATCH_TEXT if active else _EMPTY_FROZEN_TEXT)
        return
    selected = st.session_state.get("m6_people_selected_value")
    if selected not in visible:
        st.session_state["m6_people_selected_value"] = visible[0]
    selected = st.selectbox("Exact recorded value", visible, key="m6_people_selected_value")
    st.subheader("Exact recorded occurrences")
    for occurrence in index.recorded_names[selected]:
        if selected_contexts and occurrence.context not in selected_contexts:
            continue
        _text("Exact value", occurrence.value)
        _text("Context", occurrence.context)
        _text("Target", _format_key(occurrence.target) if occurrence.target is not None else None)


def _comparison_refs(index: WorkspaceIndex, citations) -> tuple[WorkspaceObjectKey, ...]:
    seen: set[WorkspaceObjectKey] = set()
    result: list[WorkspaceObjectKey] = []
    for citation in citations:
        key = WorkspaceObjectKey("citation", citation.citation_id)
        for _field_name, target in index.outgoing[key]:
            if target not in seen:
                seen.add(target)
                result.append(target)
        for backlink in index.backlinks[key]:
            if backlink.source not in seen:
                seen.add(backlink.source)
                result.append(backlink.source)
    return tuple(result)


def _render_comparison_side(index: WorkspaceIndex, label: str, key: DocumentGroupKey) -> None:
    st.subheader(label)
    _text("Document name", key.document_name)
    _text("Document ID", key.document_id)
    citations = index.document_groups[key]
    _text("Citation count", len(citations))
    _text("Pages", _first_values(item.page for item in citations))
    _text("Chunk IDs", _first_values(item.chunk_id for item in citations))
    _text("Source types", _first_values(item.source_type for item in citations))
    _text("Evidence statuses", _first_values(item.evidence_status for item in citations))
    _text("Provenance types", _first_values(item.provenance_type for item in citations))
    _text("Provenance bases", _first_values(item.provenance_basis for item in citations))
    _text("Provenance confidences", _first_values(item.provenance_confidence for item in citations))
    _text("Evidence-use coordinates", tuple(coord for item in citations for coord in item.evidence_use_coordinates))
    st.text("Citation records")
    for citation in citations:
        st.text(f"{citation.citation_id} · page {citation.page if citation.page is not None else 'not recorded'}")
    st.text("Explicitly linked frozen objects")
    refs = _comparison_refs(index, citations)
    if not refs:
        st.text(_EMPTY_FROZEN_TEXT)
    for ref in refs:
        st.text(_format_key(ref))


def _render_comparison(index: WorkspaceIndex) -> None:
    st.header("Projection Evidence-Use Comparison")
    st.caption(
        "This view compares frozen projection evidence-use inventories. "
        "It does not perform a full-text or merits comparison of the underlying documents."
    )
    options = index.document_group_keys
    if len(options) < 2:
        st.info("Comparison requires at least two distinct document groups in the frozen citation catalogue.")
        return
    left = st.session_state.get("m6_compare_left_key")
    right = st.session_state.get("m6_compare_right_key")
    if left not in options:
        st.session_state["m6_compare_left_key"] = options[0]
    if right not in options or right == st.session_state["m6_compare_left_key"]:
        st.session_state["m6_compare_right_key"] = next(item for item in options if item != st.session_state["m6_compare_left_key"])
    left = st.selectbox("Left document group", options, key="m6_compare_left_key", format_func=_document_label)
    right = st.selectbox("Right document group", options, key="m6_compare_right_key", format_func=_document_label)
    if left == right:
        st.info("Select two distinct document groups for comparison.")
        return
    columns = st.columns(2)
    with columns[0]:
        _render_comparison_side(index, "Left inventory", left)
    with columns[1]:
        _render_comparison_side(index, "Right inventory", right)


def show_workspace(
    active_case_id: str | None,
    projection: CaseReportProjection | None,
) -> None:
    """Render the deterministic read-only M6 workspace for the active case."""

    if active_case_id is None:
        st.info(_NO_CASE_TEXT)
        return
    if projection is None:
        st.info(_NO_PROJECTION_TEXT)
        return
    try:
        validate_case_report_projection(projection)
        if projection.case_header.case_id != active_case_id:
            raise WorkspaceIndexError("Cross-case projection is not permitted.")
        index = build_workspace_index(projection)
    except (ValueError, WorkspaceIndexError):
        st.error(_INVALID_WORKSPACE_TEXT)
        return

    view = st.session_state.get("m6_workspace_view")
    if view not in _VIEW_ORDER:
        st.session_state["m6_workspace_view"] = "traceability"
        view = "traceability"

    st.title("LegalRAG Pro — Interactive Legal Workspace")
    if st.button("Close Workspace"):
        st.session_state["m6_workspace_view"] = None
        st.rerun()
    view = st.selectbox(
        "Workspace view",
        options=_VIEW_ORDER,
        key="m6_workspace_view",
        format_func=lambda value: _VIEW_LABELS[value],
    )
    {
        "review": _render_issue_review,
        "traceability": _render_traceability,
        "evidence": _render_evidence,
        "chronology": _render_chronology,
        "people": _render_people,
        "comparison": _render_comparison,
    }[view](index)


__all__ = ["show_workspace", "synchronise_workspace_session_state"]
