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


def test_schema_10_history_remains_readable_and_unchanged(tmp_path):
    task = _create(tmp_path)
    path = task_event_path(CASE_ID, root=tmp_path)
    before = path.read_bytes()
    event = json.loads(before.decode("utf-8").strip())
    assert event["schema_version"] == "1.0"
    assert "origin_evidence_key" not in event["task"]
    assert load_tasks(CASE_ID, root=tmp_path) == (task,)
    assert path.read_bytes() == before


def test_evidence_origin_uses_schema_11_and_exact_evidence_reference(tmp_path):
    task = create_task(
        case_id=CASE_ID,
        title="Establish whether the plan was sent to CACI",
        priority=TaskPriority.HIGH,
        issue_analysis_id="issue-id",
        issue_name="Employer knowledge of disability",
        originating_question="Transmission and receipt have not been proved.",
        origin=TaskOrigin.EVIDENCE,
        why_it_matters="Receipt is material to employer knowledge.",
        origin_evidence_key="evidence-key-123",
        origin_evidence_citation="May 2005 rehabilitation plan, p.2",
        origin_document_name="May 2005 rehabilitation plan.pdf",
        origin_page=2,
        root=tmp_path,
    )
    event = json.loads(
        task_event_path(CASE_ID, root=tmp_path).read_text(encoding="utf-8").strip()
    )
    assert event["schema_version"] == "1.1"
    assert task.origin_evidence_key == "evidence-key-123"
    assert task.origin_evidence_citation == "May 2005 rehabilitation plan, p.2"
    assert task.origin_document_name == "May 2005 rehabilitation plan.pdf"
    assert task.origin_page == 2


def test_evidence_origin_fails_closed_without_evidence_key(tmp_path):
    with pytest.raises(SolicitorTaskError):
        create_task(
            case_id=CASE_ID,
            title="Follow up evidence",
            priority=TaskPriority.NOT_SET,
            issue_analysis_id="issue-id",
            issue_name="Issue",
            originating_question="Investigate limitation.",
            origin=TaskOrigin.EVIDENCE,
            why_it_matters="Material follow-up.",
            origin_evidence_citation="Doc.pdf, p.1",
            root=tmp_path,
        )


def test_non_evidence_task_rejects_evidence_provenance(tmp_path):
    with pytest.raises(SolicitorTaskError):
        create_task(
            case_id=CASE_ID,
            title="Task",
            priority=TaskPriority.NOT_SET,
            issue_analysis_id="issue-id",
            issue_name="Issue",
            originating_question="Question",
            origin=TaskOrigin.NEXT_LEGAL_ACTION,
            why_it_matters="Reason",
            origin_evidence_key="not-permitted",
            root=tmp_path,
        )


def test_completion_preserves_evidence_and_issue_bindings(tmp_path):
    task = create_task(
        case_id=CASE_ID,
        title="Investigate evidence",
        priority=TaskPriority.MEDIUM,
        issue_analysis_id="issue-id",
        issue_name="Issue",
        originating_question="Receipt is unproved.",
        origin=TaskOrigin.EVIDENCE,
        why_it_matters="Receipt matters.",
        origin_evidence_key="evidence-key-1",
        origin_evidence_citation="Doc.pdf, p.3",
        origin_document_name="Doc.pdf",
        origin_page=3,
        root=tmp_path,
    )
    completed = update_task(
        case_id=CASE_ID,
        task_id=task.task_id,
        status=TaskStatus.COMPLETED,
        root=tmp_path,
    )
    assert completed.origin_evidence_key == task.origin_evidence_key
    assert completed.issue_analysis_id == task.issue_analysis_id


def test_task_api_has_no_evidence_text_parameters():
    import inspect
    import solicitor_tasks
    forbidden = {
        "evidence_text", "source_text", "passage_text",
        "chunk_text", "exact_page_text",
    }
    assert forbidden.isdisjoint(inspect.signature(solicitor_tasks.create_task).parameters)


def test_chronology_origin_uses_schema_12_and_exact_event_reference(tmp_path):
    task = create_task(
        case_id=CASE_ID,
        title="Follow up chronology event · 5 July 2005 · medical",
        priority=TaskPriority.NOT_SET,
        issue_analysis_id="issue-id",
        issue_name="Employer knowledge of disability",
        originating_question="Operational follow-up arising from the frozen chronology event.",
        origin=TaskOrigin.CHRONOLOGY,
        why_it_matters="Follow up the legal-work implication of this chronology event.",
        origin_chronology_event_id="chronology-event-123",
        origin_chronology_time="5 July 2005",
        origin_chronology_event_type="medical",
        root=tmp_path,
    )
    event = json.loads(
        task_event_path(CASE_ID, root=tmp_path).read_text(encoding="utf-8").strip()
    )
    assert event["schema_version"] == "1.2"
    assert task.origin is TaskOrigin.CHRONOLOGY
    assert task.origin_chronology_event_id == "chronology-event-123"
    assert task.origin_chronology_time == "5 July 2005"
    assert task.origin_chronology_event_type == "medical"
    assert "origin_evidence_key" not in event["task"]
    assert "description" not in event["task"]
    assert "evidence_keys" not in event["task"]
    assert "citations" not in event["task"]


