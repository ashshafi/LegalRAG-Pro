"""LegalRAG Pro R6 solicitor shell.

Presentation-only navigation.  The shell never creates or changes governed
analytical, evidence, task, draft, finance or release state.
"""
from __future__ import annotations

from html import escape
from typing import Any

import streamlit as st

from ui.matter_overview import is_matter_overview_active, set_matter_overview_view

DOCUMENTS_VIEW_KEY = "ux_d2_documents_view"
DRAFTS_VIEW_KEY = "ux_d2_drafts_view"
DOCUMENT_UPLOAD_OPEN_KEY = "ux_r5_open_document_upload"
INSPECTION_ORIGIN_KEY = "ux_r6_evidence_inspection_origin"
_NAV_SYNC_KEY = "ux_r6_nav_last_active"
_NAV_EPOCH_PREFIX = "ux_r6_nav_epoch::"
_ACTIVE_PEOPLE_KEY = "ux_r6_active_case_people"

_PRIMARY = (
    "Overview",
    "Issues",
    "Chronology",
    "Evidence",
    "Documents",
    "People",
    "Case Operator",
    "Drafts",
    "Reports",
)


def _clear_route_state() -> None:
    set_matter_overview_view(st.session_state, False)
    st.session_state["u8_evidence_inspection_view"] = False
    st.session_state["ppr3_legal_issue_dashboard_view"] = False
    st.session_state["m7_source_evidence_view"] = False
    st.session_state["m6_workspace_view"] = None
    st.session_state[DOCUMENTS_VIEW_KEY] = False
    st.session_state[DRAFTS_VIEW_KEY] = False
    st.session_state.pop("case_operator_workspace_case_id", None)
    st.session_state.pop("mw1_task_workspace_case_id", None)


def activate_solicitor_view(view: str, *, case_id: str | None) -> None:
    """Activate one presentation route without mutating governed matter state."""
    _clear_route_state()
    st.session_state["m55_main_view"] = "assistant"

    if view == "Overview":
        set_matter_overview_view(st.session_state, case_id is not None)
    elif view == "Issues":
        st.session_state["ppr3_legal_issue_dashboard_view"] = case_id is not None
    elif view == "Chronology":
        st.session_state["m6_workspace_view"] = "chronology"
    elif view == "Evidence":
        st.session_state["m6_workspace_view"] = "evidence"
    elif view == "Documents":
        st.session_state[DOCUMENTS_VIEW_KEY] = case_id is not None
    elif view == "People":
        st.session_state["m6_workspace_view"] = "people"
    elif view == "Case Operator":
        st.session_state["ppr3_legal_issue_dashboard_view"] = case_id is not None
        if case_id is not None:
            st.session_state["case_operator_workspace_case_id"] = case_id
    elif view == "Drafts":
        st.session_state[DRAFTS_VIEW_KEY] = case_id is not None
    elif view == "Reports":
        st.session_state["m55_main_view"] = "reports"
    elif view == "Audit":
        st.session_state["m7_source_evidence_view"] = case_id is not None
    elif view == "Ask LegalRAG":
        pass
    else:
        raise ValueError(f"Unknown solicitor view: {view}")


def current_solicitor_view(case_id: str | None) -> str:
    if st.session_state.get(DOCUMENTS_VIEW_KEY, False):
        return "Documents"
    if st.session_state.get(DRAFTS_VIEW_KEY, False):
        return "Drafts"
    if case_id is not None and (
        st.session_state.get("case_operator_workspace_case_id") == case_id
        or st.session_state.get("mw1_task_workspace_case_id") == case_id
    ):
        return "Case Operator"
    if st.session_state.get("u8_evidence_inspection_view", False):
        return "Evidence"
    if st.session_state.get("ppr3_legal_issue_dashboard_view", False):
        return "Issues"
    if st.session_state.get("m7_source_evidence_view", False):
        return "Audit"

    workspace = st.session_state.get("m6_workspace_view")
    if workspace == "chronology":
        return "Chronology"
    if workspace in {"evidence", "comparison"}:
        return "Evidence"
    if workspace == "people":
        return "People"

    main_view = st.session_state.get("m55_main_view", "assistant")
    if main_view == "finance":
        return "Finance"
    if main_view == "reports":
        return "Reports"
    if is_matter_overview_active(st.session_state):
        return "Overview"
    return "Ask LegalRAG"


def _epoch_key(case_id: str | None) -> str:
    return _NAV_EPOCH_PREFIX + (case_id or "none")


def _advance_epoch(case_id: str | None) -> int:
    key = _epoch_key(case_id)
    value = int(st.session_state.get(key, 0) or 0) + 1
    st.session_state[key] = value
    return value


