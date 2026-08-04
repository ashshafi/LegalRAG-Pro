"""Fail-closed validation for Sprint 2.4 Milestone 4.1 durable synthesis."""

from __future__ import annotations

from dataclasses import dataclass

from case_analysis.models import CaseAnalysisFoundation
from case_analysis.validation import validate_foundation
from case_analysis.m2.matrices import CaseMatrices, EvidenceUse, IssueElementRecord, IssueMatrixRecord
from case_analysis.m2.matrix_validation import validate_case_matrices
from case_analysis.m3.models import CaseChronology, EventAssertion, EventStatus
from legal_analysis.enums import Confidence
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
    CaseSynthesis,
    DisputedMatterRef,
    ElementRef,
    EvidenceUseRef,
    EventAssertionRef,
    EventRef,
    EvidentialGapRef,
    FindingScope,
    FindingStatus,
    FindingType,
    IssueRef,
    PropositionRef,
    ProvenanceTarget,
    SynthesisProvenanceRef,
)


@dataclass(frozen=True, slots=True)
class _NativeIndex:
    source_by_issue: dict[str, object]
    issue_by_id: dict[str, IssueMatrixRecord]
    element_by_identity: dict[tuple[str, str], IssueElementRecord]
    use_by_identity: dict[tuple[str, str, str], EvidenceUse]
    event_by_id: dict[str, object]
    assertion_by_identity: dict[tuple[str, str], EventAssertion]


_CONFIDENCE_RANK = {
    Confidence.LOW: 0,
    Confidence.MEDIUM: 1,
    Confidence.HIGH: 2,
}

_FINDING_STATUS_RANK = {
    FindingStatus.UNRESOLVED_IN_FROZEN_STATE: 0,
    FindingStatus.DISPUTED_IN_FROZEN_STATE: 1,
    FindingStatus.SUPPORTED_BY_FROZEN_STATE: 2,
    FindingStatus.ESTABLISHED_BY_FROZEN_STATE: 3,
}


def _min_confidence(values: tuple[Confidence, ...]) -> Confidence | None:
    if not values:
        return None
    return min(values, key=lambda item: _CONFIDENCE_RANK[item])


def _source_ids(value) -> tuple[str, ...]:
    return tuple(sorted(value))


def _build_index(
    foundation: CaseAnalysisFoundation,
    matrices: CaseMatrices,
    chronology: CaseChronology,
) -> _NativeIndex:
    source_by_issue = {item.issue_analysis_id: item for item in foundation.source_analyses}
    issue_by_id = {item.issue_analysis_id: item for item in matrices.issue_matrix}
    element_by_identity: dict[tuple[str, str], IssueElementRecord] = {}
    for issue in matrices.issue_matrix:
        for element in issue.element_records:
            element_by_identity[(issue.issue_analysis_id, element.element_id)] = element

    use_by_identity: dict[tuple[str, str, str], EvidenceUse] = {}
    for record in matrices.evidence_matrix:
        for use in record.uses:
            if use.identity in use_by_identity:
                raise ValueError(f"Duplicate frozen EvidenceUse identity {use.identity!r}.")
            use_by_identity[use.identity] = use

    event_by_id = {item.event_id: item for item in chronology.events}
    assertion_by_identity: dict[tuple[str, str], EventAssertion] = {}
    for event in chronology.events:
        for assertion in event.assertions:
            identity = (event.event_id, assertion.assertion_id)
            if identity in assertion_by_identity:
                raise ValueError(f"Duplicate frozen EventAssertion identity {identity!r}.")
            assertion_by_identity[identity] = assertion

    return _NativeIndex(
        source_by_issue=source_by_issue,
        issue_by_id=issue_by_id,
        element_by_identity=element_by_identity,
        use_by_identity=use_by_identity,
        event_by_id=event_by_id,
        assertion_by_identity=assertion_by_identity,
    )


