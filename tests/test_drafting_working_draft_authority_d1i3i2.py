from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import drafting_working_draft_authority as module

from drafting_working_draft import (
    WORKING_DRAFT_SCHEMA_VERSION,
    WorkingDraft,
    WorkingDraftStatement,
)


CASE_ID = "8081166d-9889-40bb-8add-5d0893037ff0"

ISSUE_ID = "191f424e-cf96-45cb-9d7a-597952a0c10c"

AUTHORITY_ID = (
    "sha256:"
    + ("a" * 64)
)

DRAFT_ID = (
    "sha256:"
    + ("b" * 64)
)


def statement(
    *,
    statement_id_suffix: str = "c",
    sequence: int = 1,
    element_id: str = "DA-DISABILITY",
    text: str = "The claimant was disabled.",
    claimed_status: str = "partially_supported",
    claimed_confidence: str = "medium",
    cited_evidence_keys: tuple[str, ...] = (
        "evidence:support",
    ),
) -> WorkingDraftStatement:
    return WorkingDraftStatement(
        statement_id=(
            "sha256:"
            + (
                statement_id_suffix
                * 64
            )
        ),
        sequence=sequence,
        text=text,
        element_id=element_id,
        claimed_status=claimed_status,
        claimed_confidence=claimed_confidence,
        cited_evidence_keys=cited_evidence_keys,
    )


def draft(
    *,
    authority_id: str = AUTHORITY_ID,
    issue_analysis_id: str = ISSUE_ID,
    statements: tuple[
        WorkingDraftStatement,
        ...,
    ] | None = None,
) -> WorkingDraft:
    if statements is None:
        statements = (
            statement(),
        )

    return WorkingDraft(
        schema_version=
            WORKING_DRAFT_SCHEMA_VERSION,
        draft_id=DRAFT_ID,
        case_id=CASE_ID,
        task_id=
            "e162d3c5-abe2-4553-b464-15a828798a8e",
        progress_id=
            "11111111-1111-4111-8111-111111111111",
        task_work_recorded_at=
            "2026-09-07T09:30:00Z",
        task_work_question_sha256=
            ("1" * 64),
        task_work_answer_sha256=
            ("2" * 64),
        scope_binding_id=
            ("sha256:" + ("3" * 64)),
        authority_id=authority_id,
        issue_analysis_id=
            issue_analysis_id,
        issue_definition_id=
            "DISABILITY",
        title=
            "Disability working draft",
        purpose=
            "Prepare bounded solicitor text.",
        statements=statements,
        creator_reference=
            "reviewer@example.test",
        recorded_at=
            "2026-09-07T09:31:00Z",
    )


def element(
    *,
    element_id: str = "DA-DISABILITY",
):
    return SimpleNamespace(
        element_id=element_id,
        analytical_status=
            "partially_supported",
        analytical_confidence=
            "medium",
        supporting_evidence_keys=(
            "evidence:support",
            "evidence:duplicate",
        ),
        adverse_evidence_keys=(
            "evidence:adverse",
        ),
        corroborative_evidence_keys=(
            "evidence:corroborative",
            "evidence:duplicate",
        ),
        conflicting_evidence_keys=(
            "evidence:conflict",
        ),
        unresolved_matters=(
            "One unresolved matter.",
            "Second unresolved matter.",
        ),
        evidential_gap_ids=(
            "gap:1",
        ),
    )


def authority():
    return SimpleNamespace(
        manifest=SimpleNamespace(
            case_id=CASE_ID,
            authority_id=AUTHORITY_ID,
        )
    )


def ledger(
    *,
    authority_id: str = AUTHORITY_ID,
    issue_analysis_id: str = ISSUE_ID,
    elements=None,
):
    if elements is None:
        elements = (
            element(),
        )

    return SimpleNamespace(
        authority_id=authority_id,
        issues=(
            SimpleNamespace(
                issue_analysis_id=
                    issue_analysis_id,
                elements=tuple(elements),
            ),
        ),
    )


def test_d1i3i2_maps_exact_statement_and_element_to_existing_checker(
    monkeypatch,
) -> None:
    captured = []

    sentinel = SimpleNamespace(
        result="ALIGNED"
    )

    monkeypatch.setattr(
        module,
        "build_matter_analysis_ledger",
        lambda *, authority, events: ledger(),
    )

    def fake_checker(**kwargs):
        captured.append(
            kwargs
        )

        return sentinel

    monkeypatch.setattr(
        module,
        "check_work_product_authority",
        fake_checker,
    )

    result = (
        module
        .evaluate_working_draft_authority(
            draft=draft(),
            authority=authority(),
        )
    )

    assert len(
        result.statement_evaluations
    ) == 1

    evaluation = (
        result.statement_evaluations[0]
    )

    assert (
        evaluation.element_id
        == "DA-DISABILITY"
    )

    assert evaluation.check is sentinel

    assert captured == [
        {
            "statement":
                "The claimant was disabled.",
            "current_status":
                "partially_supported",
            "current_confidence":
                "medium",
            "claimed_status":
                "partially_supported",
            "claimed_confidence":
                "medium",
            "cited_evidence_keys": (
                "evidence:support",
            ),
            "allowed_evidence_keys": (
                "evidence:adverse",
                "evidence:conflict",
                "evidence:corroborative",
                "evidence:duplicate",
                "evidence:support",
            ),
            "approved_contradiction_count":
                1,
            "unresolved_matter_count":
                2,
            "formal_gap_count":
                1,
        }
    ]


