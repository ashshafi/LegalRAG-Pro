from __future__ import annotations

from dataclasses import replace

import pytest

from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.m2.matrices import CaseMatrices, build_case_matrices
from case_analysis.m2.matrix_serialization import dumps_case_matrices
from case_analysis.m3.chronology_serialization import dumps_case_chronology
from case_analysis.m3.models import CaseChronology
from case_analysis.m4.models import (
    AnalyticalBasis,
    ConflictType,
    EvidenceUseRef,
    FindingScope,
    FindingStatus,
    FindingType,
    PriorityBasis,
    PropositionRef,
    RiskType,
)
from case_analysis.m4.serialization import dumps_case_synthesis, loads_case_synthesis
from case_analysis.m4.synthesis import (
    _build_m44_semantic_core,
    _derive_m45_findings,
    _derive_single_source_dependency_findings,
    _eligible_single_source_parent,
    build_case_synthesis,
)
from case_analysis.serialization import dumps_case_analysis_foundation
from case_analysis_m2_helpers import evidence, make_m5_result
from case_analysis_m4_helpers import synthetic_sources
from legal_analysis.enums import AnalyticalRole, Confidence
from legal_analysis.evidence_assessment import AssessedProposition, PropositionAssessmentStatus


CASE_ID = "66666666-6666-4666-8666-666666666666"
ISSUE_ANALYSIS_ID = "66666666-6666-4666-8666-666666666601"


def _empty_chronology(foundation) -> CaseChronology:
    return CaseChronology(
        case_id=foundation.case_id,
        synthesis_id=foundation.synthesis_id,
        source_analysis_ids=foundation.source_issue_analysis_ids,
        events=(),
    )


def _proposition(
    text: str,
    status: PropositionAssessmentStatus,
    confidence: Confidence,
    evidence_keys: tuple[str, ...],
) -> AssessedProposition:
    return AssessedProposition(
        text=text,
        status=status,
        confidence=confidence,
        evidence_keys=evidence_keys,
        rationale=f"Synthetic rationale for {text}",
    )


def _one_issue_sources(
    *,
    propositions: tuple[AssessedProposition, ...],
    evidence_keys: tuple[str, ...] = ("e1",),
    role_overrides: dict[tuple[str, str], AnalyticalRole] | None = None,
):
    items = tuple(
        evidence(
            key=key,
            document_name=f"{key}.pdf",
            page=index + 1,
            summary=f"Synthetic source {key}.",
        )
        for index, key in enumerate(evidence_keys)
    )
    result = make_m5_result(
        "EK-001",
        case_id=CASE_ID,
        issue_analysis_id=ISSUE_ANALYSIS_ID,
        evidence_by_element={"EK-INFORMATION": items},
        proposition_overrides={"EK-INFORMATION": propositions},
        role_overrides=role_overrides,
    )
    foundation = build_case_analysis_foundation((result,))
    matrices = build_case_matrices(foundation, (result,))
    return foundation, matrices, _empty_chronology(foundation)


def _find_basis(synthesis, basis: AnalyticalBasis):
    return [item for item in synthesis.findings if item.analytical_bases == (basis,)]


def _support_parent(synthesis):
    return next(
        item
        for item in synthesis.findings
        if item.analytical_bases
        in {
            (AnalyticalBasis.ESTABLISHED_PROPOSITION,),
            (AnalyticalBasis.SUPPORTED_PROPOSITION,),
        }
    )


def test_multiple_supporting_propositions_means_two_distinct_families_not_two_uses():
    propositions = (
        _proposition(
            "First supporting proposition.",
            PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
            Confidence.MEDIUM,
            ("e1",),
        ),
        _proposition(
            "Second supporting proposition.",
            PropositionAssessmentStatus.ESTABLISHED_BY_CURRENT_EVIDENCE,
            Confidence.HIGH,
            ("e1",),
        ),
    )
    foundation, matrices, chronology = _one_issue_sources(propositions=propositions)
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    findings = _find_basis(synthesis, AnalyticalBasis.MULTIPLE_SUPPORTING_PROPOSITIONS)
    assert len(findings) == 1
    finding = findings[0]
    indexes = {
        ref.target.source_proposition_index
        for ref in finding.provenance_refs
        if isinstance(ref.target, PropositionRef)
    }
    assert indexes == {0, 1}
    assert finding.status is FindingStatus.SUPPORTED_BY_FROZEN_STATE
    assert finding.confidence is Confidence.MEDIUM