def _validate_lineage(
    value: CaseSynthesis,
    foundation: CaseAnalysisFoundation,
    matrices: CaseMatrices,
    chronology: CaseChronology,
) -> None:
    validate_foundation(foundation)
    validate_case_matrices(matrices, foundation=foundation)

    if value.case_id != foundation.case_id:
        raise ValueError("CaseSynthesis.case_id does not match the frozen M1 foundation.")
    if matrices.case_id != foundation.case_id or chronology.case_id != foundation.case_id:
        raise ValueError("M1/M2/M3 case identities must match exactly.")
    if matrices.synthesis_id != foundation.synthesis_id:
        raise ValueError("M2 synthesis identity does not match M1.")
    if chronology.synthesis_id != foundation.synthesis_id:
        raise ValueError("M3 synthesis identity does not match M1.")

    expected_sources = _source_ids(foundation.source_issue_analysis_ids)
    if _source_ids(matrices.source_analysis_ids) != expected_sources:
        raise ValueError("M2 source-analysis set does not match M1.")
    if _source_ids(chronology.source_analysis_ids) != expected_sources:
        raise ValueError("M3 source-analysis set does not match M1/M2.")

    lineage = value.source_lineage
    if lineage.case_id != foundation.case_id:
        raise ValueError("M4 source lineage case_id does not match M1.")
    if lineage.foundation_synthesis_id != foundation.synthesis_id:
        raise ValueError("M4 foundation_synthesis_id does not match M1.")
    if lineage.foundation_schema_version != foundation.schema_version:
        raise ValueError("M4 foundation schema lineage does not match M1.")
    if lineage.foundation_synthesiser_version != foundation.synthesiser_version:
        raise ValueError("M4 foundation synthesiser lineage does not match M1.")
    if lineage.matrices_schema_version != matrices.schema_version:
        raise ValueError("M4 matrices schema lineage does not match M2.")
    if lineage.matrices_builder_version != matrices.matrix_builder_version:
        raise ValueError("M4 matrices builder lineage does not match M2.")
    if lineage.chronology_schema_version != chronology.schema_version:
        raise ValueError("M4 chronology schema lineage does not match M3.")
    if lineage.chronology_builder_version != chronology.chronology_builder_version:
        raise ValueError("M4 chronology builder lineage does not match M3.")
    if lineage.source_analysis_ids != expected_sources:
        raise ValueError("M4 source_analysis_ids do not match the frozen M1/M2/M3 set.")

    actual_matrices_sha = fingerprint_case_matrices(matrices)
    if lineage.source_matrices_sha256 != actual_matrices_sha:
        raise ValueError("M4 source_matrices_sha256 does not match canonical frozen M2 bytes.")
    actual_chronology_sha = fingerprint_case_chronology(chronology)
    if lineage.source_chronology_sha256 != actual_chronology_sha:
        raise ValueError("M4 source_chronology_sha256 does not match canonical frozen M3 bytes.")

    expected_synthesis_id = derive_case_synthesis_id(
        case_id=foundation.case_id,
        foundation_synthesis_id=foundation.synthesis_id,
        source_matrices_sha256=actual_matrices_sha,
        source_chronology_sha256=actual_chronology_sha,
        schema_version=value.schema_version,
        synthesiser_version=value.synthesiser_version,
    )
    if value.synthesis_id != expected_synthesis_id:
        raise ValueError("CaseSynthesis.synthesis_id does not match its exact frozen source lineage.")


def _resolve_use(ref: EvidenceUseRef, index: _NativeIndex) -> EvidenceUse:
    try:
        return index.use_by_identity[ref.identity]
    except KeyError as exc:
        raise ValueError(f"Unknown frozen EvidenceUse reference {ref.identity!r}.") from exc


def _resolve_proposition(ref: PropositionRef, index: _NativeIndex):
    use = _resolve_use(ref.evidence_use_ref, index)
    for link in use.proposition_links:
        if link.source_proposition_index == ref.source_proposition_index:
            return link
    raise ValueError(
        "Unknown frozen proposition coordinate "
        f"{(*ref.evidence_use_ref.identity, ref.source_proposition_index)!r}."
    )


