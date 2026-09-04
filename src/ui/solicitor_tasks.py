"""Solicitor-facing Matter Workflow v1 task surfaces."""
from __future__ import annotations
from authentication import current_user_identity
from case_management import CaseRepository
from case_management.access import MatterMutationError

from datetime import date
import streamlit as st

from solicitor_tasks import (
    SolicitorTask,
    SolicitorTaskError,
    TaskOrigin,
    TaskPriority,
    TaskStatus,
    create_task,
    load_tasks,
    update_task,
)

_STATUS = {
    TaskStatus.OPEN: "Open",
    TaskStatus.IN_PROGRESS: "In progress",
    TaskStatus.COMPLETED: "Completed",
    TaskStatus.DEFERRED: "Deferred",
}
_PRIORITY = {
    TaskPriority.NOT_SET: "Not set",
    TaskPriority.HIGH: "High",
    TaskPriority.MEDIUM: "Medium",
    TaskPriority.LOW: "Low",
}


def _from_label(mapping, label):
    for value, display in mapping.items():
        if display == label:
            return value
    raise ValueError(label)


def _origin_label(origin: TaskOrigin) -> str:
    if origin is TaskOrigin.NEXT_LEGAL_ACTION:
        return "Next legal action"
    if origin is TaskOrigin.WHAT_REMAINS_UNCLEAR:
        return "What remains unclear"
    if origin is TaskOrigin.EVIDENCE:
        return "Evidence"
    if origin is TaskOrigin.CHRONOLOGY:
        return "Chronology"
    raise ValueError(origin)


def _evidence_label(citation, document_name, page) -> str:
    if citation:
        return citation
    value = document_name or "Evidence"
    if page is not None:
        value += f" — p.{page}"
    return value


