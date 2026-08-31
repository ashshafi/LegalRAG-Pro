from pathlib import Path

import pytest

from analytical_change_proposals import (
    AnalyticalChangeProposalError,
    AnalyticalChangeProposalState,
    load_change_proposal_events,
    project_change_proposals,
    propose_analytical_change,
    review_analytical_change,
)


CASE = "case-1"
AUTHORITY = "authority-1"
ISSUE = "issue-1"
ELEMENT = "element-1"


def _propose(
    root: Path,
    **overrides,
):

    values = {
        "case_id":
            CASE,

        "authority_id":
            AUTHORITY,

        "issue_analysis_id":
            ISSUE,

        "element_id":
            ELEMENT,

        "current_status":
            "disputed",

        "current_confidence":
            "medium",

        "proposed_status":
            "partially_supported",

        "proposed_confidence":
            "medium",

        "rationale":
            "Reviewed evidence justifies reconsideration.",

        "actor":
            "interactive_user",

        "basis_relationship_ids":
            (
                "relationship-b",
                "relationship-a",
                "relationship-a",
            ),

        "root":
            root,
    }

    values.update(
        overrides
    )

    return propose_analytical_change(
        **values
    )


def test_proposal_is_append_only_and_projected(
    tmp_path,
):

    proposal = _propose(
        tmp_path
    )

    assert (
        proposal.state
        is AnalyticalChangeProposalState.PROPOSED
    )

    assert (
        proposal.basis_relationship_ids
        == (
            "relationship-a",
            "relationship-b",
        )
    )

    events = load_change_proposal_events(
        case_id=
            CASE,
        authority_id=
            AUTHORITY,
        root=
            tmp_path,
    )

    assert len(
        events
    ) == 1

    projected = project_change_proposals(
        events=
            events,
        issue_analysis_id=
            ISSUE,
        element_id=
            ELEMENT,
    )

    assert projected == (
        proposal,
    )


def test_approval_appends_terminal_review(
    tmp_path,
):

    proposal = _propose(
        tmp_path
    )

    approved = review_analytical_change(
        case_id=
            CASE,
        authority_id=
            AUTHORITY,
        proposal_id=
            proposal.proposal_id,
        decision=
            AnalyticalChangeProposalState.APPROVED,
        actor=
            "interactive_user",
        root=
            tmp_path,
    )

    assert (
        approved.state
        is AnalyticalChangeProposalState.APPROVED
    )

    assert (
        approved.previous_event_id
        == proposal.event_id
    )

    events = load_change_proposal_events(
        case_id=
            CASE,
        root=
            tmp_path,
    )

    assert len(
        events
    ) == 2

    assert events[
        0
    ] == proposal

    assert events[
        1
    ] == approved


def test_rejection_appends_terminal_review(
    tmp_path,
):

    proposal = _propose(
        tmp_path
    )

    rejected = review_analytical_change(
        case_id=
            CASE,
        authority_id=
            AUTHORITY,
        proposal_id=
            proposal.proposal_id,
        decision=
            AnalyticalChangeProposalState.REJECTED,
        actor=
            "interactive_user",
        review_note=
            "Evidence does not justify the proposed change.",
        root=
            tmp_path,
    )

    assert (
        rejected.state
        is AnalyticalChangeProposalState.REJECTED
    )

    assert (
        rejected.review_note
        == "Evidence does not justify the proposed change."
    )


def test_noop_change_is_rejected(
    tmp_path,
):

    with pytest.raises(
        AnalyticalChangeProposalError,
        match=
            "must actually change",
    ):

        _propose(
            tmp_path,
            proposed_status=
                "disputed",
            proposed_confidence=
                "medium",
        )


def test_second_pending_proposal_is_rejected(
    tmp_path,
):

    _propose(
        tmp_path
    )

    with pytest.raises(
        AnalyticalChangeProposalError,
        match=
            "already pending",
    ):

        _propose(
            tmp_path,
            proposed_status=
                "well_supported",
        )


def test_terminal_proposal_cannot_be_reviewed_twice(
    tmp_path,
):

    proposal = _propose(
        tmp_path
    )

    review_analytical_change(
        case_id=
            CASE,
        authority_id=
            AUTHORITY,
        proposal_id=
            proposal.proposal_id,
        decision=
            AnalyticalChangeProposalState.APPROVED,
        actor=
            "interactive_user",
        root=
            tmp_path,
    )

    with pytest.raises(
        AnalyticalChangeProposalError,
        match=
            "already been reviewed",
    ):

        review_analytical_change(
            case_id=
                CASE,
            authority_id=
                AUTHORITY,
            proposal_id=
                proposal.proposal_id,
            decision=
                AnalyticalChangeProposalState.REJECTED,
            actor=
                "interactive_user",
            root=
                tmp_path,
        )


def test_new_proposal_allowed_after_terminal_review(
    tmp_path,
):

    first = _propose(
        tmp_path
    )

    review_analytical_change(
        case_id=
            CASE,
        authority_id=
            AUTHORITY,
        proposal_id=
            first.proposal_id,
        decision=
            AnalyticalChangeProposalState.REJECTED,
        actor=
            "interactive_user",
        root=
            tmp_path,
    )

    second = _propose(
        tmp_path,
        proposed_status=
            "well_supported",
        proposed_confidence=
            "high",
    )

    assert (
        second.proposal_id
        != first.proposal_id
    )


def test_authority_filter_is_exact(
    tmp_path,
):

    _propose(
        tmp_path
    )

    assert (
        load_change_proposal_events(
            case_id=
                CASE,
            authority_id=
                "different-authority",
            root=
                tmp_path,
        )
        == ()
    )


def test_module_contains_no_authority_application_or_ai():

    source = Path(
        "src/analytical_change_proposals.py"
    ).read_text(
        encoding="utf-8"
    ).lower()

    assert "openai" not in source
    assert "chromadb" not in source

    assert (
        "publish_governed_analytical_authority"
        not in source
    )

    assert (
        "activate_governed_analytical_authority"
        not in source
    )

    assert (
        "apply_analytical_change"
        not in source
    )
