from __future__ import annotations

from dataclasses import replace

import pytest

from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.m2.matrices import CaseMatrices, build_case_matrices
from case_analysis.m3.event_extraction import assertion_id_for
from case_analysis.m3.event_identity import event_id_for
from case_analysis.m3.models import (
    CaseChronology,
    CaseEvent,
    DatePrecision,
    EventAssertion,
    EventStatus,
    PartialDate,
    TemporalExtent,
    TemporalKind,
    TimingStatus,
)
from case_analysis.m4.models import (
    ConflictType,
    ElementRef,
    EventAssertionRef,
    EvidentialGapRef,
    FindingStatus,
    FindingType,
    GapType,
    PropositionRef,
)
from case_analysis.m4.serialization import dumps_case_synthesis, loads_case_synthesis
from case_analysis.m4.synthesis import _derive_timing_conflicts, build_case_synthesis
from case_analysis.m2.matrix_serialization import dumps_case_matrices
from case_analysis.m3.chronology_serialization import dumps_case_chronology
from case_analysis.serialization import dumps_case_analysis_foundation
from case_analysis_m2_helpers import evidence, make_m5_result
from case_analysis_m4_helpers import synthetic_sources
from legal_analysis.enums import AnalyticalRole, Confidence, Materiality
from legal_analysis.evidence_assessment import AssessedProposition, PropositionAssessmentStatus
from legal_analysis.legal_analysis import ElementAnalysisStatus


CASE_ID = "44444444-4444-4444-8444-444444444444"
ISSUE_ANALYSIS_ID = "44444444-4444-4444-8444-444444444401"


def _extent(day: int) -> TemporalExtent:
    return TemporalExtent(
        kind=TemporalKind.POINT,
        start=PartialDate(2025, 9, day, DatePrecision.EXACT),
        original_text=f"{day} September 2025",
    )


def _one_issue_sources(
    *,
    proposition_status: PropositionAssessmentStatus = PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
    evidence_keys: tuple[str, ...] = ("e1",),
) -> tuple:
    evidence_items = tuple(
        evidence(
            key=key,
            document_name=f"{key}.pdf",
            page=index + 1,
            summary=f"Synthetic source {key}.",
        )
        for index, key in enumerate(evidence_keys)
    )
    proposition = AssessedProposition(
        text="Synthetic proposition requiring exact frozen treatment.",
        status=proposition_status,
        confidence=Confidence.MEDIUM,
        evidence_keys=evidence_keys,
        rationale="Synthetic proposition rationale.",
    )
    result = make_m5_result(
        "EK-001",
        case_id=CASE_ID,
        issue_analysis_id=ISSUE_ANALYSIS_ID,
        evidence_by_element={"EK-INFORMATION": evidence_items},
        proposition_overrides={"EK-INFORMATION": (proposition,)},
    )
    foundation = build_case_analysis_foundation((result,))
    matrices = build_case_matrices(foundation, (result,))
    chronology = CaseChronology(
        case_id=foundation.case_id,
        synthesis_id=foundation.synthesis_id,
        source_analysis_ids=foundation.source_issue_analysis_ids,
        events=(),
    )
    return foundation, matrices, chronology


def _element(matrices: CaseMatrices, element_id: str):
    return next(
        element
        for issue in matrices.issue_matrix
        for element in issue.element_records
        if element.element_id == element_id
    )


def _replace_element(matrices: CaseMatrices, element_id: str, **changes) -> CaseMatrices:
    issues = []
    for issue in matrices.issue_matrix:
        elements = tuple(
            replace(element, **changes) if element.element_id == element_id else element
            for element in issue.element_records
        )
        issues.append(replace(issue, element_records=elements))
    return replace(matrices, issue_matrix=tuple(issues))


