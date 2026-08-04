from dataclasses import replace

import pytest

from case_analysis.m4.identity import derive_finding_id
from case_analysis.m4.models import (
    AnalyticalBasis,
    EvidenceUseRef,
    EventRef,
    FindingScope,
    FindingStatus,
    FindingType,
    PropositionRef,
    SynthesisFinding,
    SynthesisProvenanceRef,
)
from case_analysis.m4.validation import validate_case_synthesis
from case_analysis_m4_helpers import make_case_synthesis
from legal_analysis.enums import Confidence


def _with_only_finding(synthesis, finding):
    positions = tuple(
        replace(
            item,
            material_finding_ids=(),
            conflict_ids=(),
            gap_ids=(),
            risk_ids=(),
        )
        for item in synthesis.issue_positions
    )
    return replace(
        synthesis,
        issue_positions=positions,
        findings=(finding,),
        conflicts=(),
        gaps=(),
        risks=(),
        priority_questions=(),
    )


def test_valid_synthetic_m4_state_resolves_entirely_against_frozen_m1_m2_m3():
    foundation, matrices, chronology, synthesis, _ = make_case_synthesis()
    validate_case_synthesis(synthesis, foundation=foundation, matrices=matrices, chronology=chronology)


def test_validation_fails_closed_on_m2_fingerprint_mismatch():
    foundation, matrices, chronology, synthesis, _ = make_case_synthesis()
    bad_lineage = replace(synthesis.source_lineage, source_matrices_sha256="0" * 64)
    bad = replace(synthesis, source_lineage=bad_lineage)
    with pytest.raises(ValueError, match="source_matrices_sha256"):
        validate_case_synthesis(bad, foundation=foundation, matrices=matrices, chronology=chronology)


def test_validation_fails_closed_on_m3_fingerprint_mismatch():
    foundation, matrices, chronology, synthesis, _ = make_case_synthesis()
    bad_lineage = replace(synthesis.source_lineage, source_chronology_sha256="0" * 64)
    bad = replace(synthesis, source_lineage=bad_lineage)
    with pytest.raises(ValueError, match="source_chronology_sha256"):
        validate_case_synthesis(bad, foundation=foundation, matrices=matrices, chronology=chronology)


def test_validation_resolves_exact_evidence_use_identity_not_evidence_key_alone():
    foundation, matrices, chronology, synthesis, refs = make_case_synthesis()
    original = refs["ek_use"].target
    bad_ref = SynthesisProvenanceRef(
        EvidenceUseRef(
            issue_analysis_id=original.issue_analysis_id,
            element_id="EK-RECIPIENT",
            evidence_key=original.evidence_key,
        )
    )
    finding = synthesis.findings[0]
    bad_id = derive_finding_id(
        synthesis_id=synthesis.synthesis_id,
        finding_type=finding.finding_type,
        scope=finding.scope,
        analytical_bases=finding.analytical_bases,
        provenance_refs=(bad_ref,),
    )
    bad_finding = replace(finding, finding_id=bad_id, provenance_refs=(bad_ref,))
    bad = _with_only_finding(synthesis, bad_finding)
    with pytest.raises(ValueError, match="Unknown frozen EvidenceUse"):
        validate_case_synthesis(bad, foundation=foundation, matrices=matrices, chronology=chronology)


def test_validation_resolves_proposition_by_evidence_use_plus_exact_source_index():
    foundation, matrices, chronology, synthesis, refs = make_case_synthesis()
    use_ref = refs["ek_use"].target
    bad_ref = SynthesisProvenanceRef(PropositionRef(use_ref, 99))
    finding = synthesis.findings[0]
    bad_id = derive_finding_id(
        synthesis_id=synthesis.synthesis_id,
        finding_type=finding.finding_type,
        scope=finding.scope,
        analytical_bases=finding.analytical_bases,
        provenance_refs=(bad_ref,),
    )
    bad_finding = replace(finding, finding_id=bad_id, provenance_refs=(bad_ref,))
    bad = _with_only_finding(synthesis, bad_finding)
    with pytest.raises(ValueError, match="Unknown frozen proposition coordinate"):
        validate_case_synthesis(bad, foundation=foundation, matrices=matrices, chronology=chronology)


