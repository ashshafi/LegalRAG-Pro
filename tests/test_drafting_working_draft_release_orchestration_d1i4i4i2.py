from __future__ import annotations

import hashlib
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

import pytest

import drafting_working_draft_release_orchestration as orchestration
import work_product_release as wpr


CASE_ID = "8081166d-9889-40bb-8add-5d0893037ff0"


def target(
    *,
    suffix: str = "1",
):
    projection_identity = (
        "working-draft-release-test-projection:"
        + suffix
    )

    manifest_identity = (
        "working-draft-release-test-manifest:"
        + suffix
    )

    artifact_identity = (
        "working-draft-release-test-artifact:"
        + suffix
    )

    report_projection_id = str(
        uuid5(
            NAMESPACE_URL,
            projection_identity,
        )
    )

    projection_payload_sha256 = (
        hashlib.sha256(
            projection_identity.encode(
                "utf-8"
            )
        ).hexdigest()
    )

    manifest_id = str(
        uuid5(
            NAMESPACE_URL,
            manifest_identity,
        )
    )

    artifact_id = str(
        uuid5(
            NAMESPACE_URL,
            artifact_identity,
        )
    )

    markdown = (
        "# Exact WorkingDraft professional review "
        + suffix
        + "\n"
    )

    markdown_sha256 = hashlib.sha256(
        markdown.encode(
            "utf-8"
        )
    ).hexdigest()

    manifest = SimpleNamespace(
        manifest_id=
            manifest_id,
        fixture_identity=
            manifest_identity,
    )

    projection = SimpleNamespace(
        case_header=
            SimpleNamespace(
                case_id=
                    CASE_ID,
            ),
        report_projection_id=
            report_projection_id,
        projection_payload_sha256=
            projection_payload_sha256,
        manifest=
            manifest,
    )

    artifact = SimpleNamespace(
        markdown_report_id=
            artifact_id,
        markdown_sha256=
            markdown_sha256,
        markdown=
            markdown,
        report_projection_id=
            report_projection_id,
        projection_payload_sha256=
            projection_payload_sha256,
        manifest_id=
            manifest_id,
        report_manifest=
            manifest,
        renderer_version=
            "drafting-working-draft-markdown-renderer/1.0",
        output_profile=
            "working-draft-professional-review/1.0",
    )

    return (
        wpr.build_work_product_release_target(
            projection=
                projection,
            artifact=
                artifact,
            artifact_format=
                "markdown",
        )
    )


def prepared(
    *results: str,
):
    if not results:
        results = (
            "CAUTION",
        )

    return SimpleNamespace(
        projection=
            SimpleNamespace(
                authority_evaluations=
                    tuple(
                        SimpleNamespace(
                            result=result,
                        )
                        for result
                        in results
                    ),
            ),
        target=
            target(),
    )


def install_prepared(
    monkeypatch,
    value,
):
    monkeypatch.setattr(
        orchestration,
        "prepare_working_draft_professional_review",
        lambda **_kwargs: value,
    )


def approval_values(
    *,
    root,
):
    return dict(
        decision=
            wpr.WorkProductReleaseDecision.APPROVED_FOR_RELIANCE,
        factual_basis_reviewed=
            True,
        legal_authorities_reviewed=
            True,
        unverified_authorities_remaining=
            0,
        professional_judgment_completed=
            True,
        court_or_tribunal_reliance=
            False,
        reviewer_reference=
            "solicitor:functional-reviewer",
        review_note=
            "Exact WorkingDraft professionally reviewed.",
        root=
            root,
    )


def test_aligned_can_reach_existing_approval_state_machine(
    monkeypatch,
    tmp_path,
):
    value = prepared(
        "ALIGNED",
    )

    install_prepared(
        monkeypatch,
        value,
    )

    result = (
        orchestration
        .record_working_draft_professional_release(
            draft=
                object(),
            authority=
                object(),
            **approval_values(
                root=tmp_path,
            ),
        )
    )

    assert (
        result.release_projection.state
        is wpr.WorkProductReleaseState.APPROVED_FOR_RELIANCE
    )

    assert (
        result.event.decision
        is wpr.WorkProductReleaseDecision.APPROVED_FOR_RELIANCE
    )


def test_caution_can_reach_existing_approval_state_machine(
    monkeypatch,
    tmp_path,
):
    value = prepared(
        "CAUTION",
        "CAUTION",
    )

    install_prepared(
        monkeypatch,
        value,
    )

    result = (
        orchestration
        .record_working_draft_professional_release(
            draft=
                object(),
            authority=
                object(),
            **approval_values(
                root=tmp_path,
            ),
        )
    )

    assert (
        result.release_projection.state
        is wpr.WorkProductReleaseState.APPROVED_FOR_RELIANCE
    )

    assert (
        result.release_projection.court_or_tribunal_reliance
        is False
    )