def _timing_conflict_chronology(*, reverse_assertions: bool = False):
    foundation, matrices, chronology = synthetic_sources()
    event = chronology.events[0]
    assert len(event.assertions) == 2
    first, second = event.assertions
    assertions = (
        replace(first, temporal_extent=_extent(4), timing_status=TimingStatus.ESTABLISHED),
        replace(second, temporal_extent=_extent(5), timing_status=TimingStatus.ESTABLISHED),
    )
    if reverse_assertions:
        assertions = tuple(reversed(assertions))
    disputed_event = replace(
        event,
        assertions=assertions,
        timing_status=TimingStatus.DISPUTED,
        canonical_temporal_extent=None,
    )
    return foundation, matrices, replace(chronology, events=(disputed_event,))


def _single_disputed_timing_chronology():
    foundation, matrices, chronology = synthetic_sources()
    event = chronology.events[0]
    source = event.assertions[0]
    assertion = replace(
        source,
        timing_status=TimingStatus.DISPUTED,
        temporal_extent=_extent(4),
    )
    new_event_id = event_id_for(
        foundation.case_id,
        event.event_type.value,
        event.normalized_event_core,
        (assertion.assertion_id,),
    )
    event = replace(
        event,
        event_id=new_event_id,
        assertions=(assertion,),
        evidence_keys=(assertion.evidence_key,),
        related_issue_analysis_ids=(assertion.issue_analysis_id,),
        related_issue_definition_ids=(assertion.issue_definition_id,),
        related_element_ids=(assertion.element_id,),
        timing_status=TimingStatus.DISPUTED,
        canonical_temporal_extent=None,
    )
    return foundation, matrices, replace(chronology, events=(event,))


def _unknown_timing_chronology():
    foundation, matrices, chronology = synthetic_sources()
    event = chronology.events[0]
    assertions = tuple(
        replace(item, temporal_extent=None, timing_status=TimingStatus.UNKNOWN)
        for item in event.assertions
    )
    event = replace(
        event,
        assertions=assertions,
        timing_status=TimingStatus.UNKNOWN,
        canonical_temporal_extent=None,
    )
    return foundation, matrices, replace(chronology, events=(event,))


def _three_way_timing_conflict_sources():
    foundation, matrices, chronology = _timing_conflict_chronology()
    event = chronology.events[0]
    source = event.assertions[0]
    use = next(
        use
        for record in matrices.evidence_matrix
        for use in record.uses
        if use.identity == (source.issue_analysis_id, source.element_id, source.evidence_key)
    )
    link = next(
        link
        for link in use.proposition_links
        if link.source_proposition_index == source.source_proposition_index
    )
    third = replace(
        source,
        assertion_id=assertion_id_for(use, link, 1),
        extraction_ordinal=1,
        temporal_extent=_extent(6),
        timing_status=TimingStatus.ESTABLISHED,
    )
    assertions = (*event.assertions, third)
    event = replace(
        event,
        event_id=event_id_for(
            foundation.case_id,
            event.event_type.value,
            event.normalized_event_core,
            tuple(item.assertion_id for item in assertions),
        ),
        assertions=assertions,
        timing_status=TimingStatus.DISPUTED,
        canonical_temporal_extent=None,
    )
    return foundation, matrices, replace(chronology, events=(event,))


def test_zero_evidence_uses_produces_exactly_missing_evidence_for_element():
    foundation, matrices, chronology = synthetic_sources()
    target = next(
        element
        for issue in matrices.issue_matrix
        for element in issue.element_records
        if not any(
            use.issue_analysis_id == issue.issue_analysis_id and use.element_id == element.element_id
            for record in matrices.evidence_matrix
            for use in record.uses
        )
    )
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    gaps = [item for item in synthesis.gaps if item.element_id == target.element_id]
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap.gap_type is GapType.MISSING_EVIDENCE
    assert gap.materiality is Materiality.MEDIUM
    assert gap.unresolved_question == target.legal_question
    assert any(isinstance(ref.target, ElementRef) for ref in gap.provenance_refs)


