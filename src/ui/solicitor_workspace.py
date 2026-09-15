"""Bounded solicitor presentation over the immutable M6 workspace projection.

The underlying workspace/index remain the semantic authority.  This facade only
limits how much material is rendered at once and supplements the People view
with exact claimant/respondent strings from the active matter presentation.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

import streamlit as st

from case_reporting.validation import validate_case_report_projection
from workspace_index import DocumentGroupKey, WorkspaceIndexError, build_workspace_index, literal_query_matches
import ui.workspace as base
from ui.solicitor_workflow import (
    open_chronology_reference,
    open_evidence_reference,
    open_issue,
    open_people_search,
)

_PAGE_SIZE_EVIDENCE = 20
_PAGE_SIZE_CHRONOLOGY = 15
_ACTIVE_PEOPLE_KEY = "ux_r6_active_case_people"


def _plain(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip()


def _status_label(value: Any) -> str:
    if value is None:
        return ""
    for field in ("label", "raw_value", "value"):
        text = _plain(getattr(value, field, None))
        if text:
            return text
    return _plain(value)


def _first_values(values: Iterable[Any]) -> tuple[Any, ...]:
    seen = set()
    result = []
    for value in values:
        if value is None:
            continue
        try:
            if value in seen:
                continue
            seen.add(value)
        except TypeError:
            continue
        result.append(value)
    return tuple(result)


def _page_slice(values: tuple[Any, ...], *, page: int, page_size: int) -> tuple[tuple[Any, ...], int, int, int]:
    total_pages = max(1, (len(values) + page_size - 1) // page_size)
    page = min(max(int(page or 1), 1), total_pages)
    first = (page - 1) * page_size
    return values[first:first + page_size], page, total_pages, first


def _pager(*, key: str, total: int, page_size: int) -> tuple[int, int, int]:
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(max(int(st.session_state.get(key, 1) or 1), 1), total_pages)
    st.session_state[key] = page
    first = (page - 1) * page_size
    shown = min(page_size, max(total - first, 0))
    if total:
        st.caption(f"Showing {first + 1}-{first + shown} of {total} · page {page} of {total_pages}")
    else:
        st.caption("Showing 0 of 0")
    prev_col, next_col, spacer = st.columns([1.0, 1.0, 5.0])
    with prev_col:
        if st.button("Previous", key=key + "::prev", disabled=page <= 1, use_container_width=True):
            st.session_state[key] = page - 1
            st.rerun()
    with next_col:
        if st.button("Next", key=key + "::next", disabled=page >= total_pages, use_container_width=True):
            st.session_state[key] = page + 1
            st.rerun()
    with spacer:
        st.empty()
    return page, total_pages, first


def _citation_search_values(value: Any) -> tuple[Any, ...]:
    return (
        getattr(value, "citation_id", None), getattr(value, "evidence_key", None),
        getattr(value, "citation", None), getattr(value, "document_name", None),
        getattr(value, "document_id", None), getattr(value, "page", None),
        getattr(value, "chunk_id", None), getattr(value, "date", None),
        getattr(value, "author", None), getattr(value, "parties", ()),
        getattr(value, "source_type", None), getattr(value, "evidence_status", None),
        getattr(value, "provenance_type", None), getattr(value, "provenance_basis", None),
        getattr(value, "provenance_confidence", None),
        getattr(value, "evidence_use_coordinates", ()),
    )


def _render_evidence(index: Any, active_case_id: str) -> None:
    st.header("Evidence")
    st.caption("Compact source-linked evidence register. Open technical details only when needed.")
    citations = tuple(index.citations_by_id[key.primary_id] for key in index.citation_keys)

    query_key = f"ux_r6_evidence_query::{active_case_id}"
    doc_key = f"ux_r6_evidence_doc::{active_case_id}"
    type_key = f"ux_r6_evidence_type::{active_case_id}"
    issue_key = f"ux_r6_evidence_issue::{active_case_id}"
    page_key = f"ux_r6_evidence_page::{active_case_id}"

    document_names = _first_values(getattr(item, "document_name", None) for item in citations)
    source_types = _first_values(getattr(item, "source_type", None) for item in citations)
    issue_ids = _first_values(
        coord[0] for item in citations for coord in (getattr(item, "evidence_use_coordinates", ()) or ())
        if isinstance(coord, tuple) and coord
    )
    with st.form(key=f"ux_r6_evidence_filters::{active_case_id}", clear_on_submit=False):
        st.text_input("Search evidence", key=query_key)
        st.multiselect("Document", document_names, key=doc_key)
        st.multiselect("Source type", source_types, key=type_key)
        st.multiselect("Related issue", issue_ids, key=issue_key)
        submitted = st.form_submit_button("Apply filters", use_container_width=True)
    if submitted:
        st.session_state[page_key] = 1

    query = str(st.session_state.get(query_key, ""))
    docs = set(st.session_state.get(doc_key, []) or ())
    types = set(st.session_state.get(type_key, []) or ())
    issues = set(st.session_state.get(issue_key, []) or ())

    def keep(item: Any) -> bool:
        coords = getattr(item, "evidence_use_coordinates", ()) or ()
        item_issues = {coord[0] for coord in coords if isinstance(coord, tuple) and coord}
        return (
            (not docs or getattr(item, "document_name", None) in docs)
            and (not types or getattr(item, "source_type", None) in types)
            and (not issues or bool(issues.intersection(item_issues)))
            and literal_query_matches(query, _citation_search_values(item))
        )

    visible = tuple(item for item in citations if keep(item))
    if not visible:
        st.info("No evidence items match the current filters." if (query.strip() or docs or types or issues) else "No evidence citations are recorded.")
        return

    page, _total_pages, first = _pager(key=page_key, total=len(visible), page_size=_PAGE_SIZE_EVIDENCE)
    page_items, _page, _pages, _first = _page_slice(visible, page=page, page_size=_PAGE_SIZE_EVIDENCE)
    for ordinal, item in enumerate(page_items, start=first + 1):
        with st.container(border=True):
            left, right = st.columns([5.5, 1.5])
            with left:
                title = _plain(getattr(item, "document_name", None)) or "Evidence"
                page_value = getattr(item, "page", None)
                st.markdown(f"**{ordinal}. {title}**" + (f" · p.{page_value}" if page_value else ""))
                citation = _plain(getattr(item, "citation", None))
                if citation:
                    st.write(citation if len(citation) <= 420 else citation[:417] + "…")
            with right:
                status = _status_label(getattr(item, "evidence_status", None))
                if status:
                    st.caption(status)
                source_type = _plain(getattr(item, "source_type", None))
                if source_type:
                    st.caption(source_type)
            with st.expander("Evidence details", expanded=False):
                for label, value in (
                    ("Citation ID", getattr(item, "citation_id", None)),
                    ("Evidence key", getattr(item, "evidence_key", None)),
                    ("Document ID", getattr(item, "document_id", None)),
                    ("Chunk ID", getattr(item, "chunk_id", None)),
                    ("Date", getattr(item, "date", None)),
                    ("Author", getattr(item, "author", None)),
                    ("Parties", getattr(item, "parties", None)),
                    ("Provenance type", getattr(item, "provenance_type", None)),
                    ("Provenance basis", getattr(item, "provenance_basis", None)),
                    ("Provenance confidence", getattr(item, "provenance_confidence", None)),
                    ("Related coordinates", getattr(item, "evidence_use_coordinates", None)),
                ):
                    if value not in (None, "", (), []):
                        st.text(f"{label}: {value}")

                issue_ids = _first_values(
                    coord[0]
                    for coord in (getattr(item, "evidence_use_coordinates", ()) or ())
                    if isinstance(coord, tuple) and coord
                )
                people_values = _first_values(
                    (getattr(item, "author", None),)
                    + tuple(getattr(item, "parties", ()) or ())
                )
                if issue_ids or people_values:
                    st.markdown("**Matter links**")
                for issue_id in issue_ids:
                    issue = getattr(index, "issues_by_id", {}).get(issue_id)
                    issue_name = _plain(getattr(issue, "issue_name", None)) or str(issue_id)
                    if st.button(
                        "Open related issue · " + issue_name,
                        key=f"wc1_evidence_issue::{active_case_id}::{getattr(item, 'citation_id', ordinal)}::{issue_id}",
                        use_container_width=True,
                    ):
                        open_issue(active_case_id, str(issue_id))
                        st.rerun()
                for person in people_values:
                    person_text = _plain(person)
                    if not person_text:
                        continue
                    if st.button(
                        "Find in People · " + person_text,
                        key=f"wc1_evidence_person::{active_case_id}::{getattr(item, 'citation_id', ordinal)}::{person_text}",
                        use_container_width=True,
                    ):
                        open_people_search(active_case_id, person_text)
                        st.rerun()


def _event_search_values(event: Any) -> tuple[Any, ...]:
    extent = getattr(event, "canonical_temporal_extent", None)
    temporal = getattr(extent, "display_text", None) if extent is not None else None
    return (
        getattr(event, "event_id", None), getattr(event, "description", None),
        getattr(event, "normalized_event_core", None), getattr(event, "event_type", None),
        getattr(event, "participants", ()), temporal, getattr(event, "citation_ids", ()),
        getattr(event, "related_issue_ids", ()), getattr(event, "related_element_coordinates", ()),
    )


def _render_chronology(active_case_id: str, index: Any) -> None:
    st.header("Chronology")
    st.caption("Dated matter events in a paged register. Assertions and audit detail stay collapsed until opened.")
    events = tuple(index.events_by_id[key.primary_id] for key in index.event_keys)

    query_key = f"ux_r6_chronology_query::{active_case_id}"
    type_key = f"ux_r6_chronology_type::{active_case_id}"
    participant_key = f"ux_r6_chronology_participant::{active_case_id}"
    issue_key = f"ux_r6_chronology_issue::{active_case_id}"
    page_key = f"ux_r6_chronology_page::{active_case_id}"

    event_types = _first_values(getattr(item, "event_type", None) for item in events)
    participants = _first_values(value for item in events for value in (getattr(item, "participants", ()) or ()))
    issue_ids = _first_values(value for item in events for value in (getattr(item, "related_issue_ids", ()) or ()))
    with st.form(key=f"ux_r6_chronology_filters::{active_case_id}", clear_on_submit=False):
        st.text_input("Search chronology", key=query_key)
        st.multiselect("Event type", event_types, key=type_key)
        st.multiselect("Participant", participants, key=participant_key)
        st.multiselect("Related issue", issue_ids, key=issue_key)
        submitted = st.form_submit_button("Apply filters", use_container_width=True)
    if submitted:
        st.session_state[page_key] = 1

    query = str(st.session_state.get(query_key, ""))
    selected_types = set(st.session_state.get(type_key, []) or ())
    selected_people = set(st.session_state.get(participant_key, []) or ())
    selected_issues = set(st.session_state.get(issue_key, []) or ())

    def keep(item: Any) -> bool:
        return (
            (not selected_types or getattr(item, "event_type", None) in selected_types)
            and (not selected_people or bool(selected_people.intersection(getattr(item, "participants", ()) or ())))
            and (not selected_issues or bool(selected_issues.intersection(getattr(item, "related_issue_ids", ()) or ())))
            and literal_query_matches(query, _event_search_values(item))
        )

    visible = tuple(item for item in events if keep(item))
    if not visible:
        st.info("No chronology events match the current filters." if (query.strip() or selected_types or selected_people or selected_issues) else "No chronology events are recorded.")
        return

    page, _total_pages, first = _pager(key=page_key, total=len(visible), page_size=_PAGE_SIZE_CHRONOLOGY)
    page_items, _page, _pages, _first = _page_slice(visible, page=page, page_size=_PAGE_SIZE_CHRONOLOGY)
    task_creator = getattr(base, "_render_chronology_task_creator", None)
    for ordinal, event in enumerate(page_items, start=first + 1):
        extent = getattr(event, "canonical_temporal_extent", None)
        when = _plain(getattr(extent, "display_text", None)) if extent is not None else ""
        description = _plain(getattr(event, "description", None)) or "Chronology event"
        with st.container(border=True):
            st.markdown(f"**{ordinal}. {when or 'Date not recorded'} — {description}**")
            meta = []
            event_type = _plain(getattr(event, "event_type", None))
            if event_type:
                meta.append(event_type)
            people = tuple(getattr(event, "participants", ()) or ())
            if people:
                meta.append("People: " + ", ".join(str(value) for value in people))
            occurrence = _status_label(getattr(event, "occurrence_status", None))
            if occurrence:
                meta.append("Status: " + occurrence)
            if meta:
                st.caption(" · ".join(meta))
            with st.expander("Event details and actions", expanded=False):
                core = _plain(getattr(event, "normalized_event_core", None))
                if core and core != description:
                    st.write(core)
                for label, value in (
                    ("Event ID", getattr(event, "event_id", None)),
                    ("Timing", _status_label(getattr(event, "timing_status", None))),
                    ("Confidence", _status_label(getattr(event, "confidence", None))),
                    ("Citation IDs", getattr(event, "citation_ids", None)),
                    ("Related issue IDs", getattr(event, "related_issue_ids", None)),
                    ("Related element coordinates", getattr(event, "related_element_coordinates", None)),
                ):
                    if value not in (None, "", (), []):
                        st.text(f"{label}: {value}")
                assertions = tuple(getattr(event, "assertions", ()) or ())
                if assertions:
                    st.markdown(f"**Assertions ({len(assertions)})**")
                    for assertion in assertions:
                        st.text("• " + _plain(getattr(assertion, "description", None)))

                related_issue_ids = _first_values(getattr(event, "related_issue_ids", ()) or ())
                people_values = _first_values(getattr(event, "participants", ()) or ())
                if related_issue_ids or people_values:
                    st.markdown("**Matter links**")
                for issue_id in related_issue_ids:
                    issue = getattr(index, "issues_by_id", {}).get(issue_id)
                    issue_name = _plain(getattr(issue, "issue_name", None)) or str(issue_id)
                    if st.button(
                        "Open related issue · " + issue_name,
                        key=f"wc1_chronology_issue::{active_case_id}::{getattr(event, 'event_id', ordinal)}::{issue_id}",
                        use_container_width=True,
                    ):
                        open_issue(active_case_id, str(issue_id))
                        st.rerun()
                for person in people_values:
                    person_text = _plain(person)
                    if not person_text:
                        continue
                    if st.button(
                        "Find in People · " + person_text,
                        key=f"wc1_chronology_person::{active_case_id}::{getattr(event, 'event_id', ordinal)}::{person_text}",
                        use_container_width=True,
                    ):
                        open_people_search(active_case_id, person_text)
                        st.rerun()
                if callable(task_creator):
                    task_creator(active_case_id=active_case_id, index=index, event=event)


def _source_excerpt(text: str, start: int, end: int, *, radius: int = 120) -> str:
    """Return a compact exact-source excerpt around one deterministic name match."""
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    excerpt = " ".join(text[left:right].split())
    if left:
        excerpt = "…" + excerpt
    if right < len(text):
        excerpt += "…"
    return excerpt


_NAME_WORD = r"(?:[A-Z]\.?|[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’\-]+)"
_NAME_2_4 = rf"{_NAME_WORD}(?:\s+{_NAME_WORD}){{1,3}}"
_TITLE_PATTERN = re.compile(
    rf"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof|Professor|Sir|Dame)\.?\s+"
    rf"{_NAME_WORD}(?:\s+\({_NAME_WORD}\))?(?:\s+{_NAME_WORD}){{0,2}}\b"
)
_ARROW_PATTERN = re.compile(rf"\b({_NAME_2_4})\s*(?=→|->)")
_FROM_PATTERN = re.compile(rf"\b(?:Email\s+from|from)\s+({_NAME_2_4})(?=\s*(?:,|—|–|-|\(|$))")
_VERB_PATTERN = re.compile(
    rf"\b({_NAME_2_4})\s+(?="
    r"sent|wrote|informed|asked|said|stated|confirmed|advised|told|emailed|replied|responded|joined|attended|rejected)\b"
)
_MEETING_PATTERN = re.compile(rf"\b(?:meeting|call|discussion)\s+with\s+({_NAME_2_4})(?=\s*(?:,|—|–|-|\(|$|and\b))", re.IGNORECASE)
_BEHALF_PATTERN = re.compile(rf"\bon\s+behalf\s+of\s+({_NAME_2_4})(?=\s*(?:,|—|–|-|\(|$))", re.IGNORECASE)
_PAREN_NAME_PATTERN = re.compile(rf"\(({_NAME_2_4})\)")

_GENERIC_NAME_START = {
    "The", "This", "That", "Source", "Evidence", "Appendix", "Email", "Current",
    "Occupational", "Legal", "Case", "Finance", "Managing", "Payroll", "Rother",
    "Newcastle", "Employment", "Equality", "Borderline", "Principal", "Business",
    "Statutory", "Long", "Human", "Return", "Internal", "External", "Active",
    "Professional", "Historical", "Material", "Reasonable", "Working", "Frozen",
}
_GENERIC_NAME_END = {
    "Director", "Manager", "Consultant", "Council", "Centre", "Health", "Tribunal",
    "Act", "Respondent", "Claimant", "Evidence", "Assessment", "Workspace", "Report",
    "Policy", "Correspondence", "Certificate", "Statement", "Email", "Division",
}


def _clean_name_match(value: str) -> str:
    return " ".join(str(value or "").strip(" ,;:–—-").split())


def _accept_named_source_match(value: str, *, titled: bool) -> bool:
    """Conservative lexical gate; this is text matching, not person/entity inference."""
    value = _clean_name_match(value)
    if not value:
        return False
    if titled:
        return True
    tokens = value.replace("(", " ").replace(")", " ").split()
    if len(tokens) < 2:
        return False
    if tokens[0].rstrip(".") in _GENERIC_NAME_START:
        return False
    if tokens[-1].rstrip(".") in _GENERIC_NAME_END:
        return False
    if any(token.isupper() and len(token) > 2 for token in tokens):
        return False
    return True


def _extract_named_source_mentions(text: Any) -> tuple[tuple[str, int, int], ...]:
    """Extract explicit name-shaped phrases from exact frozen source-bound text.

    The function deliberately does not merge aliases, classify organisations, call an
    LLM, or create a new evidential identity.  It only exposes lexical matches with
    their source occurrence so a solicitor can find names already written in the
    frozen material.
    """
    raw = str(text or "")
    if not raw.strip():
        return ()
    found: list[tuple[int, int, str]] = []

    def add(match: re.Match[str], *, group: int | str = 0, titled: bool = False) -> None:
        value = _clean_name_match(match.group(group))
        if not _accept_named_source_match(value, titled=titled):
            return
        start, end = match.span(group)
        row = (start, end, value)
        if row not in found:
            found.append(row)

    for match in _TITLE_PATTERN.finditer(raw):
        add(match, titled=True)
    for pattern in (_ARROW_PATTERN, _FROM_PATTERN, _VERB_PATTERN, _MEETING_PATTERN, _BEHALF_PATTERN, _PAREN_NAME_PATTERN):
        for match in pattern.finditer(raw):
            add(match, group=1, titled=False)

    found.sort(key=lambda row: (row[0], -(row[1] - row[0]), row[2]))
    kept: list[tuple[int, int, str]] = []
    for row in found:
        start, end, _value = row
        if any(start >= k_start and end <= k_end for k_start, k_end, _k_value in kept):
            continue
        kept.append(row)
    kept.sort(key=lambda row: (row[0], row[1], row[2]))
    return tuple((value, start, end) for start, end, value in kept)


def _iter_people_source_text(projection: Any):
    """Yield exact frozen source-bound text surfaces used only for mention discovery."""
    for event in tuple(getattr(projection, "chronology", ()) or ()):
        event_id = _plain(getattr(event, "event_id", None))
        for field in ("description", "normalized_event_core"):
            text = getattr(event, field, None)
            if str(text or "").strip():
                yield f"event.{field}", event_id, str(text)
        for assertion in tuple(getattr(event, "assertions", ()) or ()):
            text = getattr(assertion, "description", None)
            if str(text or "").strip():
                assertion_id = _plain(getattr(assertion, "assertion_id", None))
                target = event_id + ("|" + assertion_id if assertion_id else "")
                yield "event.assertion.description", target, str(text)

    statement_fields = (
        "established_matters",
        "supported_matters",
        "not_supported_matters",
        "source_assertions",
    )
    for issue in tuple(getattr(projection, "issues", ()) or ()):
        issue_id = _plain(getattr(issue, "issue_analysis_id", None))
        for element in tuple(getattr(issue, "elements", ()) or ()):
            element_id = _plain(getattr(element, "element_id", None))
            for field in statement_fields:
                for statement in tuple(getattr(element, field, ()) or ()):
                    text = getattr(statement, "text", None)
                    if not str(text or "").strip():
                        continue
                    statement_id = _plain(getattr(statement, "report_statement_id", None))
                    target = statement_id or "|".join(part for part in (issue_id, element_id) if part)
                    yield f"report_statement.{field}", target, str(text)


def _collect_people(index: Any, projection: Any) -> dict[str, list[tuple[str, str, str, str]]]:
    """Build one solicitor-facing exact-string register without alias/entity merging.

    Rows are (context, target, kind, excerpt).  ``recorded`` rows preserve the M6 v1
    exact people fields.  ``source_mention`` rows are conservative lexical matches
    from exact frozen chronology / evidence-backed statement text and are displayed
    explicitly as text mentions, not as identity-resolved people.
    """
    result: dict[str, list[tuple[str, str, str, str]]] = {}

    def add(value: Any, context: str, target: str = "", *, kind: str = "recorded", excerpt: str = "") -> None:
        text = str(value or "").strip()
        if not text:
            return
        row = (context, target, kind, excerpt)
        result.setdefault(text, [])
        if row not in result[text]:
            result[text].append(row)

    try:
        active_people = tuple(st.session_state.get(_ACTIVE_PEOPLE_KEY, ()) or ())
    except Exception:
        active_people = ()
    for value, context in active_people:
        add(value, context, "Active matter record")

    # Preserve exact frozen-index occurrences where they exist.
    for value in tuple(getattr(index, "recorded_name_values", ()) or ()):
        for occurrence in tuple(getattr(index, "recorded_names", {}).get(value, ()) or ()):
            target = getattr(occurrence, "target", None)
            add(value, str(getattr(occurrence, "context", "recorded")), str(target or ""))

    header = getattr(projection, "case_header", None)
    if header is not None:
        add(getattr(header, "claimant", None), "case_header.claimant", "Frozen projection")
        add(getattr(header, "respondent", None), "case_header.respondent", "Frozen projection")
    for event in tuple(getattr(projection, "chronology", ()) or ()):
        for participant in tuple(getattr(event, "participants", ()) or ()):
            add(participant, "event.participants", _plain(getattr(event, "event_id", None)))
    for citation in tuple(getattr(projection, "citations", ()) or ()):
        target = _plain(getattr(citation, "citation_id", None))
        add(getattr(citation, "author", None), "citation.author", target)
        for party in tuple(getattr(citation, "parties", ()) or ()):
            add(party, "citation.parties", target)

    # Solicitor-facing discovery layer.  This extends presentation only; it does not
    # modify WorkspaceIndex, the frozen projection, evidence bindings or identities.
    for context, target, source_text in _iter_people_source_text(projection):
        for value, start, end in _extract_named_source_mentions(source_text):
            add(
                value,
                context,
                target,
                kind="source_mention",
                excerpt=_source_excerpt(source_text, start, end),
            )
    return result


def _render_people(active_case_id: str, index: Any, projection: Any) -> None:
    st.header("People / Participants")
    st.caption(
        "Recorded participant/party strings are preserved exactly. Named source mentions are "
        "also surfaced from exact frozen chronology and evidence-backed statement text. "
        "Source mentions are not identity-resolved, alias-merged or classified as a person or organisation."
    )
    people = _collect_people(index, projection)
    query_key = f"ux_r6_people_query::{active_case_id}"
    context_key = f"ux_r6_people_context::{active_case_id}"
    contexts = tuple(dict.fromkeys(context for rows in people.values() for context, _, _, _ in rows))
    with st.form(key=f"ux_r6_people_filters::{active_case_id}", clear_on_submit=False):
        st.text_input("Search names", key=query_key)
        st.multiselect("Occurrence context", contexts, key=context_key)
        st.form_submit_button("Apply filters", use_container_width=True)
    query = str(st.session_state.get(query_key, ""))
    selected_contexts = set(st.session_state.get(context_key, []) or ())
    visible = tuple(
        value for value, rows in people.items()
        if literal_query_matches(query, (value,))
        and (not selected_contexts or any(context in selected_contexts for context, _, _, _ in rows))
    )

    recorded_values = sum(
        1 for rows in people.values() if any(kind == "recorded" for _, _, kind, _ in rows)
    )
    mention_values = sum(
        1 for rows in people.values() if any(kind == "source_mention" for _, _, kind, _ in rows)
    )
    st.caption(
        f"{recorded_values} exact recorded participant/party string(s) · "
        f"{mention_values} exact named source-mention string(s)"
    )

    if not visible:
        st.caption(f"Showing 0 of {len(people)}")
        st.info("No recorded names or named source mentions match the current filters." if (query.strip() or selected_contexts) else "No recorded names or named source mentions are available for this matter.")
        return
    page_key = f"ux_r6_people_page::{active_case_id}"
    page, _total_pages, _first = _pager(key=page_key, total=len(visible), page_size=25)
    page_values, _page, _pages, _start = _page_slice(visible, page=page, page_size=25)
    for value in page_values:
        rows = [row for row in people[value] if not selected_contexts or row[0] in selected_contexts]
        has_recorded = any(kind == "recorded" for _, _, kind, _ in rows)
        has_mentions = any(kind == "source_mention" for _, _, kind, _ in rows)
        labels = []
        if has_recorded:
            labels.append("recorded participant/party")
        if has_mentions:
            labels.append("named source mention")
        with st.container(border=True):
            st.markdown("**" + value + "**")
            st.caption(" · ".join(labels) + f" · {len(rows)} occurrence" + ("" if len(rows) == 1 else "s"))
            with st.expander("Occurrences and source context", expanded=False):
                for occurrence_index, (context, target, kind, excerpt) in enumerate(rows):
                    label = "Recorded field" if kind == "recorded" else "Source-text mention"
                    st.text(label + " · " + context + (" · " + target if target else ""))
                    if excerpt:
                        st.write(excerpt)
                    if target and context.startswith("event."):
                        event_id = str(target).split("|", 1)[0].strip()
                        if event_id and st.button(
                            "Open chronology occurrence",
                            key=f"wc1_people_event::{active_case_id}::{value}::{occurrence_index}::{event_id}",
                            use_container_width=True,
                        ):
                            open_chronology_reference(active_case_id, event_id)
                            st.rerun()
                    elif target and context.startswith("citation."):
                        evidence_reference = str(target).strip()
                        if evidence_reference and st.button(
                            "Open evidence occurrence",
                            key=f"wc1_people_evidence::{active_case_id}::{value}::{occurrence_index}::{evidence_reference}",
                            use_container_width=True,
                        ):
                            open_evidence_reference(active_case_id, evidence_reference)
                            st.rerun()

def show_solicitor_workspace(
    active_case_id: str | None,
    projection: Any | None,
    *,
    evidential_dashboard: Any | None = None,
) -> None:
    """Render bounded solicitor views while delegating non-target M6 views unchanged."""
    view = st.session_state.get("m6_workspace_view")
    if view not in {"evidence", "chronology", "people"}:
        base.show_workspace(active_case_id, projection, evidential_dashboard=evidential_dashboard)
        return
    if active_case_id is None or not str(active_case_id).strip():
        st.info("Select an active matter to use this workspace.")
        return
    if projection is None:
        st.info("No frozen report projection is available for this matter.")
        return
    try:
        validate_case_report_projection(projection)
        if projection.case_header.case_id != active_case_id:
            raise WorkspaceIndexError("Cross-case projection is not permitted.")
        index = build_workspace_index(projection)
    except (ValueError, TypeError, WorkspaceIndexError):
        st.error("The frozen report projection could not be validated for this workspace.")
        return

    if view == "evidence":
        _render_evidence(index, active_case_id)
    elif view == "chronology":
        _render_chronology(active_case_id, index)
    else:
        _render_people(active_case_id, index, projection)


__all__ = ["show_solicitor_workspace", "_collect_people", "_extract_named_source_mentions", "_iter_people_source_text", "_page_slice", "_PAGE_SIZE_EVIDENCE", "_PAGE_SIZE_CHRONOLOGY"]
