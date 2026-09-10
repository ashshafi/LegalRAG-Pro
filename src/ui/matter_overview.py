"""Read-only Matter Overview presentation for the LegalRAG Pro workspace shell."""

from __future__ import annotations

from collections.abc import MutableMapping
from datetime import date
from typing import Any, Protocol

import streamlit as st

from case_reporting.validation import validate_case_report_projection


MATTER_OVERVIEW_VIEW_KEY = "ppr4_matter_overview_view"
MATTER_OVERVIEW_CASE_KEY = "ppr4_matter_overview_case_id"


class MatterRecord(Protocol):
    """Minimal persisted matter presentation contract."""

    case_id: str
    name: str
    case_number: str | None
    claimant: str | None
    respondent: str | None
    status: str


def set_matter_overview_view(
    session_state: MutableMapping[str, Any],
    active: bool,
) -> None:
    """Set the presentation-only Matter Overview route state."""

    session_state[MATTER_OVERVIEW_VIEW_KEY] = bool(active)


def is_matter_overview_active(session_state: MutableMapping[str, Any]) -> bool:
    """Return whether the presentation-only Matter Overview route is active."""

    return bool(session_state.get(MATTER_OVERVIEW_VIEW_KEY, False))


def synchronise_matter_overview_session_state(
    active_case_id: str | None,
    *,
    session_state: MutableMapping[str, Any] | None = None,
) -> None:
    """Default each newly selected matter to Overview without overriding user navigation."""

    state = st.session_state if session_state is None else session_state
    previous_case_id = state.get(MATTER_OVERVIEW_CASE_KEY)

    if previous_case_id != active_case_id:
        state[MATTER_OVERVIEW_CASE_KEY] = active_case_id
        set_matter_overview_view(state, active_case_id is not None)
        return

    if MATTER_OVERVIEW_VIEW_KEY not in state:
        set_matter_overview_view(state, active_case_id is not None)


def _metric_columns(values: tuple[tuple[str, str | int], ...]) -> None:
    for start in range(0, len(values), 2):
        row = values[start : start + 2]
        columns = st.columns(len(row))
        for column, (label, value) in zip(columns, row, strict=True):
            column.metric(label, value)


def _status_text(value: str) -> str:
    stripped = str(value).strip()
    return stripped.title() if stripped else "Not recorded"


def _party_text(value: str | None) -> str:
    if value is None:
        return "Not recorded"
    stripped = str(value).strip()
    return stripped if stripped else "Not recorded"


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().casefold()


def _issue_position(issue: Any) -> str:
    counts = getattr(issue, "synthesis_counts", None)
    if counts is None:
        return "NOT ASSESSED"
    if int(getattr(counts, "disputed", 0) or 0):
        return "DISPUTED"
    if int(getattr(counts, "insufficiently_evidenced", 0) or 0):
        return "EVIDENCE INCOMPLETE"
    if int(getattr(counts, "unresolved", 0) or 0):
        return "UNRESOLVED"
    if int(getattr(counts, "partially_supported", 0) or 0):
        return "PARTIALLY SUPPORTED"
    if int(getattr(counts, "well_supported", 0) or 0):
        return "WELL SUPPORTED"
    return "NOT ASSESSED"


_UNSETTLED_POSITIONS = {
    "DISPUTED",
    "EVIDENCE INCOMPLETE",
    "UNRESOLVED",
}


def _task_is_active(task: Any) -> bool:
    return _enum_value(getattr(task, "status", "")) in {
        "open",
        "in_progress",
    }