def test_zero_evidence_uses_does_not_also_produce_insufficient_or_unresolved_gap():
    foundation, matrices, chronology = synthetic_sources()
    target = next(
        element
        for issue in matrices.issue_matrix
        for element in issue.element_records
        if not any(use.element_id == element.element_id and use.issue_analysis_id == issue.issue_analysis_id for record in matrices.evidence_matrix for use in record.uses)
    )
    gaps = [item for item in build_case_synthesis(foundation, matrices, chronology).gaps if item.element_id == target.element_id]
    assert {item.gap_type for item in gaps} == {GapType.MISSING_EVIDENCE}


def test_existing_use_plus_insufficient_status_produces_exactly_one_insufficient_gap():
    foundation, matrices, chronology = synthetic_sources()
    target = _element(matrices, "EK-INFORMATION")
    matrices = _replace_element(
        matrices,
        target.element_id,
        analysis_status=ElementAnalysisStatus.INSUFFICIENTLY_EVIDENCED,
    )
    gaps = [item for item in build_case_synthesis(foundation, matrices, chronology).gaps if item.element_id == target.element_id]
    assert len(gaps) == 1
    assert gaps[0].gap_type is GapType.INSUFFICIENT_EVIDENCE
    assert gaps[0].materiality is Materiality.MEDIUM
    assert gaps[0].unresolved_question == target.legal_question


def test_element_level_insufficient_gap_suppresses_unresolved_proposition_gap():
    foundation, matrices, chronology = _one_issue_sources(
        proposition_status=PropositionAssessmentStatus.UNRESOLVED,
        evidence_keys=("e1", "e2"),
    )
    matrices = _replace_element(
        matrices,
        "EK-INFORMATION",
        analysis_status=ElementAnalysisStatus.INSUFFICIENTLY_EVIDENCED,
    )
    gaps = [item for item in build_case_synthesis(foundation, matrices, chronology).gaps if item.element_id == "EK-INFORMATION"]
    assert [item.gap_type for item in gaps] == [GapType.INSUFFICIENT_EVIDENCE]


def test_unresolved_proposition_family_becomes_one_gap_with_all_exact_refs():
    foundation, matrices, chronology = _one_issue_sources(
        proposition_status=PropositionAssessmentStatus.UNRESOLVED,
        evidence_keys=("e1", "e2"),
    )
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    gaps = [item for item in synthesis.gaps if item.element_id == "EK-INFORMATION"]
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap.gap_type is GapType.UNRESOLVED_PROPOSITION
    refs = [ref.target for ref in gap.provenance_refs]
    assert len(refs) == 2
    assert all(isinstance(ref, PropositionRef) for ref in refs)
    assert {ref.evidence_use_ref.evidence_key for ref in refs} == {"e1", "e2"}
    assert {ref.source_proposition_index for ref in refs} == {0}


def test_repeated_evidence_uses_do_not_duplicate_unresolved_proposition_gap():
    foundation, matrices, chronology = _one_issue_sources(
        proposition_status=PropositionAssessmentStatus.UNRESOLVED,
        evidence_keys=("e1", "e2"),
    )
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert sum(item.gap_type is GapType.UNRESOLVED_PROPOSITION and item.element_id == "EK-INFORMATION" for item in synthesis.gaps) == 1


def test_not_supported_proposition_is_not_mistranslated_into_gap():
    foundation, matrices, chronology = _one_issue_sources(
        proposition_status=PropositionAssessmentStatus.NOT_SUPPORTED_BY_CURRENT_EVIDENCE,
    )
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert not any(item.element_id == "EK-INFORMATION" for item in synthesis.gaps)


def test_upstream_gap_refs_are_only_supplemental_to_independent_element_gap():
    foundation, matrices, chronology = synthetic_sources()
    matrices = _replace_element(
        matrices,
        "EK-INFORMATION",
        analysis_status=ElementAnalysisStatus.INSUFFICIENTLY_EVIDENCED,
    )
    gap = next(item for item in build_case_synthesis(foundation, matrices, chronology).gaps if item.element_id == "EK-INFORMATION")
    assert gap.gap_type is GapType.INSUFFICIENT_EVIDENCE
    assert any(isinstance(ref.target, EvidentialGapRef) for ref in gap.provenance_refs)


