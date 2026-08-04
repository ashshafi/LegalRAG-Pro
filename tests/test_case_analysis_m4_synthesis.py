from __future__ import annotations

from dataclasses import replace

import pytest

from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.m2.matrices import CaseMatrices, build_case_matrices
from case_analysis.m3.chronology_serialization import dumps_case_chronology
from case_analysis.m3.models import CaseChronology
from case_analysis.m4.models import (
    AnalyticalBasis,
    ElementRef,
    FindingScope,
    FindingStatus,
    FindingType,
    IssuePositionStatus,
    OverallState,
    PropositionRef,
)
from case_analysis.m4.serialization import dumps_case_synthesis, loads_case_synthesis
from case_analysis.m4.synthesis import build_case_synthesis
from case_analysis.serialization import dumps_case_analysis_foundation
from case_analysis.m2.matrix_serialization import dumps_case_matrices
from case_analysis_m2_helpers import evidence, make_m5_result
from case_analysis_m4_helpers import synthetic_sources
from legal_analysis.enums import Confidence
from legal_analysis.evidence_assessment import AssessedProposition, PropositionAssessmentStatus
from legal_analysis.legal_analysis import ElementAnalysisStatus


CASE_ID = "22222222-2222-4222-8222-222222222222"
ISSUE_ANALYSIS_ID = "22222222-2222-4222-8222-222222222201"


def _empty_chronology(foundation) -> CaseChronology:
    return CaseChronology(
        case_id=foundation.case_id,
        synthesis_id=foundation.synthesis_id,
        source_analysis_ids=foundation.source_issue_analysis_ids,
        events=(),
    )


def _one_issue_sources(*, propositions: tuple[AssessedProposition, ...] | None = None, two_evidence: bool = False):
    evidence_items = (
        evidence(key="e1", document_name="one.pdf", page=1, summary="One factual source."),
        evidence(key="e2", document_name="two.pdf", page=2, summary="A second factual source."),
    ) if two_evidence else (
        evidence(key="e1", document_name="one.pdf", page=1, summary="One factual source."),
    )
    overrides = {"EK-INFORMATION": propositions} if propositions is not None else None
    result = make_m5_result(
        "EK-001",
        case_id=CASE_ID,
        issue_analysis_id=ISSUE_ANALYSIS_ID,
        evidence_by_element={"EK-INFORMATION": evidence_items},
        proposition_overrides=overrides,
    )
    foundation = build_case_analysis_foundation((result,))
    matrices = build_case_matrices(foundation, (result,))
    return foundation, matrices, _empty_chronology(foundation)


def _replace_element_state(
    matrices: CaseMatrices,
    *,
    statuses: tuple[ElementAnalysisStatus, ...] | None = None,
    confidences: tuple[Confidence, ...] | None = None,
) -> CaseMatrices:
    issue = matrices.issue_matrix[0]
    records = list(issue.element_records)
    if statuses is not None:
        if len(statuses) != len(records):
            raise AssertionError("statuses length must match element records")
        records = [replace(item, analysis_status=status) for item, status in zip(records, statuses)]
    if confidences is not None:
        if len(confidences) != len(records):
            raise AssertionError("confidences length must match element records")
        records = [replace(item, analysis_confidence=confidence) for item, confidence in zip(records, confidences)]
    return replace(matrices, issue_matrix=(replace(issue, element_records=tuple(records)),))


def _all_status(matrices: CaseMatrices, status: ElementAnalysisStatus) -> CaseMatrices:
    count = len(matrices.issue_matrix[0].element_records)
    return _replace_element_state(matrices, statuses=(status,) * count)


def _all_confidence(matrices: CaseMatrices, confidence: Confidence) -> CaseMatrices:
    count = len(matrices.issue_matrix[0].element_records)
    return _replace_element_state(matrices, confidences=(confidence,) * count)


def _proposition(status: PropositionAssessmentStatus, confidence: Confidence = Confidence.MEDIUM, *, evidence_keys=("e1",)) -> AssessedProposition:
    return AssessedProposition(
        text="Synthetic factual proposition.",
        status=status,
        confidence=confidence,
        evidence_keys=tuple(evidence_keys),
        rationale="Synthetic proposition rationale.",
    )


