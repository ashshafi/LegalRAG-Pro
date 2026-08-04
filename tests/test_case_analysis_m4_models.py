from dataclasses import FrozenInstanceError

import pytest

from case_analysis.models import CASE_SYNTHESIS_SCHEMA_VERSION
from case_analysis.m4.models import (
    WHOLE_CASE_SYNTHESIS_SCHEMA_VERSION,
    AnalyticalBasis,
    DisputedMatterRef,
    EvidenceUseRef,
    EvidentialGapRef,
    FindingStatus,
    PriorityLevel,
    PropositionRef,
    SynthesisProvenanceType,
)
from case_analysis_m4_helpers import UPSTREAM_DISPUTE_ID, UPSTREAM_GAP_ID, make_case_synthesis
from legal_analysis.enums import Confidence, Materiality


def test_m4_schema_namespace_is_distinct_from_frozen_m1_schema():
    assert CASE_SYNTHESIS_SCHEMA_VERSION == "case-synthesis-schema/1.0"
    assert WHOLE_CASE_SYNTHESIS_SCHEMA_VERSION == "whole-case-synthesis-schema/1.0"
    assert WHOLE_CASE_SYNTHESIS_SCHEMA_VERSION != CASE_SYNTHESIS_SCHEMA_VERSION


def test_evidence_use_ref_reuses_exact_frozen_m2_identity():
    _, _, _, _, refs = make_case_synthesis()
    target = refs["ek_use"].target
    assert isinstance(target, EvidenceUseRef)
    assert target.identity == (target.issue_analysis_id, target.element_id, target.evidence_key)


def test_proposition_ref_is_exact_evidence_use_plus_source_index():
    _, _, _, _, refs = make_case_synthesis()
    target = refs["ek_prop"].target
    assert isinstance(target, PropositionRef)
    assert target.evidence_use_ref.identity == refs["ek_use"].target.identity
    assert target.source_proposition_index == 0


def test_upstream_gap_and_dispute_references_are_identity_only():
    _, _, _, _, refs = make_case_synthesis()
    gap = refs["upstream_gap"].target
    dispute = refs["upstream_dispute"].target
    assert isinstance(gap, EvidentialGapRef)
    assert isinstance(dispute, DisputedMatterRef)
    assert gap.gap_id == UPSTREAM_GAP_ID
    assert dispute.disputed_matter_id == UPSTREAM_DISPUTE_ID
    assert not hasattr(gap, "description")
    assert not hasattr(dispute, "claimant_position")


def test_provenance_type_vocabulary_includes_disputed_matter_exactly():
    assert {item.value for item in SynthesisProvenanceType} == {
        "issue",
        "element",
        "evidence_use",
        "proposition",
        "event",
        "event_assertion",
        "evidential_gap",
        "disputed_matter",
    }


def test_m4_reuses_native_confidence_and_materiality_enums():
    _, _, _, synthesis, _ = make_case_synthesis()
    assert isinstance(synthesis.findings[0].confidence, Confidence)
    assert isinstance(synthesis.gaps[0].materiality, Materiality)
    assert isinstance(synthesis.risks[0].materiality, Materiality)


def test_m4_durable_models_are_immutable():
    _, _, _, synthesis, _ = make_case_synthesis()
    with pytest.raises(FrozenInstanceError):
        synthesis.case_id = "22222222-2222-4222-8222-222222222222"


def test_contract_uses_precise_finding_language_not_strength_weakness_primitives():
    import case_analysis.m4.models as models

    assert not hasattr(models, "Strength")
    assert not hasattr(models, "Weakness")
    assert AnalyticalBasis.SUPPORTED_PROPOSITION.value == "supported_proposition"
    assert FindingStatus.SUPPORTED_BY_FROZEN_STATE.value == "supported_by_frozen_state"
    assert tuple(item.value for item in PriorityLevel) == ("low", "medium", "high")


def test_invalid_analytical_basis_fails_closed_with_value_error():
    _, _, _, synthesis, _ = make_case_synthesis()
    finding = synthesis.findings[0]
    with pytest.raises(ValueError, match="AnalyticalBasis"):
        type(finding)(
            finding_id=finding.finding_id,
            finding_type=finding.finding_type,
            analytical_bases=("supported_proposition",),
            scope=finding.scope,
            summary=finding.summary,
            status=finding.status,
            confidence=finding.confidence,
            provenance_refs=finding.provenance_refs,
        )