def _resolve_provenance_target(target: ProvenanceTarget, index: _NativeIndex):
    if isinstance(target, IssueRef):
        try:
            source = index.source_by_issue[target.issue_analysis_id]
            issue = index.issue_by_id[target.issue_analysis_id]
        except KeyError as exc:
            raise ValueError(f"Unknown frozen issue {target.issue_analysis_id!r}.") from exc
        if source.issue_definition_id != target.issue_definition_id:
            raise ValueError("IssueRef.issue_definition_id does not match frozen M1 lineage.")
        if source.issue_definition_version != target.issue_definition_version:
            raise ValueError("IssueRef.issue_definition_version does not match frozen M1 lineage.")
        if issue.issue_definition_id != target.issue_definition_id or issue.issue_definition_version != target.issue_definition_version:
            raise ValueError("IssueRef does not match frozen M2 issue-definition lineage.")
        return issue

    if isinstance(target, ElementRef):
        try:
            return index.element_by_identity[(target.issue_analysis_id, target.element_id)]
        except KeyError as exc:
            raise ValueError(
                f"Unknown frozen element {(target.issue_analysis_id, target.element_id)!r}."
            ) from exc

    if isinstance(target, EvidenceUseRef):
        return _resolve_use(target, index)

    if isinstance(target, PropositionRef):
        return _resolve_proposition(target, index)

    if isinstance(target, EventRef):
        try:
            return index.event_by_id[target.event_id]
        except KeyError as exc:
            raise ValueError(f"Unknown frozen event {target.event_id!r}.") from exc

    if isinstance(target, EventAssertionRef):
        try:
            return index.assertion_by_identity[(target.event_id, target.assertion_id)]
        except KeyError as exc:
            raise ValueError(
                f"Unknown frozen event assertion {(target.event_id, target.assertion_id)!r}."
            ) from exc

    if isinstance(target, EvidentialGapRef):
        try:
            element = index.element_by_identity[(target.issue_analysis_id, target.element_id)]
        except KeyError as exc:
            raise ValueError("EvidentialGapRef points to an unknown frozen element.") from exc
        if target.gap_id not in element.evidential_gap_ids:
            raise ValueError("EvidentialGapRef.gap_id is not retained by the frozen M2 element.")
        return target

    if isinstance(target, DisputedMatterRef):
        try:
            element = index.element_by_identity[(target.issue_analysis_id, target.element_id)]
        except KeyError as exc:
            raise ValueError("DisputedMatterRef points to an unknown frozen element.") from exc
        if target.disputed_matter_id not in element.disputed_matter_ids:
            raise ValueError(
                "DisputedMatterRef.disputed_matter_id is not retained by the frozen M2 element."
            )
        return target

    raise ValueError(f"Unsupported M4 provenance target {type(target)!r}.")


def _validate_m3_to_m2_bridge(chronology: CaseChronology, index: _NativeIndex) -> None:
    """Validate the complete frozen M3 assertion bridge without reopening M5."""

    for event in chronology.events:
        for assertion in event.assertions:
            use_ref = EvidenceUseRef(
                issue_analysis_id=assertion.issue_analysis_id,
                element_id=assertion.element_id,
                evidence_key=assertion.evidence_key,
            )
            use = _resolve_use(use_ref, index)
            if assertion.issue_definition_id != use.issue_definition_id:
                raise ValueError("M3 assertion issue-definition ID does not match its frozen M2 EvidenceUse.")
            if assertion.issue_definition_version != use.issue_definition_version:
                raise ValueError("M3 assertion issue-definition version does not match its frozen M2 EvidenceUse.")
            _resolve_proposition(
                PropositionRef(
                    evidence_use_ref=use_ref,
                    source_proposition_index=assertion.source_proposition_index,
                ),
                index,
            )


def _confidence_for_target(target: ProvenanceTarget, index: _NativeIndex) -> Confidence | None:
    resolved = _resolve_provenance_target(target, index)
    if isinstance(target, IssueRef):
        values = tuple(item.analysis_confidence for item in resolved.element_records)
        return _min_confidence(values)
    if isinstance(target, ElementRef):
        return resolved.analysis_confidence
    if isinstance(target, EvidenceUseRef):
        return _min_confidence((resolved.mapping_confidence, resolved.assessment_confidence))
    if isinstance(target, PropositionRef):
        return resolved.confidence
    if isinstance(target, EventRef):
        values = tuple(item.confidence for item in resolved.assertions)
        return _min_confidence(values)
    if isinstance(target, EventAssertionRef):
        return resolved.confidence
    return None


def _status_for_target(target: ProvenanceTarget, index: _NativeIndex) -> FindingStatus:
    resolved = _resolve_provenance_target(target, index)
    if isinstance(target, IssueRef):
        element_statuses = tuple(item.analysis_status for item in resolved.element_records)
        return min(
            (_finding_status_from_element_status(item) for item in element_statuses),
            key=lambda item: _FINDING_STATUS_RANK[item],
        )
    if isinstance(target, ElementRef):
        return _finding_status_from_element_status(resolved.analysis_status)
    if isinstance(target, PropositionRef):
        return _finding_status_from_proposition_status(resolved.status)
    if isinstance(target, EventRef):
        return _finding_status_from_event_status(resolved.event_status)
    if isinstance(target, EventAssertionRef):
        return _finding_status_from_event_status(resolved.event_status)
    # Existence of a frozen relationship/gap/dispute is itself established state.
    return FindingStatus.ESTABLISHED_BY_FROZEN_STATE


