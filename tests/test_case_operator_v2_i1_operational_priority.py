from __future__ import annotations

from datetime import date
import inspect
from types import SimpleNamespace as NS

import pytest

import ui.case_operator as case_operator
from solicitor_tasks import TaskStatus
from task_work_progress import TaskWorkProgressError


def _task(
    task_id: str,
    *,
    priority: str = "medium",
    status=TaskStatus.OPEN,
    due_date: str | None = None,
):
    return NS(
        task_id=task_id,
        title=task_id,
        priority=NS(value=priority),
        status=status,
        due_date=due_date,
    )


def _entry(answer: str):
    return NS(answer=answer)


def _install_history(monkeypatch, histories):
    def load(case_id, task_id):
        value = histories.get(task_id, ())
        if isinstance(value, Exception):
            raise value
        return tuple(value)

    monkeypatch.setattr(
        case_operator,
        "load_task_work_progress",
        load,
    )


def _ids(items):
    return [item.task_id for item in items]


def test_v2_i1_overdue_ready_task_beats_non_overdue_high_task(monkeypatch):
    _install_history(monkeypatch, {})
    tasks = (
        _task("high-future", priority="high", due_date="2026-09-11"),
        _task("low-overdue", priority="low", due_date="2026-09-09"),
    )

    ready, blocked, unavailable = case_operator._project_approved_task_queue(
        case_id="case",
        open_tasks=tasks,
        today=date(2026, 9, 10),
    )

    assert _ids(ready) == ["low-overdue", "high-future"]
    assert blocked == ()
    assert unavailable == ()


def test_v2_i1_high_ready_task_beats_other_non_overdue_work(monkeypatch):
    _install_history(monkeypatch, {})
    tasks = (
        _task("medium", priority="medium"),
        _task("high", priority="high"),
        _task("low", priority="low"),
    )

    ready, _, _ = case_operator._project_approved_task_queue(
        case_id="case",
        open_tasks=tasks,
        today=date(2026, 9, 10),
    )

    assert _ids(ready)[0] == "high"


def test_v2_i1_in_progress_precedes_open_within_same_band(monkeypatch):
    _install_history(monkeypatch, {})
    tasks = (
        _task("open-high", priority="high", status=TaskStatus.OPEN),
        _task(
            "progress-high",
            priority="high",
            status=TaskStatus.IN_PROGRESS,
        ),
    )

    ready, _, _ = case_operator._project_approved_task_queue(
        case_id="case",
        open_tasks=tasks,
        today=date(2026, 9, 10),
    )

    assert _ids(ready) == ["progress-high", "open-high"]


def test_v2_i1_earlier_due_date_precedes_later_date_within_same_band(monkeypatch):
    _install_history(monkeypatch, {})
    tasks = (
        _task("later", priority="medium", due_date="2026-09-20"),
        _task("earlier", priority="medium", due_date="2026-09-15"),
    )

    ready, _, _ = case_operator._project_approved_task_queue(
        case_id="case",
        open_tasks=tasks,
        today=date(2026, 9, 10),
    )

    assert _ids(ready) == ["earlier", "later"]


def test_v2_i1_explicit_non_high_priority_remains_safe_tiebreaker(monkeypatch):
    _install_history(monkeypatch, {})
    tasks = (
        _task("low", priority="low"),
        _task("medium", priority="medium"),
        _task("unset", priority="not_set"),
    )

    ready, _, _ = case_operator._project_approved_task_queue(
        case_id="case",
        open_tasks=tasks,
        today=date(2026, 9, 10),
    )

    assert _ids(ready) == ["medium", "low", "unset"]


def test_v2_i1_canonical_order_is_final_deterministic_tiebreaker(monkeypatch):
    _install_history(monkeypatch, {})
    tasks = (
        _task("first", priority="medium"),
        _task("second", priority="medium"),
    )

    ready, _, _ = case_operator._project_approved_task_queue(
        case_id="case",
        open_tasks=tasks,
        today=date(2026, 9, 10),
    )

    assert _ids(ready) == ["first", "second"]


