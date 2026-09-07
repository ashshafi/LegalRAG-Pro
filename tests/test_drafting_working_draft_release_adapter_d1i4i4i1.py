from __future__ import annotations

from dataclasses import replace
import hashlib
import inspect
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

import drafting_working_draft_release_adapter as adapter
import work_product_release as wpr


CASE_ID = "8081166d-9889-40bb-8add-5d0893037ff0"
TASK_ID = "e162d3c5-abe2-4553-b464-15a828798a8e"
PROGRESS_ID = "1c53897d-9a6b-42c8-a181-8a2e3094dfb3"

DRAFT_ID = (
    "sha256:"
    "b4e86aaa75f4c6b7783dae6d83f0ad7259dccabf1d5c2a06fa19adcfbe19dc5e"
)

AUTHORITY_ID = (
    "sha256:"
    "0e9c4d278b4817aac21a689421116ed596eb4bb5c10bb4c13ace8dcbebc7815f"
)

SCOPE_BINDING_ID = (
    "sha256:"
    "2d0d850fab788bfefb3b5663ebf0f9adcf0d6579ef60f72607337184a2016c14"
)

STATEMENT_1_ID = (
    "sha256:"
    "eca96d7bbc2d7abd5e7e9b89d2ec1e162a52689e3d3ac53f771d7fa855923374"
)

STATEMENT_2_ID = (
    "sha256:"
    "52ea2f1b37703562fdc43e2083db1a32882bae4161e86d30752e1b924c3c1a5d"
)


def statement(
    *,
    sequence: int,
    statement_id: str,
    text: str,
    evidence_key: str,
):
    return SimpleNamespace(
        sequence=sequence,
        statement_id=statement_id,
        element_id="EK-RECIPIENT",
        text=text,
        claimed_status="partially_supported",
        claimed_confidence="medium",
        cited_evidence_keys=(
            evidence_key,
        ),
    )


def draft(
    *,
    first_text: str = "First exact proposed statement.",
):
    return SimpleNamespace(
        schema_version=
            "drafting-working-draft/1.0",
        draft_id=
            DRAFT_ID,
        case_id=
            CASE_ID,
        task_id=
            TASK_ID,
        progress_id=
            PROGRESS_ID,
        task_work_recorded_at=
            "2026-09-07T12:37:18.443017Z",
        task_work_question_sha256=
            "6" * 64,
        task_work_answer_sha256=
            "9" * 64,
        scope_binding_id=
            SCOPE_BINDING_ID,
        authority_id=
            AUTHORITY_ID,
        issue_analysis_id=
            "2df52940-c44d-4759-99fe-6a624edc05c0",
        issue_definition_id=
            "EK-001",
        title=
            "Establish transmission of May 2005 rehabilitation plan",
        purpose=
            "Resolve the exact employer-recipient work point.",
        creator_reference=
            "solicitor@example.test",
        recorded_at=
            "2026-09-07T15:42:01.854932Z",
        statements=(
            statement(
                sequence=1,
                statement_id=STATEMENT_1_ID,
                text=first_text,
                evidence_key="evidence-1",
            ),
            statement(
                sequence=2,
                statement_id=STATEMENT_2_ID,
                text="Second exact proposed statement.",
                evidence_key="evidence-2",
            ),
        ),
    )


def authority():
    return SimpleNamespace(
        manifest=
            SimpleNamespace(
                authority_id=
                    AUTHORITY_ID,
            ),
    )


def evaluation(
    *,
    first_result: str = "CAUTION",
    first_citations: tuple[str, ...] = (
        "evidence-1",
    ),
    authority_id: str = AUTHORITY_ID,
    include_second: bool = True,
):
    items = [
        SimpleNamespace(
            sequence=1,
            statement_id=
                STATEMENT_1_ID,
            element_id=
                "EK-RECIPIENT",
            check=
                SimpleNamespace(
                    result=
                        first_result,
                    current_status=
                        "partially_supported",
                    current_confidence=
                        "medium",
                    reasons=(
                        "One unresolved matter remains.",
                    ),
                    cited_evidence_keys=
                        first_citations,
                ),
        ),
    ]

    if include_second:
        items.append(
            SimpleNamespace(
                sequence=2,
                statement_id=
                    STATEMENT_2_ID,
                element_id=
                    "EK-RECIPIENT",
                check=
                    SimpleNamespace(
                        result=
                            "CAUTION",
                        current_status=
                            "partially_supported",
                        current_confidence=
                            "medium",
                        reasons=(
                            "One unresolved matter remains.",
                        ),
                        cited_evidence_keys=(
                            "evidence-2",
                        ),
                    ),
            )
        )

    return SimpleNamespace(
        authority_id=
            authority_id,
        case_id=
            CASE_ID,
        draft_id=
            DRAFT_ID,
        issue_analysis_id=
            "2df52940-c44d-4759-99fe-6a624edc05c0",
        statement_evaluations=
            tuple(
                items
            ),
    )


