from __future__ import annotations

from typing import Any

import streamlit as st

from ui.solicitor_tasks import show_issue_task_creator
from governed_analytical_authority.provider import load_active_governed_analytical_authority
from legal_issue_dashboard import build_legal_issue_dashboard


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _issue_label(issue: Any) -> str:
    return (
        _clean(getattr(issue, "issue_name", ""))
        or _clean(getattr(issue, "title", ""))
        or "Legal issue"
    )


def render_custom_governed_task_initiation(*, case_id: str) -> None:
    st.markdown("### Start a custom governed task")
    st.caption(
        "Use this when a new evidential question needs governed investigation but "
        "Case Operator has not proposed the task automatically. This form does not "
        "change the Current Assessment or create a task by itself."
    )

    try:
        authority = load_active_governed_analytical_authority(case_id=case_id)
        if authority is None:
            st.info(
                "Custom task initiation is unavailable because there is no active "
                "governed analytical authority for this matter."
            )
            return
        dashboard = build_legal_issue_dashboard(active_case_id=case_id, authority=authority)
    except Exception as exc:
        st.error("The governed legal-issue list could not be loaded safely.")
        st.caption(str(exc))
        return

    issues = tuple(getattr(dashboard, "issues", ()) or ())
    if not issues:
        st.info("No governed legal issues are available for custom task initiation.")
        return

    keyed = {
        str(getattr(issue, "issue_analysis_id", "") or "").strip(): issue
        for issue in issues
        if str(getattr(issue, "issue_analysis_id", "") or "").strip()
    }
    if not keyed:
        st.info("No governed issue identities are available for custom task initiation.")
        return

    ordered_ids = tuple(keyed)
    selected_id = st.selectbox(
        "Related legal issue",
        ordered_ids,
        format_func=lambda value: _issue_label(keyed[value]),
        key=f"case_operator_custom_task_issue_{case_id}",
    )
    selected_issue = keyed[selected_id]
    issue_name = _issue_label(selected_issue)

    title = st.text_input(
        "Task title",
        key=f"case_operator_custom_task_title_{case_id}",
        placeholder="e.g. Investigate CACI vacancies and alternative work",
    )
    objective = st.text_area(
        "Why this matters / investigation objective",
        key=f"case_operator_custom_task_objective_{case_id}",
        height=170,
        placeholder=(
            "Describe the specific evidential question to investigate and why it "
            "matters to the selected legal issue."
        ),
    )

    if not (_clean(title) and _clean(objective)):
        st.caption(
            "Enter both a task title and investigation objective. The existing "
            "professional task-approval control will then be shown."
        )
        return

    st.caption(
        "The task below is still only proposed. Creation remains subject to the "
        "existing professional approval control."
    )

    show_issue_task_creator(
        case_id=case_id,
        issue_analysis_id=selected_id,
        issue_name=issue_name,
        origin="next_legal_action",
        originating_question=_clean(objective),
        default_title=_clean(title),
        why_it_matters=_clean(objective),
    )
