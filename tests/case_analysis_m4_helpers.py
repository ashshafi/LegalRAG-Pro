from __future__ import annotations

from dataclasses import replace
from datetime import date
from uuid import UUID

from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.m2.matrices import CaseMatrices, build_case_matrices
from case_analysis.m3.event_extraction import assertion_id_for
from case_analysis.m3.event_identity import group_assertions
from case_analysis.m3.models import (
    CaseChronology,
    DatePrecision,
    EventAssertion,
    EventStatus,
    EventType,
    ExtractionBasis,
    PartialDate,
    TemporalExtent,
    TemporalKind,
    TimingStatus,
)
from case_analysis.m4.identity import (
    derive_case_synthesis_id,
    derive_conflict_id,
    derive_finding_id,
    derive_gap_id,
    derive_priority_question_id,
    derive_risk_id,
    fingerprint_case_chronology,
    fingerprint_case_matrices,
)
from case_analysis.m4.models import (
    AnalyticalBasis,
    CaseSynthesis,
    ConflictType,
    DisputedMatterRef,
    ElementRef,
    EvidenceGap,
    EvidenceUseRef,
    EventAssertionRef,
    EventRef,
    EvidentialGapRef,
    FindingScope,
    FindingStatus,
    FindingType,
    GapType,
    IssuePosition,
    IssuePositionStatus,
    IssueRef,
    MaterialConflict,
    OverallState,
    PriorityBasis,
    PriorityLevel,
    PriorityQuestion,
    PropositionRef,
    RiskArea,
    RiskType,
    SynthesisFinding,
    SynthesisProvenanceRef,
    SynthesisSourceLineage,
)
from case_analysis_m2_helpers import evidence, make_m5_result
from legal_analysis.enums import Confidence, Materiality

CASE_ID = "11111111-1111-4111-8111-111111111111"
UPSTREAM_GAP_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
UPSTREAM_DISPUTE_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def synthetic_sources():
    shared = evidence(
        key="shared-event",
        document_name="shared.pdf",
        page=1,
        summary="On 4 September 2025 HR recorded a return-to-work communication.",
    )
    ek = make_m5_result(
        "EK-001",
        case_id=CASE_ID,
        evidence_by_element={"EK-INFORMATION": (shared,)},
        issue_analysis_id="11111111-1111-4111-8111-111111111101",
    )
    ra = make_m5_result(
        "RA-001",
        case_id=CASE_ID,
        evidence_by_element={"RA-KNOWLEDGE": (shared,)},
        issue_analysis_id="11111111-1111-4111-8111-111111111102",
    )
    results = (ek, ra)
    foundation = build_case_analysis_foundation(results)
    matrices = build_case_matrices(foundation, results)
    matrices = _inject_upstream_identity_only_refs(matrices)
    chronology = _chronology(foundation, matrices)
    return foundation, matrices, chronology


def _inject_upstream_identity_only_refs(matrices: CaseMatrices) -> CaseMatrices:
    issue_records = []
    for issue in matrices.issue_matrix:
        elements = []
        for element in issue.element_records:
            if issue.issue_definition_id == "EK-001" and element.element_id == "EK-INFORMATION":
                element = replace(
                    element,
                    evidential_gap_ids=(UPSTREAM_GAP_ID,),
                    disputed_matter_ids=(UPSTREAM_DISPUTE_ID,),
                )
            elements.append(element)
        issue_records.append(replace(issue, element_records=tuple(elements)))
    return replace(matrices, issue_matrix=tuple(issue_records))


def _chronology(foundation, matrices: CaseMatrices) -> CaseChronology:
    record = next(item for item in matrices.evidence_matrix if item.evidence_key == "shared-event")
    uses = tuple(sorted(record.uses, key=lambda item: item.identity))
    temporal = TemporalExtent(
        kind=TemporalKind.POINT,
        start=PartialDate(2025, 9, 4, DatePrecision.EXACT),
        original_text="4 September 2025",
    )
    assertions = []
    for use in uses:
        link = use.proposition_links[0]
        assertions.append(
            EventAssertion(
                assertion_id=assertion_id_for(use, link, 0),
                issue_analysis_id=use.issue_analysis_id,
                issue_definition_id=use.issue_definition_id,
                issue_definition_version=use.issue_definition_version,
                element_id=use.element_id,
                source_proposition_index=link.source_proposition_index,
                evidence_key=use.evidence_key,
                extraction_ordinal=0,
                description="HR recorded a return-to-work communication on 4 September 2025.",
                normalized_event_core="hr recorded return to work communication",
                event_type=EventType.COMMUNICATION,
                event_status=EventStatus.SUPPORTED,
                confidence=link.confidence,
                temporal_extent=temporal,
                timing_status=TimingStatus.ESTABLISHED,
                extraction_basis=ExtractionBasis.PROPOSITION_WITH_EVIDENCE_ENRICHMENT,
                profile_version="chronology-profile/1.1",
            )
        )
    events = group_assertions(foundation.case_id, assertions, matrices.evidence_matrix)
    return CaseChronology(
        case_id=foundation.case_id,
        synthesis_id=foundation.synthesis_id,
        source_analysis_ids=foundation.source_issue_analysis_ids,
        events=events,
    )


