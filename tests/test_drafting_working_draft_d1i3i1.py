from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

import drafting_working_draft as module


CASE_ID = "8081166d-9889-40bb-8add-5d0893037ff0"
TASK_ID = "e162d3c5-abe2-4553-b464-15a828798a8e"
PROGRESS_ID = "11111111-1111-4111-8111-111111111111"
ISSUE_ID = "2df52940-c44d-4759-99fe-6a624edc05c0"

AUTHORITY_ID = (
    "sha256:"
    + ("a" * 64)
)

SCOPE_BINDING_ID = (
    "sha256:"
    + ("b" * 64)
)

RECORDED_AT = "2026-09-07T09:30:00Z"

QUESTION = "Establish transmission of the rehabilitation plan."
ANSWER = "The available evidence supports further work."


def sha(value: str) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def make_chain(
    *,
    element_ids=(
        "EK-INFORMATION",
        "EK-RECIPIENT",
    ),
):
    task = SimpleNamespace(
        case_id=CASE_ID,
        task_id=TASK_ID,
        issue_analysis_id=ISSUE_ID,
    )

    progress = SimpleNamespace(
        case_id=CASE_ID,
        task_id=TASK_ID,
        progress_id=PROGRESS_ID,
        recorded_at=RECORDED_AT,
        question=QUESTION,
        answer=ANSWER,
    )

    receipt = SimpleNamespace(
        case_id=CASE_ID,
        task_id=TASK_ID,
        progress_id=PROGRESS_ID,
        task_work_recorded_at=RECORDED_AT,
        question_sha256=sha(QUESTION),
        answer_sha256=sha(ANSWER),
    )

    scope = SimpleNamespace(
        binding_id=SCOPE_BINDING_ID,
        case_id=CASE_ID,
        task_id=TASK_ID,
        progress_id=PROGRESS_ID,
        authority_id=AUTHORITY_ID,
        issue_analysis_id=ISSUE_ID,
        issue_definition_id="EMPLOYER-KNOWLEDGE",
        element_ids=tuple(element_ids),
    )

    authority = SimpleNamespace(
        manifest=SimpleNamespace(
            case_id=CASE_ID,
            authority_id=AUTHORITY_ID,
        )
    )

    return (
        task,
        progress,
        receipt,
        scope,
        authority,
    )


def inputs():
    return (
        module.WorkingDraftStatementInput(
            text=(
                "The May 2005 material is relevant "
                "to what information reached CACI."
            ),
            element_id="EK-INFORMATION",
            claimed_status="SUPPORTED",
            claimed_confidence="MEDIUM",
            cited_evidence_keys=(
                "evidence:b",
                "evidence:a",
            ),
        ),
        module.WorkingDraftStatementInput(
            text=(
                "The recipient question must be "
                "addressed separately."
            ),
            element_id="EK-RECIPIENT",
            claimed_status="UNRESOLVED",
            claimed_confidence="LOW",
            cited_evidence_keys=(),
        ),
    )


@pytest.fixture(autouse=True)
def current_scope(monkeypatch):
    monkeypatch.setattr(
        module,
        "resolve_task_work_authority_scope",
        lambda scope, *, authority: SimpleNamespace(
            elements=tuple(
                SimpleNamespace(
                    element_id=element_id
                )
                for element_id
                in scope.element_ids
            )
        ),
    )


def build():
    (
        task,
        progress,
        receipt,
        scope,
        authority,
    ) = make_chain()

    return module.build_working_draft(
        task=task,
        progress=progress,
        retrieval_receipt=receipt,
        scope=scope,
        authority=authority,
        title="Employer knowledge working draft",
        purpose="Prepare bounded solicitor working text.",
        statements=inputs(),
        creator_reference="reviewer@example.test",
        recorded_at="2026-09-07T09:31:00Z",
    )


def test_d1i3i1_builds_exact_working_draft() -> None:
    draft = build()

    assert (
        draft.schema_version
        == module.WORKING_DRAFT_SCHEMA_VERSION
    )

    assert draft.case_id == CASE_ID
    assert draft.task_id == TASK_ID
    assert draft.progress_id == PROGRESS_ID
    assert draft.scope_binding_id == SCOPE_BINDING_ID
    assert draft.authority_id == AUTHORITY_ID
    assert draft.issue_analysis_id == ISSUE_ID
    assert len(draft.statements) == 2

    assert all(
        item.statement_id.startswith(
            "sha256:"
        )
        for item in draft.statements
    )

    assert draft.draft_id.startswith(
        "sha256:"
    )


def test_d1i3i1_binds_exact_task_work_hashes() -> None:
    draft = build()

    assert (
        draft.task_work_question_sha256
        == sha(QUESTION)
    )

    assert (
        draft.task_work_answer_sha256
        == sha(ANSWER)
    )


def test_d1i3i1_canonicalises_citations() -> None:
    draft = build()

    assert (
        draft.statements[0].cited_evidence_keys
        == (
            "evidence:a",
            "evidence:b",
        )
    )