def test_two_incompatible_retained_assertions_produce_one_timing_conflict():
    foundation, matrices, chronology = _timing_conflict_chronology()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert len(synthesis.conflicts) == 1
    conflict = synthesis.conflicts[0]
    assert conflict.conflict_type is ConflictType.TIMING_CONFLICT
    assert conflict.materiality is Materiality.MEDIUM
    assert conflict.status is FindingStatus.DISPUTED_IN_FROZEN_STATE
    assert conflict.subject == chronology.events[0].normalized_event_core
    assert all(isinstance(ref.target, EventAssertionRef) for ref in (*conflict.side_a_refs, *conflict.side_b_refs))
    assert len(conflict.side_a_refs) == len(conflict.side_b_refs) == 1
    assert set(conflict.related_issue_ids) == {item.issue_analysis_id for item in chronology.events[0].assertions}


def test_timing_conflict_is_linked_to_each_exact_related_issue_position():
    foundation, matrices, chronology = _timing_conflict_chronology()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    conflict = synthesis.conflicts[0]
    positions = {item.issue_analysis_id: item for item in synthesis.issue_positions}
    for issue_id in conflict.related_issue_ids:
        assert conflict.conflict_id in positions[issue_id].conflict_ids


def test_reversing_timing_assertion_traversal_preserves_conflict_identity_with_fixed_lineage():
    foundation, matrices, chronology = _timing_conflict_chronology()
    _, _, reversed_chronology = _timing_conflict_chronology(reverse_assertions=True)
    fixed_synthesis_id = build_case_synthesis(foundation, matrices, chronology).synthesis_id
    first = _derive_timing_conflicts(synthesis_id=fixed_synthesis_id, chronology=chronology)
    second = _derive_timing_conflicts(synthesis_id=fixed_synthesis_id, chronology=reversed_chronology)
    assert first == second
    assert first[0].conflict_id == second[0].conflict_id


def test_single_disputed_timing_assertion_does_not_manufacture_conflict():
    foundation, matrices, chronology = _single_disputed_timing_chronology()
    assert build_case_synthesis(foundation, matrices, chronology).conflicts == ()


def test_more_than_two_incompatible_retained_temporal_assertions_fails_closed():
    foundation, matrices, chronology = _three_way_timing_conflict_sources()
    with pytest.raises(ValueError, match="more than two incompatible retained temporal assertions"):
        build_case_synthesis(foundation, matrices, chronology)


def test_generic_disputed_proposition_does_not_generate_factual_conflict():
    foundation, matrices, chronology = _one_issue_sources(
        proposition_status=PropositionAssessmentStatus.DISPUTED,
    )
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert not any(item.conflict_type is ConflictType.FACTUAL_CONFLICT for item in synthesis.conflicts)
    assert synthesis.conflicts == ()


def test_conflicting_evidence_use_alone_does_not_generate_generic_conflict():
    foundation, matrices, chronology = synthetic_sources()
    records = []
    target_identity = None
    for record in matrices.evidence_matrix:
        uses = []
        for use in record.uses:
            if target_identity is None:
                target_identity = use.identity
                use = replace(use, analytical_role=AnalyticalRole.CONFLICTING)
            uses.append(use)
        records.append(replace(record, uses=tuple(uses)))
    matrices = replace(matrices, evidence_matrix=tuple(records))
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert target_identity is not None
    assert any(use.analytical_role is AnalyticalRole.CONFLICTING for record in matrices.evidence_matrix for use in record.uses)
    assert synthesis.conflicts == ()


def test_disputed_matter_id_alone_does_not_generate_generic_conflict():
    foundation, matrices, chronology = synthetic_sources()
    assert any(element.disputed_matter_ids for issue in matrices.issue_matrix for element in issue.element_records)
    assert build_case_synthesis(foundation, matrices, chronology).conflicts == ()


def test_unknown_event_timing_does_not_generate_missing_temporal_support():
    foundation, matrices, chronology = _unknown_timing_chronology()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert not any(item.gap_type is GapType.MISSING_TEMPORAL_SUPPORT for item in synthesis.gaps)
    assert synthesis.conflicts == ()