def _finding_status_from_element_status(status: ElementAnalysisStatus) -> FindingStatus:
    if status in {
        ElementAnalysisStatus.WELL_SUPPORTED_ON_CURRENT_RECORD,
        ElementAnalysisStatus.PARTIALLY_SUPPORTED,
    }:
        return FindingStatus.SUPPORTED_BY_FROZEN_STATE
    if status is ElementAnalysisStatus.DISPUTED:
        return FindingStatus.DISPUTED_IN_FROZEN_STATE
    return FindingStatus.UNRESOLVED_IN_FROZEN_STATE


def _finding_status_from_proposition_status(status: PropositionAssessmentStatus) -> FindingStatus:
    if status is PropositionAssessmentStatus.ESTABLISHED_BY_CURRENT_EVIDENCE:
        return FindingStatus.ESTABLISHED_BY_FROZEN_STATE
    if status is PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED:
        return FindingStatus.SUPPORTED_BY_FROZEN_STATE
    if status is PropositionAssessmentStatus.DISPUTED:
        return FindingStatus.DISPUTED_IN_FROZEN_STATE
    return FindingStatus.UNRESOLVED_IN_FROZEN_STATE


def _finding_status_from_event_status(status: EventStatus) -> FindingStatus:
    if status is EventStatus.ESTABLISHED:
        return FindingStatus.ESTABLISHED_BY_FROZEN_STATE
    if status is EventStatus.SUPPORTED:
        return FindingStatus.SUPPORTED_BY_FROZEN_STATE
    if status is EventStatus.DISPUTED:
        return FindingStatus.DISPUTED_IN_FROZEN_STATE
    return FindingStatus.UNRESOLVED_IN_FROZEN_STATE


def _validate_status_ceiling(
    status: FindingStatus,
    refs: tuple[SynthesisProvenanceRef, ...],
    index: _NativeIndex,
) -> None:
    source_statuses = tuple(_status_for_target(item.target, index) for item in refs)
    if not source_statuses:
        raise ValueError("Finding status validation requires provenance.")
    ceiling = min(source_statuses, key=lambda item: _FINDING_STATUS_RANK[item])
    if _FINDING_STATUS_RANK[status] > _FINDING_STATUS_RANK[ceiling]:
        raise ValueError(
            f"M4 finding status {status.value!r} exceeds frozen source ceiling {ceiling.value!r}."
        )


def _validate_confidence_ceiling(
    confidence: Confidence,
    refs: tuple[SynthesisProvenanceRef, ...],
    index: _NativeIndex,
) -> None:
    source_confidences = tuple(
        item
        for item in (_confidence_for_target(ref.target, index) for ref in refs)
        if item is not None
    )
    ceiling = _min_confidence(source_confidences)
    if ceiling is not None and _CONFIDENCE_RANK[confidence] > _CONFIDENCE_RANK[ceiling]:
        raise ValueError(
            f"M4 confidence {confidence.value!r} exceeds frozen source ceiling {ceiling.value!r}."
        )


def _issue_ids_for_ref(ref: SynthesisProvenanceRef, index: _NativeIndex) -> set[str]:
    target = ref.target
    if isinstance(target, (IssueRef, ElementRef, EvidenceUseRef, EvidentialGapRef, DisputedMatterRef)):
        return {target.issue_analysis_id}
    if isinstance(target, PropositionRef):
        return {target.evidence_use_ref.issue_analysis_id}
    if isinstance(target, EventAssertionRef):
        assertion = _resolve_provenance_target(target, index)
        return {assertion.issue_analysis_id}
    if isinstance(target, EventRef):
        event = _resolve_provenance_target(target, index)
        return set(event.related_issue_analysis_ids)
    return set()


