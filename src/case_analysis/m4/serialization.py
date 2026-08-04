"""Canonical JSON serialization for Sprint 2.4 Milestone 4.1 durable synthesis."""

from __future__ import annotations

import json
from typing import Any

from legal_analysis.enums import Confidence, Materiality

from .models import (
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
    SynthesisProvenanceType,
    SynthesisSourceLineage,
)


def _provenance_to_dict(value: SynthesisProvenanceRef) -> dict[str, Any]:
    target = value.target
    payload: dict[str, Any]
    if isinstance(target, IssueRef):
        payload = {
            "issue_analysis_id": target.issue_analysis_id,
            "issue_definition_id": target.issue_definition_id,
            "issue_definition_version": target.issue_definition_version,
        }
    elif isinstance(target, ElementRef):
        payload = {
            "issue_analysis_id": target.issue_analysis_id,
            "element_id": target.element_id,
        }
    elif isinstance(target, EvidenceUseRef):
        payload = {
            "issue_analysis_id": target.issue_analysis_id,
            "element_id": target.element_id,
            "evidence_key": target.evidence_key,
        }
    elif isinstance(target, PropositionRef):
        payload = {
            "issue_analysis_id": target.evidence_use_ref.issue_analysis_id,
            "element_id": target.evidence_use_ref.element_id,
            "evidence_key": target.evidence_use_ref.evidence_key,
            "source_proposition_index": target.source_proposition_index,
        }
    elif isinstance(target, EventRef):
        payload = {"event_id": target.event_id}
    elif isinstance(target, EventAssertionRef):
        payload = {
            "event_id": target.event_id,
            "assertion_id": target.assertion_id,
        }
    elif isinstance(target, EvidentialGapRef):
        payload = {
            "issue_analysis_id": target.issue_analysis_id,
            "element_id": target.element_id,
            "gap_id": target.gap_id,
        }
    elif isinstance(target, DisputedMatterRef):
        payload = {
            "issue_analysis_id": target.issue_analysis_id,
            "element_id": target.element_id,
            "disputed_matter_id": target.disputed_matter_id,
        }
    else:  # pragma: no cover - guarded by the durable model
        raise ValueError(f"Unsupported provenance target {type(target)!r}.")
    return {"reference_type": value.reference_type.value, "reference": payload}


def _provenance_from_dict(data: dict[str, Any]) -> SynthesisProvenanceRef:
    reference_type = SynthesisProvenanceType(data["reference_type"])
    payload = data["reference"]
    if not isinstance(payload, dict):
        raise ValueError("M4 provenance reference payload must be an object.")
    if reference_type is SynthesisProvenanceType.ISSUE:
        target = IssueRef(
            issue_analysis_id=str(payload["issue_analysis_id"]),
            issue_definition_id=str(payload["issue_definition_id"]),
            issue_definition_version=str(payload["issue_definition_version"]),
        )
    elif reference_type is SynthesisProvenanceType.ELEMENT:
        target = ElementRef(
            issue_analysis_id=str(payload["issue_analysis_id"]),
            element_id=str(payload["element_id"]),
        )
    elif reference_type is SynthesisProvenanceType.EVIDENCE_USE:
        target = EvidenceUseRef(
            issue_analysis_id=str(payload["issue_analysis_id"]),
            element_id=str(payload["element_id"]),
            evidence_key=str(payload["evidence_key"]),
        )
    elif reference_type is SynthesisProvenanceType.PROPOSITION:
        target = PropositionRef(
            evidence_use_ref=EvidenceUseRef(
                issue_analysis_id=str(payload["issue_analysis_id"]),
                element_id=str(payload["element_id"]),
                evidence_key=str(payload["evidence_key"]),
            ),
            source_proposition_index=int(payload["source_proposition_index"]),
        )
    elif reference_type is SynthesisProvenanceType.EVENT:
        target = EventRef(event_id=str(payload["event_id"]))
    elif reference_type is SynthesisProvenanceType.EVENT_ASSERTION:
        target = EventAssertionRef(
            event_id=str(payload["event_id"]),
            assertion_id=str(payload["assertion_id"]),
        )
    elif reference_type is SynthesisProvenanceType.EVIDENTIAL_GAP:
        target = EvidentialGapRef(
            issue_analysis_id=str(payload["issue_analysis_id"]),
            element_id=str(payload["element_id"]),
            gap_id=str(payload["gap_id"]),
        )
    elif reference_type is SynthesisProvenanceType.DISPUTED_MATTER:
        target = DisputedMatterRef(
            issue_analysis_id=str(payload["issue_analysis_id"]),
            element_id=str(payload["element_id"]),
            disputed_matter_id=str(payload["disputed_matter_id"]),
        )
    else:  # pragma: no cover
        raise ValueError(f"Unsupported M4 provenance type {reference_type!r}.")
    return SynthesisProvenanceRef(target=target)