def route_solicitor_view(view: str, *, case_id: str | None) -> None:
    """Route from a non-primary control and invalidate stale primary widget state."""
    activate_solicitor_view(view, case_id=case_id)
    _advance_epoch(case_id)
    st.session_state[_NAV_SYNC_KEY] = view


def _primary_nav_changed(nav_key: str, case_id: str | None) -> None:
    """Apply an explicit segmented-control change before Streamlit reruns."""
    selected = st.session_state.get(nav_key)
    if selected not in _PRIMARY:
        return
    activate_solicitor_view(str(selected), case_id=case_id)
    st.session_state[_NAV_SYNC_KEY] = str(selected)


def _utility_button(*, label: str, key: str, active: bool, disabled: bool, help_text: str | None = None) -> bool:
    return st.button(
        label,
        key=key,
        use_container_width=True,
        type="primary" if active else "secondary",
        disabled=disabled,
        help=help_text,
    )


def _remember_active_case_people(active_case: Any | None) -> None:
    values: list[tuple[str, str]] = []
    if active_case is not None:
        for field, context in (("claimant", "case_header.claimant"), ("respondent", "case_header.respondent")):
            value = str(getattr(active_case, field, "") or "").strip()
            if value:
                values.append((value, context))
    st.session_state[_ACTIVE_PEOPLE_KEY] = tuple(values)


def show_solicitor_shell(active_case: Any | None, *, reports_available: bool) -> None:
    case_id = None
    if active_case is not None:
        case_id = str(getattr(active_case, "case_id", "") or "").strip() or None
    _remember_active_case_people(active_case)

    active = current_solicitor_view(case_id)
    synced = st.session_state.get(_NAV_SYNC_KEY)
    if synced != active:
        # Route changed outside the segmented control (sidebar Finance, evidence
        # drill-down/back, etc.).  A new widget identity discards stale selection
        # without overwriting a user's next click.
        _advance_epoch(case_id)
        st.session_state[_NAV_SYNC_KEY] = active

    name = "No matter selected"
    reference = ""
    status = ""
    if active_case is not None:
        name = str(getattr(active_case, "name", "") or "").strip() or "Active matter"
        reference = str(getattr(active_case, "case_number", "") or "").strip()
        status = str(getattr(active_case, "status", "") or "").strip().title()

    meta: list[str] = []
    if reference:
        meta.append(f"<span>{escape(reference)}</span>")
    if status:
        meta.append(f'<span class="lr-status">{escape(status)}</span>')
    st.markdown(
        f'<div class="lr-matter-head">'
        f'<div class="lr-eyebrow">Active matter</div>'
        f'<div class="lr-matter-title">{escape(name)}</div>'
        f'<div class="lr-matter-meta">{"".join(meta)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    add_col, audit_col, ask_col, spacer = st.columns([2.0, 1.15, 1.15, 4.0])
    with add_col:
        if _utility_button(
            label="Add document",
            key="ux_r6_add_document",
            active=False,
            disabled=case_id is None,
            help_text="Add a governed PDF to the current matter",
        ):
            route_solicitor_view("Documents", case_id=case_id)
            st.session_state[DOCUMENT_UPLOAD_OPEN_KEY] = True
            st.rerun()
    with audit_col:
        if _utility_button(
            label="Audit",
            key="ux_r6_audit",
            active=active == "Audit",
            disabled=case_id is None or not reports_available,
        ):
            route_solicitor_view("Audit", case_id=case_id)
            st.rerun()
    with ask_col:
        if _utility_button(
            label="Ask",
            key="ux_r6_ask",
            active=active == "Ask LegalRAG",
            disabled=case_id is None,
            help_text="Ask LegalRAG about the current matter",
        ):
            route_solicitor_view("Ask LegalRAG", case_id=case_id)
            st.rerun()
    with spacer:
        st.empty()

    epoch = int(st.session_state.get(_epoch_key(case_id), 0) or 0)
    nav_key = f"ux_r6_primary_nav::{case_id or 'none'}::{epoch}"
    default = active if active in _PRIMARY else None
    st.segmented_control(
        "Matter navigation",
        _PRIMARY,
        selection_mode="single",
        required=False,
        default=default,
        key=nav_key,
        on_change=_primary_nav_changed,
        args=(nav_key, case_id),
        label_visibility="collapsed",
        width="stretch",
    )


__all__ = [
    "DOCUMENTS_VIEW_KEY",
    "DRAFTS_VIEW_KEY",
    "DOCUMENT_UPLOAD_OPEN_KEY",
    "INSPECTION_ORIGIN_KEY",
    "activate_solicitor_view",
    "current_solicitor_view",
    "route_solicitor_view",
    "show_solicitor_shell",
]
