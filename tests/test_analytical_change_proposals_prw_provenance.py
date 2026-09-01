from __future__ import annotations

import json
from pathlib import Path

import pytest
import controlled_agentic_analysis_review as prw

from analytical_change_proposals import (
    ANALYTICAL_CHANGE_EVENT_PRW_PROVENANCE_SCHEMA_VERSION,
    ANALYTICAL_CHANGE_EVENT_SCHEMA_VERSION,
    AnalyticalChangeProposalError,
    AnalyticalChangeProposalEvent,
    AnalyticalChangeProposalState,
    ProfessionalReviewBoundAnalyticalChangeProposalEvent,
    load_change_proposal_events,
    propose_analytical_change,
    propose_analytical_change_from_professional_review,
    review_analytical_change,
)

CASE = "case-bridge"
AUTHORITY = "sha256:" + "a" * 64
RUN = "sha256:" + "b" * 64
OBS = "sha256:" + "c" * 64
OBS_SHA = "sha256:" + "d" * 64
ISSUE = "issue-bridge"
ELEMENT = "element-bridge"


def review_event(
    decision=prw.ProfessionalReviewDecision.ACCEPT_FOR_MAL1_CONSIDERATION,
):
    identity = prw._event_identity_payload(
        case_id=CASE,
        active_authority_id=AUTHORITY,
        analysis_run_id=RUN,
        source_agent=prw.ObservationSource.CAA1,
        observation_id=OBS,
        observation_sha256=OBS_SHA,
        issue_analysis_id=ISSUE,
        element_id=ELEMENT,
        recommended_action=prw.RecommendedAction.PROFESSIONAL_REVIEW,
        decision=decision,
        reviewer_reference="reviewer",
        reviewer_note="review note",
        reviewed_at_utc="2026-09-01T20:00:00Z",
        previous_event_id=None,
    )
    return prw.ProfessionalReviewEvent(
        schema_version=prw.PRW1_SCHEMA_VERSION,
        case_id=CASE,
        active_authority_id=AUTHORITY,
        analysis_run_id=RUN,
        source_agent=prw.ObservationSource.CAA1,
        observation_id=OBS,
        observation_sha256=OBS_SHA,
        issue_analysis_id=ISSUE,
        element_id=ELEMENT,
        recommended_action=prw.RecommendedAction.PROFESSIONAL_REVIEW,
        decision=decision,
        reviewer_reference="reviewer",
        reviewer_note="review note",
        reviewed_at_utc="2026-09-01T20:00:00Z",
        previous_event_id=None,
        event_id=prw._canonical_sha256(
            prw._canonical_json_bytes(identity)
        ),
    )


def bridge(root: Path, **overrides):
    values = dict(
        case_id=CASE,
        authority_id=AUTHORITY,
        issue_analysis_id=ISSUE,
        element_id=ELEMENT,
        current_status="disputed",
        current_confidence="medium",
        proposed_status="partially_supported",
        proposed_confidence="medium",
        rationale="Explicit accepted-review MAL1 consideration.",
        actor="interactive_user",
        professional_review_events=(review_event(),),
        root=root,
    )
    values.update(overrides)
    return propose_analytical_change_from_professional_review(**values)


def jsonl(root):
    paths = tuple(root.rglob("*.jsonl"))
    assert len(paths) == 1
    return paths[0]


def test_ordinary_path_remains_legacy(tmp_path):
    x = propose_analytical_change(
        case_id=CASE,
        authority_id=AUTHORITY,
        issue_analysis_id=ISSUE,
        element_id=ELEMENT,
        current_status="disputed",
        current_confidence="medium",
        proposed_status="partially_supported",
        proposed_confidence="medium",
        rationale="ordinary proposal",
        actor="interactive_user",
        root=tmp_path,
    )
    assert type(x) is AnalyticalChangeProposalEvent
    assert x.schema_version == ANALYTICAL_CHANGE_EVENT_SCHEMA_VERSION
    raw = json.loads(jsonl(tmp_path).read_text().splitlines()[0])
    assert "basis_analysis_run_id" not in raw
    assert "basis_observation_id" not in raw
    assert "basis_professional_review_event_id" not in raw


def test_bridge_binds_exact_prw_provenance(tmp_path):
    r = review_event()
    x = bridge(tmp_path, professional_review_events=(r,))
    assert isinstance(
        x,
        ProfessionalReviewBoundAnalyticalChangeProposalEvent,
    )
    assert (
        x.schema_version
        == ANALYTICAL_CHANGE_EVENT_PRW_PROVENANCE_SCHEMA_VERSION
    )
    assert x.basis_analysis_run_id == RUN
    assert x.basis_observation_id == OBS
    assert x.basis_professional_review_event_id == r.event_id
    assert load_change_proposal_events(
        case_id=CASE,
        authority_id=AUTHORITY,
        root=tmp_path,
    ) == (x,)


def test_terminal_review_preserves_bound_provenance(tmp_path):
    x = bridge(tmp_path)
    y = review_analytical_change(
        case_id=CASE,
        authority_id=AUTHORITY,
        proposal_id=x.proposal_id,
        decision=AnalyticalChangeProposalState.APPROVED,
        actor="reviewer",
        root=tmp_path,
    )
    assert isinstance(
        y,
        ProfessionalReviewBoundAnalyticalChangeProposalEvent,
    )
    assert y.basis_analysis_run_id == x.basis_analysis_run_id
    assert y.basis_observation_id == x.basis_observation_id
    assert (
        y.basis_professional_review_event_id
        == x.basis_professional_review_event_id
    )
    assert y.previous_event_id == x.event_id


def test_nonaccepted_review_fails_before_write(tmp_path):
    r = review_event(prw.ProfessionalReviewDecision.DEFER)
    with pytest.raises(
        AnalyticalChangeProposalError,
        match="does not permit",
    ):
        bridge(tmp_path, professional_review_events=(r,))
    assert not tuple(tmp_path.rglob("*.jsonl"))


@pytest.mark.parametrize(
    "kwargs,match",
    (
        ({"case_id": "wrong-case"}, "case_id"),
        (
            {"authority_id": "sha256:" + "e" * 64},
            "active_authority_id",
        ),
        ({"issue_analysis_id": "wrong-issue"}, "issue_analysis_id"),
        ({"element_id": "wrong-element"}, "element_id"),
    ),
)
def test_review_target_mismatch_fails_before_write(
    tmp_path,
    kwargs,
    match,
):
    with pytest.raises(AnalyticalChangeProposalError, match=match):
        bridge(tmp_path, **kwargs)
    assert not tuple(tmp_path.rglob("*.jsonl"))


def test_ui_does_not_auto_invoke_bridge():
    ui = (
        Path(__file__).resolve().parents[1]
        / "src/ui/matter_analysis_ledger.py"
    ).read_text(encoding="utf-8")
    assert (
        "propose_analytical_change_from_professional_review"
        not in ui
    )