def _task_due(task: Any) -> date | None:
    raw = getattr(task, "due_date", None)
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def _attention_rows(
    issue_dashboard: Any | None,
    tasks: tuple[Any, ...],
    *,
    today: date | None = None,
) -> tuple[dict[str, str], ...]:
    """Rank explicit operational state only; never invent a merits-risk score."""
    current_day = date.today() if today is None else today
    issues = tuple(getattr(issue_dashboard, "issues", ()) or ())
    issue_by_id = {
        str(getattr(issue, "issue_analysis_id", "")): issue
        for issue in issues
        if str(getattr(issue, "issue_analysis_id", "")).strip()
    }

    ranked: list[tuple[tuple[object, ...], dict[str, str]]] = []
    represented_issue_ids: set[str] = set()

    for task_index, task in enumerate(tuple(tasks or ())):
        if not _task_is_active(task):
            continue

        due = _task_due(task)
        priority = _enum_value(getattr(task, "priority", ""))
        issue_id = str(getattr(task, "issue_analysis_id", "") or "").strip()
        issue = issue_by_id.get(issue_id)
        position = _issue_position(issue) if issue is not None else "NOT ASSESSED"

        if due is not None and due < current_day:
            band = 0
            operational_state = "OVERDUE"
        elif priority == "high":
            band = 1
            operational_state = "HIGH-PRIORITY TASK"
        else:
            band = 3
            operational_state = "OPEN TASK"

        due_sort = due if due is not None else date.max
        issue_name = str(
            getattr(task, "issue_name", "")
            or getattr(issue, "issue_name", "")
            or "Matter work"
        ).strip()
        title = str(getattr(task, "title", "") or "Recorded matter task").strip()
        why = str(
            getattr(task, "why_it_matters", "")
            or getattr(task, "originating_question", "")
            or ""
        ).strip()

        row = {
            "kind": "task",
            "issue_id": issue_id,
            "issue_name": issue_name,
            "position": position,
            "work": title,
            "due": due.isoformat() if due is not None else "",
            "priority": priority.upper() if priority else "NOT_SET",
            "operational_state": operational_state,
            "why": why,
        }
        ranked.append(((band, due_sort, task_index), row))
        if issue_id:
            represented_issue_ids.add(issue_id)

    for issue_index, issue in enumerate(issues):
        issue_id = str(getattr(issue, "issue_analysis_id", "") or "").strip()
        if issue_id in represented_issue_ids:
            continue

        position = _issue_position(issue)
        if position not in _UNSETTLED_POSITIONS:
            continue

        issue_name = str(
            getattr(issue, "issue_name", "") or "Legal issue"
        ).strip()
        row = {
            "kind": "issue",
            "issue_id": issue_id,
            "issue_name": issue_name,
            "position": position,
            "work": "No open task is currently recorded for this unsettled issue.",
            "due": "",
            "priority": "",
            "operational_state": "UNSETTLED ISSUE",
            "why": "",
        }
        ranked.append(((2, date.max, issue_index), row))

    ranked.sort(key=lambda item: item[0])
    return tuple(row for _, row in ranked)


def _next_work_due(
    tasks: tuple[Any, ...],
    *,
    today: date | None = None,
) -> str:
    current_day = date.today() if today is None else today
    dated = [
        (due, index, task)
        for index, task in enumerate(tuple(tasks or ()))
        if _task_is_active(task)
        for due in (_task_due(task),)
        if due is not None
    ]
    if not dated:
        return "No due date is recorded for current open work."

    due, _, task = min(dated, key=lambda item: (item[0], item[1]))
    title = str(getattr(task, "title", "") or "Recorded matter task").strip()
    prefix = "Overdue" if due < current_day else "Due"
    return f"{prefix} {due.isoformat()} - {title}"


def _next_recorded_work(
    issue_dashboard: Any | None,
    tasks: tuple[Any, ...],
    *,
    today: date | None = None,
) -> str:
    rows = _attention_rows(issue_dashboard, tasks, today=today)
    for row in rows:
        if row["kind"] == "task":
            issue = row["issue_name"]
            return row["work"] + (f" ({issue})" if issue else "")
    return (
        "No open or in-progress solicitor task is currently recorded. "
        "Review unsettled issues in Legal Issues before deciding the next step."
    )


