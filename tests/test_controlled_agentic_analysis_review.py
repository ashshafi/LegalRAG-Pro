from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from controlled_agentic_analysis import (
    Materiality,
    ObservationConfidence,
    ObservationType,
    RecommendedAction,
    build_agent_observation,
    build_frozen_inspection_universe,
)
from controlled_agentic_analysis_review import (
    ObservationSource,
    ProfessionalReviewDecision,
    ProfessionalReviewError,
    ProfessionalReviewState,
    assert_review_allows_mal1_consideration,
    dumps_professional_review_event,
    loads_professional_review_event,
    project_professional_review,
    review_agent_observation,
)


AUTH = "sha256:" + ("a" * 64)
REF_ID = "sha256:" + ("b" * 64)


def run():
    refs = (
        SimpleNamespace(
            case_id="case-1",
            evidence_key="E1",
            evidence_binding_sha256=REF_ID,
            schema_version="controlled-agentic-analysis-evidence-ref/v1",
        ),
        SimpleNamespace(
            case_id="case-1",
            evidence_key="E2",
            evidence_binding_sha256="sha256:" + ("c" * 64),
            schema_version="controlled-agentic-analysis-evidence-ref/v1",
        ),
    )
    # Build through the real public constructor using the real evidence-ref
    # dataclass shape already validated by CAA1.
    from controlled_agentic_analysis import CAA1EvidenceRef
    refs = tuple(CAA1EvidenceRef(**item.__dict__) for item in refs)
    return build_frozen_inspection_universe(
        case_id="case-1",
        active_authority_id=AUTH,
        evidence_bindings=refs,
        agent_definition_version="agent/v1",
        analysis_engine_identity="engine/v1",
        execution_configuration={"mode": "test"},
    )


def observation(value):
    return build_agent_observation(
        run=value,
        observation_type=ObservationType.ADVERSE_EVIDENCE,
        title="Material adverse evidence",
        summary="Evidence may be material.",
        supporting_evidence_keys=("E1",),
        contrary_evidence_keys=("E2",),
        reasoning_summary="Professional review is required.",
        materiality=Materiality.HIGH,
        observation_confidence=ObservationConfidence.MEDIUM,
        uncertainty="Current record only.",
        limitations=("No authority effect.",),
        recommended_action=RecommendedAction.PROFESSIONAL_REVIEW,
        issue_analysis_id="issue-1",
        element_id="element-1",
    )


def loader(authority_id=AUTH):
    return lambda _: SimpleNamespace(
        manifest=SimpleNamespace(authority_id=authority_id)
    )


def test_acceptance_is_only_eligibility_for_separate_mal1_consideration():
    value = run()
    obs = observation(value)
    event = review_agent_observation(
        run=value,
        observation=obs,
        decision=ProfessionalReviewDecision.ACCEPT_FOR_MAL1_CONSIDERATION,
        reviewer_reference="reviewer@example.test",
        reviewer_note="Suitable for separate proposal drafting.",
        reviewed_at_utc="2026-09-01T10:00:00Z",
        active_authority_loader=loader(),
    )

    assert event.source_agent is ObservationSource.CAA1
    projection = project_professional_review((event,))
    assert projection is not None
    assert projection.state is ProfessionalReviewState.ACCEPTED_FOR_MAL1_CONSIDERATION
    assert projection.eligible_for_mal1_consideration is True
    assert_review_allows_mal1_consideration((event,))


def test_defer_can_be_followed_by_terminal_acceptance():
    value = run()
    obs = observation(value)
    first = review_agent_observation(
        run=value,
        observation=obs,
        decision=ProfessionalReviewDecision.DEFER,
        reviewer_reference="reviewer",
        reviewer_note="Need underlying insurer material.",
        reviewed_at_utc="2026-09-01T10:00:00Z",
        active_authority_loader=loader(),
    )
    second = review_agent_observation(
        run=value,
        observation=obs,
        decision=ProfessionalReviewDecision.ACCEPT_FOR_MAL1_CONSIDERATION,
        reviewer_reference="reviewer",
        reviewer_note="Sufficient after professional review.",
        reviewed_at_utc="2026-09-01T10:01:00Z",
        existing_events=(first,),
        active_authority_loader=loader(),
    )
    assert second.previous_event_id == first.event_id
    projection = project_professional_review((first, second))
    assert projection is not None
    assert projection.eligible_for_mal1_consideration


def test_terminal_review_cannot_be_reopened():
    value = run()
    obs = observation(value)
    first = review_agent_observation(
        run=value,
        observation=obs,
        decision=ProfessionalReviewDecision.REJECT,
        reviewer_reference="reviewer",
        reviewer_note="Not suitable for proposal.",
        reviewed_at_utc="2026-09-01T10:00:00Z",
        active_authority_loader=loader(),
    )
    with pytest.raises(ProfessionalReviewError, match="terminal"):
        review_agent_observation(
            run=value,
            observation=obs,
            decision=ProfessionalReviewDecision.DEFER,
            reviewer_reference="reviewer",
            reviewer_note="Attempt to reopen.",
            reviewed_at_utc="2026-09-01T10:01:00Z",
            existing_events=(first,),
            active_authority_loader=loader(),
        )


def test_authority_drift_fails_closed_before_review_event():
    value = run()
    obs = observation(value)
    with pytest.raises(Exception, match="authority"):
        review_agent_observation(
            run=value,
            observation=obs,
            decision=ProfessionalReviewDecision.DEFER,
            reviewer_reference="reviewer",
            reviewer_note="Should fail.",
            reviewed_at_utc="2026-09-01T10:00:00Z",
            active_authority_loader=loader("sha256:" + ("c" * 64)),
        )


def test_observation_run_mismatch_fails_closed():
    value = run()
    obs = observation(value)
    mismatched = replace(
        obs,
        analysis_run_id="sha256:" + ("d" * 64),
    )
    with pytest.raises(ProfessionalReviewError, match="analysis_run_id"):
        review_agent_observation(
            run=value,
            observation=mismatched,
            decision=ProfessionalReviewDecision.DEFER,
            reviewer_reference="reviewer",
            reviewer_note="Should fail.",
            reviewed_at_utc="2026-09-01T10:00:00Z",
            active_authority_loader=loader(),
        )


def test_review_event_serialization_roundtrip_is_exact():
    value = run()
    obs = observation(value)
    event = review_agent_observation(
        run=value,
        observation=obs,
        decision=ProfessionalReviewDecision.DEFER,
        reviewer_reference="reviewer",
        reviewer_note="Awaiting professional material.",
        reviewed_at_utc="2026-09-01T10:00:00Z",
        active_authority_loader=loader(),
    )
    payload = dumps_professional_review_event(event)
    assert loads_professional_review_event(payload) == event
    assert dumps_professional_review_event(loads_professional_review_event(payload)) == payload


def test_mal1_consideration_guard_rejects_nonaccepted_review():
    value = run()
    obs = observation(value)
    event = review_agent_observation(
        run=value,
        observation=obs,
        decision=ProfessionalReviewDecision.DEFER,
        reviewer_reference="reviewer",
        reviewer_note="Not yet accepted.",
        reviewed_at_utc="2026-09-01T10:00:00Z",
        active_authority_loader=loader(),
    )
    with pytest.raises(ProfessionalReviewError, match="does not permit"):
        assert_review_allows_mal1_consideration((event,))
