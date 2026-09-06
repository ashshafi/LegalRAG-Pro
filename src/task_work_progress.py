"""Append-only operational work history for solicitor matter tasks.

This service is deliberately separate from the SolicitorTask snapshot/event schema.
Recording task work does not change task status, priority, analytical authority,
evidence, chronology, or the Current Assessment.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import json
import os
from pathlib import Path
import uuid

from case_management.access import MatterAccessContext, require_matter_mutation
from solicitor_tasks import load_tasks, task_event_path


TASK_WORK_PROGRESS_SCHEMA_VERSION = "task-work-progress/1.0"
_TASK_WORK_EVENT_TYPE = "TASK_WORK_RECORDED"


class TaskWorkProgressError(RuntimeError):
    """Raised when persisted task-work history is invalid."""


class TaskWorkOutcome(str, Enum):
    COMPLETE = "COMPLETE"
    CONTINUE = "CONTINUE"
    BLOCKED = "BLOCKED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class TaskWorkProgress:
    schema_version: str
    progress_id: str
    case_id: str
    task_id: str
    recorded_at: str
    question: str
    answer: str
    outcome: TaskWorkOutcome


def _required(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TaskWorkProgressError(field_name + " must be text.")
    result = value.strip()
    if not result:
        raise TaskWorkProgressError(field_name + " must not be blank.")
    return result


def _case_name(value: object) -> str:
    return _required(value, "case_id")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def task_work_progress_path(case_id: str, *, root=None) -> Path:
    """Keep operational task-work history beside, but separate from, task events."""
    return task_event_path(case_id, root=root).with_name("work_progress.jsonl")


def _record_from_value(value: object) -> TaskWorkProgress:
    if not isinstance(value, dict):
        raise TaskWorkProgressError("Task-work record must be an object.")
    try:
        schema_version = _required(value.get("schema_version"), "schema_version")
        if schema_version != TASK_WORK_PROGRESS_SCHEMA_VERSION:
            raise TaskWorkProgressError("Unsupported task-work progress schema.")
        return TaskWorkProgress(
            schema_version=schema_version,
            progress_id=_required(value.get("progress_id"), "progress_id"),
            case_id=_case_name(value.get("case_id")),
            task_id=_required(value.get("task_id"), "task_id"),
            recorded_at=_required(value.get("recorded_at"), "recorded_at"),
            question=_required(value.get("question"), "question"),
            answer=_required(value.get("answer"), "answer"),
            outcome=TaskWorkOutcome(value.get("outcome")),
        )
    except ValueError as exc:
        raise TaskWorkProgressError("Unsupported task-work outcome.") from exc


def append_task_work_progress(
    *,
    case_id: str,
    access: MatterAccessContext,
    task_id: str,
    question: str,
    answer: str,
    outcome: TaskWorkOutcome | str,
    root=None,
) -> TaskWorkProgress:
    """Append one governed operational task-work result after an explicit work action."""
    require_matter_mutation(access)

    normalized_case_id = _case_name(case_id)
    if access.case_id != normalized_case_id:
        raise TaskWorkProgressError("Matter access does not match task-work case_id.")

    normalized_task_id = _required(task_id, "task_id")
    known = {
        task.task_id: task
        for task in load_tasks(normalized_case_id, root=root)
    }
    if normalized_task_id not in known:
        raise TaskWorkProgressError("Task was not found in this matter.")

    try:
        normalized_outcome = TaskWorkOutcome(outcome)
    except ValueError as exc:
        raise TaskWorkProgressError("Unsupported task-work outcome.") from exc

    record = TaskWorkProgress(
        schema_version=TASK_WORK_PROGRESS_SCHEMA_VERSION,
        progress_id=str(uuid.uuid4()),
        case_id=normalized_case_id,
        task_id=normalized_task_id,
        recorded_at=_now(),
        question=_required(question, "question"),
        answer=_required(answer, "answer"),
        outcome=normalized_outcome,
    )

    event = {
        "schema_version": TASK_WORK_PROGRESS_SCHEMA_VERSION,
        "event_id": str(uuid.uuid4()),
        "event_type": _TASK_WORK_EVENT_TYPE,
        "recorded_at": record.recorded_at,
        "case_id": normalized_case_id,
        "task_id": normalized_task_id,
        "progress": {
            **asdict(record),
            "outcome": record.outcome.value,
        },
    }

    path = task_work_progress_path(normalized_case_id, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        event,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(payload + "\n")
        handle.flush()
        os.fsync(handle.fileno())

    return record


def load_task_work_progress(
    case_id: str,
    task_id: str,
    *,
    root=None,
) -> tuple[TaskWorkProgress, ...]:
    """Load append-only task work in recorded order, failing closed on invalid events."""
    normalized_case_id = _case_name(case_id)
    normalized_task_id = _required(task_id, "task_id")
    path = task_work_progress_path(normalized_case_id, root=root)
    if not path.exists():
        return ()

    records: list[TaskWorkProgress] = []
    seen_progress_ids: set[str] = set()
    seen_event_ids: set[str] = set()

    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise TaskWorkProgressError(
                    f"Invalid task-work event JSON at line {line_number}."
                ) from exc

            if not isinstance(event, dict):
                raise TaskWorkProgressError(
                    f"Invalid task-work event at line {line_number}."
                )
            if event.get("schema_version") != TASK_WORK_PROGRESS_SCHEMA_VERSION:
                raise TaskWorkProgressError(
                    f"Unsupported task-work schema at line {line_number}."
                )
            if event.get("event_type") != _TASK_WORK_EVENT_TYPE:
                raise TaskWorkProgressError(
                    f"Unsupported task-work event type at line {line_number}."
                )

            event_id = _required(event.get("event_id"), "event_id")
            if event_id in seen_event_ids:
                raise TaskWorkProgressError(
                    f"Duplicate task-work event_id at line {line_number}."
                )
            seen_event_ids.add(event_id)

            record = _record_from_value(event.get("progress"))
            if event.get("case_id") != normalized_case_id or record.case_id != normalized_case_id:
                raise TaskWorkProgressError(
                    f"Cross-matter task-work event at line {line_number}."
                )
            if event.get("task_id") != record.task_id:
                raise TaskWorkProgressError(
                    f"Task-work identity mismatch at line {line_number}."
                )
            if event.get("recorded_at") != record.recorded_at:
                raise TaskWorkProgressError(
                    f"Task-work timestamp mismatch at line {line_number}."
                )
            if record.progress_id in seen_progress_ids:
                raise TaskWorkProgressError(
                    f"Duplicate task-work progress_id at line {line_number}."
                )
            seen_progress_ids.add(record.progress_id)

            if record.task_id == normalized_task_id:
                records.append(record)

    return tuple(records)


__all__ = [
    "TASK_WORK_PROGRESS_SCHEMA_VERSION",
    "TaskWorkOutcome",
    "TaskWorkProgress",
    "TaskWorkProgressError",
    "append_task_work_progress",
    "load_task_work_progress",
    "task_work_progress_path",
]