@pytest.mark.parametrize(
    ("source_status", "expected"),
    [
        (ElementAnalysisStatus.WELL_SUPPORTED_ON_CURRENT_RECORD, IssuePositionStatus.WELL_SUPPORTED),
        (ElementAnalysisStatus.PARTIALLY_SUPPORTED, IssuePositionStatus.PARTIALLY_SUPPORTED),
        (ElementAnalysisStatus.UNRESOLVED, IssuePositionStatus.UNRESOLVED),
        (ElementAnalysisStatus.INSUFFICIENTLY_EVIDENCED, IssuePositionStatus.EVIDENCE_INCOMPLETE),
        (ElementAnalysisStatus.DISPUTED, IssuePositionStatus.MATERIALLY_DISPUTED),
    ],
)
def test_issue_position_status_maps_conservatively(source_status, expected):
    foundation, matrices, chronology = _one_issue_sources()
    matrices = _all_status(matrices, source_status)
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert synthesis.issue_positions[0].position_status is expected


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ((ElementAnalysisStatus.DISPUTED, ElementAnalysisStatus.INSUFFICIENTLY_EVIDENCED), IssuePositionStatus.MATERIALLY_DISPUTED),
        ((ElementAnalysisStatus.INSUFFICIENTLY_EVIDENCED, ElementAnalysisStatus.UNRESOLVED), IssuePositionStatus.EVIDENCE_INCOMPLETE),
        ((ElementAnalysisStatus.UNRESOLVED, ElementAnalysisStatus.PARTIALLY_SUPPORTED), IssuePositionStatus.UNRESOLVED),
        ((ElementAnalysisStatus.PARTIALLY_SUPPORTED, ElementAnalysisStatus.WELL_SUPPORTED_ON_CURRENT_RECORD), IssuePositionStatus.PARTIALLY_SUPPORTED),
    ],
)
def test_issue_position_status_precedence(statuses, expected):
    foundation, matrices, chronology = _one_issue_sources()
    records = matrices.issue_matrix[0].element_records
    assigned = tuple(statuses[index] if index < len(statuses) else ElementAnalysisStatus.WELL_SUPPORTED_ON_CURRENT_RECORD for index in range(len(records)))
    matrices = _replace_element_state(matrices, statuses=assigned)
    assert build_case_synthesis(foundation, matrices, chronology).issue_positions[0].position_status is expected


@pytest.mark.parametrize(
    ("confidences", "expected"),
    [
        ((Confidence.HIGH,), Confidence.HIGH),
        ((Confidence.HIGH, Confidence.MEDIUM), Confidence.MEDIUM),
        ((Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW), Confidence.LOW),
    ],
)
def test_issue_position_confidence_is_weakest_material_element(confidences, expected):
    foundation, matrices, chronology = _one_issue_sources()
    records = matrices.issue_matrix[0].element_records
    assigned = tuple(confidences[index] if index < len(confidences) else Confidence.HIGH for index in range(len(records)))
    matrices = _replace_element_state(matrices, confidences=assigned)
    assert build_case_synthesis(foundation, matrices, chronology).issue_positions[0].confidence is expected


@pytest.mark.parametrize(
    ("source_status", "finding_type", "basis", "finding_status"),
    [
        (
            PropositionAssessmentStatus.ESTABLISHED_BY_CURRENT_EVIDENCE,
            FindingType.SUPPORTING_FEATURE,
            AnalyticalBasis.ESTABLISHED_PROPOSITION,
            FindingStatus.ESTABLISHED_BY_FROZEN_STATE,
        ),
        (
            PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
            FindingType.SUPPORTING_FEATURE,
            AnalyticalBasis.SUPPORTED_PROPOSITION,
            FindingStatus.SUPPORTED_BY_FROZEN_STATE,
        ),
        (
            PropositionAssessmentStatus.DISPUTED,
            FindingType.LIMITING_FEATURE,
            AnalyticalBasis.DISPUTED_PROPOSITION,
            FindingStatus.DISPUTED_IN_FROZEN_STATE,
        ),
        (
            PropositionAssessmentStatus.UNRESOLVED,
            FindingType.LIMITING_FEATURE,
            AnalyticalBasis.UNRESOLVED_PROPOSITION,
            FindingStatus.UNRESOLVED_IN_FROZEN_STATE,
        ),
    ],
)
def test_proposition_status_maps_to_exact_direct_finding(source_status, finding_type, basis, finding_status):
    foundation, matrices, chronology = _one_issue_sources(propositions=(_proposition(source_status),))
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    proposition_findings = [item for item in synthesis.findings if any(isinstance(ref.target, PropositionRef) for ref in item.provenance_refs)]
    assert len(proposition_findings) == 1
    finding = proposition_findings[0]
    assert finding.finding_type is finding_type
    assert finding.scope is FindingScope.ELEMENT
    assert finding.analytical_bases == (basis,)
    assert finding.status is finding_status
    assert finding.confidence is Confidence.MEDIUM
    assert _proposition(source_status).text in finding.summary