def test_unresolved_element_does_not_generate_unresolved_required_element_gap():
    foundation, matrices, chronology = synthetic_sources()
    matrices = _replace_element(
        matrices,
        "EK-INFORMATION",
        analysis_status=ElementAnalysisStatus.UNRESOLVED,
    )
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert not any(item.gap_type is GapType.UNRESOLVED_REQUIRED_ELEMENT for item in synthesis.gaps)


def test_single_source_does_not_generate_missing_corroboration():
    foundation, matrices, chronology = _one_issue_sources()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert not any(item.gap_type is GapType.MISSING_CORROBORATION for item in synthesis.gaps)


def test_only_authorised_gap_and_conflict_types_are_generated():
    foundation, matrices, chronology = _timing_conflict_chronology()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert {item.gap_type for item in synthesis.gaps}.issubset(
        {GapType.MISSING_EVIDENCE, GapType.INSUFFICIENT_EVIDENCE, GapType.UNRESOLVED_PROPOSITION}
    )
    assert {item.conflict_type for item in synthesis.conflicts}.issubset({ConflictType.TIMING_CONFLICT})


def test_m43_keeps_risks_priority_questions_and_cross_issue_findings_empty():
    foundation, matrices, chronology = _timing_conflict_chronology()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert synthesis.risks == ()
    assert synthesis.priority_questions == ()
    assert all(item.finding_type is not FindingType.CROSS_ISSUE_FEATURE for item in synthesis.findings)


def test_m43_generated_gaps_are_neutral_medium_and_reuse_exact_legal_question():
    foundation, matrices, chronology = synthetic_sources()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    elements = {
        (issue.issue_analysis_id, element.element_id): element
        for issue in matrices.issue_matrix
        for element in issue.element_records
    }
    assert synthesis.gaps
    for gap in synthesis.gaps:
        assert gap.materiality is Materiality.MEDIUM
        assert gap.unresolved_question == elements[(gap.issue_analysis_id, gap.element_id)].legal_question


def test_m43_same_inputs_same_children_serialization_and_round_trip():
    foundation, matrices, chronology = _timing_conflict_chronology()
    first = build_case_synthesis(foundation, matrices, chronology)
    second = build_case_synthesis(foundation, matrices, chronology)
    assert tuple(item.conflict_id for item in first.conflicts) == tuple(item.conflict_id for item in second.conflicts)
    assert tuple(item.gap_id for item in first.gaps) == tuple(item.gap_id for item in second.gaps)
    assert dumps_case_synthesis(first) == dumps_case_synthesis(second)
    payload = dumps_case_synthesis(first)
    restored = loads_case_synthesis(payload)
    assert restored == first
    assert dumps_case_synthesis(restored) == payload


def test_m43_source_foundation_matrices_and_chronology_remain_immutable():
    foundation, matrices, chronology = _timing_conflict_chronology()
    before = (
        dumps_case_analysis_foundation(foundation),
        dumps_case_matrices(matrices),
        dumps_case_chronology(chronology),
    )
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    dumps_case_synthesis(synthesis)
    after = (
        dumps_case_analysis_foundation(foundation),
        dumps_case_matrices(matrices),
        dumps_case_chronology(chronology),
    )
    assert after == before


def test_m43_preserves_m42_finding_issue_and_overall_semantics_while_only_linking_new_children():
    foundation, matrices, chronology = synthetic_sources()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    # Frozen M4.2 semantics remain under their original tests; M4.3 only populates
    # conflict/gap links on those immutable semantic issue positions.
    assert synthesis.synthesis_id
    assert synthesis.findings
    assert synthesis.overall_state
    gap_ids = {item.gap_id for item in synthesis.gaps}
    conflict_ids = {item.conflict_id for item in synthesis.conflicts}
    for position in synthesis.issue_positions:
        assert set(position.gap_ids).issubset(gap_ids)
        assert set(position.conflict_ids).issubset(conflict_ids)
        assert position.risk_ids == ()