def test_v2_i1_latest_blocked_work_is_not_ready_even_if_overdue_high(monkeypatch):
    blocked_task = _task(
        "blocked",
        priority="high",
        status=TaskStatus.IN_PROGRESS,
        due_date="2026-09-01",
    )
    ready_task = _task(
        "ready",
        priority="low",
        status=TaskStatus.OPEN,
    )
    _install_history(
        monkeypatch,
        {
            "blocked": (
                _entry(
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
        today=date(2026, 9, 10),
    )

    assert _ids(ready) == ["ready"]
    assert _ids(blocked) == ["blocked"]
    assert unavailable == ()


def test_v2_i1_post_block_handoff_consumes_first_operationally_ready_task(
    monkeypatch,
):
    blocked_task = _task(
        "blocked",
        priority="high",
        status=TaskStatus.IN_PROGRESS,
    )
    high_future = _task(
        "high-future",
        priority="high",
        due_date="2026-09-20",
    )
    overdue = _task(
        "overdue",
        priority="medium",
        due_date="2026-09-09",
    )
    _install_history(
        monkeypatch,
        {
            "blocked": (
                _entry(
                    "NEXT_TASK_INVESTIGATION: obtain external material\n"
                    "TASK_OUTCOME: BLOCKED"
                ),
            ),
        },
    )

    ready, blocked, unavailable = case_operator._project_approved_task_queue(
        case_id="case",
        open_tasks=(blocked_task, high_future, overdue),
        today=date(2026, 9, 10),
    )

    assert _ids(ready) == ["overdue", "high-future"]
    assert _ids(blocked) == ["blocked"]
    assert unavailable == ()

    target = case_operator._post_block_handoff_target(
        handoff_from_task_id="blocked",
        current_selected_task_id="blocked",
        ready_tasks=ready,
    )
    assert target == "overdue"


def test_v2_i1_invalid_history_fails_closed_and_is_not_recommended(monkeypatch):
    invalid = _task("invalid", priority="high", due_date="2026-09-01")
    ready_task = _task("ready", priority="low")
    _install_history(
        monkeypatch,
        {
            "invalid": TaskWorkProgressError("invalid persisted history"),
        },
    )

    ready, blocked, unavailable = case_operator._project_approved_task_queue(
        case_id="case",
        open_tasks=(invalid, ready_task),
        today=date(2026, 9, 10),
    )

    assert _ids(ready) == ["ready"]
    assert blocked == ()
    assert _ids(unavailable) == ["invalid"]


def test_v2_i1_completed_and_deferred_are_not_eligible(monkeypatch):
    _install_history(monkeypatch, {})
    tasks = (
        _task("completed", status=TaskStatus.COMPLETED),
        _task("deferred", status=TaskStatus.DEFERRED),
    )

    ready, blocked, unavailable = case_operator._project_approved_task_queue(
        case_id="case",
        open_tasks=tasks,
        today=date(2026, 9, 10),
    )

    assert ready == ()
    assert blocked == ()
    assert unavailable == ()


def test_v2_i1_queue_is_operational_not_legal_merits_and_has_no_mutation(monkeypatch):
    _install_history(monkeypatch, {})
    monkeypatch.setattr(
        case_operator,
        "_run_question",
        lambda *args, **kwargs: pytest.fail("provider must not be called"),
    )
    monkeypatch.setattr(
        case_operator,
        "_update_task_status",
        lambda *args, **kwargs: pytest.fail("task status must not mutate"),
    )

    source = inspect.getsource(case_operator._project_approved_task_queue)

    for forbidden in (
        "issue_analysis_id",
        "issue_name",
        "legal importance",
        "merit",
        "_run_question",
        "_update_task_status",
        "create_task",
        "append_task_work_progress",
    ):
        assert forbidden not in source

    assert "date.today()" in source
    assert "due_date" in source
    assert 'priority_value == "high"' in source
    assert "TaskStatus.IN_PROGRESS" in source

    ready, blocked, unavailable = case_operator._project_approved_task_queue(
        case_id="case",
        open_tasks=(_task("ready"),),
        today=date(2026, 9, 10),
    )
    assert _ids(ready) == ["ready"]
    assert blocked == ()
    assert unavailable == ()


def test_v2_i1_does_not_enable_automatic_provider_loop_after_handoff():
    source = inspect.getsource(case_operator._render_approved_task_execution)
    handoff = source.find("_post_block_handoff_target(")
    assert handoff >= 0

    selectbox = source.find("st.selectbox(", handoff)
    assert selectbox > handoff

    handoff_window = source[handoff:selectbox]
    assert "_run_question(" not in handoff_window
    assert "Case Operator has moved to the next approved task" in source