def _lineage_to_dict(value: SynthesisSourceLineage) -> dict[str, Any]:
    return {
        "case_id": value.case_id,
        "foundation_synthesis_id": value.foundation_synthesis_id,
        "foundation_schema_version": value.foundation_schema_version,
        "foundation_synthesiser_version": value.foundation_synthesiser_version,
        "matrices_schema_version": value.matrices_schema_version,
        "matrices_builder_version": value.matrices_builder_version,
        "source_matrices_sha256": value.source_matrices_sha256,
        "chronology_schema_version": value.chronology_schema_version,
        "chronology_builder_version": value.chronology_builder_version,
        "source_chronology_sha256": value.source_chronology_sha256,
        "source_analysis_ids": list(value.source_analysis_ids),
    }


def _lineage_from_dict(data: dict[str, Any]) -> SynthesisSourceLineage:
    return SynthesisSourceLineage(
        case_id=str(data["case_id"]),
        foundation_synthesis_id=str(data["foundation_synthesis_id"]),
        foundation_schema_version=str(data["foundation_schema_version"]),
        foundation_synthesiser_version=str(data["foundation_synthesiser_version"]),
        matrices_schema_version=str(data["matrices_schema_version"]),
        matrices_builder_version=str(data["matrices_builder_version"]),
        source_matrices_sha256=str(data["source_matrices_sha256"]),
        chronology_schema_version=str(data["chronology_schema_version"]),
        chronology_builder_version=str(data["chronology_builder_version"]),
        source_chronology_sha256=str(data["source_chronology_sha256"]),
        source_analysis_ids=tuple(data["source_analysis_ids"]),
    )


def _finding_to_dict(value: SynthesisFinding) -> dict[str, Any]:
    return {
        "finding_id": value.finding_id,
        "finding_type": value.finding_type.value,
        "analytical_bases": [item.value for item in value.analytical_bases],
        "scope": value.scope.value,
        "summary": value.summary,
        "status": value.status.value,
        "confidence": value.confidence.value,
        "provenance_refs": [_provenance_to_dict(item) for item in value.provenance_refs],
        "related_finding_ids": list(value.related_finding_ids),
    }


def _finding_from_dict(data: dict[str, Any]) -> SynthesisFinding:
    return SynthesisFinding(
        finding_id=str(data["finding_id"]),
        finding_type=FindingType(data["finding_type"]),
        analytical_bases=tuple(AnalyticalBasis(item) for item in data["analytical_bases"]),
        scope=FindingScope(data["scope"]),
        summary=str(data["summary"]),
        status=FindingStatus(data["status"]),
        confidence=Confidence(data["confidence"]),
        provenance_refs=tuple(_provenance_from_dict(item) for item in data["provenance_refs"]),
        related_finding_ids=tuple(data.get("related_finding_ids", ())),
    )


def _conflict_to_dict(value: MaterialConflict) -> dict[str, Any]:
    return {
        "conflict_id": value.conflict_id,
        "conflict_type": value.conflict_type.value,
        "scope": value.scope.value,
        "subject": value.subject,
        "side_a_refs": [_provenance_to_dict(item) for item in value.side_a_refs],
        "side_b_refs": [_provenance_to_dict(item) for item in value.side_b_refs],
        "materiality": value.materiality.value,
        "status": value.status.value,
        "related_issue_ids": list(value.related_issue_ids),
    }