def test_d1i3i1_rejects_statement_outside_professional_scope() -> None:
    (
        task,
        progress,
        receipt,
        scope,
        authority,
    ) = make_chain(
        element_ids=(
            "EK-INFORMATION",
        )
    )

    statement = (
        module.WorkingDraftStatementInput(
            text="Outside scope.",
            element_id="EK-RECIPIENT",
            claimed_status="SUPPORTED",
            claimed_confidence="MEDIUM",
            cited_evidence_keys=(),
        )
    )

    with pytest.raises(
        module.DraftingWorkingDraftError,
        match="outside the explicit D1-I1 scope",
    ):
        module.build_working_draft(
            task=task,
            progress=progress,
            retrieval_receipt=receipt,
            scope=scope,
            authority=authority,
            title="Draft",
            purpose="Purpose",
            statements=(statement,),
            creator_reference="reviewer@example.test",
        )


def test_d1i3i1_rejects_unreceipted_answer_change() -> None:
    (
        task,
        progress,
        receipt,
        scope,
        authority,
    ) = make_chain()

    progress.answer = (
        "Changed after the R68 receipt."
    )

    with pytest.raises(
        module.DraftingWorkingDraftError,
        match="answer hash",
    ):
        module.build_working_draft(
            task=task,
            progress=progress,
            retrieval_receipt=receipt,
            scope=scope,
            authority=authority,
            title="Draft",
            purpose="Purpose",
            statements=inputs(),
            creator_reference="reviewer@example.test",
        )


def test_d1i3i1_rejects_stale_scope_authority() -> None:
    (
        task,
        progress,
        receipt,
        scope,
        authority,
    ) = make_chain()

    authority.manifest.authority_id = (
        "sha256:"
        + ("c" * 64)
    )

    with pytest.raises(
        module.DraftingWorkingDraftError,
        match="stale D1-I1 authority scope",
    ):
        module.build_working_draft(
            task=task,
            progress=progress,
            retrieval_receipt=receipt,
            scope=scope,
            authority=authority,
            title="Draft",
            purpose="Purpose",
            statements=inputs(),
            creator_reference="reviewer@example.test",
        )


def test_d1i3i1_requires_at_least_one_statement() -> None:
    (
        task,
        progress,
        receipt,
        scope,
        authority,
    ) = make_chain()

    with pytest.raises(
        module.DraftingWorkingDraftError,
        match="at least one statement",
    ):
        module.build_working_draft(
            task=task,
            progress=progress,
            retrieval_receipt=receipt,
            scope=scope,
            authority=authority,
            title="Draft",
            purpose="Purpose",
            statements=(),
            creator_reference="reviewer@example.test",
        )


def test_d1i3i1_record_and_load_round_trip(
    tmp_path: Path,
) -> None:
    (
        task,
        progress,
        receipt,
        scope,
        authority,
    ) = make_chain()

    recorded = module.record_working_draft(
        task=task,
        progress=progress,
        retrieval_receipt=receipt,
        scope=scope,
        authority=authority,
        title="Employer knowledge working draft",
        purpose="Prepare bounded solicitor working text.",
        statements=inputs(),
        creator_reference="reviewer@example.test",
        recorded_at="2026-09-07T09:31:00Z",
        root=tmp_path,
    )

    loaded = module.load_working_draft(
        CASE_ID,
        TASK_ID,
        recorded.draft_id,
        root=tmp_path,
    )

    assert loaded == recorded

    assert (
        module.load_working_drafts(
            CASE_ID,
            TASK_ID,
            root=tmp_path,
        )
        == (recorded,)
    )


def test_d1i3i1_rejects_duplicate_exact_draft(
    tmp_path: Path,
) -> None:
    (
        task,
        progress,
        receipt,
        scope,
        authority,
    ) = make_chain()

    kwargs = dict(
        task=task,
        progress=progress,
        retrieval_receipt=receipt,
        scope=scope,
        authority=authority,
        title="Employer knowledge working draft",
        purpose="Prepare bounded solicitor working text.",
        statements=inputs(),
        creator_reference="reviewer@example.test",
        recorded_at="2026-09-07T09:31:00Z",
        root=tmp_path,
    )

    module.record_working_draft(
        **kwargs
    )

    with pytest.raises(
        module.DraftingWorkingDraftError,
        match="already recorded",
    ):
        module.record_working_draft(
            **kwargs
        )


def test_d1i3i1_no_existing_store_returns_empty(
    tmp_path: Path,
) -> None:
    assert (
        module.load_working_drafts(
            CASE_ID,
            TASK_ID,
            root=tmp_path,
        )
        == ()
    )


def test_d1i3i1_has_no_release_state() -> None:
    fields = {
        field.name
        for field
        in module.WorkingDraft.__dataclass_fields__.values()
    }

    assert "release_state" not in fields
    assert "release_decision" not in fields
    assert "approved" not in fields
    assert "court_or_tribunal_reliance" not in fields


def test_d1i3i1_has_no_openai_chroma_or_streamlit_dependency() -> None:
    source = Path(
        module.__file__
    ).read_text(
        encoding="utf-8"
    ).lower()

    forbidden = (
        "openai",
        "chromadb",
        "chroma",
        "streamlit",
        "requests",
        "responses.create",
        "chat.completions",
    )

    assert not any(
        token in source
        for token in forbidden
    )


def test_d1i3i1_working_draft_is_not_report_release_artifact() -> None:
    fields = set(
        module.WorkingDraft.__dataclass_fields__
    )

    assert "report_projection_id" not in fields
    assert "projection_payload_sha256" not in fields
    assert "manifest_id" not in fields
    assert "renderer_version" not in fields
    assert "output_profile" not in fields
    assert "report_manifest" not in fields