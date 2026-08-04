from __future__ import annotations

from dataclasses import replace
import pytest

from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.m2.matrices import build_case_matrices
from case_analysis.m2.matrix_serialization import dumps_case_matrices
from case_analysis.m3.chronology_serialization import dumps_case_chronology
from case_analysis.m3.models import CaseChronology
from case_analysis.m4.models import (
    ConflictType,
    FindingScope,
    FindingStatus,
    MaterialConflict,
    PriorityBasis,
    PriorityLevel,
    RiskType,
)
from case_analysis.m4.serialization import dumps_case_synthesis, loads_case_synthesis
from case_analysis.m4.synthesis import (
    _build_m43_semantic_core,
    _derive_priority_questions,
    _derive_risks,
    build_case_synthesis,
)
from case_analysis.serialization import dumps_case_analysis_foundation
from case_analysis_m2_helpers import evidence, make_m5_result
from case_analysis_m4_helpers import synthetic_sources
from legal_analysis.enums import Confidence, Materiality
from legal_analysis.evidence_assessment import AssessedProposition, PropositionAssessmentStatus


CASE_ID = "55555555-5555-4555-8555-555555555555"
ISSUE_ANALYSIS_ID = "55555555-5555-4555-8555-555555555501"

def _empty_chronology(foundation) -> CaseChronology:
    return CaseChronology(
        case_id=foundation.case_id,
        synthesis_id=foundation.synthesis_id,
        source_analysis_ids=foundation.source_issue_analysis_ids,
        events=(),
    )


def _unresolved_sources(*, proposition_count: int = 1):
    item = evidence(
        key="e1",
        document_name="one.pdf",
        page=1,
        summary="Synthetic factual source.",
    )
    propositions = tuple(
        AssessedProposition(
            text=f"Synthetic unresolved proposition {index + 1}.",
            status=PropositionAssessmentStatus.UNRESOLVED,
            confidence=Confidence.MEDIUM,
            evidence_keys=("e1",),
            rationale="Synthetic unresolved proposition rationale.",
        )
        for index in range(proposition_count)
    )
    result = make_m5_result(
        "EK-001",
        case_id=CASE_ID,
        issue_analysis_id=ISSUE_ANALYSIS_ID,
        evidence_by_element={"EK-INFORMATION": (item,)},
        proposition_overrides={"EK-INFORMATION": propositions},
    )
    foundation = build_case_analysis_foundation((result,))
    matrices = build_case_matrices(foundation, (result,))
    return foundation, matrices, _empty_chronology(foundation)


def _timing_conflict_sources():
    # Reuse the frozen synthetic multi-issue event, then alter only retained
    # assertion timing in the same manner covered by the M4.3 contract tests.
    from case_analysis.m3.models import (
        DatePrecision,
        PartialDate,
        TemporalExtent,
        TemporalKind,
        TimingStatus,
    )

    foundation, matrices, chronology = synthetic_sources()
    event = chronology.events[0]
    first, second = event.assertions

    def extent(day: int) -> TemporalExtent:
        return TemporalExtent(
            kind=TemporalKind.POINT,
            start=PartialDate(2025, 9, day, DatePrecision.EXACT),
            original_text=f"{day} September 2025",
        )

    event = replace(
        event,
        assertions=(
            replace(first, temporal_extent=extent(4), timing_status=TimingStatus.ESTABLISHED),
            replace(second, temporal_extent=extent(5), timing_status=TimingStatus.ESTABLISHED),
        ),
        timing_status=TimingStatus.DISPUTED,
        canonical_temporal_extent=None,
    )
    return foundation, matrices, replace(chronology, events=(event,))


def _semantic_core(synthesis):
    return replace(
        synthesis,
        risks=(),
        priority_questions=(),
        issue_positions=tuple(replace(item, risk_ids=()) for item in synthesis.issue_positions),
    )


def test_each_exact_gap_produces_exactly_one_evidence_risk_with_same_materiality():
    foundation, matrices, chronology = synthetic_sources()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    evidence_risks = [item for item in synthesis.risks if item.risk_type is RiskType.EVIDENCE_RISK]
    assert len(evidence_risks) == len(synthesis.gaps)
    by_gap = {item.gap_ids[0]: item for item in evidence_risks}
    assert set(by_gap) == {item.gap_id for item in synthesis.gaps}
    for gap in synthesis.gaps:
        risk = by_gap[gap.gap_id]
        assert risk.gap_ids == (gap.gap_id,)
        assert risk.materiality is gap.materiality
        assert risk.affected_issue_ids == (gap.issue_analysis_id,)
        assert risk.conflict_ids == ()
        assert risk.basis_finding_ids == ()
        assert risk.description == f"Evidence risk: {gap.description}"