def install_evaluation(
    monkeypatch,
    value,
):
    monkeypatch.setattr(
        adapter,
        "evaluate_working_draft_authority",
        lambda **_kwargs: value,
    )


def prepare(
    monkeypatch,
    *,
    draft_value=None,
    evaluation_value=None,
):
    if draft_value is None:
        draft_value = draft()

    if evaluation_value is None:
        evaluation_value = evaluation()

    install_evaluation(
        monkeypatch,
        evaluation_value,
    )

    return (
        adapter.prepare_working_draft_professional_review(
            draft=draft_value,
            authority=authority(),
        )
    )


def test_exact_adapter_is_deterministic_and_release_compatible(
    monkeypatch,
):
    first = prepare(
        monkeypatch
    )

    second = prepare(
        monkeypatch
    )

    assert (
        first.projection
        == second.projection
    )

    assert (
        first.artifact
        == second.artifact
    )

    assert (
        first.target
        == second.target
    )

    UUID(
        first.projection.report_projection_id
    )

    UUID(
        first.projection.manifest.manifest_id
    )

    UUID(
        first.artifact.markdown_report_id
    )

    assert (
        first.target.report_projection_id
        == first.projection.report_projection_id
    )

    assert (
        first.target.manifest_id
        == first.projection.manifest.manifest_id
    )

    assert (
        first.target.artifact_id
        == first.artifact.markdown_report_id
    )

    assert (
        first.target.artifact_sha256
        == first.artifact.markdown_sha256
    )

    assert (
        first.target.artifact_format
        == "markdown"
    )

    assert (
        first.target.renderer_version
        == adapter.WORKING_DRAFT_MARKDOWN_RENDERER_VERSION
    )

    assert (
        first.target.output_profile
        == adapter.WORKING_DRAFT_MARKDOWN_OUTPUT_PROFILE
    )


def test_missing_release_history_projects_to_working(
    monkeypatch,
):
    prepared = prepare(
        monkeypatch
    )

    projected = (
        wpr.project_work_product_release(
            target=
                prepared.target,
            events=(),
        )
    )

    assert (
        projected.state
        is wpr.WorkProductReleaseState.WORKING
    )

    assert (
        projected.latest_event_id
        is None
    )


def test_markdown_is_neutral_about_separate_release_state(
    monkeypatch,
):
    prepared = prepare(
        monkeypatch
    )

    markdown = (
        prepared.artifact.markdown
    )

    assert (
        "does not itself establish approval for reliance"
        in markdown
    )

    assert (
        "Reliance status is held separately"
        in markdown
    )

    assert (
        "APPROVED_FOR_RELIANCE"
        not in markdown
    )

    assert (
        "WORKING MATERIAL ? NOT APPROVED FOR RELIANCE"
        not in markdown
    )


def test_markdown_hash_binds_exact_utf8_bytes(
    monkeypatch,
):
    prepared = prepare(
        monkeypatch
    )

    assert (
        prepared.artifact.markdown_sha256
        == hashlib.sha256(
            prepared.artifact.markdown.encode(
                "utf-8"
            )
        ).hexdigest()
    )

    assert (
        prepared.artifact.markdown.endswith(
            "\n"
        )
    )

    assert not (
        prepared.artifact.markdown.endswith(
            "\n\n"
        )
    )

    assert "\r" not in (
        prepared.artifact.markdown
    )


def test_projection_freezes_complete_task_work_lineage(
    monkeypatch,
):
    prepared = prepare(
        monkeypatch
    )

    value = prepared.projection

    assert (
        value.draft_id
        == DRAFT_ID
    )

    assert (
        value.task_id
        == TASK_ID
    )

    assert (
        value.progress_id
        == PROGRESS_ID
    )

    assert (
        value.scope_binding_id
        == SCOPE_BINDING_ID
    )

    assert (
        value.draft_authority_id
        == AUTHORITY_ID
    )

    assert (
        value.review_authority_id
        == AUTHORITY_ID
    )

    assert (
        value.task_work_question_sha256
        == "6" * 64
    )

    assert (
        value.task_work_answer_sha256
        == "9" * 64
    )

    assert (
        value.task_work_recorded_at
        == "2026-09-07T12:37:18.443017Z"
    )