def test_one_proposition_family_across_two_evidence_uses_is_not_multiple_propositions():
    proposition = _proposition(
        "One shared proposition family.",
        PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
        Confidence.MEDIUM,
        ("e1", "e2"),
    )
    roles = {
        ("EK-INFORMATION", "e1"): AnalyticalRole.SUPPORTING,
        ("EK-INFORMATION", "e2"): AnalyticalRole.SUPPORTING,
    }
    foundation, matrices, chronology = _one_issue_sources(
        propositions=(proposition,), evidence_keys=("e1", "e2"), role_overrides=roles
    )
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert not _find_basis(synthesis, AnalyticalBasis.MULTIPLE_SUPPORTING_PROPOSITIONS)
    assert len(_find_basis(synthesis, AnalyticalBasis.CORROBORATED_EVIDENCE)) == 1


def test_corroborated_evidence_requires_one_family_and_two_distinct_canonical_evidence_keys():
    proposition = _proposition(
        "One proposition supported by two canonical sources.",
        PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
        Confidence.LOW,
        ("e1", "e2"),
    )
    roles = {
        ("EK-INFORMATION", "e1"): AnalyticalRole.SUPPORTING,
        ("EK-INFORMATION", "e2"): AnalyticalRole.CORROBORATIVE,
    }
    foundation, matrices, chronology = _one_issue_sources(
        propositions=(proposition,), evidence_keys=("e1", "e2"), role_overrides=roles
    )
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    findings = _find_basis(synthesis, AnalyticalBasis.CORROBORATED_EVIDENCE)
    assert len(findings) == 1
    finding = findings[0]
    refs = tuple(ref.target for ref in finding.provenance_refs)
    assert all(isinstance(ref, PropositionRef) for ref in refs)
    assert {ref.evidence_use_ref.evidence_key for ref in refs} == {"e1", "e2"}
    assert {ref.source_proposition_index for ref in refs} == {0}
    assert finding.status is FindingStatus.SUPPORTED_BY_FROZEN_STATE
    assert finding.confidence is Confidence.LOW


def test_corroborative_role_alone_without_second_canonical_source_does_not_create_corroborated_finding():
    proposition = _proposition(
        "Single-source proposition.",
        PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
        Confidence.MEDIUM,
        ("e1",),
    )
    foundation, matrices, chronology = _one_issue_sources(
        propositions=(proposition,),
        role_overrides={("EK-INFORMATION", "e1"): AnalyticalRole.CORROBORATIVE},
    )
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert not _find_basis(synthesis, AnalyticalBasis.CORROBORATED_EVIDENCE)


@pytest.mark.parametrize(
    ("role", "basis", "label"),
    [
        (AnalyticalRole.ADVERSE, AnalyticalBasis.ADVERSE_EVIDENCE, "adverse"),
        (AnalyticalRole.CONFLICTING, AnalyticalBasis.CONFLICTING_EVIDENCE, "conflicting"),
    ],
)
def test_frozen_adverse_and_conflicting_roles_produce_one_element_finding_with_exact_use_refs(
    role, basis, label
):
    proposition = _proposition(
        "Synthetic role proposition.",
        PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
        Confidence.MEDIUM,
        ("e1", "e2"),
    )
    roles = {
        ("EK-INFORMATION", "e1"): role,
        ("EK-INFORMATION", "e2"): role,
    }
    foundation, matrices, chronology = _one_issue_sources(
        propositions=(proposition,), evidence_keys=("e1", "e2"), role_overrides=roles
    )
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    findings = _find_basis(synthesis, basis)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.finding_type is FindingType.LIMITING_FEATURE
    assert finding.scope is FindingScope.ELEMENT
    assert finding.status is FindingStatus.ESTABLISHED_BY_FROZEN_STATE
    refs = tuple(ref.target for ref in finding.provenance_refs)
    assert all(isinstance(ref, EvidenceUseRef) for ref in refs)
    assert {ref.evidence_key for ref in refs} == {"e1", "e2"}
    assert label in finding.summary


def test_conflicting_evidence_role_does_not_reconstruct_generic_conflict_or_conflict_risk():
    proposition = _proposition(
        "Synthetic conflict-role proposition.",
        PropositionAssessmentStatus.DISPUTED,
        Confidence.MEDIUM,
        ("e1",),
    )
    foundation, matrices, chronology = _one_issue_sources(
        propositions=(proposition,),
        role_overrides={("EK-INFORMATION", "e1"): AnalyticalRole.CONFLICTING},
    )
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert len(_find_basis(synthesis, AnalyticalBasis.CONFLICTING_EVIDENCE)) == 1
    assert not any(
        item.conflict_type in {ConflictType.FACTUAL_CONFLICT, ConflictType.SOURCE_POSITION_CONFLICT}
        for item in synthesis.conflicts
    )
    assert not any(item.risk_type is RiskType.CONFLICT_RISK for item in synthesis.risks)


