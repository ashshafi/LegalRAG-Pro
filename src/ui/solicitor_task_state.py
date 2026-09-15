"""Read-only presentation access to the Case Operator's approved-task queue."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RecommendedTaskView:
    task_id: str
    title: str
    issue_name: str
    why_it_matters: str


def recommended_next_approved_task(case_id: str) -> RecommendedTaskView | None:
    """Return exactly the task the Case Operator would present as its next READY task."""
    from solicitor_tasks import TaskStatus, load_tasks
    from ui.case_operator import _project_approved_task_queue

    tasks = tuple(load_tasks(case_id))
    open_tasks = tuple(
        task for task in tasks
        if getattr(task, "status", None) in {TaskStatus.OPEN, TaskStatus.IN_PROGRESS}
    )
    ready_tasks, _blocked_tasks, _unavailable_tasks = _project_approved_task_queue(
        case_id=case_id,
        open_tasks=open_tasks,
    )
    if not ready_tasks:
        return None
    task = ready_tasks[0]
    return RecommendedTaskView(
        task_id=str(getattr(task, "task_id", "") or ""),
        title=str(getattr(task, "title", "Task") or "Task").strip(),
        issue_name=str(getattr(task, "issue_name", "Legal issue") or "Legal issue").strip(),
        why_it_matters=str(getattr(task, "why_it_matters", "") or "").strip(),
    )


__all__ = ["RecommendedTaskView", "recommended_next_approved_task"]