def test_statement_change_changes_projection_artifact_and_target_identity(
    monkeypatch,
):
    first = prepare(
        monkeypatch,
        draft_value=
            draft(
                first_text=
                    "First exact proposed statement.",
            ),
    )

    second = prepare(
        monkeypatch,
        draft_value=
            draft(
                first_text=
                    "Materially changed proposed statement.",
            ),
    )

    assert (
        first.projection.projection_payload_sha256
        != second.projection.projection_payload_sha256
    )

    assert (
        first.projection.report_projection_id
        != second.projection.report_projection_id
    )

    assert (
        first.artifact.markdown_sha256
        != second.artifact.markdown_sha256
    )

    assert (
        first.target.target_id
        != second.target.target_id
    )


def test_authority_result_change_changes_exact_target_identity(
    monkeypatch,
):
    first = prepare(
        monkeypatch,
        evaluation_value=
            evaluation(
                first_result=
                    "CAUTION",
            ),
    )

    second = prepare(
        monkeypatch,
        evaluation_value=
            evaluation(
                first_result=
                    "ALIGNED",
            ),
    )

    assert (
        first.projection.projection_payload_sha256
        != second.projection.projection_payload_sha256
    )

    assert (
        first.target.target_id
        != second.target.target_id
    )


def test_not_authorized_is_visible_but_does_not_create_release_state(
    monkeypatch,
):
    prepared = prepare(
        monkeypatch,
        evaluation_value=
            evaluation(
                first_result=
                    "NOT_AUTHORIZED",
            ),
    )

    assert (
        "Authority check: NOT_AUTHORIZED"
        in prepared.artifact.markdown
    )

    projected = (
        wpr.project_work_product_release(
            target=
                prepared.target,
            events=(),
        )
    )

    assert (
        projected.state
        is wpr.WorkProductReleaseState.WORKING
    )


def test_missing_statement_authority_evaluation_fails_closed(
    monkeypatch,
):
    install_evaluation(
        monkeypatch,
        evaluation(
            include_second=False,
        ),
    )

    with pytest.raises(
        adapter.WorkingDraftReleaseAdapterError,
        match="does not cover every statement",
    ):
        (
            adapter
            .prepare_working_draft_professional_review(
                draft=draft(),
                authority=authority(),
            )
        )


def test_authority_citations_must_match_exact_statement_citations(
    monkeypatch,
):
    install_evaluation(
        monkeypatch,
        evaluation(
            first_citations=(
                "different-evidence",
            ),
        ),
    )

    with pytest.raises(
        adapter.WorkingDraftReleaseAdapterError,
        match="citations do not match",
    ):
        (
            adapter
            .prepare_working_draft_professional_review(
                draft=draft(),
                authority=authority(),
            )
        )


def test_evaluation_must_bind_current_authority(
    monkeypatch,
):
    install_evaluation(
        monkeypatch,
        evaluation(
            authority_id=(
                "sha256:"
                + "a" * 64
            ),
        ),
    )

    with pytest.raises(
        adapter.WorkingDraftReleaseAdapterError,
        match="does not bind the current authority",
    ):
        (
            adapter
            .prepare_working_draft_professional_review(
                draft=draft(),
                authority=authority(),
            )
        )


def test_artifact_tampering_fails_closed(
    monkeypatch,
):
    prepared = prepare(
        monkeypatch
    )

    with pytest.raises(
        adapter.WorkingDraftReleaseAdapterError,
        match="markdown_sha256 does not match",
    ):
        replace(
            prepared.artifact,
            markdown_sha256=
                "0" * 64,
        )


def test_adapter_has_no_case_report_or_release_write_dependency():
    source = inspect.getsource(
        adapter
    )

    forbidden = (
        "case_reporting",
        "record_work_product_release",
        "streamlit",
        "openai",
        "chromadb",
    )

    for token in forbidden:
        assert (
            token
            not in source
        ), token


def test_existing_release_module_remains_the_only_release_state_machine():
    assert (
        not hasattr(
            adapter,
            "WorkProductReleaseDecision",
        )
    )

    assert (
        not hasattr(
            adapter,
            "WorkProductReleaseState",
        )
    )

    assert (
        not hasattr(
            adapter.WorkingDraftProfessionalReviewProjection,
            "approved_for_reliance",
        )
    )

    assert (
        not hasattr(
            adapter.WorkingDraftProfessionalReviewMarkdown,
            "approved_for_reliance",
        )
    )


def test_adapter_source_is_new_isolated_module():
    path = Path(
        adapter.__file__
    ).resolve()

    assert (
        path.name
        == "drafting_working_draft_release_adapter.py"
    )
