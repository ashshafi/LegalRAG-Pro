from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

import drafting_working_draft_orchestration as module

from drafting_working_draft import (
    WorkingDraftStatementInput,
)
from drafting_working_draft_generation import (
    WorkingDraftGenerationCandidate,
)
from solicitor_tasks import SolicitorTask
from task_work_authority_scope import (
    TaskWorkAuthorityScope,
)
from task_work_progress import TaskWorkProgress
from task_work_retrieval_receipt import (
    TaskWorkRetrievalReceipt,
)


CASE_ID = "8081166d-9889-40bb-8add-5d0893037ff0"
TASK_ID = "11111111-1111-4111-8111-111111111111"
PROGRESS_ID = "22222222-2222-4222-8222-222222222222"
ISSUE_ID = "33333333-3333-4333-8333-333333333333"

AUTHORITY_ID = "sha256:" + ("a" * 64)
SCOPE_ID = "sha256:" + ("b" * 64)
DRAFT_ID = "sha256:" + ("c" * 64)

ELEMENT_ID = "DA-DISABILITY"
KEY = CASE_ID + "__Evidence_1_0"
OUTSIDE_KEY = CASE_ID + "__Outside_1_0"

QUESTION = "What does the evidence establish?"
ANSWER = "The governed task-work answer."


def digest(value: str) -> str:
    return sha256(
        value.encode("utf-8")
    ).hexdigest()


def task():
    return SolicitorTask(
        task_id=TASK_ID,
        case_id=CASE_ID,
        title="Review disability evidence",
        status="IN_PROGRESS",
        priority="HIGH",
        due_date=None,
        assigned_to=None,
        issue_analysis_id=ISSUE_ID,
        issue_name="Disability",
        originating_question=QUESTION,
        origin="MANUAL",
        why_it_matters="Prepare the issue accurately.",
        created_at="2026-09-07T10:00:00Z",
        updated_at="2026-09-07T10:00:00Z",
    )


def progress():
    return TaskWorkProgress(
        schema_version="task-work-progress/1.0",
        progress_id=PROGRESS_ID,
        case_id=CASE_ID,
        task_id=TASK_ID,
        recorded_at="2026-09-07T10:05:00Z",
        question=QUESTION,
        answer=ANSWER,
        outcome="CONTINUE",
    )


def receipt():
    return TaskWorkRetrievalReceipt(
        schema_version=
            "task-work-retrieval-receipt/1.0",
        case_id=CASE_ID,
        task_id=TASK_ID,
        progress_id=PROGRESS_ID,
        task_work_recorded_at=
            "2026-09-07T10:05:00Z",
        receipt_recorded_at=
            "2026-09-07T10:06:00Z",
        retrieval_mode="document_complete",
        question_sha256=digest(QUESTION),
        answer_sha256=digest(ANSWER),
        answer_scope_evidence_keys=(KEY,),
        sources=(),
        semantic_discovery_receipt=None,
        evidence_search_receipt=None,
        relied_evidence_keys=(KEY,),
        answer_statement_bindings=(),
        evidence_reference_resolution=None,
    )


def scope():
    return TaskWorkAuthorityScope(
        schema_version=
            "task-work-authority-scope/1.0",
        binding_id=SCOPE_ID,
        case_id=CASE_ID,
        task_id=TASK_ID,
        progress_id=PROGRESS_ID,
        authority_id=AUTHORITY_ID,
        issue_analysis_id=ISSUE_ID,
        issue_definition_id="DISABILITY",
        element_ids=(ELEMENT_ID,),
        reviewer_reference="solicitor@example.test",
        review_note="Explicit scope.",
        recorded_at="2026-09-07T10:07:00Z",
    )


def authority():
    return SimpleNamespace(
        manifest=SimpleNamespace(
            case_id=CASE_ID,
            authority_id=AUTHORITY_ID,
        )
    )


def statement(
    *,
    cited=(KEY,),
):
    return WorkingDraftStatementInput(
        text=(
            "The governed evidence provides partial "
            "factual support, subject to the unresolved "
            "legal assessment."
        ),
        element_id=ELEMENT_ID,
        claimed_status="partially_supported",
        claimed_confidence="medium",
        cited_evidence_keys=tuple(cited),
    )