def _validate_deterministic_ids(value: CaseSynthesis) -> None:
    for finding in value.findings:
        expected = derive_finding_id(
            synthesis_id=value.synthesis_id,
            finding_type=finding.finding_type,
            scope=finding.scope,
            analytical_bases=finding.analytical_bases,
            provenance_refs=finding.provenance_refs,
        )
        if finding.finding_id != expected:
            raise ValueError("SynthesisFinding.finding_id is not deterministic for its semantic basis.")

    for conflict in value.conflicts:
        expected = derive_conflict_id(
            synthesis_id=value.synthesis_id,
            conflict_type=conflict.conflict_type,
            scope=conflict.scope,
            side_a_refs=conflict.side_a_refs,
            side_b_refs=conflict.side_b_refs,
        )
        if conflict.conflict_id != expected:
            raise ValueError("MaterialConflict.conflict_id is not deterministic for its semantic basis.")

    for gap in value.gaps:
        expected = derive_gap_id(
            synthesis_id=value.synthesis_id,
            gap_type=gap.gap_type,
            scope=gap.scope,
            issue_analysis_id=gap.issue_analysis_id,
            element_id=gap.element_id,
            provenance_refs=gap.provenance_refs,
        )
        if gap.gap_id != expected:
            raise ValueError("EvidenceGap.gap_id is not deterministic for its semantic basis.")

    for risk in value.risks:
        expected = derive_risk_id(
            synthesis_id=value.synthesis_id,
            risk_type=risk.risk_type,
            scope=risk.scope,
            basis_finding_ids=risk.basis_finding_ids,
            conflict_ids=risk.conflict_ids,
            gap_ids=risk.gap_ids,
            provenance_refs=risk.provenance_refs,
        )
        if risk.risk_id != expected:
            raise ValueError("RiskArea.risk_id is not deterministic for its semantic basis.")

    for question in value.priority_questions:
        expected = derive_priority_question_id(
            synthesis_id=value.synthesis_id,
            basis_type=question.basis_type,
            affected_issue_ids=question.affected_issue_ids,
            affected_element_ids=question.affected_element_ids,
            finding_ids=question.finding_ids,
            gap_ids=question.gap_ids,
            conflict_ids=question.conflict_ids,
            provenance_refs=question.provenance_refs,
        )
        if question.question_id != expected:
            raise ValueError("PriorityQuestion.question_id is not deterministic for its semantic basis.")