def test_chronology_origin_fails_closed_without_event_id(tmp_path):
    with pytest.raises(SolicitorTaskError):
        create_task(
            case_id=CASE_ID,
            title="Follow up chronology",
            priority=TaskPriority.NOT_SET,
            issue_analysis_id="issue-id",
            issue_name="Issue",
            originating_question="Operational follow-up.",
            origin=TaskOrigin.CHRONOLOGY,
            why_it_matters="Material follow-up.",
            origin_chronology_time="5 July 2005",
            root=tmp_path,
        )


def test_non_chronology_task_rejects_chronology_provenance(tmp_path):
    with pytest.raises(SolicitorTaskError):
        create_task(
            case_id=CASE_ID,
            title="Task",
            priority=TaskPriority.NOT_SET,
            issue_analysis_id="issue-id",
            issue_name="Issue",
            originating_question="Question",
            origin=TaskOrigin.NEXT_LEGAL_ACTION,
            why_it_matters="Reason",
            origin_chronology_event_id="not-permitted",
            root=tmp_path,
        )


def test_chronology_completion_preserves_event_and_issue_bindings(tmp_path):
    task = create_task(
        case_id=CASE_ID,
        title="Follow up chronology event",
        priority=TaskPriority.MEDIUM,
        issue_analysis_id="issue-id",
        issue_name="Issue",
        originating_question="Operational follow-up.",
        origin=TaskOrigin.CHRONOLOGY,
        why_it_matters="Follow-up only.",
        origin_chronology_event_id="event-id-1",
        origin_chronology_time="5 July 2005",
        origin_chronology_event_type="medical",
        root=tmp_path,
    )
    completed = update_task(
        case_id=CASE_ID,
        task_id=task.task_id,
        status=TaskStatus.COMPLETED,
        root=tmp_path,
    )
    assert completed.origin_chronology_event_id == task.origin_chronology_event_id
    assert completed.issue_analysis_id == task.issue_analysis_id
    assert completed.origin_chronology_time == task.origin_chronology_time
    assert completed.origin_chronology_event_type == task.origin_chronology_event_type


def test_schema_10_and_11_serialization_contracts_remain_unextended(tmp_path):
    ordinary = _create(tmp_path / "ordinary")
    ordinary_event = json.loads(
        task_event_path(CASE_ID, root=tmp_path / "ordinary").read_text(encoding="utf-8").strip()
    )
    assert ordinary_event["schema_version"] == "1.0"
    assert not any(key.startswith("origin_chronology_") for key in ordinary_event["task"])

    evidence = create_task(
        case_id=CASE_ID,
        title="Evidence task",
        priority=TaskPriority.NOT_SET,
        issue_analysis_id="issue-id",
        issue_name="Issue",
        originating_question="Question",
        origin=TaskOrigin.EVIDENCE,
        why_it_matters="Reason",
        origin_evidence_key="evidence-key",
        root=tmp_path / "evidence",
    )
    evidence_event = json.loads(
        task_event_path(CASE_ID, root=tmp_path / "evidence").read_text(encoding="utf-8").strip()
    )
    assert evidence.origin_evidence_key == "evidence-key"
    assert evidence_event["schema_version"] == "1.1"
    assert not any(key.startswith("origin_chronology_") for key in evidence_event["task"])


def test_task_api_has_no_chronology_or_evidence_content_copy_parameters():
    import inspect
    import solicitor_tasks
    forbidden = {
        "event_description", "assertion_text", "event_evidence_keys",
        "event_citations", "evidence_text", "source_text", "passage_text",
    }
    assert forbidden.isdisjoint(inspect.signature(solicitor_tasks.create_task).parameters)


def test_chronology_display_context_is_optional_but_identity_is_not(tmp_path):
    task = create_task(
        case_id=CASE_ID,
        title="Follow up chronology event",
        priority=TaskPriority.NOT_SET,
        issue_analysis_id="issue-id",
        issue_name="Issue",
        originating_question="Operational follow-up.",
        origin=TaskOrigin.CHRONOLOGY,
        why_it_matters="Reason",
        origin_chronology_event_id="event-id-only",
        root=tmp_path,
    )
    assert task.origin_chronology_event_id == "event-id-only"
    assert task.origin_chronology_time is None
    assert task.origin_chronology_event_type is None


def test_schema_12_rejects_non_chronology_origin(tmp_path):
    task = _create(tmp_path)
    path = task_event_path(CASE_ID, root=tmp_path)
    event = json.loads(path.read_text(encoding="utf-8").strip())
    event["schema_version"] = "1.2"
    path.write_text(json.dumps(event) + "\n", encoding="utf-8")
    with pytest.raises(SolicitorTaskError):
        load_tasks(CASE_ID, root=tmp_path)


def test_chronology_task_store_has_no_chronology_or_analysis_dependency():
    import solicitor_tasks
    source = open(solicitor_tasks.__file__, "r", encoding="utf-8").read().lower()
    for forbidden in (
        "case_analysis",
        "workspace_index",
        "chronology_validation",
        "event_identity",
        "matter_analysis_ledger",
    ):
        assert forbidden not in source