def source_refs(foundation, matrices, chronology):
    ek_source = next(item for item in foundation.source_analyses if item.issue_definition_id == "EK-001")
    ra_source = next(item for item in foundation.source_analyses if item.issue_definition_id == "RA-001")
    ek_use = next(
        use
        for record in matrices.evidence_matrix
        for use in record.uses
        if use.issue_analysis_id == ek_source.issue_analysis_id
    )
    ra_use = next(
        use
        for record in matrices.evidence_matrix
        for use in record.uses
        if use.issue_analysis_id == ra_source.issue_analysis_id
    )
    event = chronology.events[0]
    ek_assertion = next(item for item in event.assertions if item.issue_analysis_id == ek_source.issue_analysis_id)

    refs = {
        "ek_issue": SynthesisProvenanceRef(IssueRef(ek_source.issue_analysis_id, ek_source.issue_definition_id, ek_source.issue_definition_version)),
        "ra_issue": SynthesisProvenanceRef(IssueRef(ra_source.issue_analysis_id, ra_source.issue_definition_id, ra_source.issue_definition_version)),
        "ek_element": SynthesisProvenanceRef(ElementRef(ek_source.issue_analysis_id, ek_use.element_id)),
        "ek_use": SynthesisProvenanceRef(EvidenceUseRef(*ek_use.identity)),
        "ra_use": SynthesisProvenanceRef(EvidenceUseRef(*ra_use.identity)),
        "ek_prop": SynthesisProvenanceRef(PropositionRef(EvidenceUseRef(*ek_use.identity), ek_use.proposition_links[0].source_proposition_index)),
        "ra_prop": SynthesisProvenanceRef(PropositionRef(EvidenceUseRef(*ra_use.identity), ra_use.proposition_links[0].source_proposition_index)),
        "event": SynthesisProvenanceRef(EventRef(event.event_id)),
        "assertion": SynthesisProvenanceRef(EventAssertionRef(event.event_id, ek_assertion.assertion_id)),
        "upstream_gap": SynthesisProvenanceRef(EvidentialGapRef(ek_source.issue_analysis_id, "EK-INFORMATION", UPSTREAM_GAP_ID)),
        "upstream_dispute": SynthesisProvenanceRef(DisputedMatterRef(ek_source.issue_analysis_id, "EK-INFORMATION", UPSTREAM_DISPUTE_ID)),
    }
    return refs


