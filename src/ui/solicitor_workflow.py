"""Session-only solicitor workflow handoffs between existing governed matter views.

WC1/WC2 deliberately change navigation context only. They do not create, update
or approve evidence, analysis, tasks, task work, drafts, reports or any other
persisted matter state.
"""
from __future__ import annotations

import streamlit as st

from ui.solicitor_shell import route_solicitor_view

_WC2_DRAFT_HANDOFF_KEY = "wc2_draft_handoff"
_WC3_REPORT_HANDOFF_KEY = "wc3_report_handoff"


def _clean(value: object) -> str:
    return str(value or "").strip()


def _case(case_id: object) -> str:
    value = _clean(case_id)
    if not value:
        raise ValueError("A matter is required for a workflow handoff.")
    return value


def _value(value: object, label: str) -> str:
    result = _clean(value)
    if not result:
        raise ValueError(f"{label} is required for a workflow handoff.")
    return result


def open_issue(case_id: str, issue_id: str) -> None:
    """Open one exact existing legal issue without changing analytical state."""
    case_id = _case(case_id)
    issue_id = _value(issue_id, "Issue ID")
    st.session_state["swd1_selected_issue_id"] = issue_id
    st.session_state.pop("swd1_selected_element_id", None)
    route_solicitor_view("Issues", case_id=case_id)


def open_issue_evidence(case_id: str, issue_id: str) -> None:
    """Open Evidence filtered to one exact existing issue reference."""
    case_id = _case(case_id)
    issue_id = _value(issue_id, "Issue ID")
    st.session_state[f"ux_r6_evidence_query::{case_id}"] = ""
    st.session_state[f"ux_r6_evidence_doc::{case_id}"] = []
    st.session_state[f"ux_r6_evidence_type::{case_id}"] = []
    st.session_state[f"ux_r6_evidence_issue::{case_id}"] = [issue_id]
    st.session_state[f"ux_r6_evidence_page::{case_id}"] = 1
    route_solicitor_view("Evidence", case_id=case_id)


def open_evidence_reference(case_id: str, reference: str) -> None:
    """Open Evidence using an exact citation/evidence reference as a literal query."""
    case_id = _case(case_id)
    reference = _value(reference, "Evidence reference")
    st.session_state[f"ux_r6_evidence_query::{case_id}"] = reference
    st.session_state[f"ux_r6_evidence_doc::{case_id}"] = []
    st.session_state[f"ux_r6_evidence_type::{case_id}"] = []
    st.session_state[f"ux_r6_evidence_issue::{case_id}"] = []
    st.session_state[f"ux_r6_evidence_page::{case_id}"] = 1
    route_solicitor_view("Evidence", case_id=case_id)


def open_issue_chronology(case_id: str, issue_id: str) -> None:
    """Open Chronology filtered to one exact existing issue reference."""
    case_id = _case(case_id)
    issue_id = _value(issue_id, "Issue ID")
    st.session_state[f"ux_r6_chronology_query::{case_id}"] = ""
    st.session_state[f"ux_r6_chronology_type::{case_id}"] = []
    st.session_state[f"ux_r6_chronology_participant::{case_id}"] = []
    st.session_state[f"ux_r6_chronology_issue::{case_id}"] = [issue_id]
    st.session_state[f"ux_r6_chronology_page::{case_id}"] = 1
    route_solicitor_view("Chronology", case_id=case_id)


def open_chronology_reference(case_id: str, event_id: str) -> None:
    """Open Chronology using one exact event ID as a literal query."""
    case_id = _case(case_id)
    event_id = _value(event_id, "Chronology event ID")
    st.session_state[f"ux_r6_chronology_query::{case_id}"] = event_id
    st.session_state[f"ux_r6_chronology_type::{case_id}"] = []
    st.session_state[f"ux_r6_chronology_participant::{case_id}"] = []
    st.session_state[f"ux_r6_chronology_issue::{case_id}"] = []
    st.session_state[f"ux_r6_chronology_page::{case_id}"] = 1
    route_solicitor_view("Chronology", case_id=case_id)


def open_people_search(case_id: str, exact_name: str) -> None:
    """Open People using one exact displayed name string as a literal query."""
    case_id = _case(case_id)
    exact_name = _value(exact_name, "Name")
    st.session_state[f"ux_r6_people_query::{case_id}"] = exact_name
    st.session_state[f"ux_r6_people_context::{case_id}"] = []
    st.session_state[f"ux_r6_people_page::{case_id}"] = 1
    route_solicitor_view("People", case_id=case_id)


