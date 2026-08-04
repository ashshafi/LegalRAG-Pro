"""Deterministic Sprint 2.4 Milestone 4.2 whole-case synthesis.

M4.2 is deliberately narrow.  It derives only issue positions, direct
proposition/element findings and an overall analytical-development state from
frozen M1/M2/M3 durable objects.  It does not retrieve evidence, invoke an LLM,
create conflicts/gaps/risks/questions, or reinterpret frozen legal state.
"""

from __future__ import annotations

from collections import defaultdict
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
from case_analysis.m3.models import CaseChronology
from case_analysis.validation import validate_foundation
from legal_analysis.enums import Confidence
from legal_analysis.evidence_assessment import PropositionAssessmentStatus
from legal_analysis.legal_analysis import ElementAnalysisStatus

from .identity import (
    derive_case_synthesis_id,
    derive_finding_id,
    fingerprint_case_chronology,
    fingerprint_case_matrices,
)
from .models import (
    AnalyticalBasis,
    CaseSynthesis,
    ElementRef,
    EvidenceUseRef,
    FindingScope,
    FindingStatus,
    FindingType,
    IssuePosition,
    IssuePositionStatus,
    OverallState,
    PropositionRef,
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


def build_case_synthesis(
    foundation: CaseAnalysisFoundation,
    matrices: CaseMatrices,
    chronology: CaseChronology,
) -> CaseSynthesis:
    """Build the deterministic M4.2 synthesis from one frozen M1/M2/M3 state."""

    _validate_source_preconditions(foundation, matrices, chronology)
    lineage, synthesis_id = _source_lineage(foundation, matrices, chronology)

    findings: list[SynthesisFinding] = []
    finding_ids_by_issue: dict[str, list[str]] = defaultdict(list)

    for family in _proposition_families(matrices):
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
                conflict_ids=(),
                gap_ids=(),
                risk_ids=(),
            )
        )

    synthesis = CaseSynthesis(
        case_id=foundation.case_id,
        synthesis_id=synthesis_id,
        source_lineage=lineage,
        issue_positions=tuple(issue_positions),
        findings=tuple(findings),
        conflicts=(),
        gaps=(),
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


__all__ = ["build_case_synthesis"]