def _conflict_from_dict(data: dict[str, Any]) -> MaterialConflict:
    return MaterialConflict(
        conflict_id=str(data["conflict_id"]),
        conflict_type=ConflictType(data["conflict_type"]),
        scope=FindingScope(data["scope"]),
        subject=str(data["subject"]),
        side_a_refs=tuple(_provenance_from_dict(item) for item in data["side_a_refs"]),
        side_b_refs=tuple(_provenance_from_dict(item) for item in data["side_b_refs"]),
        materiality=Materiality(data["materiality"]),
        status=FindingStatus(data["status"]),
        related_issue_ids=tuple(data["related_issue_ids"]),
    )


def _gap_to_dict(value: EvidenceGap) -> dict[str, Any]:
    return {
        "gap_id": value.gap_id,
        "gap_type": value.gap_type.value,
        "scope": value.scope.value,
        "issue_analysis_id": value.issue_analysis_id,
        "issue_definition_id": value.issue_definition_id,
        "issue_definition_version": value.issue_definition_version,
        "element_id": value.element_id,
        "description": value.description,
        "materiality": value.materiality.value,
        "unresolved_question": value.unresolved_question,
        "provenance_refs": [_provenance_to_dict(item) for item in value.provenance_refs],
        "related_finding_ids": list(value.related_finding_ids),
    }


def _gap_from_dict(data: dict[str, Any]) -> EvidenceGap:
    return EvidenceGap(
        gap_id=str(data["gap_id"]),
        gap_type=GapType(data["gap_type"]),
        scope=FindingScope(data["scope"]),
        issue_analysis_id=str(data["issue_analysis_id"]),
        issue_definition_id=str(data["issue_definition_id"]),
        issue_definition_version=str(data["issue_definition_version"]),
        element_id=str(data["element_id"]) if data.get("element_id") is not None else None,
        description=str(data["description"]),
        materiality=Materiality(data["materiality"]),
        unresolved_question=str(data["unresolved_question"]),
        provenance_refs=tuple(_provenance_from_dict(item) for item in data["provenance_refs"]),
        related_finding_ids=tuple(data.get("related_finding_ids", ())),
    )


def _risk_to_dict(value: RiskArea) -> dict[str, Any]:
    return {
        "risk_id": value.risk_id,
        "risk_type": value.risk_type.value,
        "scope": value.scope.value,
        "materiality": value.materiality.value,
        "description": value.description,
        "basis_finding_ids": list(value.basis_finding_ids),
        "conflict_ids": list(value.conflict_ids),
        "gap_ids": list(value.gap_ids),
        "provenance_refs": [_provenance_to_dict(item) for item in value.provenance_refs],
        "affected_issue_ids": list(value.affected_issue_ids),
    }


def _risk_from_dict(data: dict[str, Any]) -> RiskArea:
    return RiskArea(
        risk_id=str(data["risk_id"]),
        risk_type=RiskType(data["risk_type"]),
        scope=FindingScope(data["scope"]),
        materiality=Materiality(data["materiality"]),
        description=str(data["description"]),
        basis_finding_ids=tuple(data.get("basis_finding_ids", ())),
        conflict_ids=tuple(data.get("conflict_ids", ())),
        gap_ids=tuple(data.get("gap_ids", ())),
        provenance_refs=tuple(_provenance_from_dict(item) for item in data.get("provenance_refs", ())),
        affected_issue_ids=tuple(data.get("affected_issue_ids", ())),
    )


def _question_to_dict(value: PriorityQuestion) -> dict[str, Any]:
    return {
        "question_id": value.question_id,
        "question": value.question,
        "priority": value.priority.value,
        "basis_type": value.basis_type.value,
        "affected_issue_ids": list(value.affected_issue_ids),
        "affected_element_ids": list(value.affected_element_ids),
        "finding_ids": list(value.finding_ids),
        "gap_ids": list(value.gap_ids),
        "conflict_ids": list(value.conflict_ids),
        "provenance_refs": [_provenance_to_dict(item) for item in value.provenance_refs],
    }


