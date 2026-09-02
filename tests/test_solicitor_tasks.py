import json
import pytest

from solicitor_tasks import (
    SolicitorTaskError,
    TaskOrigin,
    TaskPriority,
    TaskStatus,
    create_task,
    load_tasks,
    task_event_path,
    update_task,
)

CASE_ID = "8081166d-9889-40bb-8add-5d0893037ff0"


def _create(root):
    return create_task(
        case_id=CASE_ID,
        title="Establish transmission of May 2005 rehabilitation plan",
        priority=TaskPriority.HIGH,
        due_date="2026-09-10",
        assigned_to="Solicitor",
        issue_analysis_id="2df52940-c44d-4759-99fe-6a624edc05c0",
        issue_name="Employer knowledge of disability",
        originating_question="Was the May 2005 rehabilitation plan sent to CACI?",
        origin=TaskOrigin.WHAT_REMAINS_UNCLEAR,
        why_it_matters="Receipt is presently unproved and is material to the employer-knowledge analysis.",
        root=root,
    )


def test_create_task_preserves_matter_issue_origin_and_why(tmp_path):
    task = _create(tmp_path)
    assert task.case_id == CASE_ID
    assert task.status is TaskStatus.OPEN
    assert task.priority is TaskPriority.HIGH
    assert task.issue_name == "Employer knowledge of disability"
    assert task.origin is TaskOrigin.WHAT_REMAINS_UNCLEAR
    assert "sent to CACI" in task.originating_question
    assert "presently unproved" in task.why_it_matters
    assert load_tasks(CASE_ID, root=tmp_path) == (task,)


def test_events_are_append_only_and_update_preserves_identity(tmp_path):
    created = _create(tmp_path)
    updated = update_task(
        case_id=CASE_ID,
        task_id=created.task_id,
        title="Check insurer transmission and CACI receipt",
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.MEDIUM,
        due_date="2026-09-12",
        due_date_supplied=True,
        assigned_to="A. Solicitor",
        assigned_to_supplied=True,
        root=tmp_path,
    )
    lines = task_event_path(CASE_ID, root=tmp_path).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event_type"] == "TASK_CREATED"
    assert json.loads(lines[1])["event_type"] == "TASK_UPDATED"
    assert updated.task_id == created.task_id
    assert updated.status is TaskStatus.IN_PROGRESS
    assert load_tasks(CASE_ID, root=tmp_path) == (updated,)


@pytest.mark.parametrize("status", tuple(TaskStatus))
def test_all_authorised_statuses_persist(tmp_path, status):
    task = _create(tmp_path)
    updated = update_task(
        case_id=CASE_ID,
        task_id=task.task_id,
        status=status,
        root=tmp_path,
    )
    assert updated.status is status


def test_completed_task_does_not_change_analytical_binding(tmp_path):
    task = _create(tmp_path)
    completed = update_task(
        case_id=CASE_ID,
        task_id=task.task_id,
        status=TaskStatus.COMPLETED,
        root=tmp_path,
    )
    assert completed.issue_analysis_id == task.issue_analysis_id
    assert completed.originating_question == task.originating_question
    assert completed.why_it_matters == task.why_it_matters


def test_cross_matter_update_is_rejected(tmp_path):
    task = _create(tmp_path)
    with pytest.raises(SolicitorTaskError):
        update_task(
            case_id="another-matter",
            task_id=task.task_id,
            status=TaskStatus.COMPLETED,
            root=tmp_path,
        )


def test_invalid_due_date_is_rejected(tmp_path):
    with pytest.raises(SolicitorTaskError):
        create_task(
            case_id=CASE_ID,
            title="Task",
            priority=TaskPriority.NOT_SET,
            due_date="10/09/2026",
            issue_analysis_id="issue-id",
            issue_name="Issue",
            originating_question="Question",
            origin=TaskOrigin.NEXT_LEGAL_ACTION,
            why_it_matters="Reason",
            root=tmp_path,
        )


def test_task_store_has_no_analytical_authority_dependencies():
    import solicitor_tasks
    source = open(solicitor_tasks.__file__, "r", encoding="utf-8").read().lower()
    for forbidden in (
        "governed_analytical_authority",
        "governed_authority_revision",
        "matter_analysis_change",
        "controlled_agentic",
        "openai",
        "chromadb",
    ):
        assert forbidden not in source