def test_d1i3i2_preserves_one_check_per_statement(
    monkeypatch,
) -> None:
    statements = (
        statement(
            statement_id_suffix="c",
            sequence=1,
            element_id=
                "DA-DISABILITY",
        ),
        statement(
            statement_id_suffix="d",
            sequence=2,
            element_id=
                "DA-KNOWLEDGE",
            text=
                "Knowledge requires separate analysis.",
        ),
    )

    monkeypatch.setattr(
        module,
        "build_matter_analysis_ledger",
        lambda *, authority, events: ledger(
            elements=(
                element(
                    element_id=
                        "DA-DISABILITY"
                ),
                element(
                    element_id=
                        "DA-KNOWLEDGE"
                ),
            )
        ),
    )

    calls = []

    def fake_checker(**kwargs):
        calls.append(
            kwargs
        )

        return SimpleNamespace(
            result="CAUTION"
        )

    monkeypatch.setattr(
        module,
        "check_work_product_authority",
        fake_checker,
    )

    result = (
        module
        .evaluate_working_draft_authority(
            draft=draft(
                statements=statements
            ),
            authority=authority(),
        )
    )

    assert tuple(
        item.element_id
        for item
        in result.statement_evaluations
    ) == (
        "DA-DISABILITY",
        "DA-KNOWLEDGE",
    )

    assert len(calls) == 2


def test_d1i3i2_rejects_stale_draft_authority() -> None:
    stale = (
        "sha256:"
        + ("9" * 64)
    )

    with pytest.raises(
        module.DraftingWorkingDraftAuthorityError,
        match="stale governed authority",
    ):
        module.evaluate_working_draft_authority(
            draft=draft(
                authority_id=stale
            ),
            authority=authority(),
        )


def test_d1i3i2_rejects_wrong_case() -> None:
    other_authority = SimpleNamespace(
        manifest=SimpleNamespace(
            case_id=
                "11111111-1111-4111-8111-111111111111",
            authority_id=
                AUTHORITY_ID,
        )
    )

    with pytest.raises(
        module.DraftingWorkingDraftAuthorityError,
        match="another case",
    ):
        module.evaluate_working_draft_authority(
            draft=draft(),
            authority=other_authority,
        )


def test_d1i3i2_rejects_stale_ledger_projection(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        module,
        "build_matter_analysis_ledger",
        lambda *, authority, events: ledger(
            authority_id=(
                "sha256:"
                + ("8" * 64)
            )
        ),
    )

    with pytest.raises(
        module.DraftingWorkingDraftAuthorityError,
        match="Ledger authority",
    ):
        module.evaluate_working_draft_authority(
            draft=draft(),
            authority=authority(),
        )


def test_d1i3i2_rejects_missing_draft_issue(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        module,
        "build_matter_analysis_ledger",
        lambda *, authority, events: ledger(
            issue_analysis_id=
                "22222222-2222-4222-8222-222222222222"
        ),
    )

    with pytest.raises(
        module.DraftingWorkingDraftAuthorityError,
        match="issue is not uniquely present",
    ):
        module.evaluate_working_draft_authority(
            draft=draft(),
            authority=authority(),
        )


def test_d1i3i2_rejects_element_outside_draft_issue(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        module,
        "build_matter_analysis_ledger",
        lambda *, authority, events: ledger(
            elements=(
                element(
                    element_id=
                        "OTHER-ELEMENT"
                ),
            )
        ),
    )

    with pytest.raises(
        module.DraftingWorkingDraftAuthorityError,
        match="not present in the draft's current governed issue",
    ):
        module.evaluate_working_draft_authority(
            draft=draft(),
            authority=authority(),
        )


def test_d1i3i2_rejects_duplicate_governed_element_ids(
    monkeypatch,
) -> None:
    duplicate = element()

    monkeypatch.setattr(
        module,
        "build_matter_analysis_ledger",
        lambda *, authority, events: ledger(
            elements=(
                duplicate,
                duplicate,
            )
        ),
    )

    with pytest.raises(
        module.DraftingWorkingDraftAuthorityError,
        match="duplicate element identities",
    ):
        module.evaluate_working_draft_authority(
            draft=draft(),
            authority=authority(),
        )


def test_d1i3i2_does_not_mutate_working_draft(
    monkeypatch,
) -> None:
    source_draft = draft()

    before = repr(
        source_draft
    )

    monkeypatch.setattr(
        module,
        "build_matter_analysis_ledger",
        lambda *, authority, events: ledger(),
    )

    monkeypatch.setattr(
        module,
        "check_work_product_authority",
        lambda **kwargs: SimpleNamespace(
            result="ALIGNED"
        ),
    )

    module.evaluate_working_draft_authority(
        draft=source_draft,
        authority=authority(),
    )

    assert repr(
        source_draft
    ) == before


def test_d1i3i2_evaluation_has_no_aggregate_release_decision(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        module,
        "build_matter_analysis_ledger",
        lambda *, authority, events: ledger(),
    )

    monkeypatch.setattr(
        module,
        "check_work_product_authority",
        lambda **kwargs: SimpleNamespace(
            result="CAUTION"
        ),
    )

    result = (
        module
        .evaluate_working_draft_authority(
            draft=draft(),
            authority=authority(),
        )
    )

    fields = set(
        result.__dataclass_fields__
    )

    assert "release_state" not in fields
    assert "release_decision" not in fields
    assert "approved" not in fields
    assert "overall_result" not in fields
    assert "court_or_tribunal_reliance" not in fields


def test_d1i3i2_has_no_persistence_openai_chroma_streamlit_or_release_dependency() -> None:
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
        "work_product_release",
        "write_text",
        "write_bytes",
        '".open("',
        "responses.create",
        "chat.completions",
    )

    assert not any(
        token in source
        for token in forbidden
    )