def test_same_canonical_evidence_across_two_issues_produces_one_structural_cross_issue_feature():
    foundation, matrices, chronology = synthetic_sources()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    findings = _find_basis(synthesis, AnalyticalBasis.CROSS_ISSUE_COVERAGE)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.finding_type is FindingType.CROSS_ISSUE_FEATURE
    assert finding.scope is FindingScope.CROSS_ISSUE
    refs = tuple(ref.target for ref in finding.provenance_refs)
    assert all(isinstance(ref, EvidenceUseRef) for ref in refs)
    assert {ref.evidence_key for ref in refs} == {"shared-event"}
    assert len({ref.issue_analysis_id for ref in refs}) == 2


def test_cross_issue_feature_does_not_create_dependency_risk_or_priority_question():
    foundation, matrices, chronology = synthetic_sources()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert _find_basis(synthesis, AnalyticalBasis.CROSS_ISSUE_COVERAGE)
    assert not any(item.risk_type is RiskType.CROSS_ISSUE_DEPENDENCY_RISK for item in synthesis.risks)
    assert not any(
        item.basis_type is PriorityBasis.CROSS_ISSUE_DEPENDENCY
        for item in synthesis.priority_questions
    )


def test_single_source_dependency_uses_only_exact_existing_direct_parent_and_keeps_parent_reference():
    proposition = _proposition(
        "Single-source supported proposition.",
        PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
        Confidence.MEDIUM,
        ("e1",),
    )
    foundation, matrices, chronology = _one_issue_sources(propositions=(proposition,))
    m44 = _build_m44_semantic_core(foundation, matrices, chronology)
    parent = _support_parent(m44)
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    findings = _find_basis(synthesis, AnalyticalBasis.DEPENDENCY_ON_SINGLE_EVIDENCE_SOURCE)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.related_finding_ids == (parent.finding_id,)
    assert finding.provenance_refs == parent.provenance_refs
    assert finding.status is parent.status
    assert finding.confidence is parent.confidence
    assert {
        ref.target.evidence_use_ref.evidence_key
        for ref in finding.provenance_refs
        if isinstance(ref.target, PropositionRef)
    } == {"e1"}


def test_multi_source_direct_parent_does_not_produce_single_source_dependency():
    proposition = _proposition(
        "Multi-source parent proposition.",
        PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
        Confidence.MEDIUM,
        ("e1", "e2"),
    )
    roles = {
        ("EK-INFORMATION", "e1"): AnalyticalRole.SUPPORTING,
        ("EK-INFORMATION", "e2"): AnalyticalRole.SUPPORTING,
    }
    foundation, matrices, chronology = _one_issue_sources(
        propositions=(proposition,), evidence_keys=("e1", "e2"), role_overrides=roles
    )
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert not _find_basis(synthesis, AnalyticalBasis.DEPENDENCY_ON_SINGLE_EVIDENCE_SOURCE)


def test_m45_aggregate_findings_are_structurally_ineligible_as_single_source_parents():
    propositions = (
        _proposition(
            "First proposition.",
            PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
            Confidence.MEDIUM,
            ("e1",),
        ),
        _proposition(
            "Second proposition.",
            PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
            Confidence.MEDIUM,
            ("e1",),
        ),
    )
    foundation, matrices, chronology = _one_issue_sources(propositions=propositions)
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    aggregates = [
        item
        for item in synthesis.findings
        if item.analytical_bases
        in {
            (AnalyticalBasis.MULTIPLE_SUPPORTING_PROPOSITIONS,),
            (AnalyticalBasis.DEPENDENCY_ON_SINGLE_EVIDENCE_SOURCE,),
        }
    ]
    assert aggregates
    assert all(not _eligible_single_source_parent(item) for item in aggregates)
    assert _derive_single_source_dependency_findings(
        synthesis_id=synthesis.synthesis_id,
        pre_m45_findings=tuple(aggregates),
        matrices=matrices,
    ) == ()


def test_deferred_and_blocked_analytical_bases_are_not_generated():
    foundation, matrices, chronology = synthetic_sources()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    present = {basis for finding in synthesis.findings for basis in finding.analytical_bases}
    prohibited = {
        AnalyticalBasis.CROSS_ELEMENT_COVERAGE,
        AnalyticalBasis.TEMPORAL_CONSISTENCY,
        AnalyticalBasis.TIMING_UNCERTAINTY,
        AnalyticalBasis.REQUIRED_ELEMENT_COVERAGE,
        AnalyticalBasis.LOW_CONFIDENCE_SUPPORT,
        AnalyticalBasis.MATERIAL_EVIDENCE_GAP,
        AnalyticalBasis.SOURCE_POSITION_CONFLICT,
        AnalyticalBasis.DEPENDENCY_ON_QUALIFIED_ASSERTION,
    }
    assert present.isdisjoint(prohibited)


