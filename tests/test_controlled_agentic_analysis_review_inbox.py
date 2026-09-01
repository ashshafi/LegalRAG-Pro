from __future__ import annotations

from hashlib import sha256
import json
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
from controlled_agentic_analysis_gaps import (
    CAA2AnalysisResult,
    GapAgentObservation,
    GapCandidate,
    GapObservationType,
)
from controlled_agentic_analysis_gaps_publication import (
    publish_caa2_analysis,
)
from controlled_agentic_analysis_publication import publish_caa1_run
from controlled_agentic_analysis_review import (
    ObservationSource,
    ProfessionalReviewDecision,
    ProfessionalReviewState,
    review_agent_observation,
)
from controlled_agentic_analysis_review_inbox import (
    ProfessionalReviewInboxError,
    load_professional_review_inbox,
)
from controlled_agentic_analysis_review_publication import (
    publish_professional_review_event,
)


CASE = "case-1"
AUTH = "sha256:" + ("a" * 64)


def canonical_sha(value):
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + sha256(payload).hexdigest()


def refs():
    return (
        CAA1EvidenceRef(
            schema_version="controlled-agentic-analysis-evidence-ref/v1",
            case_id=CASE,
            evidence_key="E1",
            evidence_binding_sha256="sha256:" + ("b" * 64),
        ),
        CAA1EvidenceRef(
            schema_version="controlled-agentic-analysis-evidence-ref/v1",
            case_id=CASE,
            evidence_key="E2",
            evidence_binding_sha256="sha256:" + ("c" * 64),
        ),
    )


def frozen():
    return build_frozen_inspection_universe(
        case_id=CASE,
        active_authority_id=AUTH,
        evidence_bindings=refs(),
        agent_definition_version="test-agent/v1",
        analysis_engine_identity="test-engine/v1",
        execution_configuration={"mode": "test"},
    )


def loader(authority_id=AUTH):
    return lambda _: SimpleNamespace(
        manifest=SimpleNamespace(authority_id=authority_id)
    )


def caa1_observation(run):
    return build_agent_observation(
        run=run,
        observation_type=ObservationType.CONTRADICTION,
        title="Material contradiction",
        summary="Two frozen records conflict.",
        supporting_evidence_keys=("E1",),
        contrary_evidence_keys=("E2",),
        reasoning_summary="The propositions are materially incompatible.",
        materiality=Materiality.HIGH,
        observation_confidence=ObservationConfidence.MEDIUM,
        uncertainty="Professional assessment remains required.",
        limitations=("Frozen evidence only.",),
        recommended_action=RecommendedAction.PROFESSIONAL_REVIEW,
        issue_analysis_id="issue-1",
        element_id="element-1",
    )


def caa2_result(run):
    candidate_base = {
        "schema_version": "controlled-agentic-evidence-gap-candidate/v1",
        "case_id": CASE,
        "active_authority_id": AUTH,
        "analysis_run_id": run.analysis_run_id,
        "issue_analysis_id": "issue-1",
        "issue_definition_id": "definition-1",
        "element_id": "element-1",
        "gap_type": "unresolved_proposition",
        "legal_question": "What remains unresolved?",
        "finding_text": "A material proposition remains unresolved.",
        "related_evidence_keys": ["E1", "E2"],
        "governed_basis": "The frozen authority records an unresolved matter.",
        "requires_engine_confirmation": False,
    }
    candidate_id = canonical_sha(candidate_base)
    candidate = GapCandidate(
        candidate_id=candidate_id,
        gap_type=GapObservationType.UNRESOLVED_PROPOSITION,
        related_evidence_keys=("E1", "E2"),
        **{
            key: value
            for key, value in candidate_base.items()
            if key not in {"gap_type", "related_evidence_keys"}
        },
    )

    observation_base = {
        "schema_version": "controlled-agentic-evidence-gap-observation/v1",
        "candidate_id": candidate_id,
        "case_id": CASE,
        "active_authority_id": AUTH,
        "analysis_run_id": run.analysis_run_id,
        "issue_analysis_id": "issue-1",
        "element_id": "element-1",
        "observation_type": "unresolved_proposition",
        "title": "Unresolved governed proposition",
        "summary": "The frozen evidence leaves a material proposition unresolved.",
        "finding_text": "A material proposition remains unresolved.",
        "inspected_evidence_bindings": [
            {
                "schema_version": ref.schema_version,
                "case_id": ref.case_id,
                "evidence_key": ref.evidence_key,
                "evidence_binding_sha256": ref.evidence_binding_sha256,
            }
            for ref in run.evidence_bindings
        ],
        "reasoning_summary": "The controlled record contains material conflict.",
        "materiality": "high",
        "observation_confidence": "high",
        "uncertainty": "Credibility is not determined.",
        "limitations": ["No authority effect."],
        "recommended_action": "professional_review",
    }
    observation = GapAgentObservation(
        observation_id=canonical_sha(observation_base),
        candidate_id=candidate_id,
        observation_type=GapObservationType.UNRESOLVED_PROPOSITION,
        inspected_evidence_bindings=run.evidence_bindings,
        materiality=Materiality.HIGH,
        observation_confidence=ObservationConfidence.HIGH,
        recommended_action=RecommendedAction.PROFESSIONAL_REVIEW,
        **{
            key: value
            for key, value in observation_base.items()
            if key
            not in {
                "candidate_id",
                "observation_type",
                "inspected_evidence_bindings",
                "materiality",
                "observation_confidence",
                "recommended_action",
            }
        },
    )
    return CAA2AnalysisResult(
        run=run,
        candidates=(candidate,),
        observations=(observation,),
    )


