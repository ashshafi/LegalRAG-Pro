from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import ui.case_operator as case_operator
from solicitor_tasks import TaskStatus
from task_work_progress import TaskWorkProgressError


def _task(
    task_id: str,
    *,
    priority: str = "high",
    status=TaskStatus.OPEN,
):
    return SimpleNamespace(
        task_id=task_id,
        title=task_id,
        priority=SimpleNamespace(value=priority),
        status=status,
    )


def _entry(answer: str):
    return SimpleNamespace(answer=answer)


def _install_history(monkeypatch, histories):
    def load(case_id, task_id):
        value = histories.get(task_id, ())
        if isinstance(value, Exception):
            raise value
        return tuple(value)

    monkeypatch.setattr(case_operator, "load_task_work_progress", load)


def test_ready_tasks_are_ranked_by_priority_then_canonical_order(monkeypatch):
    tasks = (
        _task("high-a", priority="high"),
        _task("low", priority="low"),
        _task("high-b", priority="high"),
        _task("medium", priority="medium"),
        _task("unset", priority="not_set"),
    )
    _install_history(monkeypatch, {})

    ready, blocked, unavailable = case_operator._project_approved_task_queue(
        case_id="case",
        open_tasks=tasks,
    )

    assert [task.task_id for task in ready] == [
        "high-a",
        "high-b",
        "medium",
        "low",
        "unset",
    ]
    assert blocked == ()
    assert unavailable == ()


def test_latest_blocked_task_is_excluded_from_ready_queue(monkeypatch):
    blocked_task = _task("blocked", status=TaskStatus.IN_PROGRESS)
    ready_task = _task("ready", status=TaskStatus.OPEN)

    _install_history(
        monkeypatch,
        {
            "blocked": (
                _entry(
                    "Work cannot proceed.\n"
                    "NEXT_TASK_INVESTIGATION: obtain external material\n"
                    "TASK_OUTCOME: BLOCKED"
                ),
            ),
            "ready": (),
        },
    )

    ready, blocked, unavailable = case_operator._project_approved_task_queue(
        case_id="case",
        open_tasks=(blocked_task, ready_task),
    )

    assert [task.task_id for task in ready] == ["ready"]
    assert [task.task_id for task in blocked] == ["blocked"]
    assert unavailable == ()


def test_open_task_with_latest_blocked_work_is_also_queue_blocked(monkeypatch):
    task = _task("blocked-open", status=TaskStatus.OPEN)

    _install_history(
        monkeypatch,
        {
            "blocked-open": (
                _entry(
                    "NEXT_TASK_INVESTIGATION: obtain document\n"
                    "TASK_OUTCOME: BLOCKED"
                ),
            ),
        },
    )

    ready, blocked, unavailable = case_operator._project_approved_task_queue(
        case_id="case",
        open_tasks=(task,),
    )

    assert ready == ()
    assert [item.task_id for item in blocked] == ["blocked-open"]
    assert unavailable == ()


def test_failed_analytical_history_is_not_used_as_latest_substantive_work(monkeypatch):
    task = _task("filtered", status=TaskStatus.IN_PROGRESS)

    generic_failure = (
        "I could not validate the governed analytical constraint for this answer. "
        "No analytically governed answer has been presented."
    )

    _install_history(
        monkeypatch,
        {
            "filtered": (
                _entry(
                    "NEXT_TASK_INVESTIGATION: obtain external material\n"
                    "TASK_OUTCOME: BLOCKED"
                ),
                _entry(generic_failure),
            ),
        },
    )

    ready, blocked, unavailable = case_operator._project_approved_task_queue(
        case_id="case",
        open_tasks=(task,),
    )

    assert ready == ()
    assert [item.task_id for item in blocked] == ["filtered"]
    assert unavailable == ()


def test_completed_and_deferred_tasks_are_not_projected(monkeypatch):
    tasks = (
        _task("completed", status=TaskStatus.COMPLETED),
        _task("deferred", status=TaskStatus.DEFERRED),
    )
    _install_history(monkeypatch, {})

    ready, blocked, unavailable = case_operator._project_approved_task_queue(
        case_id="case",
        open_tasks=tasks,
    )

    assert ready == ()
    assert blocked == ()
    assert unavailable == ()


def test_invalid_history_is_not_recommended(monkeypatch):
    task = _task("invalid", status=TaskStatus.OPEN)

    _install_history(
        monkeypatch,
        {
            "invalid": TaskWorkProgressError("invalid persisted history"),
        },
    )

    ready, blocked, unavailable = case_operator._project_approved_task_queue(
        case_id="case",
        open_tasks=(task,),
    )

    assert ready == ()
    assert blocked == ()
    assert [item.task_id for item in unavailable] == ["invalid"]


def test_queue_projection_does_not_call_provider_or_mutate_task(monkeypatch):
    task = _task("ready")

    _install_history(monkeypatch, {})

    monkeypatch.setattr(
        case_operator,
        "_run_question",
        lambda *args, **kwargs: pytest.fail("provider must not be called"),
    )
    monkeypatch.setattr(
        case_operator,
        "_update_task_status",
        lambda *args, **kwargs: pytest.fail("task status must not be mutated"),
    )

    ready, blocked, unavailable = case_operator._project_approved_task_queue(
        case_id="case",
        open_tasks=(task,),
    )

    assert [item.task_id for item in ready] == ["ready"]
    assert blocked == ()
    assert unavailable == ()


def test_execution_ui_orders_ready_before_blocked_without_removing_blocked_access():
    source = Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")

    assert (
        "ordered_tasks = ready_tasks + blocked_tasks + unavailable_tasks"
        in source
    )
    assert "Recommended next approved task" in source
    assert "Blocked task work remains preserved" in source
    assert '"Retry blocked task"' in source