def open_drafts_for_task_work(case_id: str, task_id: str, progress_id: str) -> None:
    """Open Drafts bound to one exact existing task-work record.

    This function stores navigation context only. It does not generate, save,
    approve or release draft content and does not change task/task-work state.
    """
    case_id = _case(case_id)
    task_id = _value(task_id, "Task ID")
    progress_id = _value(progress_id, "Task-work progress ID")
    st.session_state[_WC2_DRAFT_HANDOFF_KEY] = {
        "case_id": case_id,
        "task_id": task_id,
        "progress_id": progress_id,
    }
    # This is the existing Case Operator drafting selector key. Setting it here
    # merely preselects the exact recorded-work identity when the reused governed
    # drafting renderer opens in Drafts.
    st.session_state["case_operator_drafting_progress_" + task_id] = progress_id
    route_solicitor_view("Drafts", case_id=case_id)


def current_draft_handoff(case_id: str) -> dict[str, str] | None:
    """Return the current exact WC2 handoff for this matter, if one exists."""
    case_id = _case(case_id)
    raw = st.session_state.get(_WC2_DRAFT_HANDOFF_KEY)
    if not isinstance(raw, dict):
        return None
    if _clean(raw.get("case_id")) != case_id:
        return None
    task_id = _clean(raw.get("task_id"))
    progress_id = _clean(raw.get("progress_id"))
    if not task_id or not progress_id:
        return None
    return {
        "case_id": case_id,
        "task_id": task_id,
        "progress_id": progress_id,
    }



def open_reports_for_approved_work_product(
    case_id: str,
    draft_id: str,
    target_id: str,
) -> None:
    """Open Reports with one exact already-approved work product as read-only context.

    This is navigation context only. It does not change the frozen report
    projection, professional release state, immutable artifact, court/tribunal
    reliance, or any other persisted matter state.
    """
    case_id = _case(case_id)
    draft_id = _value(draft_id, "Draft ID")
    target_id = _value(target_id, "Approved work-product target ID")
    st.session_state[_WC3_REPORT_HANDOFF_KEY] = {
        "case_id": case_id,
        "draft_id": draft_id,
        "target_id": target_id,
    }
    route_solicitor_view("Reports", case_id=case_id)


def current_report_handoff(case_id: str) -> dict[str, str] | None:
    """Return the exact WC3 Reports handoff for this matter, if one exists."""
    case_id = _case(case_id)
    raw = st.session_state.get(_WC3_REPORT_HANDOFF_KEY)
    if not isinstance(raw, dict):
        return None
    if _clean(raw.get("case_id")) != case_id:
        return None
    draft_id = _clean(raw.get("draft_id"))
    target_id = _clean(raw.get("target_id"))
    if not draft_id or not target_id:
        return None
    return {
        "case_id": case_id,
        "draft_id": draft_id,
        "target_id": target_id,
    }


def clear_report_handoff(case_id: str) -> None:
    """Clear read-only WC3 Reports handoff context for this matter."""
    case_id = _case(case_id)
    raw = st.session_state.get(_WC3_REPORT_HANDOFF_KEY)
    if isinstance(raw, dict) and _clean(raw.get("case_id")) == case_id:
        st.session_state.pop(_WC3_REPORT_HANDOFF_KEY, None)

def clear_draft_handoff(case_id: str) -> None:
    """Clear the WC2 handoff and its task-specific drafting preselection."""
    case_id = _case(case_id)
    raw = st.session_state.get(_WC2_DRAFT_HANDOFF_KEY)
    if isinstance(raw, dict) and _clean(raw.get("case_id")) == case_id:
        task_id = _clean(raw.get("task_id"))
        st.session_state.pop(_WC2_DRAFT_HANDOFF_KEY, None)
        if task_id:
            st.session_state.pop("case_operator_drafting_progress_" + task_id, None)


__all__ = [
    "clear_draft_handoff",
    "clear_report_handoff",
    "current_draft_handoff",
    "current_report_handoff",
    "open_chronology_reference",
    "open_drafts_for_task_work",
    "open_evidence_reference",
    "open_issue",
    "open_issue_chronology",
    "open_issue_evidence",
    "open_people_search",
    "open_reports_for_approved_work_product",
]