def test_not_authorized_cannot_be_approved_and_writes_nothing(
    monkeypatch,
    tmp_path,
):
    value = prepared(
        "CAUTION",
        "NOT_AUTHORIZED",
    )

    install_prepared(
        monkeypatch,
        value,
    )

    with pytest.raises(
        orchestration.WorkingDraftProfessionalReleaseError,
        match="NOT_AUTHORIZED",
    ):
        (
            orchestration
            .record_working_draft_professional_release(
                draft=
                    object(),
                authority=
                    object(),
                **approval_values(
                    root=tmp_path,
                ),
            )
        )

    assert (
        wpr.load_work_product_release_events(
            CASE_ID,
            root=tmp_path,
        )
        == ()
    )


def test_not_authorized_may_be_explicitly_rejected(
    monkeypatch,
    tmp_path,
):
    value = prepared(
        "NOT_AUTHORIZED",
    )

    install_prepared(
        monkeypatch,
        value,
    )

    result = (
        orchestration
        .record_working_draft_professional_release(
            draft=
                object(),
            authority=
                object(),
            decision=
                wpr.WorkProductReleaseDecision.REJECTED,
            factual_basis_reviewed=
                False,
            legal_authorities_reviewed=
                False,
            unverified_authorities_remaining=
                2,
            professional_judgment_completed=
                False,
            court_or_tribunal_reliance=
                False,
            reviewer_reference=
                "solicitor:functional-reviewer",
            review_note=
                "Rejected because a statement is not authorised.",
            root=
                tmp_path,
        )
    )

    assert (
        result.release_projection.state
        is wpr.WorkProductReleaseState.REJECTED
    )

    assert (
        result.event.decision
        is wpr.WorkProductReleaseDecision.REJECTED
    )


@pytest.mark.parametrize(
    (
        "field",
        "value",
    ),
    [
        (
            "factual_basis_reviewed",
            False,
        ),
        (
            "legal_authorities_reviewed",
            False,
        ),
        (
            "unverified_authorities_remaining",
            1,
        ),
        (
            "professional_judgment_completed",
            False,
        ),
    ],
)
def test_existing_professional_approval_gates_remain_authoritative(
    monkeypatch,
    tmp_path,
    field,
    value,
):
    prepared_value = prepared(
        "CAUTION",
    )

    install_prepared(
        monkeypatch,
        prepared_value,
    )

    values = approval_values(
        root=tmp_path,
    )

    values[
        field
    ] = value

    with pytest.raises(
        orchestration.WorkingDraftProfessionalReleaseError,
        match="Existing work-product release processing failed",
    ):
        (
            orchestration
            .record_working_draft_professional_release(
                draft=
                    object(),
                authority=
                    object(),
                **values,
            )
        )

    assert (
        wpr.load_work_product_release_events(
            CASE_ID,
            root=tmp_path,
        )
        == ()
    )


def test_general_reliance_does_not_imply_court_or_tribunal_reliance(
    monkeypatch,
    tmp_path,
):
    install_prepared(
        monkeypatch,
        prepared(
            "ALIGNED",
        ),
    )

    result = (
        orchestration
        .record_working_draft_professional_release(
            draft=
                object(),
            authority=
                object(),
            **approval_values(
                root=tmp_path,
            ),
        )
    )

    assert (
        result.release_projection.state
        is wpr.WorkProductReleaseState.APPROVED_FOR_RELIANCE
    )

    assert (
        result.release_projection.court_or_tribunal_reliance
        is False
    )


def test_explicit_court_or_tribunal_reliance_remains_separate(
    monkeypatch,
    tmp_path,
):
    install_prepared(
        monkeypatch,
        prepared(
            "ALIGNED",
        ),
    )

    values = approval_values(
        root=tmp_path,
    )

    values[
        "court_or_tribunal_reliance"
    ] = True

    result = (
        orchestration
        .record_working_draft_professional_release(
            draft=
                object(),
            authority=
                object(),
            **values,
        )
    )

    assert (
        result.release_projection.state
        is wpr.WorkProductReleaseState.APPROVED_FOR_RELIANCE
    )

    assert (
        result.release_projection.court_or_tribunal_reliance
        is True
    )


def test_rejected_decision_cannot_claim_court_or_tribunal_reliance(
    monkeypatch,
    tmp_path,
):
    install_prepared(
        monkeypatch,
        prepared(
            "CAUTION",
        ),
    )

    with pytest.raises(
        orchestration.WorkingDraftProfessionalReleaseError,
        match="Existing work-product release processing failed",
    ):
        (
            orchestration
            .record_working_draft_professional_release(
                draft=
                    object(),
                authority=
                    object(),
                decision=
                    wpr.WorkProductReleaseDecision.REJECTED,
                factual_basis_reviewed=
                    True,
                legal_authorities_reviewed=
                    True,
                unverified_authorities_remaining=
                    0,
                professional_judgment_completed=
                    True,
                court_or_tribunal_reliance=
                    True,
                reviewer_reference=
                    "solicitor:functional-reviewer",
                review_note=
                    "Rejected.",
                root=
                    tmp_path,
            )
        )

    assert (
        wpr.load_work_product_release_events(
            CASE_ID,
            root=tmp_path,
        )
        == ()
    )