def test_m45_preserves_complete_m44_semantic_core_and_issue_position_material_finding_ids():
    foundation, matrices, chronology = synthetic_sources()
    frozen_core = _build_m44_semantic_core(foundation, matrices, chronology)
    synthesis = build_case_synthesis(foundation, matrices, chronology)

    assert synthesis.synthesis_id == frozen_core.synthesis_id
    assert synthesis.overall_state is frozen_core.overall_state
    assert synthesis.conflicts == frozen_core.conflicts
    assert synthesis.gaps == frozen_core.gaps
    assert synthesis.risks == frozen_core.risks
    assert synthesis.priority_questions == frozen_core.priority_questions
    assert synthesis.issue_positions == frozen_core.issue_positions

    frozen_ids = {item.finding_id for item in frozen_core.findings}
    preserved = tuple(item for item in synthesis.findings if item.finding_id in frozen_ids)
    assert preserved == frozen_core.findings
    projected = replace(synthesis, findings=frozen_core.findings)
    assert dumps_case_synthesis(projected) == dumps_case_synthesis(frozen_core)

    new_ids = {item.finding_id for item in synthesis.findings} - frozen_ids
    assert new_ids
    assert all(
        not (set(position.material_finding_ids) & new_ids)
        for position in synthesis.issue_positions
    )


def test_same_inputs_same_m45_ids_serialization_and_exact_round_trip():
    foundation, matrices, chronology = synthetic_sources()
    first = build_case_synthesis(foundation, matrices, chronology)
    second = build_case_synthesis(foundation, matrices, chronology)
    assert tuple(item.finding_id for item in first.findings) == tuple(
        item.finding_id for item in second.findings
    )
    payload = dumps_case_synthesis(first)
    assert payload == dumps_case_synthesis(second)
    restored = loads_case_synthesis(payload)
    assert restored == first
    assert dumps_case_synthesis(restored) == payload


def test_m45_does_not_mutate_frozen_m1_m2_m3_sources():
    foundation, matrices, chronology = synthetic_sources()
    before = (
        dumps_case_analysis_foundation(foundation),
        dumps_case_matrices(matrices),
        dumps_case_chronology(chronology),
    )
    build_case_synthesis(foundation, matrices, chronology)
    after = (
        dumps_case_analysis_foundation(foundation),
        dumps_case_matrices(matrices),
        dumps_case_chronology(chronology),
    )
    assert after == before


def test_m45_helper_is_order_independent_for_equivalent_matrix_traversal_with_same_lineage_id():
    foundation, matrices, chronology = synthetic_sources()
    core = _build_m44_semantic_core(foundation, matrices, chronology)
    first = _derive_m45_findings(
        synthesis_id=core.synthesis_id,
        matrices=matrices,
        pre_m45_findings=core.findings,
    )
    reversed_records = tuple(
        replace(record, uses=tuple(reversed(record.uses)))
        for record in reversed(matrices.evidence_matrix)
    )
    reordered = replace(matrices, evidence_matrix=reversed_records)
    second = _derive_m45_findings(
        synthesis_id=core.synthesis_id,
        matrices=reordered,
        pre_m45_findings=core.findings,
    )
    assert first == second


def test_malformed_same_family_links_fail_closed_before_higher_order_derivation():
    proposition = _proposition(
        "Shared family.",
        PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
        Confidence.MEDIUM,
        ("e1", "e2"),
    )
    roles = {
        ("EK-INFORMATION", "e1"): AnalyticalRole.SUPPORTING,
        ("EK-INFORMATION", "e2"): AnalyticalRole.SUPPORTING,
    }
    foundation, matrices, chronology = _one_issue_sources(
        propositions=(proposition,), evidence_keys=("e1", "e2"), role_overrides=roles
    )
    record = next(item for item in matrices.evidence_matrix if item.evidence_key == "e2")
    use = record.uses[0]
    link = use.proposition_links[0]
    broken_use = replace(use, proposition_links=(replace(link, text="Inconsistent family text."),))
    broken_record = replace(record, uses=(broken_use,))
    broken = replace(
        matrices,
        evidence_matrix=tuple(
            broken_record if item.evidence_key == "e2" else item
            for item in matrices.evidence_matrix
        ),
    )
    with pytest.raises(ValueError, match="proposition family is inconsistent"):
        build_case_synthesis(foundation, broken, chronology)


def test_no_new_risk_or_priority_types_are_introduced_by_m45():
    foundation, matrices, chronology = synthetic_sources()
    frozen_core = _build_m44_semantic_core(foundation, matrices, chronology)
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert synthesis.risks == frozen_core.risks
    assert synthesis.priority_questions == frozen_core.priority_questions
    assert {item.risk_type for item in synthesis.risks}.issubset(
        {RiskType.EVIDENCE_RISK, RiskType.TIMING_RISK}
    )
    assert {item.basis_type for item in synthesis.priority_questions}.issubset(
        {PriorityBasis.MATERIAL_GAP}
    )
