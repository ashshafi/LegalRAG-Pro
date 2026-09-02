"""Solicitor-facing Matter Workflow v1 task surfaces."""
from __future__ import annotations

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
    return "Next legal action" if origin is TaskOrigin.NEXT_LEGAL_ACTION else "What remains unclear"


def show_issue_task_creator(
    *,
    case_id: str,
    issue_analysis_id: str,
    issue_name: str,
    origin: str,
    originating_question: str,
    default_title: str,
    why_it_matters: str,
) -> None:
    task_origin = TaskOrigin(origin)
    key = "::".join(("mw1_create_task", case_id, issue_analysis_id, task_origin.value))

    with st.expander("Create task", expanded=False):
        st.caption(
            "Creates matter work only. Creating or completing this task does not change the legal assessment."
        )
        title = st.text_input("Task title", value=" ".join(str(default_title or "").split()), key=key + "::title")
        priority_label = st.selectbox(
            "Priority",
            options=tuple(_PRIORITY.values()),
            index=0,
            key=key + "::priority",
        )
        due_date = st.date_input("Due date", value=None, key=key + "::due")
        assigned_to = st.text_input("Assigned to", value="", key=key + "::assigned")
        st.markdown("**Related issue**")
        st.write(issue_name)
        st.markdown("**Why this matters**")
        st.write(why_it_matters)
        st.markdown("**Origin**")
        st.write(_origin_label(task_origin) + " → " + originating_question)

        if st.button("Create task", key=key + "::submit"):
            try:
                task = create_task(
                    case_id=case_id,
                    title=title,
                    priority=_from_label(_PRIORITY, priority_label),
                    due_date=due_date,
                    assigned_to=assigned_to,
                    issue_analysis_id=issue_analysis_id,
                    issue_name=issue_name,
                    originating_question=originating_question,
                    origin=task_origin,
                    why_it_matters=why_it_matters,
                )
            except SolicitorTaskError as exc:
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
        st.markdown("**Why this matters**")
        st.write(task.why_it_matters)
        st.markdown("**Origin**")
        st.write(_origin_label(task.origin) + " → " + task.originating_question)

        with st.expander("Update task", expanded=False):
            title = st.text_input("Task title", value=task.title, key="mw1_title::" + task.task_id)
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
            due_date = st.date_input("Due date", value=_due_value(task), key="mw1_due::" + task.task_id)
            assigned_to = st.text_input(
                "Assigned to",
                value=task.assigned_to or "",
                key="mw1_assigned::" + task.task_id,
            )
            if st.button("Save task", key="mw1_save::" + task.task_id):
                try:
                    update_task(
                        case_id=task.case_id,
                        task_id=task.task_id,
                        title=title,
                        status=_from_label(_STATUS, status_label),
                        priority=_from_label(_PRIORITY, priority_label),
                        due_date=due_date,
                        due_date_supplied=True,
                        assigned_to=assigned_to,
                        assigned_to_supplied=True,
                    )
                except SolicitorTaskError as exc:
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
    except SolicitorTaskError as exc:
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