def test_not_supported_proposition_is_not_translated_into_an_m4_finding():
    foundation, matrices, chronology = _one_issue_sources(
        propositions=(_proposition(PropositionAssessmentStatus.NOT_SUPPORTED_BY_CURRENT_EVIDENCE),)
    )
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert not any(
        isinstance(ref.target, PropositionRef)
        for finding in synthesis.findings
        for ref in finding.provenance_refs
    )
    assert all(AnalyticalBasis.UNRESOLVED_PROPOSITION not in item.analytical_bases for item in synthesis.findings)


def test_proposition_finding_preserves_exact_source_confidence_without_accumulation():
    foundation, matrices, chronology = _one_issue_sources(
        propositions=(_proposition(PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED, Confidence.LOW),)
    )
    finding = next(item for item in build_case_synthesis(foundation, matrices, chronology).findings if AnalyticalBasis.SUPPORTED_PROPOSITION in item.analytical_bases)
    assert finding.confidence is Confidence.LOW


def test_same_element_proposition_across_two_evidence_uses_becomes_one_finding_with_two_exact_refs():
    proposition = _proposition(
        PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
        evidence_keys=("e1", "e2"),
    )
    foundation, matrices, chronology = _one_issue_sources(propositions=(proposition,), two_evidence=True)
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    findings = [item for item in synthesis.findings if AnalyticalBasis.SUPPORTED_PROPOSITION in item.analytical_bases]
    assert len(findings) == 1
    refs = tuple(ref.target for ref in findings[0].provenance_refs)
    assert len(refs) == 2
    assert all(isinstance(ref, PropositionRef) for ref in refs)
    assert {ref.evidence_use_ref.evidence_key for ref in refs} == {"e1", "e2"}
    assert {ref.source_proposition_index for ref in refs} == {0}


def test_inconsistent_same_family_payload_fails_closed():
    proposition = _proposition(
        PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
        evidence_keys=("e1", "e2"),
    )
    foundation, matrices, chronology = _one_issue_sources(propositions=(proposition,), two_evidence=True)
    records = list(matrices.evidence_matrix)
    second = records[1]
    use = second.uses[0]
    link = replace(use.proposition_links[0], text="Different proposition text.")
    records[1] = replace(second, uses=(replace(use, proposition_links=(link,)),))
    corrupted = replace(matrices, evidence_matrix=tuple(records))
    with pytest.raises(ValueError, match="proposition family is inconsistent"):
        build_case_synthesis(foundation, corrupted, chronology)


def test_insufficient_element_creates_one_element_limiting_finding_not_gap():
    foundation, matrices, chronology = _one_issue_sources()
    issue = matrices.issue_matrix[0]
    target = issue.element_records[0]
    records = tuple(
        replace(item, analysis_status=ElementAnalysisStatus.INSUFFICIENTLY_EVIDENCED)
        if item.element_id == target.element_id
        else replace(item, analysis_status=ElementAnalysisStatus.WELL_SUPPORTED_ON_CURRENT_RECORD)
        for item in issue.element_records
    )
    matrices = replace(matrices, issue_matrix=(replace(issue, element_records=records),))
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    matches = [item for item in synthesis.findings if AnalyticalBasis.INSUFFICIENT_EVIDENCE in item.analytical_bases]
    assert len(matches) == 1
    assert matches[0].finding_type is FindingType.LIMITING_FEATURE
    assert matches[0].status is FindingStatus.UNRESOLVED_IN_FROZEN_STATE
    assert isinstance(matches[0].provenance_refs[0].target, ElementRef)
    assert matches[0].provenance_refs[0].target.element_id == target.element_id
    assert synthesis.gaps == ()