def candidate(
    *,
    task_id=TASK_ID,
    evidence_keys=(KEY,),
    statements=None,
):
    if statements is None:
        statements = (
            statement(),
        )

    return WorkingDraftGenerationCandidate(
        case_id=CASE_ID,
        task_id=task_id,
        progress_id=PROGRESS_ID,
        scope_binding_id=SCOPE_ID,
        authority_id=AUTHORITY_ID,
        issue_analysis_id=ISSUE_ID,
        issue_definition_id="DISABILITY",
        element_id=ELEMENT_ID,
        evidence_keys=tuple(evidence_keys),
        statements=tuple(statements),
    )


def resolved_element():
    return SimpleNamespace(
        element_id=ELEMENT_ID,
        supporting_evidence_keys=(KEY,),
        adverse_evidence_keys=(),
        corroborative_evidence_keys=(),
        conflicting_evidence_keys=(),
    )


def built_statement(source):
    return SimpleNamespace(
        statement_id="sha256:" + ("d" * 64),
        sequence=1,
        text=source.text,
        element_id=source.element_id,
        claimed_status=source.claimed_status,
        claimed_confidence=
            source.claimed_confidence,
        cited_evidence_keys=tuple(
            sorted(
                source.cited_evidence_keys
            )
        ),
    )


def built_draft(
    source_candidate,
    *,
    recorded_at="2026-09-07T11:00:00Z",
    draft_id=DRAFT_ID,
):
    return SimpleNamespace(
        schema_version="drafting-working-draft/1.0",
        draft_id=draft_id,
        case_id=CASE_ID,
        task_id=TASK_ID,
        progress_id=PROGRESS_ID,
        task_work_recorded_at=
            "2026-09-07T10:05:00Z",
        task_work_question_sha256=
            digest(QUESTION),
        task_work_answer_sha256=
            digest(ANSWER),
        scope_binding_id=SCOPE_ID,
        authority_id=AUTHORITY_ID,
        issue_analysis_id=ISSUE_ID,
        issue_definition_id="DISABILITY",
        title="Draft disability analysis",
        purpose="Prepare a governed WORKING draft.",
        statements=tuple(
            built_statement(item)
            for item in source_candidate.statements
        ),
        creator_reference="solicitor@example.test",
        recorded_at=recorded_at,
    )


def evaluation(
    draft,
    *,
    result="CAUTION",
):
    return SimpleNamespace(
        draft_id=draft.draft_id,
        case_id=draft.case_id,
        authority_id=draft.authority_id,
        issue_analysis_id=
            draft.issue_analysis_id,
        statement_evaluations=tuple(
            SimpleNamespace(
                statement_id=item.statement_id,
                sequence=item.sequence,
                element_id=item.element_id,
                check=SimpleNamespace(
                    result=result,
                ),
            )
            for item in draft.statements
        ),
    )


def arrange(
    monkeypatch,
    *,
    result="CAUTION",
):
    calls = []

    monkeypatch.setattr(
        module,
        "resolve_task_work_authority_scope",
        lambda supplied_scope, *, authority:
            SimpleNamespace(
                scope=supplied_scope,
                issue=SimpleNamespace(),
                elements=(resolved_element(),),
            ),
    )

    monkeypatch.setattr(
        module,
        "generation_evidence_keys",
        lambda *, retrieval_receipt, element:
            (KEY,),
    )

    def fake_build(**kwargs):
        calls.append("build")
        source_candidate = candidate(
            statements=tuple(
                kwargs["statements"]
            )
        )

        return built_draft(
            source_candidate,
            recorded_at=(
                "2026-09-07T11:00:00Z"
                if calls.count("build") == 1
                else "2026-09-07T11:05:00Z"
            ),
        )

    monkeypatch.setattr(
        module,
        "build_working_draft",
        fake_build,
    )

    def fake_evaluate(*, draft, authority):
        calls.append("evaluate")

        return evaluation(
            draft,
            result=result,
        )

    monkeypatch.setattr(
        module,
        "evaluate_working_draft_authority",
        fake_evaluate,
    )

    def fake_record(**kwargs):
        calls.append("record")

        source_candidate = candidate(
            statements=tuple(
                kwargs["statements"]
            )
        )

        return built_draft(
            source_candidate,
            recorded_at=kwargs["recorded_at"],
        )

    monkeypatch.setattr(
        module,
        "record_working_draft",
        fake_record,
    )

    return calls