def _humanise_token(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "_" in raw or ("-" in raw and " " not in raw):
        return " ".join(raw.replace("_", " ").replace("-", " ").split()).lower().capitalize()
    return raw


def _chronology_label(event_id, chronology_time, event_type) -> str:
    context = " · ".join(
        value
        for value in (
            str(chronology_time or "").strip(),
            _humanise_token(event_type),
        )
        if value
    )
    # The immutable event ID remains task provenance, but it is not solicitor-facing
    # display text when no useful chronology context is available.
    return context or "Chronology event"


def show_issue_task_creator(
    *,
    case_id: str,
    issue_analysis_id: str,
    issue_name: str,
    origin: str,
    originating_question: str,
    default_title: str,
    why_it_matters: str,
    origin_evidence_key: str | None = None,
    origin_evidence_citation: str | None = None,
    origin_document_name: str | None = None,
    origin_page: int | None = None,
    origin_chronology_event_id: str | None = None,
    origin_chronology_time: str | None = None,
    origin_chronology_event_type: str | None = None,
    related_issues: tuple[tuple[str, str], ...] | None = None,
) -> None:
    task_origin = TaskOrigin(origin)
    key = "::".join(
        (
            "mw1_create_task",
            case_id,
            issue_analysis_id,
            task_origin.value,
            origin_evidence_key or origin_chronology_event_id or "no-origin-reference",
        )
    )

    with st.expander("Create task", expanded=False):
        with st.form(
            key=key + "::form",
            clear_on_submit=False,
            border=False,
        ):
            st.caption(
                "Creates matter work only. Creating or completing this task does not change the legal assessment."
            )

            title = st.text_input(
                "Task title",
                value=" ".join(str(default_title or "").split()),
                key=key + "::title",
            )
            priority_label = st.selectbox(
                "Priority",
                options=tuple(_PRIORITY.values()),
                index=0,
                key=key + "::priority",
            )
            due_date = st.date_input(
                "Due date",
                value=None,
                key=key + "::due",
            )
            assigned_to = st.text_input(
                "Assigned to",
                value="",
                key=key + "::assigned",
            )

            resolved_issue_id = issue_analysis_id
            resolved_issue_name = issue_name
            if related_issues:
                issue_names = dict(related_issues)
                resolved_issue_id = st.selectbox(
                    "Related issue",
                    options=tuple(issue_names),
                    key=key + "::related_issue",
                    format_func=lambda value: issue_names[value],
                )
                resolved_issue_name = issue_names[resolved_issue_id]
            else:
                st.markdown("**Related issue**")
                st.write(issue_name)

            if task_origin is TaskOrigin.EVIDENCE:
                st.markdown("**Evidence**")
                st.write(
                    _evidence_label(
                        origin_evidence_citation,
                        origin_document_name,
                        origin_page,
                    )
                )
            elif task_origin is TaskOrigin.CHRONOLOGY:
                st.markdown("**Chronology event**")
                st.write(
                    _chronology_label(
                        origin_chronology_event_id,
                        origin_chronology_time,
                        origin_chronology_event_type,
                    )
                )

            st.markdown("**Why this matters**")
            st.write(why_it_matters)

            st.markdown("**Origin**")
            st.write(
                _origin_label(task_origin)
                + " → "
                + originating_question
            )

            submitted = st.form_submit_button(
                "Create task",
                type="primary",
            )

        if submitted:
            try:
                task = create_task(
                    case_id=case_id,
                    access=CaseRepository().require_access(current_user_identity(), case_id),
                    title=title,
                    priority=_from_label(_PRIORITY, priority_label),
                    due_date=due_date,
                    assigned_to=assigned_to,
                    issue_analysis_id=resolved_issue_id,
                    issue_name=resolved_issue_name,
                    originating_question=originating_question,
                    origin=task_origin,
                    why_it_matters=why_it_matters,
                    origin_evidence_key=origin_evidence_key,
                    origin_evidence_citation=origin_evidence_citation,
                    origin_document_name=origin_document_name,
                    origin_page=origin_page,
                    origin_chronology_event_id=origin_chronology_event_id,
                    origin_chronology_time=origin_chronology_time,
                    origin_chronology_event_type=origin_chronology_event_type,
                )
            except (SolicitorTaskError, MatterMutationError) as exc:
                st.error(str(exc))
            else:
                st.success("Task created: " + task.title)


def _due_value(task: SolicitorTask):
    return date.fromisoformat(task.due_date) if task.due_date else None


def _render_task(task: SolicitorTask) -> None:
    with st.container(border=True):
        st.subheader(task.title)
        left, middle, right = st.columns(3)
        left.markdown("**Status**")
        left.write(_STATUS[task.status])
        middle.markdown("**Priority**")
        middle.write(_PRIORITY[task.priority])
        right.markdown("**Due date**")
        right.write(task.due_date or "Not set")

        st.markdown("**Assigned to**")
        st.write(task.assigned_to or "Not assigned")

        st.markdown("**Related issue**")
        st.write(task.issue_name)

        if task.origin is TaskOrigin.EVIDENCE:
            st.markdown("**Evidence**")
            st.write(
                _evidence_label(
                    task.origin_evidence_citation,
                    task.origin_document_name,
                    task.origin_page,
                )
            )
        elif task.origin is TaskOrigin.CHRONOLOGY:
            st.markdown("**Chronology event**")
            st.write(
                _chronology_label(
                    task.origin_chronology_event_id,
                    task.origin_chronology_time,
                    task.origin_chronology_event_type,
                )
            )

        st.markdown("**Why this matters**")
        st.write(task.why_it_matters)

        st.markdown("**Origin**")
        st.write(_origin_label(task.origin) + " → " + task.originating_question)

        with st.expander("Update task", expanded=False):
            with st.form(
                key="mw1_update_form::" + task.task_id,
                clear_on_submit=False,
                border=False,
            ):
                title = st.text_input(
                    "Task title",
                    value=task.title,
                    key="mw1_title::" + task.task_id,
                )
                status_label = st.selectbox(
                    "Status",
                    options=tuple(_STATUS.values()),
                    index=list(_STATUS).index(task.status),
                    key="mw1_status::" + task.task_id,
                )
                priority_label = st.selectbox(
                    "Priority",
                    options=tuple(_PRIORITY.values()),
                    index=list(_PRIORITY).index(task.priority),
                    key="mw1_priority::" + task.task_id,
                )
                due_date = st.date_input(
                    "Due date",
                    value=_due_value(task),
                    key="mw1_due::" + task.task_id,
                )
                assigned_to = st.text_input(
                    "Assigned to",
                    value=task.assigned_to or "",
                    key="mw1_assigned::" + task.task_id,
                )

                submitted = st.form_submit_button(
                    "Save task",
                    type="primary",
                )

            if submitted:
                try:
                    update_task(
                        case_id=task.case_id,
                        access=CaseRepository().require_access(current_user_identity(), task.case_id),
                        task_id=task.task_id,
                        title=title,
                        status=_from_label(_STATUS, status_label),
                        priority=_from_label(_PRIORITY, priority_label),
                        due_date=due_date,
                        due_date_supplied=True,
                        assigned_to=assigned_to,
                        assigned_to_supplied=True,
                    )
                except (SolicitorTaskError, MatterMutationError) as exc:
                    st.error(str(exc))
                else:
                    st.success("Task updated.")
                    st.rerun()


def show_solicitor_tasks(case_id: str) -> None:
    if st.button("← Back to legal issues", key="mw1_back_to_issues"):
        st.session_state.pop("mw1_task_workspace_case_id", None)
        st.rerun()

    st.title("Tasks")
    st.caption(
        "Matter work arising from legal analysis and solicitor decisions. "
        "Task completion does not prove a proposition or change the current case assessment."
    )

    try:
        tasks = load_tasks(case_id)
    except (SolicitorTaskError, MatterMutationError) as exc:
        st.error(str(exc))
        return

    selected = st.selectbox(
        "Show",
        options=("All",) + tuple(_STATUS.values()),
        index=0,
        key="mw1_task_filter",
    )
    if selected != "All":
        wanted = _from_label(_STATUS, selected)
        tasks = tuple(task for task in tasks if task.status is wanted)

    if not tasks:
        st.info("No tasks in this view.")
        return

    for task in tasks:
        _render_task(task)


__all__ = ["show_issue_task_creator", "show_solicitor_tasks"]
