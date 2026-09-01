from __future__ import annotations

from types import SimpleNamespace

import pytest

from controlled_agentic_analysis import (
    CAA1EvidenceRef,
    Materiality,
    ObservationConfidence,
    ObservationType,
    RecommendedAction,
    build_agent_observation,
    build_frozen_inspection_universe,
)
from controlled_agentic_analysis_review import (
    ProfessionalReviewDecision,
    ProfessionalReviewError,
    review_agent_observation,
)
from controlled_agentic_analysis_review_publication import (
    ProfessionalReviewPublicationError,
    load_professional_review_events,
    publish_professional_review_event,
)


AUTH = "sha256:" + ("a" * 64)


def fixture_values():
    refs = (
        CAA1EvidenceRef(
            case_id="case-1",
            evidence_key="E1",
            evidence_binding_sha256="sha256:" + ("b" * 64),
            schema_version="controlled-agentic-analysis-evidence-ref/v1",
        ),
        CAA1EvidenceRef(
            case_id="case-1",
            evidence_key="E2",
            evidence_binding_sha256="sha256:" + ("c" * 64),
            schema_version="controlled-agentic-analysis-evidence-ref/v1",
        ),
    )
    run = build_frozen_inspection_universe(
        case_id="case-1",
        active_authority_id=AUTH,
        evidence_bindings=refs,
        agent_definition_version="agent/v1",
        analysis_engine_identity="engine/v1",
        execution_configuration={"mode": "test"},
    )
    obs = build_agent_observation(
        run=run,
        observation_type=ObservationType.ADVERSE_EVIDENCE,
        title="Review me",
        summary="Summary.",
        supporting_evidence_keys=("E1",),
        contrary_evidence_keys=("E2",),
        reasoning_summary="Reason.",
        materiality=Materiality.HIGH,
        observation_confidence=ObservationConfidence.MEDIUM,
        uncertainty="Uncertain.",
        limitations=("Limit.",),
        recommended_action=RecommendedAction.PROFESSIONAL_REVIEW,
    )
    loader = lambda _: SimpleNamespace(
        manifest=SimpleNamespace(authority_id=AUTH)
    )
    return run, obs, loader


def event(run, obs, loader, *, decision, at, existing=()):
    return review_agent_observation(
        run=run,
        observation=obs,
        decision=decision,
        reviewer_reference="reviewer",
        reviewer_note="Professional reviewer note.",
        reviewed_at_utc=at,
        existing_events=existing,
        active_authority_loader=loader,
    )


def test_publication_is_create_if_absent_and_idempotent(tmp_path):
    run, obs, loader = fixture_values()
    value = event(
        run,
        obs,
        loader,
        decision=ProfessionalReviewDecision.DEFER,
        at="2026-09-01T10:00:00Z",
    )
    first = publish_professional_review_event(event=value, root=tmp_path)
    second = publish_professional_review_event(event=value, root=tmp_path)
    assert first == second
    assert first.read_bytes() == second.read_bytes()
    assert load_professional_review_events(
        case_id=run.case_id,
        observation_id=obs.observation_id,
        root=tmp_path,
    ) == (value,)


def test_publication_extends_exact_event_chain(tmp_path):
    run, obs, loader = fixture_values()
    first = event(
        run,
        obs,
        loader,
        decision=ProfessionalReviewDecision.DEFER,
        at="2026-09-01T10:00:00Z",
    )
    publish_professional_review_event(event=first, root=tmp_path)

    second = event(
        run,
        obs,
        loader,
        decision=ProfessionalReviewDecision.ACCEPT_FOR_MAL1_CONSIDERATION,
        at="2026-09-01T10:01:00Z",
        existing=(first,),
    )
    publish_professional_review_event(event=second, root=tmp_path)

    assert load_professional_review_events(
        case_id=run.case_id,
        observation_id=obs.observation_id,
        root=tmp_path,
    ) == (first, second)


def test_publication_rejects_branching_chain(tmp_path):
    run, obs, loader = fixture_values()
    first = event(
        run,
        obs,
        loader,
        decision=ProfessionalReviewDecision.DEFER,
        at="2026-09-01T10:00:00Z",
    )
    publish_professional_review_event(event=first, root=tmp_path)

    # This event was independently constructed as a new root.
    branch = event(
        run,
        obs,
        loader,
        decision=ProfessionalReviewDecision.REJECT,
        at="2026-09-01T10:02:00Z",
    )
    with pytest.raises(ProfessionalReviewPublicationError, match="extend"):
        publish_professional_review_event(event=branch, root=tmp_path)


def test_terminal_chain_cannot_be_extended(tmp_path):
    run, obs, loader = fixture_values()
    terminal = event(
        run,
        obs,
        loader,
        decision=ProfessionalReviewDecision.REJECT,
        at="2026-09-01T10:00:00Z",
    )
    publish_professional_review_event(event=terminal, root=tmp_path)

    # Core itself blocks this before publication.
    with pytest.raises(ProfessionalReviewError, match="terminal"):
        event(
            run,
            obs,
            loader,
            decision=ProfessionalReviewDecision.DEFER,
            at="2026-09-01T10:01:00Z",
            existing=(terminal,),
        )