def test_supported_proposition_cannot_be_upgraded_to_established_m4_finding():
    foundation, matrices, chronology, synthesis, _ = make_case_synthesis()
    bad_finding = replace(
        synthesis.findings[0],
        status=FindingStatus.ESTABLISHED_BY_FROZEN_STATE,
    )
    bad = _with_only_finding(synthesis, bad_finding)
    with pytest.raises(ValueError, match="exceeds frozen source ceiling"):
        validate_case_synthesis(bad, foundation=foundation, matrices=matrices, chronology=chronology)


def test_m4_confidence_cannot_exceed_frozen_proposition_confidence():
    foundation, matrices, chronology, synthesis, _ = make_case_synthesis()
    bad_finding = replace(synthesis.findings[0], confidence=Confidence.HIGH)
    bad = _with_only_finding(synthesis, bad_finding)
    with pytest.raises(ValueError, match="confidence .* exceeds frozen source ceiling"):
        validate_case_synthesis(bad, foundation=foundation, matrices=matrices, chronology=chronology)


def test_established_timing_does_not_upgrade_supported_event_occurrence():
    foundation, matrices, chronology, synthesis, refs = make_case_synthesis()
    event = chronology.events[0]
    assert event.event_status.value == "supported"
    assert event.timing_status.value == "established"
    event_ref = refs["event"]
    finding_id = derive_finding_id(
        synthesis_id=synthesis.synthesis_id,
        finding_type=FindingType.SUPPORTING_FEATURE,
        scope=FindingScope.CROSS_ISSUE,
        analytical_bases=(AnalyticalBasis.TEMPORAL_CONSISTENCY,),
        provenance_refs=(event_ref,),
    )
    bad_finding = SynthesisFinding(
        finding_id=finding_id,
        finding_type=FindingType.SUPPORTING_FEATURE,
        analytical_bases=(AnalyticalBasis.TEMPORAL_CONSISTENCY,),
        scope=FindingScope.CROSS_ISSUE,
        summary="Synthetic event whose timing is established but occurrence is supported.",
        status=FindingStatus.ESTABLISHED_BY_FROZEN_STATE,
        confidence=Confidence.MEDIUM,
        provenance_refs=(event_ref,),
    )
    bad = _with_only_finding(synthesis, bad_finding)
    with pytest.raises(ValueError, match="exceeds frozen source ceiling"):
        validate_case_synthesis(bad, foundation=foundation, matrices=matrices, chronology=chronology)


def test_identity_only_upstream_gap_and_dispute_refs_resolve_without_reopening_m5():
    foundation, matrices, chronology, synthesis, refs = make_case_synthesis()
    assert refs["upstream_gap"].target.gap_id
    assert refs["upstream_dispute"].target.disputed_matter_id
    validate_case_synthesis(synthesis, foundation=foundation, matrices=matrices, chronology=chronology)


def test_cross_issue_finding_requires_provenance_covering_at_least_two_frozen_issues():
    foundation, matrices, chronology, synthesis, refs = make_case_synthesis()
    event_ref = refs["event"]
    finding_id = derive_finding_id(
        synthesis_id=synthesis.synthesis_id,
        finding_type=FindingType.CROSS_ISSUE_FEATURE,
        scope=FindingScope.CROSS_ISSUE,
        analytical_bases=(AnalyticalBasis.CROSS_ISSUE_COVERAGE,),
        provenance_refs=(event_ref,),
    )
    finding = SynthesisFinding(
        finding_id=finding_id,
        finding_type=FindingType.CROSS_ISSUE_FEATURE,
        analytical_bases=(AnalyticalBasis.CROSS_ISSUE_COVERAGE,),
        scope=FindingScope.CROSS_ISSUE,
        summary="One frozen event spans both synthetic issues.",
        status=FindingStatus.SUPPORTED_BY_FROZEN_STATE,
        confidence=Confidence.MEDIUM,
        provenance_refs=(event_ref,),
    )
    good = _with_only_finding(synthesis, finding)
    validate_case_synthesis(good, foundation=foundation, matrices=matrices, chronology=chronology)


