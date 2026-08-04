"""Deterministic Sprint 2.4 M4 whole-case synthesis.

M4.2 derives issue positions and direct findings, M4.3 materialises the frozen
conflict/gap subset, M4.4 classifies those deficiencies as neutral risks and
priority questions, and M4.5 appends only the six authorised higher-order
evidence-relationship findings. The builder remains offline, provenance
preserving and fail-closed; it does not rank legal importance, reconstruct
discarded dependency/conflict semantics, retrieve evidence, or invoke an LLM.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from collections.abc import Iterable

from case_analysis.models import CaseAnalysisFoundation
from case_analysis.m2.matrices import (
    CaseMatrices,
    EvidencePropositionLink,
    EvidenceUse,
    IssueElementRecord,
    IssueMatrixRecord,
)
from case_analysis.m2.matrix_validation import validate_case_matrices
from case_analysis.m3.event_identity import aggregate_timing
from case_analysis.m3.models import CaseChronology, EventAssertion, TimingStatus
from case_analysis.validation import validate_foundation
from legal_analysis.enums import AnalyticalRole, Confidence, Materiality
from legal_analysis.evidence_assessment import PropositionAssessmentStatus
from legal_analysis.legal_analysis import ElementAnalysisStatus

from .identity import (
    derive_case_synthesis_id,
    derive_conflict_id,
    derive_finding_id,
    derive_gap_id,
    derive_priority_question_id,
    derive_risk_id,
    fingerprint_case_chronology,
    fingerprint_case_matrices,
)
from .models import (
    AnalyticalBasis,
    CaseSynthesis,
    ConflictType,
    ElementRef,
    EvidenceGap,
    EvidenceUseRef,
    EventAssertionRef,
    EvidentialGapRef,
    FindingScope,
    FindingStatus,
    FindingType,
    GapType,
    IssuePosition,
    IssuePositionStatus,
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
from .validation import validate_case_synthesis


_CONFIDENCE_RANK = {
    Confidence.LOW: 0,
    Confidence.MEDIUM: 1,
    Confidence.HIGH: 2,
}

_ISSUE_STATUS_BY_ELEMENT = {
    ElementAnalysisStatus.DISPUTED: IssuePositionStatus.MATERIALLY_DISPUTED,
    ElementAnalysisStatus.INSUFFICIENTLY_EVIDENCED: IssuePositionStatus.EVIDENCE_INCOMPLETE,
    ElementAnalysisStatus.UNRESOLVED: IssuePositionStatus.UNRESOLVED,
    ElementAnalysisStatus.PARTIALLY_SUPPORTED: IssuePositionStatus.PARTIALLY_SUPPORTED,
}



_SUPPORTING_PROPOSITION_STATUSES = {
    PropositionAssessmentStatus.ESTABLISHED_BY_CURRENT_EVIDENCE,
    PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
}

_SUPPORTING_ROLES = {
    AnalyticalRole.SUPPORTING,
    AnalyticalRole.CORROBORATIVE,
}

_SUPPORTING_PARENT_BASES = {
    AnalyticalBasis.ESTABLISHED_PROPOSITION,
    AnalyticalBasis.SUPPORTED_PROPOSITION,
}

_PROPOSITION_FINDING = {
    PropositionAssessmentStatus.ESTABLISHED_BY_CURRENT_EVIDENCE: (
        FindingType.SUPPORTING_FEATURE,
        AnalyticalBasis.ESTABLISHED_PROPOSITION,
        FindingStatus.ESTABLISHED_BY_FROZEN_STATE,
        "the frozen proposition is established by the current evidence",
    ),
    PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED: (
        FindingType.SUPPORTING_FEATURE,
        AnalyticalBasis.SUPPORTED_PROPOSITION,
        FindingStatus.SUPPORTED_BY_FROZEN_STATE,
        "the frozen proposition is supported but not established",
    ),
    PropositionAssessmentStatus.DISPUTED: (
        FindingType.LIMITING_FEATURE,
        AnalyticalBasis.DISPUTED_PROPOSITION,
        FindingStatus.DISPUTED_IN_FROZEN_STATE,
        "the frozen proposition remains disputed",
    ),
    PropositionAssessmentStatus.UNRESOLVED: (
        FindingType.LIMITING_FEATURE,
        AnalyticalBasis.UNRESOLVED_PROPOSITION,
        FindingStatus.UNRESOLVED_IN_FROZEN_STATE,
        "the frozen proposition remains unresolved",
    ),
}


class _PropositionFamily:
    """Internal non-durable grouping of exact M2 proposition links."""

    __slots__ = ("issue", "element", "members")

    def __init__(
        self,
        *,
        issue: IssueMatrixRecord,
        element: IssueElementRecord,
        members: tuple[tuple[EvidenceUse, EvidencePropositionLink], ...],
    ) -> None:
        self.issue = issue
        self.element = element
        self.members = members

    @property
    def canonical_link(self) -> EvidencePropositionLink:
        return self.members[0][1]

    @property
    def provenance_refs(self) -> tuple[SynthesisProvenanceRef, ...]:
        return tuple(
            SynthesisProvenanceRef(
                PropositionRef(
                    EvidenceUseRef(
                        use.issue_analysis_id,
                        use.element_id,
                        use.evidence_key,
                    ),
                    link.source_proposition_index,
                )
            )
            for use, link in self.members
        )


def _validate_source_preconditions(
    foundation: CaseAnalysisFoundation,
    matrices: CaseMatrices,
    chronology: CaseChronology,
) -> None:
    """Fail before synthesis if M1/M2/M3 do not form one coherent frozen state."""

    if not isinstance(foundation, CaseAnalysisFoundation):
        raise ValueError("foundation must be a CaseAnalysisFoundation instance.")
    if not isinstance(matrices, CaseMatrices):
        raise ValueError("matrices must be a CaseMatrices instance.")
    if not isinstance(chronology, CaseChronology):
        raise ValueError("chronology must be a CaseChronology instance.")

    validate_foundation(foundation)
    validate_case_matrices(matrices, foundation=foundation)

    if matrices.case_id != foundation.case_id or chronology.case_id != foundation.case_id:
        raise ValueError("M1/M2/M3 case identities must match exactly.")
    if matrices.synthesis_id != foundation.synthesis_id:
        raise ValueError("M2 synthesis identity does not match M1.")
    if chronology.synthesis_id != foundation.synthesis_id:
        raise ValueError("M3 synthesis identity does not match M1.")

    expected_sources = tuple(sorted(foundation.source_issue_analysis_ids))
    if tuple(sorted(matrices.source_analysis_ids)) != expected_sources:
        raise ValueError("M2 source-analysis set does not match M1.")
    if tuple(sorted(chronology.source_analysis_ids)) != expected_sources:
        raise ValueError("M3 source-analysis set does not match M1/M2.")

    use_by_identity: dict[tuple[str, str, str], EvidenceUse] = {}
    for record in matrices.evidence_matrix:
        for use in record.uses:
            if use.identity in use_by_identity:
                raise ValueError(f"Duplicate frozen EvidenceUse identity {use.identity!r}.")
            use_by_identity[use.identity] = use

    for event in chronology.events:
        for assertion in event.assertions:
            identity = (
                assertion.issue_analysis_id,
                assertion.element_id,
                assertion.evidence_key,
            )
            try:
                use = use_by_identity[identity]
            except KeyError as exc:
                raise ValueError(
                    f"M3 assertion does not resolve to frozen EvidenceUse {identity!r}."
                ) from exc
            if not any(
                link.source_proposition_index == assertion.source_proposition_index
                for link in use.proposition_links
            ):
                raise ValueError(
                    "M3 assertion does not resolve to its frozen M2 proposition link "
                    f"{(*identity, assertion.source_proposition_index)!r}."
                )


def _source_lineage(
    foundation: CaseAnalysisFoundation,
    matrices: CaseMatrices,
    chronology: CaseChronology,
) -> tuple[SynthesisSourceLineage, str]:
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
    return lineage, synthesis_id


def _issue_status(elements: tuple[IssueElementRecord, ...]) -> IssuePositionStatus:
    statuses = tuple(element.analysis_status for element in elements)
    for source_status in (
        ElementAnalysisStatus.DISPUTED,
        ElementAnalysisStatus.INSUFFICIENTLY_EVIDENCED,
        ElementAnalysisStatus.UNRESOLVED,
        ElementAnalysisStatus.PARTIALLY_SUPPORTED,
    ):
        if source_status in statuses:
            return _ISSUE_STATUS_BY_ELEMENT[source_status]
    if statuses and all(
        status is ElementAnalysisStatus.WELL_SUPPORTED_ON_CURRENT_RECORD
        for status in statuses
    ):
        return IssuePositionStatus.WELL_SUPPORTED
    raise ValueError("Unsupported frozen element-status combination for M4.2 issue synthesis.")


def _minimum_confidence(values: Iterable[Confidence]) -> Confidence:
    values = tuple(values)
    if not values:
        raise ValueError("M4.2 confidence aggregation requires at least one frozen confidence.")
    return min(values, key=lambda item: _CONFIDENCE_RANK[item])


def _proposition_families(
    matrices: CaseMatrices,
) -> tuple[_PropositionFamily, ...]:
    issue_by_id = {issue.issue_analysis_id: issue for issue in matrices.issue_matrix}
    element_by_identity = {
        (issue.issue_analysis_id, element.element_id): element
        for issue in matrices.issue_matrix
        for element in issue.element_records
    }
    grouped: dict[
        tuple[str, str, int],
        list[tuple[EvidenceUse, EvidencePropositionLink]],
    ] = defaultdict(list)
    exact_refs: set[tuple[str, str, str, int]] = set()

    for record in matrices.evidence_matrix:
        for use in record.uses:
            for link in use.proposition_links:
                exact_ref = (*use.identity, link.source_proposition_index)
                if exact_ref in exact_refs:
                    raise ValueError(f"Duplicate frozen proposition reference {exact_ref!r}.")
                exact_refs.add(exact_ref)
                grouped[
                    (use.issue_analysis_id, use.element_id, link.source_proposition_index)
                ].append((use, link))

    families: list[_PropositionFamily] = []
    for family_key in sorted(grouped):
        issue_analysis_id, element_id, _ = family_key
        try:
            issue = issue_by_id[issue_analysis_id]
            element = element_by_identity[(issue_analysis_id, element_id)]
        except KeyError as exc:
            raise ValueError(f"Proposition family references unknown element {family_key!r}.") from exc

        members = tuple(sorted(grouped[family_key], key=lambda item: item[0].identity))
        canonical = members[0][1]
        for _, link in members[1:]:
            if (
                link.text != canonical.text
                or link.status is not canonical.status
                or link.confidence is not canonical.confidence
            ):
                raise ValueError(
                    "Frozen proposition family is inconsistent across EvidenceUses for "
                    f"{family_key!r}."
                )
        families.append(_PropositionFamily(issue=issue, element=element, members=members))
    return tuple(families)


def _proposition_finding(
    *,
    synthesis_id: str,
    family: _PropositionFamily,
) -> SynthesisFinding | None:
    link = family.canonical_link
    mapping = _PROPOSITION_FINDING.get(link.status)
    if mapping is None:
        if link.status is PropositionAssessmentStatus.NOT_SUPPORTED_BY_CURRENT_EVIDENCE:
            return None
        raise ValueError(f"Unsupported proposition status {link.status!r}.")

    finding_type, analytical_basis, finding_status, template = mapping
    provenance_refs = family.provenance_refs
    finding_id = derive_finding_id(
        synthesis_id=synthesis_id,
        finding_type=finding_type,
        scope=FindingScope.ELEMENT,
        analytical_bases=(analytical_basis,),
        provenance_refs=provenance_refs,
    )
    return SynthesisFinding(
        finding_id=finding_id,
        finding_type=finding_type,
        analytical_bases=(analytical_basis,),
        scope=FindingScope.ELEMENT,
        summary=f"{family.element.element_name}: {template}: {link.text}",
        status=finding_status,
        confidence=link.confidence,
        provenance_refs=provenance_refs,
    )


def _insufficient_element_finding(
    *,
    synthesis_id: str,
    issue_analysis_id: str,
    element: IssueElementRecord,
) -> SynthesisFinding | None:
    if element.analysis_status is not ElementAnalysisStatus.INSUFFICIENTLY_EVIDENCED:
        return None
    provenance_refs = (
        SynthesisProvenanceRef(ElementRef(issue_analysis_id, element.element_id)),
    )
    finding_id = derive_finding_id(
        synthesis_id=synthesis_id,
        finding_type=FindingType.LIMITING_FEATURE,
        scope=FindingScope.ELEMENT,
        analytical_bases=(AnalyticalBasis.INSUFFICIENT_EVIDENCE,),
        provenance_refs=provenance_refs,
    )
    return SynthesisFinding(
        finding_id=finding_id,
        finding_type=FindingType.LIMITING_FEATURE,
        analytical_bases=(AnalyticalBasis.INSUFFICIENT_EVIDENCE,),
        scope=FindingScope.ELEMENT,
        summary=f"{element.element_name}: the frozen element analysis is insufficiently evidenced.",
        status=FindingStatus.UNRESOLVED_IN_FROZEN_STATE,
        confidence=element.analysis_confidence,
        provenance_refs=provenance_refs,
    )



def _uses_by_element(matrices: CaseMatrices) -> dict[tuple[str, str], tuple[EvidenceUse, ...]]:
    grouped: dict[tuple[str, str], list[EvidenceUse]] = defaultdict(list)
    for record in matrices.evidence_matrix:
        for use in record.uses:
            grouped[(use.issue_analysis_id, use.element_id)].append(use)
    return {
        identity: tuple(sorted(uses, key=lambda item: item.identity))
        for identity, uses in grouped.items()
    }


def _upstream_gap_refs(
    issue_analysis_id: str,
    element: IssueElementRecord,
) -> tuple[SynthesisProvenanceRef, ...]:
    return tuple(
        SynthesisProvenanceRef(
            EvidentialGapRef(issue_analysis_id, element.element_id, gap_id)
        )
        for gap_id in sorted(element.evidential_gap_ids)
    )


def _element_gap(
    *,
    synthesis_id: str,
    issue: IssueMatrixRecord,
    element: IssueElementRecord,
    gap_type: GapType,
) -> EvidenceGap:
    element_ref = SynthesisProvenanceRef(
        ElementRef(issue.issue_analysis_id, element.element_id)
    )
    provenance_refs = (element_ref, *_upstream_gap_refs(issue.issue_analysis_id, element))
    if gap_type is GapType.MISSING_EVIDENCE:
        description = (
            f"{element.element_name}: no frozen M2 relevant EvidenceUse is present "
            "for this element."
        )
    elif gap_type is GapType.INSUFFICIENT_EVIDENCE:
        description = (
            f"{element.element_name}: the frozen analytical record is insufficiently evidenced."
        )
    else:
        raise ValueError(f"Unsupported M4.3 element gap type {gap_type!r}.")

    gap_id = derive_gap_id(
        synthesis_id=synthesis_id,
        gap_type=gap_type,
        scope=FindingScope.ELEMENT,
        issue_analysis_id=issue.issue_analysis_id,
        element_id=element.element_id,
        provenance_refs=provenance_refs,
    )
    return EvidenceGap(
        gap_id=gap_id,
        gap_type=gap_type,
        scope=FindingScope.ELEMENT,
        issue_analysis_id=issue.issue_analysis_id,
        issue_definition_id=issue.issue_definition_id,
        issue_definition_version=issue.issue_definition_version,
        element_id=element.element_id,
        description=description,
        materiality=Materiality.MEDIUM,
        unresolved_question=element.legal_question,
        provenance_refs=provenance_refs,
    )


def _unresolved_proposition_gap(
    *,
    synthesis_id: str,
    family: _PropositionFamily,
) -> EvidenceGap:
    link = family.canonical_link
    if link.status is not PropositionAssessmentStatus.UNRESOLVED:
        raise ValueError("UNRESOLVED_PROPOSITION requires frozen UNRESOLVED status.")
    provenance_refs = family.provenance_refs
    gap_id = derive_gap_id(
        synthesis_id=synthesis_id,
        gap_type=GapType.UNRESOLVED_PROPOSITION,
        scope=FindingScope.ELEMENT,
        issue_analysis_id=family.issue.issue_analysis_id,
        element_id=family.element.element_id,
        provenance_refs=provenance_refs,
    )
    return EvidenceGap(
        gap_id=gap_id,
        gap_type=GapType.UNRESOLVED_PROPOSITION,
        scope=FindingScope.ELEMENT,
        issue_analysis_id=family.issue.issue_analysis_id,
        issue_definition_id=family.issue.issue_definition_id,
        issue_definition_version=family.issue.issue_definition_version,
        element_id=family.element.element_id,
        description=(
            f"{family.element.element_name}: the frozen proposition remains unresolved: "
            f"{link.text}"
        ),
        materiality=Materiality.MEDIUM,
        unresolved_question=family.element.legal_question,
        provenance_refs=provenance_refs,
    )


def _derive_gaps(
    *,
    synthesis_id: str,
    matrices: CaseMatrices,
    families: tuple[_PropositionFamily, ...],
) -> tuple[EvidenceGap, ...]:
    uses_by_element = _uses_by_element(matrices)
    families_by_element: dict[tuple[str, str], list[_PropositionFamily]] = defaultdict(list)
    for family in families:
        families_by_element[(family.issue.issue_analysis_id, family.element.element_id)].append(family)

    gaps: list[EvidenceGap] = []
    for issue in sorted(
        matrices.issue_matrix,
        key=lambda item: (
            item.issue_definition_id,
            item.issue_definition_version,
            item.issue_analysis_id,
        ),
    ):
        for element in sorted(issue.element_records, key=lambda item: item.element_id):
            identity = (issue.issue_analysis_id, element.element_id)
            uses = uses_by_element.get(identity, ())
            if not uses:
                gaps.append(
                    _element_gap(
                        synthesis_id=synthesis_id,
                        issue=issue,
                        element=element,
                        gap_type=GapType.MISSING_EVIDENCE,
                    )
                )
                continue

            if element.analysis_status is ElementAnalysisStatus.INSUFFICIENTLY_EVIDENCED:
                gaps.append(
                    _element_gap(
                        synthesis_id=synthesis_id,
                        issue=issue,
                        element=element,
                        gap_type=GapType.INSUFFICIENT_EVIDENCE,
                    )
                )
                continue

            for family in sorted(
                families_by_element.get(identity, ()),
                key=lambda item: item.canonical_link.source_proposition_index,
            ):
                if family.canonical_link.status is PropositionAssessmentStatus.UNRESOLVED:
                    gaps.append(
                        _unresolved_proposition_gap(
                            synthesis_id=synthesis_id,
                            family=family,
                        )
                    )
    return tuple(gaps)


def _timing_conflict_scope(assertions: tuple[EventAssertion, ...]) -> FindingScope:
    issue_ids = {item.issue_analysis_id for item in assertions}
    if len(issue_ids) > 1:
        return FindingScope.CROSS_ISSUE
    element_ids = {item.element_id for item in assertions}
    if len(element_ids) == 1:
        return FindingScope.ELEMENT
    return FindingScope.ISSUE


def _derive_timing_conflicts(
    *,
    synthesis_id: str,
    chronology: CaseChronology,
) -> tuple[MaterialConflict, ...]:
    conflicts: list[MaterialConflict] = []
    for event in sorted(chronology.events, key=lambda item: item.event_id):
        # Fail closed if an externally/manual constructed chronology contradicts
        # the frozen M3 timing aggregation it claims to represent.
        expected_extent, expected_status = aggregate_timing(event.assertions)
        if expected_extent != event.canonical_temporal_extent or expected_status is not event.timing_status:
            raise ValueError(
                f"Frozen M3 event {event.event_id!r} is inconsistent with M3 timing aggregation."
            )

        eligible = tuple(
            assertion
            for assertion in event.assertions
            if assertion.temporal_extent is not None
            and assertion.timing_status in {TimingStatus.ESTABLISHED, TimingStatus.SUPPORTED}
        )
        if len(eligible) < 2:
            continue

        candidate_extent, candidate_status = aggregate_timing(eligible)
        if candidate_status is not TimingStatus.DISPUTED or candidate_extent is not None:
            continue
        if event.timing_status is not TimingStatus.DISPUTED or event.canonical_temporal_extent is not None:
            continue

        if len(eligible) > 2:
            raise ValueError(
                "M4.3 cannot losslessly represent more than two incompatible retained "
                f"temporal assertions for event {event.event_id!r}."
            )

        ordered = tuple(sorted(eligible, key=lambda item: item.assertion_id))
        side_a_refs = (
            SynthesisProvenanceRef(EventAssertionRef(event.event_id, ordered[0].assertion_id)),
        )
        side_b_refs = (
            SynthesisProvenanceRef(EventAssertionRef(event.event_id, ordered[1].assertion_id)),
        )
        scope = _timing_conflict_scope(ordered)
        conflict_id = derive_conflict_id(
            synthesis_id=synthesis_id,
            conflict_type=ConflictType.TIMING_CONFLICT,
            scope=scope,
            side_a_refs=side_a_refs,
            side_b_refs=side_b_refs,
        )
        conflicts.append(
            MaterialConflict(
                conflict_id=conflict_id,
                conflict_type=ConflictType.TIMING_CONFLICT,
                scope=scope,
                subject=event.normalized_event_core,
                side_a_refs=side_a_refs,
                side_b_refs=side_b_refs,
                materiality=Materiality.MEDIUM,
                status=FindingStatus.DISPUTED_IN_FROZEN_STATE,
                related_issue_ids=tuple(sorted({item.issue_analysis_id for item in ordered})),
            )
        )
    return tuple(conflicts)



def _derive_risks(
    *,
    synthesis_id: str,
    gaps: tuple[EvidenceGap, ...],
    conflicts: tuple[MaterialConflict, ...],
) -> tuple[RiskArea, ...]:
    """Classify only the M4.3 deficiencies authorised by M4.4 v1.0."""

    risks: list[RiskArea] = []
    for gap in sorted(gaps, key=lambda item: item.gap_id):
        risk_id = derive_risk_id(
            synthesis_id=synthesis_id,
            risk_type=RiskType.EVIDENCE_RISK,
            scope=gap.scope,
            gap_ids=(gap.gap_id,),
        )
        risks.append(
            RiskArea(
                risk_id=risk_id,
                risk_type=RiskType.EVIDENCE_RISK,
                scope=gap.scope,
                materiality=gap.materiality,
                description=f"Evidence risk: {gap.description}",
                gap_ids=(gap.gap_id,),
                affected_issue_ids=(gap.issue_analysis_id,),
            )
        )

    for conflict in sorted(conflicts, key=lambda item: item.conflict_id):
        if conflict.conflict_type is not ConflictType.TIMING_CONFLICT:
            raise ValueError(
                "M4.4 v1.0 cannot classify non-timing MaterialConflict objects."
            )
        risk_id = derive_risk_id(
            synthesis_id=synthesis_id,
            risk_type=RiskType.TIMING_RISK,
            scope=conflict.scope,
            conflict_ids=(conflict.conflict_id,),
        )
        risks.append(
            RiskArea(
                risk_id=risk_id,
                risk_type=RiskType.TIMING_RISK,
                scope=conflict.scope,
                materiality=conflict.materiality,
                description=(
                    "Timing risk: the frozen synthesis contains incompatible retained "
                    f"temporal positions for {conflict.subject}."
                ),
                conflict_ids=(conflict.conflict_id,),
                affected_issue_ids=conflict.related_issue_ids,
            )
        )
    return tuple(risks)


def _derive_priority_questions(
    *,
    synthesis_id: str,
    gaps: tuple[EvidenceGap, ...],
) -> tuple[PriorityQuestion, ...]:
    """Reuse exact frozen legal questions for material-gap classifications."""

    grouped: dict[tuple[str, str], list[EvidenceGap]] = defaultdict(list)
    for gap in gaps:
        if gap.element_id is None:
            raise ValueError(
                "M4.4 v1.0 MATERIAL_GAP questions require an exact element coordinate."
            )
        grouped[(gap.issue_analysis_id, gap.element_id)].append(gap)

    questions: list[PriorityQuestion] = []
    for (issue_analysis_id, element_id), members in sorted(grouped.items()):
        ordered = tuple(sorted(members, key=lambda item: item.gap_id))
        question_texts = {item.unresolved_question for item in ordered}
        if len(question_texts) != 1:
            raise ValueError(
                "M4.4 grouped gaps for one issue/element disagree on unresolved_question "
                f"for {(issue_analysis_id, element_id)!r}."
            )
        question = next(iter(question_texts))
        gap_ids = tuple(item.gap_id for item in ordered)
        question_id = derive_priority_question_id(
            synthesis_id=synthesis_id,
            basis_type=PriorityBasis.MATERIAL_GAP,
            affected_issue_ids=(issue_analysis_id,),
            affected_element_ids=(element_id,),
            gap_ids=gap_ids,
        )
        questions.append(
            PriorityQuestion(
                question_id=question_id,
                question=question,
                priority=PriorityLevel.MEDIUM,
                basis_type=PriorityBasis.MATERIAL_GAP,
                affected_issue_ids=(issue_analysis_id,),
                affected_element_ids=(element_id,),
                gap_ids=gap_ids,
            )
        )
    return tuple(questions)

def _overall_state(positions: tuple[IssuePosition, ...]) -> OverallState:
    statuses = {position.position_status for position in positions}
    if IssuePositionStatus.MATERIALLY_DISPUTED in statuses:
        return OverallState.MATERIALLY_DISPUTED
    if IssuePositionStatus.EVIDENCE_INCOMPLETE in statuses:
        return OverallState.EVIDENCE_INCOMPLETE
    if (
        IssuePositionStatus.PARTIALLY_SUPPORTED in statuses
        or IssuePositionStatus.UNRESOLVED in statuses
    ):
        return OverallState.PARTIALLY_DEVELOPED
    if statuses == {IssuePositionStatus.WELL_SUPPORTED}:
        return OverallState.WELL_DEVELOPED
    raise ValueError("Unsupported IssuePosition combination for M4.2 overall state.")


def _build_m43_semantic_core(
    foundation: CaseAnalysisFoundation,
    matrices: CaseMatrices,
    chronology: CaseChronology,
) -> CaseSynthesis:
    """Build the frozen M4.3 semantic core before M4.4 classifications."""

    _validate_source_preconditions(foundation, matrices, chronology)
    lineage, synthesis_id = _source_lineage(foundation, matrices, chronology)
    families = _proposition_families(matrices)

    findings: list[SynthesisFinding] = []
    finding_ids_by_issue: dict[str, list[str]] = defaultdict(list)

    for family in families:
        finding = _proposition_finding(synthesis_id=synthesis_id, family=family)
        if finding is None:
            continue
        findings.append(finding)
        finding_ids_by_issue[family.issue.issue_analysis_id].append(finding.finding_id)

    for issue in sorted(
        matrices.issue_matrix,
        key=lambda item: (
            item.issue_definition_id,
            item.issue_definition_version,
            item.issue_analysis_id,
        ),
    ):
        for element in sorted(issue.element_records, key=lambda item: item.element_id):
            finding = _insufficient_element_finding(
                synthesis_id=synthesis_id,
                issue_analysis_id=issue.issue_analysis_id,
                element=element,
            )
            if finding is None:
                continue
            findings.append(finding)
            finding_ids_by_issue[issue.issue_analysis_id].append(finding.finding_id)

    conflicts = _derive_timing_conflicts(synthesis_id=synthesis_id, chronology=chronology)
    gaps = _derive_gaps(synthesis_id=synthesis_id, matrices=matrices, families=families)

    conflict_ids_by_issue: dict[str, list[str]] = defaultdict(list)
    for conflict in conflicts:
        for issue_analysis_id in conflict.related_issue_ids:
            conflict_ids_by_issue[issue_analysis_id].append(conflict.conflict_id)

    gap_ids_by_issue: dict[str, list[str]] = defaultdict(list)
    for gap in gaps:
        gap_ids_by_issue[gap.issue_analysis_id].append(gap.gap_id)

    issue_positions: list[IssuePosition] = []
    for issue in sorted(
        matrices.issue_matrix,
        key=lambda item: (
            item.issue_definition_id,
            item.issue_definition_version,
            item.issue_analysis_id,
        ),
    ):
        basis_refs = tuple(
            SynthesisProvenanceRef(ElementRef(issue.issue_analysis_id, element.element_id))
            for element in sorted(issue.element_records, key=lambda item: item.element_id)
        )
        issue_positions.append(
            IssuePosition(
                issue_definition_id=issue.issue_definition_id,
                issue_definition_version=issue.issue_definition_version,
                issue_analysis_id=issue.issue_analysis_id,
                issue_name=issue.issue_name,
                position_status=_issue_status(issue.element_records),
                basis_refs=basis_refs,
                confidence=_minimum_confidence(
                    element.analysis_confidence for element in issue.element_records
                ),
                material_finding_ids=tuple(sorted(set(finding_ids_by_issue[issue.issue_analysis_id]))),
                conflict_ids=tuple(sorted(set(conflict_ids_by_issue[issue.issue_analysis_id]))),
                gap_ids=tuple(sorted(set(gap_ids_by_issue[issue.issue_analysis_id]))),
                risk_ids=(),
            )
        )

    synthesis = CaseSynthesis(
        case_id=foundation.case_id,
        synthesis_id=synthesis_id,
        source_lineage=lineage,
        issue_positions=tuple(issue_positions),
        findings=tuple(findings),
        conflicts=conflicts,
        gaps=gaps,
        risks=(),
        priority_questions=(),
        overall_state=_overall_state(tuple(issue_positions)),
    )
    validate_case_synthesis(
        synthesis,
        foundation=foundation,
        matrices=matrices,
        chronology=chronology,
    )
    return synthesis


def _evidence_use_confidence(use: EvidenceUse) -> Confidence:
    """Return the frozen confidence ceiling for one exact EvidenceUse."""

    return _minimum_confidence((use.mapping_confidence, use.assessment_confidence))


def _family_is_supporting(family: _PropositionFamily) -> bool:
    """Return whether one proposition family satisfies the strict v1 support rule."""

    if family.canonical_link.status not in _SUPPORTING_PROPOSITION_STATUSES:
        return False
    return bool(family.members) and all(
        use.analytical_role in _SUPPORTING_ROLES for use, _ in family.members
    )


def _finding_status_for_supporting_family(family: _PropositionFamily) -> FindingStatus:
    status = family.canonical_link.status
    if status is PropositionAssessmentStatus.ESTABLISHED_BY_CURRENT_EVIDENCE:
        return FindingStatus.ESTABLISHED_BY_FROZEN_STATE
    if status is PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED:
        return FindingStatus.SUPPORTED_BY_FROZEN_STATE
    raise ValueError("M4.5 supporting-family status must be established or supported.")


def _element_index(matrices: CaseMatrices) -> dict[tuple[str, str], IssueElementRecord]:
    return {
        (issue.issue_analysis_id, element.element_id): element
        for issue in matrices.issue_matrix
        for element in issue.element_records
    }


def _derive_multiple_supporting_proposition_findings(
    *,
    synthesis_id: str,
    families: tuple[_PropositionFamily, ...],
) -> tuple[SynthesisFinding, ...]:
    """Derive proposition breadth without counting repeated EvidenceUse projections."""

    grouped: dict[tuple[str, str], list[_PropositionFamily]] = defaultdict(list)
    for family in families:
        if _family_is_supporting(family):
            grouped[(family.issue.issue_analysis_id, family.element.element_id)].append(family)

    findings: list[SynthesisFinding] = []
    for coordinate, members in sorted(grouped.items()):
        ordered = tuple(
            sorted(members, key=lambda item: item.canonical_link.source_proposition_index)
        )
        family_indexes = {
            item.canonical_link.source_proposition_index for item in ordered
        }
        if len(family_indexes) < 2:
            continue

        provenance_refs = tuple(
            ref
            for family in ordered
            for ref in family.provenance_refs
        )
        statuses = tuple(_finding_status_for_supporting_family(item) for item in ordered)
        finding_status = (
            FindingStatus.SUPPORTED_BY_FROZEN_STATE
            if FindingStatus.SUPPORTED_BY_FROZEN_STATE in statuses
            else FindingStatus.ESTABLISHED_BY_FROZEN_STATE
        )
        confidence = _minimum_confidence(
            family.canonical_link.confidence for family in ordered
        )
        element = ordered[0].element
        finding_id = derive_finding_id(
            synthesis_id=synthesis_id,
            finding_type=FindingType.SUPPORTING_FEATURE,
            scope=FindingScope.ELEMENT,
            analytical_bases=(AnalyticalBasis.MULTIPLE_SUPPORTING_PROPOSITIONS,),
            provenance_refs=provenance_refs,
        )
        findings.append(
            SynthesisFinding(
                finding_id=finding_id,
                finding_type=FindingType.SUPPORTING_FEATURE,
                analytical_bases=(AnalyticalBasis.MULTIPLE_SUPPORTING_PROPOSITIONS,),
                scope=FindingScope.ELEMENT,
                summary=(
                    f"{element.element_name}: multiple distinct frozen supporting "
                    "proposition families are present for this element."
                ),
                status=finding_status,
                confidence=confidence,
                provenance_refs=provenance_refs,
            )
        )
    return tuple(findings)


def _derive_corroborated_evidence_findings(
    *,
    synthesis_id: str,
    families: tuple[_PropositionFamily, ...],
) -> tuple[SynthesisFinding, ...]:
    """Derive source multiplicity for one exact proposition family."""

    findings: list[SynthesisFinding] = []
    for family in families:
        if not _family_is_supporting(family):
            continue
        evidence_keys = {use.evidence_key for use, _ in family.members}
        if len(evidence_keys) < 2:
            continue

        provenance_refs = family.provenance_refs
        finding_id = derive_finding_id(
            synthesis_id=synthesis_id,
            finding_type=FindingType.SUPPORTING_FEATURE,
            scope=FindingScope.ELEMENT,
            analytical_bases=(AnalyticalBasis.CORROBORATED_EVIDENCE,),
            provenance_refs=provenance_refs,
        )
        findings.append(
            SynthesisFinding(
                finding_id=finding_id,
                finding_type=FindingType.SUPPORTING_FEATURE,
                analytical_bases=(AnalyticalBasis.CORROBORATED_EVIDENCE,),
                scope=FindingScope.ELEMENT,
                summary=(
                    f"{family.element.element_name}: this frozen proposition family is "
                    "represented through multiple distinct canonical evidence sources."
                ),
                status=_finding_status_for_supporting_family(family),
                confidence=family.canonical_link.confidence,
                provenance_refs=provenance_refs,
            )
        )
    return tuple(findings)


def _derive_role_findings(
    *,
    synthesis_id: str,
    matrices: CaseMatrices,
    role: AnalyticalRole,
    basis: AnalyticalBasis,
    summary_label: str,
) -> tuple[SynthesisFinding, ...]:
    """Expose one exact frozen analytical role at element scope."""

    grouped: dict[tuple[str, str], list[EvidenceUse]] = defaultdict(list)
    for record in matrices.evidence_matrix:
        for use in record.uses:
            if use.analytical_role is role:
                grouped[(use.issue_analysis_id, use.element_id)].append(use)

    elements = _element_index(matrices)
    findings: list[SynthesisFinding] = []
    for coordinate, members in sorted(grouped.items()):
        ordered = tuple(sorted(members, key=lambda item: item.identity))
        element = elements[coordinate]
        provenance_refs = tuple(
            SynthesisProvenanceRef(EvidenceUseRef(*use.identity)) for use in ordered
        )
        finding_id = derive_finding_id(
            synthesis_id=synthesis_id,
            finding_type=FindingType.LIMITING_FEATURE,
            scope=FindingScope.ELEMENT,
            analytical_bases=(basis,),
            provenance_refs=provenance_refs,
        )
        findings.append(
            SynthesisFinding(
                finding_id=finding_id,
                finding_type=FindingType.LIMITING_FEATURE,
                analytical_bases=(basis,),
                scope=FindingScope.ELEMENT,
                summary=(
                    f"{element.element_name}: the frozen evidence matrix contains "
                    f"evidence uses classified as {summary_label} for this element."
                ),
                status=FindingStatus.ESTABLISHED_BY_FROZEN_STATE,
                confidence=_minimum_confidence(
                    _evidence_use_confidence(use) for use in ordered
                ),
                provenance_refs=provenance_refs,
            )
        )
    return tuple(findings)


def _derive_cross_issue_coverage_findings(
    *,
    synthesis_id: str,
    matrices: CaseMatrices,
) -> tuple[SynthesisFinding, ...]:
    """Expose shared canonical evidence use across multiple frozen issues."""

    findings: list[SynthesisFinding] = []
    for record in sorted(matrices.evidence_matrix, key=lambda item: item.evidence_key):
        issue_ids = {use.issue_analysis_id for use in record.uses}
        if len(issue_ids) < 2:
            continue
        ordered = tuple(sorted(record.uses, key=lambda item: item.identity))
        provenance_refs = tuple(
            SynthesisProvenanceRef(EvidenceUseRef(*use.identity)) for use in ordered
        )
        finding_id = derive_finding_id(
            synthesis_id=synthesis_id,
            finding_type=FindingType.CROSS_ISSUE_FEATURE,
            scope=FindingScope.CROSS_ISSUE,
            analytical_bases=(AnalyticalBasis.CROSS_ISSUE_COVERAGE,),
            provenance_refs=provenance_refs,
        )
        findings.append(
            SynthesisFinding(
                finding_id=finding_id,
                finding_type=FindingType.CROSS_ISSUE_FEATURE,
                analytical_bases=(AnalyticalBasis.CROSS_ISSUE_COVERAGE,),
                scope=FindingScope.CROSS_ISSUE,
                summary=(
                    f"Canonical evidence {record.evidence_key} is used through frozen "
                    "evidence relationships in multiple issue analyses."
                ),
                status=FindingStatus.ESTABLISHED_BY_FROZEN_STATE,
                confidence=_minimum_confidence(
                    _evidence_use_confidence(use) for use in ordered
                ),
                provenance_refs=provenance_refs,
            )
        )
    return tuple(findings)


def _eligible_single_source_parent(finding: SynthesisFinding) -> bool:
    """Restrict dependency parents to frozen direct M4.2 proposition findings."""

    if finding.finding_type is not FindingType.SUPPORTING_FEATURE:
        return False
    if finding.scope is not FindingScope.ELEMENT:
        return False
    if len(finding.analytical_bases) != 1:
        return False
    if finding.analytical_bases[0] not in _SUPPORTING_PARENT_BASES:
        return False
    return bool(finding.provenance_refs) and all(
        isinstance(ref.target, PropositionRef) for ref in finding.provenance_refs
    )


def _derive_single_source_dependency_findings(
    *,
    synthesis_id: str,
    pre_m45_findings: tuple[SynthesisFinding, ...],
    matrices: CaseMatrices,
) -> tuple[SynthesisFinding, ...]:
    """Derive local dependency only from an immutable pre-M4.5 parent snapshot."""

    elements = _element_index(matrices)
    findings: list[SynthesisFinding] = []
    for parent in pre_m45_findings:
        if not _eligible_single_source_parent(parent):
            continue

        targets = tuple(ref.target for ref in parent.provenance_refs)
        evidence_keys = {
            target.evidence_use_ref.evidence_key
            for target in targets
            if isinstance(target, PropositionRef)
        }
        if len(evidence_keys) != 1:
            continue
        coordinates = {
            (
                target.evidence_use_ref.issue_analysis_id,
                target.evidence_use_ref.element_id,
            )
            for target in targets
            if isinstance(target, PropositionRef)
        }
        if len(coordinates) != 1:
            raise ValueError(
                "M4.5 eligible supporting parent finding spans more than one element coordinate."
            )
        coordinate = next(iter(coordinates))
        try:
            element = elements[coordinate]
        except KeyError as exc:
            raise ValueError(
                f"M4.5 parent finding references unknown element coordinate {coordinate!r}."
            ) from exc

        finding_id = derive_finding_id(
            synthesis_id=synthesis_id,
            finding_type=FindingType.LIMITING_FEATURE,
            scope=FindingScope.ELEMENT,
            analytical_bases=(AnalyticalBasis.DEPENDENCY_ON_SINGLE_EVIDENCE_SOURCE,),
            provenance_refs=parent.provenance_refs,
        )
        findings.append(
            SynthesisFinding(
                finding_id=finding_id,
                finding_type=FindingType.LIMITING_FEATURE,
                analytical_bases=(AnalyticalBasis.DEPENDENCY_ON_SINGLE_EVIDENCE_SOURCE,),
                scope=FindingScope.ELEMENT,
                summary=(
                    f"{element.element_name}: this frozen supporting finding resolves to "
                    "one canonical evidence source in its complete material provenance."
                ),
                status=parent.status,
                confidence=parent.confidence,
                provenance_refs=parent.provenance_refs,
                related_finding_ids=(parent.finding_id,),
            )
        )
    return tuple(findings)


def _derive_m45_findings(
    *,
    synthesis_id: str,
    matrices: CaseMatrices,
    pre_m45_findings: tuple[SynthesisFinding, ...],
) -> tuple[SynthesisFinding, ...]:
    """Derive exactly the six higher-order finding forms authorised by M4.5 v1.0."""

    families = _proposition_families(matrices)
    additions = (
        *_derive_multiple_supporting_proposition_findings(
            synthesis_id=synthesis_id,
            families=families,
        ),
        *_derive_corroborated_evidence_findings(
            synthesis_id=synthesis_id,
            families=families,
        ),
        *_derive_role_findings(
            synthesis_id=synthesis_id,
            matrices=matrices,
            role=AnalyticalRole.ADVERSE,
            basis=AnalyticalBasis.ADVERSE_EVIDENCE,
            summary_label="adverse",
        ),
        *_derive_role_findings(
            synthesis_id=synthesis_id,
            matrices=matrices,
            role=AnalyticalRole.CONFLICTING,
            basis=AnalyticalBasis.CONFLICTING_EVIDENCE,
            summary_label="conflicting",
        ),
        *_derive_cross_issue_coverage_findings(
            synthesis_id=synthesis_id,
            matrices=matrices,
        ),
        *_derive_single_source_dependency_findings(
            synthesis_id=synthesis_id,
            pre_m45_findings=pre_m45_findings,
            matrices=matrices,
        ),
    )
    ids = tuple(item.finding_id for item in additions)
    if len(ids) != len(set(ids)):
        raise ValueError("M4.5 derivation produced duplicate finding identities.")
    return tuple(additions)


def _build_m44_semantic_core(
    foundation: CaseAnalysisFoundation,
    matrices: CaseMatrices,
    chronology: CaseChronology,
) -> CaseSynthesis:
    """Build the complete frozen M4.4 semantic core before M4.5 findings."""

    core = _build_m43_semantic_core(foundation, matrices, chronology)
    risks = _derive_risks(
        synthesis_id=core.synthesis_id,
        gaps=core.gaps,
        conflicts=core.conflicts,
    )
    priority_questions = _derive_priority_questions(
        synthesis_id=core.synthesis_id,
        gaps=core.gaps,
    )

    risk_ids_by_issue: dict[str, list[str]] = defaultdict(list)
    for risk in risks:
        for issue_analysis_id in risk.affected_issue_ids:
            risk_ids_by_issue[issue_analysis_id].append(risk.risk_id)

    issue_positions = tuple(
        replace(
            position,
            risk_ids=tuple(sorted(set(risk_ids_by_issue[position.issue_analysis_id]))),
        )
        for position in core.issue_positions
    )
    synthesis = replace(
        core,
        issue_positions=issue_positions,
        risks=risks,
        priority_questions=priority_questions,
    )
    validate_case_synthesis(
        synthesis,
        foundation=foundation,
        matrices=matrices,
        chronology=chronology,
    )
    return synthesis


def build_case_synthesis(
    foundation: CaseAnalysisFoundation,
    matrices: CaseMatrices,
    chronology: CaseChronology,
) -> CaseSynthesis:
    """Build deterministic M4.2-M4.5 synthesis from frozen M1/M2/M3 state."""

    core = _build_m44_semantic_core(foundation, matrices, chronology)

    # Snapshot the complete pre-M4.5 finding set before deriving any M4.5 finding.
    # The single-source rule can therefore never recurse through M4.5 output.
    pre_m45_findings = core.findings
    additions = _derive_m45_findings(
        synthesis_id=core.synthesis_id,
        matrices=matrices,
        pre_m45_findings=pre_m45_findings,
    )
    synthesis = replace(
        core,
        findings=(*pre_m45_findings, *additions),
    )
    validate_case_synthesis(
        synthesis,
        foundation=foundation,
        matrices=matrices,
        chronology=chronology,
    )
    return synthesis


__all__ = ["build_case_synthesis"]