def show_matter_overview(
    active_case: MatterRecord | None,
    report_projection: Any | None,
    *,
    provider_error: Exception | None = None,
    selected_document_count: int = 0,
    issue_dashboard: Any | None = None,
    tasks: tuple[Any, ...] = (),
    issue_error: Exception | None = None,
    task_error: Exception | None = None,
) -> None:
    """Render solicitor orientation from already-validated read-only application state."""
    st.title("\u2696\ufe0f Matter Overview")

    if active_case is None:
        st.info("Select or create a matter to open its workspace.")
        return

    st.header(str(getattr(active_case, "name", "") or "Active matter"))
    reference = _party_text(getattr(active_case, "case_number", None))
    matter_status = _status_text(str(getattr(active_case, "status", "") or ""))
    st.caption("Reference: " + reference + " \u00b7 Matter status: " + matter_status)

    st.subheader("Parties")
    st.write("Claimant: " + _party_text(getattr(active_case, "claimant", None)))
    st.write("Respondent: " + _party_text(getattr(active_case, "respondent", None)))

    st.subheader("Current matter position")
    st.write("Procedural stage: Not recorded in the matter workspace.")
    st.caption(
        "This Overview does not infer procedural stage, hearing dates or legal deadlines from document text."
    )

    st.subheader("Needs attention now")
    rows = _attention_rows(issue_dashboard, tuple(tasks or ()))
    if rows:
        for index, row in enumerate(rows[:5], start=1):
            st.write(f"{index}. {row['issue_name']}")
            details = [row["operational_state"]]
            if row["position"] != "NOT ASSESSED":
                details.append("Current position: " + row["position"])
            if row["kind"] == "task":
                if row["priority"] and row["priority"] != "NOT_SET":
                    details.append(
                        "Task priority: "
                        + row["priority"].replace("_", " ").title()
                    )
                if row["due"]:
                    details.append("Due: " + row["due"])
            st.caption(" \u00b7 ".join(details))
            st.write(row["work"])
            if row["why"]:
                st.caption("Why it matters: " + row["why"])
    else:
        st.caption(
            "No prioritised attention item can be shown from the currently "
            "available issue and task state."
        )

    if issue_error is not None:
        st.caption(
            "Current legal-issue position could not be loaded safely for this Overview."
        )
    if task_error is not None:
        st.caption(
            "Current solicitor tasks could not be loaded safely for this Overview."
        )

    st.subheader("Next work due")
    st.write(_next_work_due(tuple(tasks or ())))

    st.subheader("Next legal work already recorded")
    st.write(_next_recorded_work(issue_dashboard, tuple(tasks or ())))

    st.subheader("Matter information")

    if provider_error is not None:
        _metric_columns((("Selected documents", int(selected_document_count)),))
        st.error(
            "The stored report projection could not be validated. "
            "No projection-derived matter inventory has been displayed."
        )
        return

    if report_projection is None:
        _metric_columns(
            (
                ("Selected documents", int(selected_document_count)),
                ("Legal issues", "Not available"),
                ("Chronology events", "Not available"),
                ("Evidence citations", "Not available"),
            )
        )
        st.info("No validated frozen report projection is available for this matter.")
        return

    try:
        validate_case_report_projection(report_projection)
    except Exception:
        st.error(
            "The frozen report projection could not be validated. "
            "No projection-derived matter inventory has been displayed."
        )
        _metric_columns((("Selected documents", int(selected_document_count)),))
        return

    projection_case_id = getattr(
        getattr(report_projection, "case_header", None),
        "case_id",
        None,
    )
    if projection_case_id != active_case.case_id:
        st.error(
            "The frozen report projection belongs to a different matter. "
            "No projection-derived matter inventory has been displayed."
        )
        _metric_columns((("Selected documents", int(selected_document_count)),))
        return

    _metric_columns(
        (
            ("Selected documents", int(selected_document_count)),
            ("Legal issues", len(report_projection.issues)),
            ("Chronology events", len(report_projection.chronology)),
            ("Evidence citations", len(report_projection.citations)),
        )
    )
    st.caption(
        "These are read-only matter inventory counts. They are not merits findings, "
        "risk scores or a statement that no issue-level conflict exists."
    )