def test_two_distinct_gap_ids_never_collapse_into_one_evidence_risk():
    foundation, matrices, chronology = _unresolved_sources(proposition_count=2)
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    gaps = [item for item in synthesis.gaps if item.element_id == "EK-INFORMATION"]
    assert len(gaps) == 2
    risks = [item for item in synthesis.risks if item.gap_ids and item.gap_ids[0] in {gap.gap_id for gap in gaps}]
    assert len(risks) == 2
    assert len({item.risk_id for item in risks}) == 2


def test_one_timing_conflict_produces_exactly_one_timing_risk_and_no_conflict_risk():
    foundation, matrices, chronology = _timing_conflict_sources()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert len(synthesis.conflicts) == 1
    conflict = synthesis.conflicts[0]
    assert conflict.conflict_type is ConflictType.TIMING_CONFLICT
    timing_risks = [item for item in synthesis.risks if item.risk_type is RiskType.TIMING_RISK]
    assert len(timing_risks) == 1
    risk = timing_risks[0]
    assert risk.conflict_ids == (conflict.conflict_id,)
    assert risk.materiality is conflict.materiality
    assert risk.affected_issue_ids == conflict.related_issue_ids
    assert all(item.risk_type is not RiskType.CONFLICT_RISK for item in synthesis.risks)


def test_non_timing_material_conflict_is_rejected_by_m44_risk_derivation():
    foundation, matrices, chronology = synthetic_sources()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    conflict = MaterialConflict(
        conflict_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        conflict_type=ConflictType.FACTUAL_CONFLICT,
        scope=FindingScope.ISSUE,
        subject="Unsupported synthetic factual conflict.",
        side_a_refs=synthesis.findings[0].provenance_refs,
        side_b_refs=synthesis.findings[1].provenance_refs,
        materiality=Materiality.MEDIUM,
        status=FindingStatus.DISPUTED_IN_FROZEN_STATE,
        related_issue_ids=(synthesis.issue_positions[0].issue_analysis_id,),
    )
    with pytest.raises(ValueError, match="cannot classify non-timing"):
        _derive_risks(synthesis_id=synthesis.synthesis_id, gaps=(), conflicts=(conflict,))


def test_material_gap_question_reuses_exact_frozen_question_and_neutral_medium():
    foundation, matrices, chronology = synthetic_sources()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    question_by_coordinate = {
        (item.affected_issue_ids[0], item.affected_element_ids[0]): item
        for item in synthesis.priority_questions
    }
    grouped = {}
    for gap in synthesis.gaps:
        grouped.setdefault((gap.issue_analysis_id, gap.element_id), []).append(gap)
    assert set(question_by_coordinate) == set(grouped)
    for coordinate, gaps in grouped.items():
        question = question_by_coordinate[coordinate]
        assert question.basis_type is PriorityBasis.MATERIAL_GAP
        assert question.priority is PriorityLevel.MEDIUM
        assert question.question == gaps[0].unresolved_question
        assert question.gap_ids == tuple(sorted(item.gap_id for item in gaps))
        assert question.finding_ids == ()
        assert question.conflict_ids == ()


def test_two_unresolved_gaps_same_issue_element_group_into_one_question_with_all_gap_ids():
    foundation, matrices, chronology = _unresolved_sources(proposition_count=2)
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    target_gaps = [item for item in synthesis.gaps if item.element_id == "EK-INFORMATION"]
    assert len(target_gaps) == 2
    questions = [
        item
        for item in synthesis.priority_questions
        if item.affected_issue_ids == (ISSUE_ANALYSIS_ID,)
        and item.affected_element_ids == ("EK-INFORMATION",)
    ]
    assert len(questions) == 1
    assert questions[0].gap_ids == tuple(sorted(item.gap_id for item in target_gaps))
    assert questions[0].question == target_gaps[0].unresolved_question


def test_grouped_gaps_with_different_unresolved_questions_fail_closed():
    foundation, matrices, chronology = _unresolved_sources(proposition_count=2)
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    target_gaps = tuple(item for item in synthesis.gaps if item.element_id == "EK-INFORMATION")
    assert len(target_gaps) == 2
    malformed = (target_gaps[0], replace(target_gaps[1], unresolved_question="Different frozen question?"))
    with pytest.raises(ValueError, match="disagree on unresolved_question"):
        _derive_priority_questions(synthesis_id=synthesis.synthesis_id, gaps=malformed)


def test_same_question_text_on_different_element_coordinates_does_not_merge_questions():
    foundation, matrices, chronology = synthetic_sources()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    first, second = synthesis.gaps[:2]
    assert (first.issue_analysis_id, first.element_id) != (second.issue_analysis_id, second.element_id)
    common = "Exactly the same frozen question?"
    questions = _derive_priority_questions(
        synthesis_id=synthesis.synthesis_id,
        gaps=(replace(first, unresolved_question=common), replace(second, unresolved_question=common)),
    )
    assert len(questions) == 2
    assert {item.question for item in questions} == {common}


