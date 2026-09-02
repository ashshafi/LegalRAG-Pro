"""Operational solicitor task persistence for Matter Workflow v1.

Tasks are matter work only. Task creation or completion does not create
evidence, prove a legal proposition, revise analytical authority, or activate
an assessment.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

_SCHEMA_VERSION = "1.0"
_DEFAULT_ROOT = Path("solicitor_tasks")
_SAFE_CASE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class SolicitorTaskError(RuntimeError):
    pass


class TaskStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DEFERRED = "deferred"


class TaskPriority(str, Enum):
    NOT_SET = "not_set"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskOrigin(str, Enum):
    NEXT_LEGAL_ACTION = "next_legal_action"
    WHAT_REMAINS_UNCLEAR = "what_remains_unclear"


@dataclass(frozen=True)
class SolicitorTask:
    task_id: str
    case_id: str
    title: str
    status: TaskStatus
    priority: TaskPriority
    due_date: str | None
    assigned_to: str | None
    issue_analysis_id: str
    issue_name: str
    originating_question: str
    origin: TaskOrigin
    why_it_matters: str
    created_at: str
    updated_at: str


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _required(value: object, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SolicitorTaskError(name + " is required.")
    return text


def _optional(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _due(value: object) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except ValueError as exc:
        raise SolicitorTaskError("due_date must use YYYY-MM-DD.") from exc


def _case_name(case_id: str) -> str:
    value = _required(case_id, "case_id")
    if not _SAFE_CASE_ID.fullmatch(value) or value in {".", ".."}:
        raise SolicitorTaskError("case_id is invalid.")
    return value


def _root(root) -> Path:
    if root is not None:
        return Path(root)
    configured = os.getenv("LEGALRAG_SOLICITOR_TASK_ROOT", "").strip()
    return Path(configured) if configured else _DEFAULT_ROOT


def task_event_path(case_id: str, *, root=None) -> Path:
    return _root(root) / _case_name(case_id) / "events.jsonl"


def _snapshot(task: SolicitorTask) -> dict[str, Any]:
    value = asdict(task)
    value["status"] = task.status.value
    value["priority"] = task.priority.value
    value["origin"] = task.origin.value
    return value


def _from_snapshot(value: object) -> SolicitorTask:
    if not isinstance(value, dict):
        raise SolicitorTaskError("Task event snapshot is invalid.")
    try:
        return SolicitorTask(
            task_id=_required(value.get("task_id"), "task_id"),
            case_id=_required(value.get("case_id"), "case_id"),
            title=_required(value.get("title"), "title"),
            status=TaskStatus(value.get("status")),
            priority=TaskPriority(value.get("priority")),
            due_date=_due(value.get("due_date")),
            assigned_to=_optional(value.get("assigned_to")),
            issue_analysis_id=_required(value.get("issue_analysis_id"), "issue_analysis_id"),
            issue_name=_required(value.get("issue_name"), "issue_name"),
            originating_question=_required(value.get("originating_question"), "originating_question"),
            origin=TaskOrigin(value.get("origin")),
            why_it_matters=_required(value.get("why_it_matters"), "why_it_matters"),
            created_at=_required(value.get("created_at"), "created_at"),
            updated_at=_required(value.get("updated_at"), "updated_at"),
        )
    except (TypeError, ValueError) as exc:
        raise SolicitorTaskError("Task event snapshot is invalid.") from exc


def _append(task: SolicitorTask, event_type: str, root=None) -> None:
    path = task_event_path(task.case_id, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "schema_version": _SCHEMA_VERSION,
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "recorded_at": _now(),
        "case_id": task.case_id,
        "task_id": task.task_id,
        "task": _snapshot(task),
    }
    payload = json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(payload + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def create_task(
    *,
    case_id: str,
    title: str,
    priority: TaskPriority | str,
    issue_analysis_id: str,
    issue_name: str,
    originating_question: str,
    origin: TaskOrigin | str,
    why_it_matters: str,
    due_date=None,
    assigned_to=None,
    root=None,
) -> SolicitorTask:
    timestamp = _now()
    try:
        normalised_priority = TaskPriority(priority)
        normalised_origin = TaskOrigin(origin)
    except ValueError as exc:
        raise SolicitorTaskError("Unsupported task priority or origin.") from exc
    task = SolicitorTask(
        task_id=str(uuid.uuid4()),
        case_id=_case_name(case_id),
        title=_required(title, "title"),
        status=TaskStatus.OPEN,
        priority=normalised_priority,
        due_date=_due(due_date),
        assigned_to=_optional(assigned_to),
        issue_analysis_id=_required(issue_analysis_id, "issue_analysis_id"),
        issue_name=_required(issue_name, "issue_name"),
        originating_question=_required(originating_question, "originating_question"),
        origin=normalised_origin,
        why_it_matters=_required(why_it_matters, "why_it_matters"),
        created_at=timestamp,
        updated_at=timestamp,
    )
    _append(task, "TASK_CREATED", root=root)
    return task


def load_tasks(case_id: str, *, root=None) -> tuple[SolicitorTask, ...]:
    path = task_event_path(case_id, root=root)
    if not path.exists():
        return ()
    latest = {}
    order = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise SolicitorTaskError(f"Invalid task event JSON at line {line_number}.") from exc
            if not isinstance(event, dict):
                raise SolicitorTaskError(f"Invalid task event at line {line_number}.")
            if event.get("schema_version") != _SCHEMA_VERSION:
                raise SolicitorTaskError(f"Unsupported task schema at line {line_number}.")
            if event.get("event_type") not in {"TASK_CREATED", "TASK_UPDATED"}:
                raise SolicitorTaskError(f"Unsupported task event type at line {line_number}.")
            task = _from_snapshot(event.get("task"))
            if task.case_id != case_id or event.get("case_id") != case_id:
                raise SolicitorTaskError(f"Cross-matter task event at line {line_number}.")
            if event.get("task_id") != task.task_id:
                raise SolicitorTaskError(f"Task identity mismatch at line {line_number}.")
            if task.task_id not in latest:
                order.append(task.task_id)
            latest[task.task_id] = task
    return tuple(latest[task_id] for task_id in order)


def update_task(
    *,
    case_id: str,
    task_id: str,
    title=None,
    status: TaskStatus | str | None = None,
    priority: TaskPriority | str | None = None,
    due_date=None,
    due_date_supplied: bool = False,
    assigned_to=None,
    assigned_to_supplied: bool = False,
    root=None,
) -> SolicitorTask:
    current = {task.task_id: task for task in load_tasks(case_id, root=root)}.get(task_id)
    if current is None:
        raise SolicitorTaskError("Task was not found in this matter.")
    changes: dict[str, Any] = {"updated_at": _now()}
    if title is not None:
        changes["title"] = _required(title, "title")
    if status is not None:
        try:
            changes["status"] = TaskStatus(status)
        except ValueError as exc:
            raise SolicitorTaskError("Unsupported task status.") from exc
    if priority is not None:
        try:
            changes["priority"] = TaskPriority(priority)
        except ValueError as exc:
            raise SolicitorTaskError("Unsupported task priority.") from exc
    if due_date_supplied:
        changes["due_date"] = _due(due_date)
    if assigned_to_supplied:
        changes["assigned_to"] = _optional(assigned_to)
    updated = replace(current, **changes)
    _append(updated, "TASK_UPDATED", root=root)
    return updated


__all__ = [
    "SolicitorTask",
    "SolicitorTaskError",
    "TaskOrigin",
    "TaskPriority",
    "TaskStatus",
    "create_task",
    "load_tasks",
    "task_event_path",
    "update_task",
]