def _question_from_dict(data: dict[str, Any]) -> PriorityQuestion:
    return PriorityQuestion(
        question_id=str(data["question_id"]),
        question=str(data["question"]),
        priority=PriorityLevel(data["priority"]),
        basis_type=PriorityBasis(data["basis_type"]),
        affected_issue_ids=tuple(data["affected_issue_ids"]),
        affected_element_ids=tuple(data.get("affected_element_ids", ())),
        finding_ids=tuple(data.get("finding_ids", ())),
        gap_ids=tuple(data.get("gap_ids", ())),
        conflict_ids=tuple(data.get("conflict_ids", ())),
        provenance_refs=tuple(_provenance_from_dict(item) for item in data.get("provenance_refs", ())),
    )


def _position_to_dict(value: IssuePosition) -> dict[str, Any]:
    return {
        "issue_definition_id": value.issue_definition_id,
        "issue_definition_version": value.issue_definition_version,
        "issue_analysis_id": value.issue_analysis_id,
        "issue_name": value.issue_name,
        "position_status": value.position_status.value,
        "basis_refs": [_provenance_to_dict(item) for item in value.basis_refs],
        "confidence": value.confidence.value,
        "material_finding_ids": list(value.material_finding_ids),
        "conflict_ids": list(value.conflict_ids),
        "gap_ids": list(value.gap_ids),
        "risk_ids": list(value.risk_ids),
    }


def _position_from_dict(data: dict[str, Any]) -> IssuePosition:
    return IssuePosition(
        issue_definition_id=str(data["issue_definition_id"]),
        issue_definition_version=str(data["issue_definition_version"]),
        issue_analysis_id=str(data["issue_analysis_id"]),
        issue_name=str(data["issue_name"]),
        position_status=IssuePositionStatus(data["position_status"]),
        basis_refs=tuple(_provenance_from_dict(item) for item in data["basis_refs"]),
        confidence=Confidence(data["confidence"]),
        material_finding_ids=tuple(data.get("material_finding_ids", ())),
        conflict_ids=tuple(data.get("conflict_ids", ())),
        gap_ids=tuple(data.get("gap_ids", ())),
        risk_ids=tuple(data.get("risk_ids", ())),
    )


def case_synthesis_to_dict(value: CaseSynthesis) -> dict[str, Any]:
    return {
        "schema_version": value.schema_version,
        "synthesiser_version": value.synthesiser_version,
        "case_id": value.case_id,
        "synthesis_id": value.synthesis_id,
        "source_lineage": _lineage_to_dict(value.source_lineage),
        "issue_positions": [_position_to_dict(item) for item in value.issue_positions],
        "findings": [_finding_to_dict(item) for item in value.findings],
        "conflicts": [_conflict_to_dict(item) for item in value.conflicts],
        "gaps": [_gap_to_dict(item) for item in value.gaps],
        "risks": [_risk_to_dict(item) for item in value.risks],
        "priority_questions": [_question_to_dict(item) for item in value.priority_questions],
        "overall_state": value.overall_state.value,
    }


def case_synthesis_from_dict(data: dict[str, Any]) -> CaseSynthesis:
    return CaseSynthesis(
        schema_version=str(data["schema_version"]),
        synthesiser_version=str(data["synthesiser_version"]),
        case_id=str(data["case_id"]),
        synthesis_id=str(data["synthesis_id"]),
        source_lineage=_lineage_from_dict(data["source_lineage"]),
        issue_positions=tuple(_position_from_dict(item) for item in data["issue_positions"]),
        findings=tuple(_finding_from_dict(item) for item in data.get("findings", ())),
        conflicts=tuple(_conflict_from_dict(item) for item in data.get("conflicts", ())),
        gaps=tuple(_gap_from_dict(item) for item in data.get("gaps", ())),
        risks=tuple(_risk_from_dict(item) for item in data.get("risks", ())),
        priority_questions=tuple(_question_from_dict(item) for item in data.get("priority_questions", ())),
        overall_state=OverallState(data["overall_state"]),
    )


def dumps_case_synthesis(value: CaseSynthesis) -> str:
    return json.dumps(
        case_synthesis_to_dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def loads_case_synthesis(payload: str) -> CaseSynthesis:
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("CaseSynthesis JSON root must be an object.")
    return case_synthesis_from_dict(data)


__all__ = [
    "case_synthesis_from_dict",
    "case_synthesis_to_dict",
    "dumps_case_synthesis",
    "loads_case_synthesis",
]
