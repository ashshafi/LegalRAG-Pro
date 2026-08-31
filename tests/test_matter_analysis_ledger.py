from types import SimpleNamespace

import pytest

from matter_analysis_ledger import (
    MatterAnalysisLedgerError,
    RelationshipReviewState,
    RelationshipType,
    build_matter_analysis_ledger,
    current_relationships,
    derive_relationship_id,
    load_relationship_events,
    propose_relationship,
    review_relationship,
)


CASE = "case-1"
AUTHORITY = "authority-1"
ISSUE = "issue-1"
ELEMENT = "element-1"


def test_relationship_identity_is_pair_order_independent():

    first = derive_relationship_id(
        case_id=CASE,
        authority_id=AUTHORITY,
        issue_analysis_id=ISSUE,
        element_id=ELEMENT,
        relationship_type=
            RelationshipType.CONTRADICTS,
        left_evidence_key="E001",
        right_evidence_key="E002",
    )

    second = derive_relationship_id(
        case_id=CASE,
        authority_id=AUTHORITY,
        issue_analysis_id=ISSUE,
        element_id=ELEMENT,
        relationship_type=
            RelationshipType.CONTRADICTS,
        left_evidence_key="E002",
        right_evidence_key="E001",
    )

    assert first == second


def test_propose_then_approve_is_append_only(
    tmp_path,
):

    proposed = propose_relationship(
        case_id=CASE,
        authority_id=AUTHORITY,
        issue_analysis_id=ISSUE,
        element_id=ELEMENT,
        relationship_type=
            RelationshipType.CONTRADICTS,
        left_evidence_key="E001",
        right_evidence_key="E002",
        rationale=(
            "The propositions cannot "
            "both be correct."
        ),
        root=tmp_path,
        created_at=(
            "2026-08-30T22:00:00+00:00"
        ),
    )

    assert (
        proposed.state
        is RelationshipReviewState.PROPOSED
    )

    approved = review_relationship(
        case_id=CASE,
        authority_id=AUTHORITY,
        relationship_id=
            proposed.relationship_id,
        decision=
            RelationshipReviewState.APPROVED,
        root=tmp_path,
        created_at=(
            "2026-08-30T22:01:00+00:00"
        ),
    )

    events = load_relationship_events(
        case_id=CASE,
        authority_id=AUTHORITY,
        root=tmp_path,
    )

    assert len(events) == 2

    assert (
        events[0].state
        is RelationshipReviewState.PROPOSED
    )

    assert (
        events[1].state
        is RelationshipReviewState.APPROVED
    )

    assert (
        approved.previous_event_id
        == proposed.event_id
    )

    current = current_relationships(
        events
    )

    assert current == (
        approved,
    )


def test_terminal_review_cannot_be_silently_changed(
    tmp_path,
):

    proposed = propose_relationship(
        case_id=CASE,
        authority_id=AUTHORITY,
        issue_analysis_id=ISSUE,
        element_id=ELEMENT,
        relationship_type=
            RelationshipType.CORROBORATES,
        left_evidence_key="E003",
        right_evidence_key="E004",
        rationale=(
            "Independent records support "
            "the same proposition."
        ),
        root=tmp_path,
    )

    review_relationship(
        case_id=CASE,
        authority_id=AUTHORITY,
        relationship_id=
            proposed.relationship_id,
        decision=
            RelationshipReviewState.REJECTED,
        root=tmp_path,
    )

    with pytest.raises(
        MatterAnalysisLedgerError,
        match="already been reviewed",
    ):

        review_relationship(
            case_id=CASE,
            authority_id=AUTHORITY,
            relationship_id=
                proposed.relationship_id,
            decision=
                RelationshipReviewState.APPROVED,
            root=tmp_path,
        )


def test_rejected_coordinate_cannot_be_silently_reproposed(
    tmp_path,
):

    proposed = propose_relationship(
        case_id=CASE,
        authority_id=AUTHORITY,
        issue_analysis_id=ISSUE,
        element_id=ELEMENT,
        relationship_type=
            RelationshipType.CONTRADICTS,
        left_evidence_key="E010",
        right_evidence_key="E011",
        rationale="First review.",
        root=tmp_path,
    )

    review_relationship(
        case_id=CASE,
        authority_id=AUTHORITY,
        relationship_id=
            proposed.relationship_id,
        decision=
            RelationshipReviewState.REJECTED,
        root=tmp_path,
    )

    with pytest.raises(
        MatterAnalysisLedgerError,
        match="review history",
    ):

        propose_relationship(
            case_id=CASE,
            authority_id=AUTHORITY,
            issue_analysis_id=ISSUE,
            element_id=ELEMENT,
            relationship_type=
                RelationshipType.CORROBORATES,
            left_evidence_key="E010",
            right_evidence_key="E011",
            rationale="Silent retry.",
            root=tmp_path,
        )


def test_projection_reuses_existing_matrix_roles():

    status = SimpleNamespace(
        value="DISPUTED"
    )

    confidence = SimpleNamespace(
        value="MEDIUM"
    )

    element = SimpleNamespace(
        element_id=
            ELEMENT,

        element_name=
            "Knowledge",

        legal_question=
            "Did the employer know?",

        analysis_status=
            status,

        analysis_confidence=
            confidence,

        supporting_evidence_keys=
            ("E001",),

        adverse_evidence_keys=
            ("E002",),

        corroborative_evidence_keys=
            ("E003",),

        neutral_evidence_keys=
            ("E004",),

        conflicting_evidence_keys=
            ("E005",),

        evidential_gap_ids=
            ("G001",),

        unresolved_matters=
            (
                "Exact date unresolved",
            ),

        provisional_analysis=
            "Knowledge remains disputed.",
    )

    issue = SimpleNamespace(
        issue_analysis_id=
            ISSUE,

        issue_definition_id=
            "definition-1",

        issue_definition_version=
            "1.0",

        issue_name=
            "Employer knowledge",

        issue_summary=
            "Knowledge is disputed.",

        element_records=
            (
                element,
            ),
    )

    authority = SimpleNamespace(
        manifest=
            SimpleNamespace(
                case_id=
                    CASE,

                authority_id=
                    AUTHORITY,
            ),

        case_matrices=
            SimpleNamespace(
                issue_matrix=
                    (
                        issue,
                    ),
            ),
    )

    ledger = build_matter_analysis_ledger(
        authority=
            authority,
    )

    projected = (
        ledger
        .issues[0]
        .elements[0]
    )

    assert (
        projected.supporting_evidence_keys
        == ("E001",)
    )

    assert (
        projected.adverse_evidence_keys
        == ("E002",)
    )

    assert (
        projected.corroborative_evidence_keys
        == ("E003",)
    )

    assert (
        projected.conflicting_evidence_keys
        == ("E005",)
    )

    assert (
        projected.evidential_gap_ids
        == ("G001",)
    )

    assert (
        projected.analytical_status
        == "DISPUTED"
    )


def test_app_renders_ledger_after_existing_legal_issue_dashboard():

    source = open(
        "src/app.py",
        encoding="utf-8",
    ).read()

    dashboard = source.index(
        "show_legal_issue_dashboard(active_case_id)"
    )

    ledger = source.index(
        "show_matter_analysis_ledger(active_case_id)",
        dashboard,
    )

    assert (
        dashboard
        < ledger
    )


def test_ui_module_imports():

    import ui.matter_analysis_ledger

    assert (
        ui.matter_analysis_ledger
        is not None
    )