def test_unresolved_element_does_not_invent_required_element_finding():
    foundation, matrices, chronology = _one_issue_sources()
    matrices = _all_status(matrices, ElementAnalysisStatus.UNRESOLVED)
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert all(AnalyticalBasis.UNRESOLVED_REQUIRED_ELEMENT not in finding.analytical_bases for finding in synthesis.findings)


def test_issue_position_basis_is_every_exact_element_ref():
    foundation, matrices, chronology = _one_issue_sources()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    position = synthesis.issue_positions[0]
    expected = {item.element_id for item in matrices.issue_matrix[0].element_records}
    actual = {ref.target.element_id for ref in position.basis_refs if isinstance(ref.target, ElementRef)}
    assert actual == expected
    assert len(position.basis_refs) == len(expected)


def test_issue_position_material_findings_never_cross_issue_boundary():
    foundation, matrices, chronology = synthetic_sources()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    finding_by_id = {item.finding_id: item for item in synthesis.findings}
    for position in synthesis.issue_positions:
        for finding_id in position.material_finding_ids:
            finding = finding_by_id[finding_id]
            issue_ids = set()
            for ref in finding.provenance_refs:
                target = ref.target
                if isinstance(target, PropositionRef):
                    issue_ids.add(target.evidence_use_ref.issue_analysis_id)
                elif isinstance(target, ElementRef):
                    issue_ids.add(target.issue_analysis_id)
            assert issue_ids == {position.issue_analysis_id}


def test_m42_keeps_all_deferred_collections_empty_and_cross_issue_findings_absent():
    foundation, matrices, chronology = synthetic_sources()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert synthesis.conflicts == ()
    assert synthesis.gaps == ()
    assert synthesis.risks == ()
    assert synthesis.priority_questions == ()
    assert all(item.finding_type is not FindingType.CROSS_ISSUE_FEATURE for item in synthesis.findings)
    assert all(item.scope is FindingScope.ELEMENT for item in synthesis.findings)
    for position in synthesis.issue_positions:
        assert position.conflict_ids == ()
        assert position.gap_ids == ()
        assert position.risk_ids == ()


@pytest.mark.parametrize(
    ("issue_status", "expected"),
    [
        (ElementAnalysisStatus.WELL_SUPPORTED_ON_CURRENT_RECORD, OverallState.WELL_DEVELOPED),
        (ElementAnalysisStatus.PARTIALLY_SUPPORTED, OverallState.PARTIALLY_DEVELOPED),
        (ElementAnalysisStatus.UNRESOLVED, OverallState.PARTIALLY_DEVELOPED),
        (ElementAnalysisStatus.INSUFFICIENTLY_EVIDENCED, OverallState.EVIDENCE_INCOMPLETE),
        (ElementAnalysisStatus.DISPUTED, OverallState.MATERIALLY_DISPUTED),
    ],
)
def test_overall_state_derives_only_from_issue_positions(issue_status, expected):
    foundation, matrices, chronology = _one_issue_sources()
    matrices = _all_status(matrices, issue_status)
    assert build_case_synthesis(foundation, matrices, chronology).overall_state is expected


def test_same_inputs_produce_same_synthesis_child_ids_and_canonical_bytes():
    foundation, matrices, chronology = synthetic_sources()
    first = build_case_synthesis(foundation, matrices, chronology)
    second = build_case_synthesis(foundation, matrices, chronology)
    assert first.synthesis_id == second.synthesis_id
    assert tuple(item.finding_id for item in first.findings) == tuple(item.finding_id for item in second.findings)
    assert first.issue_positions == second.issue_positions
    assert dumps_case_synthesis(first) == dumps_case_synthesis(second)


def test_case_synthesis_round_trip_is_identical():
    foundation, matrices, chronology = synthetic_sources()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    payload = dumps_case_synthesis(synthesis)
    restored = loads_case_synthesis(payload)
    assert restored == synthesis
    assert dumps_case_synthesis(restored) == payload


def test_source_objects_are_immutable_across_build_and_serialization():
    foundation, matrices, chronology = synthetic_sources()
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