def roots(tmp_path):
    return (
        tmp_path / "caa1",
        tmp_path / "caa2",
        tmp_path / "reviews",
    )


def test_inbox_loads_exact_caa1_and_caa2_publications(tmp_path):
    run = frozen()
    caa1_root, caa2_root, review_root = roots(tmp_path)

    publish_caa1_run(
        run=run,
        observations=(caa1_observation(run),),
        root=caa1_root,
        active_authority_loader=loader(),
    )
    publish_caa2_analysis(
        result=caa2_result(run),
        root=caa2_root,
        active_authority_loader=loader(),
    )

    items = load_professional_review_inbox(
        case_id=CASE,
        caa1_root=caa1_root,
        caa2_root=caa2_root,
        review_root=review_root,
    )

    assert len(items) == 2
    assert {item.source_agent for item in items} == {
        ObservationSource.CAA1,
        ObservationSource.CAA2,
    }
    assert all(item.review_events == () for item in items)
    assert all(item.review_projection is None for item in items)


def test_inbox_joins_append_only_prw1_review_state(tmp_path):
    run = frozen()
    caa1_root, caa2_root, review_root = roots(tmp_path)

    published = publish_caa1_run(
        run=run,
        observations=(caa1_observation(run),),
        root=caa1_root,
        active_authority_loader=loader(),
    )

    initial = load_professional_review_inbox(
        case_id=CASE,
        caa1_root=caa1_root,
        caa2_root=caa2_root,
        review_root=review_root,
    )
    item = initial[0]

    event = review_agent_observation(
        run=item.run,
        observation=item.observation,
        decision=ProfessionalReviewDecision.DEFER,
        reviewer_reference="reviewer-1",
        reviewer_note="Further evidence inspection required.",
        reviewed_at_utc="2026-09-01T12:00:00Z",
        active_authority_loader=loader(),
    )
    publish_professional_review_event(
        event=event,
        root=review_root,
    )

    reloaded = load_professional_review_inbox(
        case_id=CASE,
        caa1_root=caa1_root,
        caa2_root=caa2_root,
        review_root=review_root,
    )
    assert len(reloaded) == 1
    assert reloaded[0].publication_path == published.observation_paths[0]
    assert reloaded[0].review_events == (event,)
    assert (
        reloaded[0].review_projection.state
        is ProfessionalReviewState.DEFERRED
    )


def test_caa1_noncanonical_observation_bytes_fail_closed(tmp_path):
    run = frozen()
    caa1_root, caa2_root, review_root = roots(tmp_path)
    published = publish_caa1_run(
        run=run,
        observations=(caa1_observation(run),),
        root=caa1_root,
        active_authority_loader=loader(),
    )
    published.observation_paths[0].write_bytes(
        published.observation_paths[0].read_bytes() + b"\n"
    )

    with pytest.raises(
        ProfessionalReviewInboxError,
        match="canonical",
    ):
        load_professional_review_inbox(
            case_id=CASE,
            caa1_root=caa1_root,
            caa2_root=caa2_root,
            review_root=review_root,
        )


def test_caa2_manifest_observation_identity_mismatch_fails_closed(tmp_path):
    run = frozen()
    caa1_root, caa2_root, review_root = roots(tmp_path)
    published = publish_caa2_analysis(
        result=caa2_result(run),
        root=caa2_root,
        active_authority_loader=loader(),
    )
    manifest = json.loads(
        published.manifest_path.read_text(encoding="utf-8")
    )
    manifest["observation_ids"] = []
    published.manifest_path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ProfessionalReviewInboxError,
        match="observation identities",
    ):
        load_professional_review_inbox(
            case_id=CASE,
            caa1_root=caa1_root,
            caa2_root=caa2_root,
            review_root=review_root,
        )


def test_missing_publication_roots_return_empty_inbox(tmp_path):
    caa1_root, caa2_root, review_root = roots(tmp_path)
    assert (
        load_professional_review_inbox(
            case_id=CASE,
            caa1_root=caa1_root,
            caa2_root=caa2_root,
            review_root=review_root,
        )
        == ()
    )


@pytest.mark.parametrize(
    "case_id",
    ("", " ", "../case", "case/other", r"case\other"),
)
def test_unsafe_case_identity_fails_closed(tmp_path, case_id):
    caa1_root, caa2_root, review_root = roots(tmp_path)
    with pytest.raises(ProfessionalReviewInboxError):
        load_professional_review_inbox(
            case_id=case_id,
            caa1_root=caa1_root,
            caa2_root=caa2_root,
            review_root=review_root,
        )