def make_case_synthesis(*, foundation=None, matrices=None, chronology=None, summary="Frozen supporting feature."):
    if foundation is None or matrices is None or chronology is None:
        foundation, matrices, chronology = synthetic_sources()
    refs = source_refs(foundation, matrices, chronology)
    matrices_sha = fingerprint_case_matrices(matrices)
    chronology_sha = fingerprint_case_chronology(chronology)
    lineage = SynthesisSourceLineage(
        case_id=foundation.case_id,
        foundation_synthesis_id=foundation.synthesis_id,
        foundation_schema_version=foundation.schema_version,
        foundation_synthesiser_version=foundation.synthesiser_version,
        matrices_schema_version=matrices.schema_version,
        matrices_builder_version=matrices.matrix_builder_version,
        source_matrices_sha256=matrices_sha,
        chronology_schema_version=chronology.schema_version,
        chronology_builder_version=chronology.chronology_builder_version,
        source_chronology_sha256=chronology_sha,
        source_analysis_ids=foundation.source_issue_analysis_ids,
    )
    synthesis_id = derive_case_synthesis_id(
        case_id=foundation.case_id,
        foundation_synthesis_id=foundation.synthesis_id,
        source_matrices_sha256=matrices_sha,
        source_chronology_sha256=chronology_sha,
    )

    finding_refs = (refs["ek_prop"],)
    finding_id = derive_finding_id(
        synthesis_id=synthesis_id,
        finding_type=FindingType.SUPPORTING_FEATURE,
        scope=FindingScope.ELEMENT,
        analytical_bases=(AnalyticalBasis.SUPPORTED_PROPOSITION,),
        provenance_refs=finding_refs,
    )
    finding = SynthesisFinding(
        finding_id=finding_id,
        finding_type=FindingType.SUPPORTING_FEATURE,
        analytical_bases=(AnalyticalBasis.SUPPORTED_PROPOSITION,),
        scope=FindingScope.ELEMENT,
        summary=summary,
        status=FindingStatus.SUPPORTED_BY_FROZEN_STATE,
        confidence=Confidence.MEDIUM,
        provenance_refs=finding_refs,
    )

    conflict_id = derive_conflict_id(
        synthesis_id=synthesis_id,
        conflict_type=ConflictType.SOURCE_POSITION_CONFLICT,
        scope=FindingScope.ISSUE,
        side_a_refs=(refs["ek_prop"],),
        side_b_refs=(refs["upstream_dispute"],),
    )
    conflict = MaterialConflict(
        conflict_id=conflict_id,
        conflict_type=ConflictType.SOURCE_POSITION_CONFLICT,
        scope=FindingScope.ISSUE,
        subject="Synthetic frozen source-position conflict.",
        side_a_refs=(refs["ek_prop"],),
        side_b_refs=(refs["upstream_dispute"],),
        materiality=Materiality.MEDIUM,
        status=FindingStatus.DISPUTED_IN_FROZEN_STATE,
        related_issue_ids=(next(item.issue_analysis_id for item in foundation.source_analyses if item.issue_definition_id == "EK-001"),),
    )

    ek_source = next(item for item in foundation.source_analyses if item.issue_definition_id == "EK-001")
    gap_refs = (refs["upstream_gap"],)
    gap_id = derive_gap_id(
        synthesis_id=synthesis_id,
        gap_type=GapType.INSUFFICIENT_EVIDENCE,
        scope=FindingScope.ELEMENT,
        issue_analysis_id=ek_source.issue_analysis_id,
        element_id="EK-INFORMATION",
        provenance_refs=gap_refs,
    )
    gap = EvidenceGap(
        gap_id=gap_id,
        gap_type=GapType.INSUFFICIENT_EVIDENCE,
        scope=FindingScope.ELEMENT,
        issue_analysis_id=ek_source.issue_analysis_id,
        issue_definition_id=ek_source.issue_definition_id,
        issue_definition_version=ek_source.issue_definition_version,
        element_id="EK-INFORMATION",
        description="Synthetic M4 gap derived from a frozen upstream gap identity.",
        materiality=Materiality.MEDIUM,
        unresolved_question="What evidence resolves the synthetic information gap?",
        provenance_refs=gap_refs,
        related_finding_ids=(finding_id,),
    )

    risk_id = derive_risk_id(
        synthesis_id=synthesis_id,
        risk_type=RiskType.EVIDENCE_RISK,
        scope=FindingScope.ISSUE,
        gap_ids=(gap_id,),
    )
    risk = RiskArea(
        risk_id=risk_id,
        risk_type=RiskType.EVIDENCE_RISK,
        scope=FindingScope.ISSUE,
        materiality=Materiality.MEDIUM,
        description="Synthetic evidence-coverage risk.",
        gap_ids=(gap_id,),
        affected_issue_ids=(ek_source.issue_analysis_id,),
    )

    question_id = derive_priority_question_id(
        synthesis_id=synthesis_id,
        basis_type=PriorityBasis.MATERIAL_GAP,
        affected_issue_ids=(ek_source.issue_analysis_id,),
        affected_element_ids=("EK-INFORMATION",),
        gap_ids=(gap_id,),
    )
    question = PriorityQuestion(
        question_id=question_id,
        question="What frozen evidence resolves the information gap?",
        priority=PriorityLevel.MEDIUM,
        basis_type=PriorityBasis.MATERIAL_GAP,
        affected_issue_ids=(ek_source.issue_analysis_id,),
        affected_element_ids=("EK-INFORMATION",),
        gap_ids=(gap_id,),
    )

    positions = []
    for source in foundation.source_analyses:
        ref = refs["ek_issue"] if source.issue_definition_id == "EK-001" else refs["ra_issue"]
        issue = next(item for item in matrices.issue_matrix if item.issue_analysis_id == source.issue_analysis_id)
        positions.append(
            IssuePosition(
                issue_definition_id=source.issue_definition_id,
                issue_definition_version=source.issue_definition_version,
                issue_analysis_id=source.issue_analysis_id,
                issue_name=issue.issue_name,
                position_status=IssuePositionStatus.UNRESOLVED,
                basis_refs=(ref,),
                confidence=Confidence.LOW,
                material_finding_ids=(finding_id,) if source.issue_definition_id == "EK-001" else (),
                conflict_ids=(conflict_id,) if source.issue_definition_id == "EK-001" else (),
                gap_ids=(gap_id,) if source.issue_definition_id == "EK-001" else (),
                risk_ids=(risk_id,) if source.issue_definition_id == "EK-001" else (),
            )
        )

    synthesis = CaseSynthesis(
        case_id=foundation.case_id,
        synthesis_id=synthesis_id,
        source_lineage=lineage,
        issue_positions=tuple(positions),
        findings=(finding,),
        conflicts=(conflict,),
        gaps=(gap,),
        risks=(risk,),
        priority_questions=(question,),
        overall_state=OverallState.PARTIALLY_DEVELOPED,
    )
    return foundation, matrices, chronology, synthesis, refs


def valid_uuid(value: str) -> bool:
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False