def _validate_cross_references(value: CaseSynthesis, index: _NativeIndex) -> None:
    issue_ids = set(index.issue_by_id)
    finding_ids = {item.finding_id for item in value.findings}
    conflict_ids = {item.conflict_id for item in value.conflicts}
    gap_ids = {item.gap_id for item in value.gaps}
    risk_ids = {item.risk_id for item in value.risks}

    position_ids = {item.issue_analysis_id for item in value.issue_positions}
    if position_ids != issue_ids:
        raise ValueError("CaseSynthesis must contain exactly one IssuePosition for every frozen issue.")

    for position in value.issue_positions:
        source = index.source_by_issue[position.issue_analysis_id]
        issue = index.issue_by_id[position.issue_analysis_id]
        if position.issue_definition_id != source.issue_definition_id or position.issue_definition_id != issue.issue_definition_id:
            raise ValueError("IssuePosition issue-definition ID does not match frozen lineage.")
        if position.issue_definition_version != source.issue_definition_version or position.issue_definition_version != issue.issue_definition_version:
            raise ValueError("IssuePosition issue-definition version does not match frozen lineage.")
        if position.issue_name != issue.issue_name:
            raise ValueError("IssuePosition.issue_name does not match frozen M2 issue metadata.")
        for ref in position.basis_refs:
            _resolve_provenance_target(ref.target, index)
        _validate_confidence_ceiling(position.confidence, position.basis_refs, index)
        if not set(position.material_finding_ids).issubset(finding_ids):
            raise ValueError("IssuePosition references an unknown material finding.")
        if not set(position.conflict_ids).issubset(conflict_ids):
            raise ValueError("IssuePosition references an unknown conflict.")
        if not set(position.gap_ids).issubset(gap_ids):
            raise ValueError("IssuePosition references an unknown M4 gap.")
        if not set(position.risk_ids).issubset(risk_ids):
            raise ValueError("IssuePosition references an unknown risk.")

    for finding in value.findings:
        for ref in finding.provenance_refs:
            _resolve_provenance_target(ref.target, index)
        _validate_status_ceiling(finding.status, finding.provenance_refs, index)
        _validate_confidence_ceiling(finding.confidence, finding.provenance_refs, index)
        if not set(finding.related_finding_ids).issubset(finding_ids):
            raise ValueError("SynthesisFinding references an unknown related finding.")
        if finding.finding_type is FindingType.CROSS_ISSUE_FEATURE and finding.scope is not FindingScope.CROSS_ISSUE:
            raise ValueError("CROSS_ISSUE_FEATURE findings must use CROSS_ISSUE scope.")
        if finding.scope is FindingScope.CROSS_ISSUE:
            covered: set[str] = set()
            for ref in finding.provenance_refs:
                covered.update(_issue_ids_for_ref(ref, index))
            if len(covered) < 2:
                raise ValueError("Cross-issue findings must resolve to at least two frozen issues.")

    for conflict in value.conflicts:
        for ref in (*conflict.side_a_refs, *conflict.side_b_refs):
            _resolve_provenance_target(ref.target, index)
        if not set(conflict.related_issue_ids).issubset(issue_ids):
            raise ValueError("MaterialConflict references an unknown frozen issue.")

    for gap in value.gaps:
        try:
            source = index.source_by_issue[gap.issue_analysis_id]
        except KeyError as exc:
            raise ValueError("EvidenceGap references an unknown frozen issue.") from exc
        if gap.issue_definition_id != source.issue_definition_id or gap.issue_definition_version != source.issue_definition_version:
            raise ValueError("EvidenceGap issue-definition lineage does not match the frozen issue.")
        if gap.element_id is not None and (gap.issue_analysis_id, gap.element_id) not in index.element_by_identity:
            raise ValueError("EvidenceGap references an unknown frozen element.")
        for ref in gap.provenance_refs:
            _resolve_provenance_target(ref.target, index)
        if not set(gap.related_finding_ids).issubset(finding_ids):
            raise ValueError("EvidenceGap references an unknown related finding.")

    for risk in value.risks:
        if not set(risk.basis_finding_ids).issubset(finding_ids):
            raise ValueError("RiskArea references an unknown finding.")
        if not set(risk.conflict_ids).issubset(conflict_ids):
            raise ValueError("RiskArea references an unknown conflict.")
        if not set(risk.gap_ids).issubset(gap_ids):
            raise ValueError("RiskArea references an unknown M4 gap.")
        if not set(risk.affected_issue_ids).issubset(issue_ids):
            raise ValueError("RiskArea references an unknown frozen issue.")
        for ref in risk.provenance_refs:
            _resolve_provenance_target(ref.target, index)

    all_element_ids = {element_id for _, element_id in index.element_by_identity}
    for question in value.priority_questions:
        if not set(question.affected_issue_ids).issubset(issue_ids):
            raise ValueError("PriorityQuestion references an unknown frozen issue.")
        if not set(question.affected_element_ids).issubset(all_element_ids):
            raise ValueError("PriorityQuestion references an unknown frozen element ID.")
        if not set(question.finding_ids).issubset(finding_ids):
            raise ValueError("PriorityQuestion references an unknown finding.")
        if not set(question.gap_ids).issubset(gap_ids):
            raise ValueError("PriorityQuestion references an unknown M4 gap.")
        if not set(question.conflict_ids).issubset(conflict_ids):
            raise ValueError("PriorityQuestion references an unknown conflict.")
        for ref in question.provenance_refs:
            _resolve_provenance_target(ref.target, index)


def validate_case_synthesis(
    value: CaseSynthesis,
    *,
    foundation: CaseAnalysisFoundation,
    matrices: CaseMatrices,
    chronology: CaseChronology,
) -> None:
    """Validate M4.1 durable state exclusively against frozen M1/M2/M3 inputs."""

    if not isinstance(value, CaseSynthesis):
        raise ValueError("value must be a CaseSynthesis instance.")
    if not isinstance(foundation, CaseAnalysisFoundation):
        raise ValueError("foundation must be a CaseAnalysisFoundation instance.")
    if not isinstance(matrices, CaseMatrices):
        raise ValueError("matrices must be a CaseMatrices instance.")
    if not isinstance(chronology, CaseChronology):
        raise ValueError("chronology must be a CaseChronology instance.")

    _validate_lineage(value, foundation, matrices, chronology)
    index = _build_index(foundation, matrices, chronology)
    _validate_m3_to_m2_bridge(chronology, index)
    _validate_deterministic_ids(value)
    _validate_cross_references(value, index)


__all__ = ["validate_case_synthesis"]