def test_invalid_decision_fails_before_release_write(
    monkeypatch,
    tmp_path,
):
    install_prepared(
        monkeypatch,
        prepared(
            "CAUTION",
        ),
    )

    with pytest.raises(
        orchestration.WorkingDraftProfessionalReleaseError,
        match="decision is invalid",
    ):
        (
            orchestration
            .record_working_draft_professional_release(
                draft=
                    object(),
                authority=
                    object(),
                decision=
                    "APPROVE",
                factual_basis_reviewed=
                    True,
                legal_authorities_reviewed=
                    True,
                unverified_authorities_remaining=
                    0,
                professional_judgment_completed=
                    True,
                court_or_tribunal_reliance=
                    False,
                reviewer_reference=
                    "solicitor:functional-reviewer",
                review_note=
                    "Review.",
                root=
                    tmp_path,
            )
        )

    assert (
        wpr.load_work_product_release_events(
            CASE_ID,
            root=tmp_path,
        )
        == ()
    )


def test_release_uses_fresh_prepared_target_each_time(
    monkeypatch,
    tmp_path,
):
    first = prepared(
        "CAUTION",
    )

    second_target = target(
        suffix="2",
    )

    second = SimpleNamespace(
        projection=
            first.projection,
        target=
            second_target,
    )

    calls = iter(
        (
            first,
            second,
        )
    )

    monkeypatch.setattr(
        orchestration,
        "prepare_working_draft_professional_review",
        lambda **_kwargs: next(
            calls
        ),
    )

    first_result = (
        orchestration
        .record_working_draft_professional_release(
            draft=
                object(),
            authority=
                object(),
            **approval_values(
                root=tmp_path,
            ),
        )
    )

    second_result = (
        orchestration
        .record_working_draft_professional_release(
            draft=
                object(),
            authority=
                object(),
            **approval_values(
                root=tmp_path,
            ),
        )
    )

    assert (
        first_result.event.target_id
        != second_result.event.target_id
    )

    first_projection = (
        wpr.project_work_product_release(
            target=
                first.target,
            events=
                wpr.load_work_product_release_events(
                    CASE_ID,
                    root=tmp_path,
                ),
        )
    )

    second_projection = (
        wpr.project_work_product_release(
            target=
                second.target,
            events=
                wpr.load_work_product_release_events(
                    CASE_ID,
                    root=tmp_path,
                ),
        )
    )

    assert (
        first_projection.state
        is wpr.WorkProductReleaseState.APPROVED_FOR_RELIANCE
    )

    assert (
        second_projection.state
        is wpr.WorkProductReleaseState.APPROVED_FOR_RELIANCE
    )


def test_append_only_rejection_then_reapproval_for_same_exact_target(
    monkeypatch,
    tmp_path,
):
    value = prepared(
        "CAUTION",
    )

    install_prepared(
        monkeypatch,
        value,
    )

    rejected = (
        orchestration
        .record_working_draft_professional_release(
            draft=
                object(),
            authority=
                object(),
            decision=
                wpr.WorkProductReleaseDecision.REJECTED,
            factual_basis_reviewed=
                True,
            legal_authorities_reviewed=
                True,
            unverified_authorities_remaining=
                1,
            professional_judgment_completed=
                True,
            court_or_tribunal_reliance=
                False,
            reviewer_reference=
                "solicitor:functional-reviewer",
            review_note=
                "Rejected pending authority verification.",
            root=
                tmp_path,
        )
    )

    approved = (
        orchestration
        .record_working_draft_professional_release(
            draft=
                object(),
            authority=
                object(),
            **approval_values(
                root=tmp_path,
            ),
        )
    )

    assert (
        approved.event.previous_event_id
        == rejected.event.event_id
    )

    events = (
        wpr.load_work_product_release_events(
            CASE_ID,
            root=tmp_path,
        )
    )

    assert len(
        events
    ) == 2

    assert (
        approved.release_projection.state
        is wpr.WorkProductReleaseState.APPROVED_FOR_RELIANCE
    )


def test_orchestration_creates_no_second_release_state_machine():
    assert (
        not hasattr(
            orchestration,
            "WorkingDraftReleaseDecision",
        )
    )

    assert (
        not hasattr(
            orchestration,
            "WorkingDraftReleaseState",
        )
    )


def test_orchestration_has_no_ui_provider_or_artifact_file_persistence_dependency():
    source = open(
        orchestration.__file__,
        "r",
        encoding="utf-8",
    ).read()

    for forbidden in (
        "streamlit",
        "openai",
        "chromadb",
        "case_reporting",
        ".write_bytes(",
        ".write_text(",
    ):
        assert forbidden not in source