def test_equivalent_reordered_issue_and_element_traversal_produces_same_semantic_order():
    foundation, matrices, chronology = synthetic_sources()
    first = build_case_synthesis(foundation, matrices, chronology)
    reversed_issues = tuple(
        replace(issue, element_records=tuple(reversed(issue.element_records)))
        for issue in reversed(matrices.issue_matrix)
    )
    reordered = replace(matrices, issue_matrix=reversed_issues)
    second = build_case_synthesis(foundation, reordered, chronology)
    assert [(item.issue_definition_id, item.position_status, item.confidence) for item in first.issue_positions] == [
        (item.issue_definition_id, item.position_status, item.confidence) for item in second.issue_positions
    ]
    assert {(item.finding_type, item.analytical_bases, item.summary) for item in first.findings} == {
        (item.finding_type, item.analytical_bases, item.summary) for item in second.findings
    }
    # Exact source fingerprints intentionally distinguish differently ordered frozen artifacts.
    assert first.synthesis_id != second.synthesis_id


def test_builder_rejects_mixed_case_before_synthesis():
    foundation, matrices, chronology = synthetic_sources()
    chronology = replace(chronology, case_id="33333333-3333-4333-8333-333333333333")
    with pytest.raises(ValueError, match="case identities"):
        build_case_synthesis(foundation, matrices, chronology)


def test_builder_rejects_mixed_synthesis_before_synthesis():
    foundation, matrices, chronology = synthetic_sources()
    chronology = replace(chronology, synthesis_id="33333333-3333-4333-8333-333333333334")
    with pytest.raises(ValueError, match="M3 synthesis identity"):
        build_case_synthesis(foundation, matrices, chronology)


def test_builder_rejects_m3_source_set_mismatch_before_synthesis():
    foundation, matrices, chronology = synthetic_sources()
    chronology = replace(chronology, source_analysis_ids=(chronology.source_analysis_ids[0],))
    with pytest.raises(ValueError, match="M3 source-analysis set"):
        build_case_synthesis(foundation, matrices, chronology)


def test_builder_rejects_m3_assertion_that_no_longer_resolves_to_m2():
    foundation, matrices, chronology = synthetic_sources()
    event = chronology.events[0]
    assertion = event.assertions[0]
    broken_assertion = replace(assertion, evidence_key="missing-evidence-key")
    broken_assertions = (broken_assertion, *event.assertions[1:])
    broken_event = replace(
        event,
        assertions=broken_assertions,
        evidence_keys=tuple(dict.fromkeys(item.evidence_key for item in broken_assertions)),
    )
    broken_chronology = replace(chronology, events=(broken_event,))
    with pytest.raises(ValueError, match="does not resolve to frozen EvidenceUse"):
        build_case_synthesis(foundation, matrices, broken_chronology)


def test_summary_is_deterministic_templated_and_contains_exact_proposition_text():
    proposition = _proposition(PropositionAssessmentStatus.ESTABLISHED_BY_CURRENT_EVIDENCE)
    foundation, matrices, chronology = _one_issue_sources(propositions=(proposition,))
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    finding = next(item for item in synthesis.findings if AnalyticalBasis.ESTABLISHED_PROPOSITION in item.analytical_bases)
    assert finding.summary.endswith(f"the frozen proposition is established by the current evidence: {proposition.text}")


def test_existing_upstream_gap_and_dispute_ids_do_not_trigger_m43_outputs():
    foundation, matrices, chronology = synthetic_sources()
    assert any(element.evidential_gap_ids for issue in matrices.issue_matrix for element in issue.element_records)
    assert any(element.disputed_matter_ids for issue in matrices.issue_matrix for element in issue.element_records)
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert synthesis.gaps == ()
    assert synthesis.conflicts == ()


def test_m3_multi_issue_event_does_not_trigger_cross_issue_synthesis():
    foundation, matrices, chronology = synthetic_sources()
    assert any(len(event.related_issue_analysis_ids) > 1 for event in chronology.events)
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert not any(item.finding_type is FindingType.CROSS_ISSUE_FEATURE for item in synthesis.findings)


def test_builder_public_contract_returns_valid_case_synthesis_without_future_outputs():
    foundation, matrices, chronology = synthetic_sources()
    synthesis = build_case_synthesis(foundation, matrices, chronology)
    assert synthesis.case_id == foundation.case_id
    assert synthesis.source_lineage.foundation_synthesis_id == foundation.synthesis_id
    assert {item.issue_analysis_id for item in synthesis.issue_positions} == set(foundation.source_issue_analysis_ids)
    assert synthesis.conflicts == synthesis.gaps == synthesis.risks == synthesis.priority_questions == ()