def prepare(monkeypatch, *, candidate_value=None):
    calls = arrange(monkeypatch)

    if candidate_value is None:
        candidate_value = candidate()

    prepared = (
        module.prepare_generated_working_draft(
            candidate=candidate_value,
            task=task(),
            progress=progress(),
            retrieval_receipt=receipt(),
            scope=scope(),
            authority=authority(),
            title="Draft disability analysis",
            purpose="Prepare a governed WORKING draft.",
            creator_reference="solicitor@example.test",
        )
    )

    return calls, prepared


def test_prepare_is_pure_and_evaluates_before_any_record(
    monkeypatch,
):
    calls, prepared = prepare(
        monkeypatch
    )

    assert calls == [
        "build",
        "evaluate",
    ]

    assert prepared.draft.draft_id == DRAFT_ID
    assert (
        prepared.authority_evaluation.draft_id
        == DRAFT_ID
    )


def test_prepare_preserves_non_aggregate_authority_result(
    monkeypatch,
):
    calls = arrange(
        monkeypatch,
        result="NOT_AUTHORIZED",
    )

    prepared = (
        module.prepare_generated_working_draft(
            candidate=candidate(),
            task=task(),
            progress=progress(),
            retrieval_receipt=receipt(),
            scope=scope(),
            authority=authority(),
            title="Draft disability analysis",
            purpose="Prepare a governed WORKING draft.",
            creator_reference="solicitor@example.test",
        )
    )

    assert calls == [
        "build",
        "evaluate",
    ]

    assert (
        prepared
        .authority_evaluation
        .statement_evaluations[0]
        .check
        .result
        == "NOT_AUTHORIZED"
    )

    assert not hasattr(
        prepared,
        "release_state",
    )

    assert not hasattr(
        prepared,
        "release_decision",
    )


def test_explicit_record_rebuilds_and_reevaluates_before_append(
    monkeypatch,
):
    calls, prepared = prepare(
        monkeypatch
    )

    result = (
        module.record_prepared_working_draft(
            prepared=prepared,
            task=task(),
            progress=progress(),
            retrieval_receipt=receipt(),
            scope=scope(),
            authority=authority(),
        )
    )

    assert calls == [
        "build",
        "evaluate",
        "build",
        "evaluate",
        "record",
    ]

    assert result.draft.draft_id == DRAFT_ID
    assert result.draft.recorded_at == (
        "2026-09-07T11:05:00Z"
    )

    assert (
        result.authority_evaluation.draft_id
        == result.draft.draft_id
    )


def test_candidate_task_identity_mismatch_fails_before_build(
    monkeypatch,
):
    calls = arrange(monkeypatch)

    with pytest.raises(
        module.DraftingWorkingDraftOrchestrationError,
        match="another task",
    ):
        module.prepare_generated_working_draft(
            candidate=candidate(
                task_id=
                    "99999999-9999-4999-8999-999999999999"
            ),
            task=task(),
            progress=progress(),
            retrieval_receipt=receipt(),
            scope=scope(),
            authority=authority(),
            title="Draft disability analysis",
            purpose="Purpose",
            creator_reference="solicitor@example.test",
        )

    assert calls == []


def test_candidate_safe_set_mismatch_fails_before_build(
    monkeypatch,
):
    calls = arrange(monkeypatch)

    with pytest.raises(
        module.DraftingWorkingDraftOrchestrationError,
        match="evidence boundary",
    ):
        module.prepare_generated_working_draft(
            candidate=candidate(
                evidence_keys=(OUTSIDE_KEY,)
            ),
            task=task(),
            progress=progress(),
            retrieval_receipt=receipt(),
            scope=scope(),
            authority=authority(),
            title="Draft disability analysis",
            purpose="Purpose",
            creator_reference="solicitor@example.test",
        )

    assert calls == []


def test_candidate_statement_outside_safe_set_fails(
    monkeypatch,
):
    calls = arrange(monkeypatch)

    bad_statement = statement(
        cited=(OUTSIDE_KEY,)
    )

    with pytest.raises(
        module.DraftingWorkingDraftOrchestrationError,
        match="outside the current safe set",
    ):
        module.prepare_generated_working_draft(
            candidate=candidate(
                statements=(bad_statement,)
            ),
            task=task(),
            progress=progress(),
            retrieval_receipt=receipt(),
            scope=scope(),
            authority=authority(),
            title="Draft disability analysis",
            purpose="Purpose",
            creator_reference="solicitor@example.test",
        )

    assert calls == []