def test_all_generated_priority_questions_are_neutral_medium_only():
    foundation, matrices, chronology = synthetic_sources()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert synthesis.priority_questions
    assert {item.priority for item in synthesis.priority_questions} == {PriorityLevel.MEDIUM}
    assert all(item.priority is not PriorityLevel.HIGH for item in synthesis.priority_questions)
    assert all(item.priority is not PriorityLevel.LOW for item in synthesis.priority_questions)


def test_only_authorised_risk_types_and_priority_bases_are_generated():
    foundation, matrices, chronology = _timing_conflict_sources()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert {item.risk_type for item in synthesis.risks}.issubset(
        {RiskType.EVIDENCE_RISK, RiskType.TIMING_RISK}
    )
    assert {item.basis_type for item in synthesis.priority_questions}.issubset(
        {PriorityBasis.MATERIAL_GAP}
    )
    assert RiskType.CONFLICT_RISK not in {item.risk_type for item in synthesis.risks}
    assert RiskType.ELEMENT_COVERAGE_RISK not in {item.risk_type for item in synthesis.risks}
    assert RiskType.CROSS_ISSUE_DEPENDENCY_RISK not in {item.risk_type for item in synthesis.risks}
    assert PriorityBasis.REQUIRED_ELEMENT not in {item.basis_type for item in synthesis.priority_questions}
    assert PriorityBasis.MATERIAL_CONFLICT not in {item.basis_type for item in synthesis.priority_questions}
    assert PriorityBasis.TIMING_DEPENDENCY not in {item.basis_type for item in synthesis.priority_questions}
    assert PriorityBasis.CROSS_ISSUE_DEPENDENCY not in {item.basis_type for item in synthesis.priority_questions}


def test_issue_positions_link_exactly_the_risks_whose_affected_issue_set_contains_them():
    foundation, matrices, chronology = _timing_conflict_sources()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    expected = {}
    for risk in synthesis.risks:
        for issue_id in risk.affected_issue_ids:
            expected.setdefault(issue_id, set()).add(risk.risk_id)
    for position in synthesis.issue_positions:
        assert set(position.risk_ids) == expected.get(position.issue_analysis_id, set())


def test_m44_preserves_frozen_m43_semantic_core_byte_identically():
    foundation, matrices, chronology = synthetic_sources()
    frozen_core = _build_m43_semantic_core(foundation, matrices, chronology)
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    projected_core = _semantic_core(synthesis)
    assert dumps_case_synthesis(projected_core) == dumps_case_synthesis(frozen_core)


def test_m44_preserves_synthesis_findings_conflicts_gaps_and_overall_state_under_risk_question_projection():
    foundation, matrices, chronology = _timing_conflict_sources()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    core = _semantic_core(synthesis)
    assert synthesis.synthesis_id == core.synthesis_id
    assert synthesis.findings == core.findings
    assert synthesis.conflicts == core.conflicts
    assert synthesis.gaps == core.gaps
    assert synthesis.overall_state is core.overall_state
    for current, prior in zip(synthesis.issue_positions, core.issue_positions):
        assert current.issue_analysis_id == prior.issue_analysis_id
        assert current.position_status is prior.position_status
        assert current.confidence is prior.confidence
        assert current.material_finding_ids == prior.material_finding_ids
        assert current.conflict_ids == prior.conflict_ids
        assert current.gap_ids == prior.gap_ids


def test_same_inputs_produce_same_risk_question_ids_and_serialization_and_round_trip():
    foundation, matrices, chronology = _timing_conflict_sources()
    first = build_case_synthesis(foundation, matrices, chronology)
    second = build_case_synthesis(foundation, matrices, chronology)
    assert first.synthesis_id == second.synthesis_id
    assert tuple(item.risk_id for item in first.risks) == tuple(item.risk_id for item in second.risks)
    assert tuple(item.question_id for item in first.priority_questions) == tuple(
        item.question_id for item in second.priority_questions
    )
    payload = dumps_case_synthesis(first)
    assert payload == dumps_case_synthesis(second)
    restored = loads_case_synthesis(payload)
    assert restored == first
    assert dumps_case_synthesis(restored) == payload


def test_m44_builder_does_not_mutate_frozen_sources():
    foundation, matrices, chronology = _timing_conflict_sources()
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


def test_no_gap_and_no_conflict_produces_no_m44_outputs_at_helper_boundary():
    assert _derive_risks(synthesis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", gaps=(), conflicts=()) == ()
    assert _derive_priority_questions(synthesis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", gaps=()) == ()
