from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import task_work_progress as progress
from task_work_progress import (
    TASK_WORK_PROGRESS_SCHEMA_VERSION,
    TaskWorkOutcome,
    TaskWorkProgressError,
    append_task_work_progress,
    load_task_work_progress,
    task_work_progress_path,
)


CASE_ID = "8081166d-9889-40bb-8add-5d0893037ff0"
TASK_ID = "task-r19"


def access(case_id=CASE_ID):
    return SimpleNamespace(case_id=case_id)


@pytest.fixture(autouse=True)
def _controlled_access_and_task(monkeypatch):
    monkeypatch.setattr(progress, "require_matter_mutation", lambda value: value)
    monkeypatch.setattr(
        progress,
        "load_tasks",
        lambda case_id, root=None: (
            SimpleNamespace(task_id=TASK_ID, case_id=case_id),
        ),
    )


def test_append_and_load_round_trip(tmp_path):
    record = append_task_work_progress(
        case_id=CASE_ID,
        access=access(),
        task_id=TASK_ID,
        question="What remains to establish limitation?",
        answer="The ET1 presentation date remains to be verified.",
        outcome=TaskWorkOutcome.CONTINUE,
        root=tmp_path,
    )

    assert record.case_id == CASE_ID
    assert record.task_id == TASK_ID
    assert record.outcome is TaskWorkOutcome.CONTINUE

    loaded = load_task_work_progress(CASE_ID, TASK_ID, root=tmp_path)
    assert loaded == (record,)


def test_multiple_progress_records_preserve_append_order(tmp_path):
    first = append_task_work_progress(
        case_id=CASE_ID,
        access=access(),
        task_id=TASK_ID,
        question="First investigation",
        answer="First result",
        outcome="CONTINUE",
        root=tmp_path,
    )
    second = append_task_work_progress(
        case_id=CASE_ID,
        access=access(),
        task_id=TASK_ID,
        question="Second investigation",
        answer="Second result",
        outcome="BLOCKED",
        root=tmp_path,
    )

    assert load_task_work_progress(CASE_ID, TASK_ID, root=tmp_path) == (
        first,
        second,
    )


def test_progress_store_is_separate_from_task_event_store(tmp_path):
    path = task_work_progress_path(CASE_ID, root=tmp_path)
    assert path.name == "work_progress.jsonl"
    assert path != progress.task_event_path(CASE_ID, root=tmp_path)


def test_cross_matter_access_fails_before_write(tmp_path):
    with pytest.raises(TaskWorkProgressError, match="does not match"):
        append_task_work_progress(
            case_id=CASE_ID,
            access=access("another-case"),
            task_id=TASK_ID,
            question="Question",
            answer="Answer",
            outcome="CONTINUE",
            root=tmp_path,
        )
    assert not task_work_progress_path(CASE_ID, root=tmp_path).exists()


def test_missing_task_fails_before_write(tmp_path, monkeypatch):
    monkeypatch.setattr(progress, "load_tasks", lambda case_id, root=None: ())
    with pytest.raises(TaskWorkProgressError, match="Task was not found"):
        append_task_work_progress(
            case_id=CASE_ID,
            access=access(),
            task_id=TASK_ID,
            question="Question",
            answer="Answer",
            outcome="CONTINUE",
            root=tmp_path,
        )
    assert not task_work_progress_path(CASE_ID, root=tmp_path).exists()


def test_unsupported_outcome_fails_before_write(tmp_path):
    with pytest.raises(TaskWorkProgressError, match="Unsupported task-work outcome"):
        append_task_work_progress(
            case_id=CASE_ID,
            access=access(),
            task_id=TASK_ID,
            question="Question",
            answer="Answer",
            outcome="MAYBE",
            root=tmp_path,
        )
    assert not task_work_progress_path(CASE_ID, root=tmp_path).exists()


def test_invalid_json_fails_closed(tmp_path):
    path = task_work_progress_path(CASE_ID, root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(TaskWorkProgressError, match="Invalid task-work event JSON"):
        load_task_work_progress(CASE_ID, TASK_ID, root=tmp_path)


def test_cross_matter_event_fails_closed(tmp_path):
    record = append_task_work_progress(
        case_id=CASE_ID,
        access=access(),
        task_id=TASK_ID,
        question="Question",
        answer="Answer",
        outcome="CONTINUE",
        root=tmp_path,
    )
    path = task_work_progress_path(CASE_ID, root=tmp_path)
    event = json.loads(path.read_text(encoding="utf-8").strip())
    event["case_id"] = "foreign-case"
    path.write_text(json.dumps(event) + "\n", encoding="utf-8")

    with pytest.raises(TaskWorkProgressError, match="Cross-matter"):
        load_task_work_progress(CASE_ID, TASK_ID, root=tmp_path)


def test_service_does_not_import_or_mutate_analytical_authority():
    source = Path("src/task_work_progress.py").read_text(encoding="utf-8-sig")
    forbidden = (
        "activate_authority",
        "publish_authority",
        "governed_analytical_authority",
        "new_ai_finding",
        "chromadb",
    )
    for token in forbidden:
        assert token not in source


def test_service_does_not_update_task_snapshot_or_status():
    source = Path("src/task_work_progress.py").read_text(encoding="utf-8-sig")
    assert "update_task(" not in source
    assert "TaskStatus" not in source
    assert '"TASK_UPDATED"' not in source
    assert '"TASK_CREATED"' not in source


def test_schema_and_event_type_are_explicit_and_append_only():
    source = Path("src/task_work_progress.py").read_text(encoding="utf-8-sig")
    assert 'TASK_WORK_PROGRESS_SCHEMA_VERSION = "task-work-progress/1.0"' in source
    assert '_TASK_WORK_EVENT_TYPE = "TASK_WORK_RECORDED"' in source
    assert 'handle.write(payload + "\\n")' in source
    assert "os.fsync(handle.fileno())" in source
    assert "path.open(\"a\"" in source


def test_load_filters_requested_task_but_validates_whole_case_file(tmp_path, monkeypatch):
    other = "task-other"
    monkeypatch.setattr(
        progress,
        "load_tasks",
        lambda case_id, root=None: (
            SimpleNamespace(task_id=TASK_ID, case_id=case_id),
            SimpleNamespace(task_id=other, case_id=case_id),
        ),
    )
    append_task_work_progress(
        case_id=CASE_ID,
        access=access(),
        task_id=TASK_ID,
        question="Q1",
        answer="A1",
        outcome="CONTINUE",
        root=tmp_path,
    )
    append_task_work_progress(
        case_id=CASE_ID,
        access=access(),
        task_id=other,
        question="Q2",
        answer="A2",
        outcome="COMPLETE",
        root=tmp_path,
    )

    records = load_task_work_progress(CASE_ID, TASK_ID, root=tmp_path)
    assert len(records) == 1
    assert records[0].task_id == TASK_ID