def test_stale_candidate_authority_fails_before_build(
    monkeypatch,
):
    calls = arrange(monkeypatch)

    value = candidate()

    object.__setattr__(
        value,
        "authority_id",
        "sha256:" + ("9" * 64),
    )

    with pytest.raises(
        module.DraftingWorkingDraftOrchestrationError,
        match="candidate is stale",
    ):
        module.prepare_generated_working_draft(
            candidate=value,
            task=task(),
            progress=progress(),
            retrieval_receipt=receipt(),
            scope=scope(),
            authority=authority(),
            title="Draft disability analysis",
            purpose="Purpose",
            creator_reference="solicitor@example.test",
        )

    assert calls == []


def test_built_draft_identity_mismatch_fails_closed(
    monkeypatch,
):
    calls = arrange(monkeypatch)

    monkeypatch.setattr(
        module,
        "build_working_draft",
        lambda **kwargs:
            SimpleNamespace(
                **{
                    **vars(
                        built_draft(
                            candidate()
                        )
                    ),
                    "task_id":
                        "99999999-9999-4999-8999-999999999999",
                }
            ),
    )

    with pytest.raises(
        module.DraftingWorkingDraftOrchestrationError,
        match="task_id",
    ):
        module.prepare_generated_working_draft(
            candidate=candidate(),
            task=task(),
            progress=progress(),
            retrieval_receipt=receipt(),
            scope=scope(),
            authority=authority(),
            title="Draft disability analysis",
            purpose="Purpose",
            creator_reference="solicitor@example.test",
        )


def test_authority_evaluation_must_cover_exact_draft(
    monkeypatch,
):
    calls = arrange(monkeypatch)

    monkeypatch.setattr(
        module,
        "evaluate_working_draft_authority",
        lambda *, draft, authority:
            SimpleNamespace(
                draft_id="sha256:" + ("8" * 64),
                case_id=draft.case_id,
                authority_id=draft.authority_id,
                issue_analysis_id=
                    draft.issue_analysis_id,
                statement_evaluations=(
                    SimpleNamespace(),
                ),
            ),
    )

    with pytest.raises(
        module.DraftingWorkingDraftOrchestrationError,
        match="exact working draft",
    ):
        module.prepare_generated_working_draft(
            candidate=candidate(),
            task=task(),
            progress=progress(),
            retrieval_receipt=receipt(),
            scope=scope(),
            authority=authority(),
            title="Draft disability analysis",
            purpose="Purpose",
            creator_reference="solicitor@example.test",
        )


def test_explicit_record_rejects_changed_draft_identity(
    monkeypatch,
):
    calls, prepared = prepare(
        monkeypatch
    )

    original_build = (
        module.build_working_draft
    )

    def changed_build(**kwargs):
        value = original_build(
            **kwargs
        )

        if calls.count("build") >= 2:
            value.draft_id = (
                "sha256:" + ("7" * 64)
            )

        return value

    monkeypatch.setattr(
        module,
        "build_working_draft",
        changed_build,
    )

    with pytest.raises(
        module.DraftingWorkingDraftOrchestrationError,
        match="identity differs",
    ):
        module.record_prepared_working_draft(
            prepared=prepared,
            task=task(),
            progress=progress(),
            retrieval_receipt=receipt(),
            scope=scope(),
            authority=authority(),
        )

    assert "record" not in calls


def test_module_has_no_ui_provider_retrieval_task_or_release_dependency():
    source = Path(
        module.__file__
    ).read_text(
        encoding="utf-8"
    ).lower()

    forbidden = (
        "streamlit",
        "chromadb",
        "openai",
        "responses.create",
        "chat.completions",
        "search_case_evidence",
        "similarity_search",
        "append_task_work_progress",
        "append_task_work_retrieval_receipt",
        "record_task_work_authority_scope",
        "update_task(",
        "work_product_release",
        "record_work_product_release",
        "report_projection_provider",
    )

    assert not any(
        token in source
        for token in forbidden
    )


def test_orchestration_creates_no_aggregate_release_state():
    prepared_fields = {
        field.name
        for field in module.PreparedWorkingDraft.__dataclass_fields__.values()
    }

    recorded_fields = {
        field.name
        for field in module.RecordedWorkingDraft.__dataclass_fields__.values()
    }

    forbidden = {
        "release_state",
        "release_decision",
        "approved",
        "approval",
        "aggregate_result",
    }

    assert not (
        prepared_fields
        & forbidden
    )

    assert not (
        recorded_fields
        & forbidden
    )