def test_every_m4_provenance_reference_type_resolves_against_native_frozen_state():
    foundation, matrices, chronology, synthesis, refs = make_case_synthesis()
    for ref in refs.values():
        finding_id = derive_finding_id(
            synthesis_id=synthesis.synthesis_id,
            finding_type=FindingType.LIMITING_FEATURE,
            scope=FindingScope.ELEMENT,
            analytical_bases=(AnalyticalBasis.INSUFFICIENT_EVIDENCE,),
            provenance_refs=(ref,),
        )
        finding = SynthesisFinding(
            finding_id=finding_id,
            finding_type=FindingType.LIMITING_FEATURE,
            analytical_bases=(AnalyticalBasis.INSUFFICIENT_EVIDENCE,),
            scope=FindingScope.ELEMENT,
            summary=f"Synthetic provenance-resolution check for {ref.reference_type.value}.",
            status=FindingStatus.UNRESOLVED_IN_FROZEN_STATE,
            confidence=Confidence.LOW,
            provenance_refs=(ref,),
        )
        candidate = _with_only_finding(synthesis, finding)
        validate_case_synthesis(
            candidate,
            foundation=foundation,
            matrices=matrices,
            chronology=chronology,
        )


def test_lineage_source_analysis_set_mismatch_fails_closed():
    foundation, matrices, chronology, synthesis, _ = make_case_synthesis()
    bad_lineage = replace(
        synthesis.source_lineage,
        source_analysis_ids=(synthesis.source_lineage.source_analysis_ids[0],),
    )
    bad = replace(synthesis, source_lineage=bad_lineage)
    with pytest.raises(ValueError, match="source_analysis_ids"):
        validate_case_synthesis(bad, foundation=foundation, matrices=matrices, chronology=chronology)


def test_nondeterministic_finding_identity_fails_closed():
    foundation, matrices, chronology, synthesis, _ = make_case_synthesis()
    bad_finding = replace(
        synthesis.findings[0],
        finding_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    )
    bad = _with_only_finding(synthesis, bad_finding)
    with pytest.raises(ValueError, match="finding_id is not deterministic"):
        validate_case_synthesis(bad, foundation=foundation, matrices=matrices, chronology=chronology)


def test_unresolved_issue_state_cannot_support_an_established_finding():
    foundation, matrices, chronology, synthesis, refs = make_case_synthesis()
    issue_ref = refs["ek_issue"]
    finding_id = derive_finding_id(
        synthesis_id=synthesis.synthesis_id,
        finding_type=FindingType.SUPPORTING_FEATURE,
        scope=FindingScope.ISSUE,
        analytical_bases=(AnalyticalBasis.REQUIRED_ELEMENT_COVERAGE,),
        provenance_refs=(issue_ref,),
    )
    finding = SynthesisFinding(
        finding_id=finding_id,
        finding_type=FindingType.SUPPORTING_FEATURE,
        analytical_bases=(AnalyticalBasis.REQUIRED_ELEMENT_COVERAGE,),
        scope=FindingScope.ISSUE,
        summary="Synthetic issue-level finding that improperly upgrades unresolved source state.",
        status=FindingStatus.ESTABLISHED_BY_FROZEN_STATE,
        confidence=Confidence.LOW,
        provenance_refs=(issue_ref,),
    )
    bad = _with_only_finding(synthesis, finding)
    with pytest.raises(ValueError, match="exceeds frozen source ceiling"):
        validate_case_synthesis(bad, foundation=foundation, matrices=matrices, chronology=chronology)
