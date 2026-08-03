"""Deterministic JSON serialization for Sprint 2.4 Milestone 2 matrices."""

from __future__ import annotations

import json
from typing import Any

from evidence_classification import EvidenceSourceType
from legal_analysis.enums import (
    AnalyticalRole,
    Confidence,
    EvidenceStatus,
    ProvenanceBasis,
    ProvenanceConfidence,
)
from legal_analysis.evidence_assessment import PropositionAssessmentStatus
from legal_analysis.evidence_mapping import EvidenceRelevance
from legal_analysis.legal_analysis import ElementAnalysisStatus, EvidenceBackedStatement

from .matrices import (
    CASE_MATRICES_SCHEMA_VERSION,
    CASE_MATRIX_BUILDER_VERSION,
    CaseEvidenceRecord,
    CaseMatrices,
    EvidencePropositionLink,
    EvidenceUse,
    IssueElementRecord,
    IssueMatrixRecord,
)
from .matrix_validation import validate_case_matrices


def _statement_to_dict(value: EvidenceBackedStatement) -> dict[str, Any]:
    return {
        "text": value.text,
        "evidence_keys": list(value.evidence_keys),
        "citations": list(value.citations),
    }


def _statement_from_dict(value: dict[str, Any]) -> EvidenceBackedStatement:
    return EvidenceBackedStatement(
        text=value["text"],
        evidence_keys=tuple(value["evidence_keys"]),
        citations=tuple(value["citations"]),
    )


def _proposition_link_to_dict(value: EvidencePropositionLink) -> dict[str, Any]:
    return {
        "source_proposition_index": value.source_proposition_index,
        "text": value.text,
        "status": value.status.value,
        "confidence": value.confidence.value,
        "rationale": value.rationale,
        "evidence_keys": list(value.evidence_keys),
    }


def _proposition_link_from_dict(value: dict[str, Any]) -> EvidencePropositionLink:
    return EvidencePropositionLink(
        source_proposition_index=int(value["source_proposition_index"]),
        text=value["text"],
        status=PropositionAssessmentStatus(value["status"]),
        confidence=Confidence(value["confidence"]),
        rationale=value["rationale"],
        evidence_keys=tuple(value["evidence_keys"]),
    )


def _use_to_dict(value: EvidenceUse) -> dict[str, Any]:
    return {
        "issue_analysis_id": value.issue_analysis_id,
        "issue_definition_id": value.issue_definition_id,
        "issue_definition_version": value.issue_definition_version,
        "element_id": value.element_id,
        "element_ordinal": value.element_ordinal,
        "evidence_key": value.evidence_key,
        "analytical_role": value.analytical_role.value,
        "mapping_relevance": value.mapping_relevance.value,
        "mapping_confidence": value.mapping_confidence.value,
        "mapping_rationale": value.mapping_rationale,
        "assessment_confidence": value.assessment_confidence.value,
        "assessment_rationale": value.assessment_rationale,
        "proposition_links": [_proposition_link_to_dict(item) for item in value.proposition_links],
        "citation": value.citation,
    }


def _use_from_dict(value: dict[str, Any]) -> EvidenceUse:
    return EvidenceUse(
        issue_analysis_id=value["issue_analysis_id"],
        issue_definition_id=value["issue_definition_id"],
        issue_definition_version=value["issue_definition_version"],
        element_id=value["element_id"],
        element_ordinal=int(value["element_ordinal"]),
        evidence_key=value["evidence_key"],
        analytical_role=AnalyticalRole(value["analytical_role"]),
        mapping_relevance=EvidenceRelevance(value["mapping_relevance"]),
        mapping_confidence=Confidence(value["mapping_confidence"]),
        mapping_rationale=value["mapping_rationale"],
        assessment_confidence=Confidence(value["assessment_confidence"]),
        assessment_rationale=value["assessment_rationale"],
        proposition_links=tuple(_proposition_link_from_dict(item) for item in value["proposition_links"]),
        citation=value["citation"],
    )


def _evidence_to_dict(value: CaseEvidenceRecord) -> dict[str, Any]:
    return {
        "evidence_key": value.evidence_key,
        "document_id": value.document_id,
        "document_name": value.document_name,
        "page": value.page,
        "chunk_id": value.chunk_id,
        "citation": value.citation,
        "source_type": value.source_type.value,
        "evidence_status": value.evidence_status.value,
        "provenance_type": value.provenance_type.value,
        "provenance_basis": value.provenance_basis.value,
        "provenance_confidence": value.provenance_confidence.value,
        "date": value.date.isoformat() if value.date is not None else None,
        "author": value.author,
        "parties": list(value.parties),
        "uses": [_use_to_dict(item) for item in value.uses],
    }


def _evidence_from_dict(value: dict[str, Any]) -> CaseEvidenceRecord:
    from datetime import date

    return CaseEvidenceRecord(
        evidence_key=value["evidence_key"],
        document_id=value.get("document_id"),
        document_name=value["document_name"],
        page=value.get("page"),
        chunk_id=value.get("chunk_id"),
        citation=value["citation"],
        source_type=EvidenceSourceType(value["source_type"]),
        evidence_status=EvidenceStatus(value["evidence_status"]),
        provenance_type=EvidenceSourceType(value["provenance_type"]),
        provenance_basis=ProvenanceBasis(value["provenance_basis"]),
        provenance_confidence=ProvenanceConfidence(value["provenance_confidence"]),
        date=date.fromisoformat(value["date"]) if value.get("date") else None,
        author=value.get("author"),
        parties=tuple(value.get("parties", ())),
        uses=tuple(_use_from_dict(item) for item in value["uses"]),
    )


def _element_to_dict(value: IssueElementRecord) -> dict[str, Any]:
    return {
        "element_id": value.element_id,
        "element_name": value.element_name,
        "legal_question": value.legal_question,
        "analysis_status": value.analysis_status.value,
        "analysis_confidence": value.analysis_confidence.value,
        "established_matters": [_statement_to_dict(item) for item in value.established_matters],
        "supported_matters": [_statement_to_dict(item) for item in value.supported_matters],
        "not_supported_matters": [_statement_to_dict(item) for item in value.not_supported_matters],
        "source_assertions": [_statement_to_dict(item) for item in value.source_assertions],
        "supporting_evidence_keys": list(value.supporting_evidence_keys),
        "adverse_evidence_keys": list(value.adverse_evidence_keys),
        "corroborative_evidence_keys": list(value.corroborative_evidence_keys),
        "neutral_evidence_keys": list(value.neutral_evidence_keys),
        "conflicting_evidence_keys": list(value.conflicting_evidence_keys),
        "disputed_matter_ids": list(value.disputed_matter_ids),
        "evidential_gap_ids": list(value.evidential_gap_ids),
        "unresolved_matters": list(value.unresolved_matters),
        "legal_significance": value.legal_significance,
        "provisional_analysis": value.provisional_analysis,
    }


def _element_from_dict(value: dict[str, Any]) -> IssueElementRecord:
    return IssueElementRecord(
        element_id=value["element_id"],
        element_name=value["element_name"],
        legal_question=value["legal_question"],
        analysis_status=ElementAnalysisStatus(value["analysis_status"]),
        analysis_confidence=Confidence(value["analysis_confidence"]),
        established_matters=tuple(_statement_from_dict(item) for item in value["established_matters"]),
        supported_matters=tuple(_statement_from_dict(item) for item in value["supported_matters"]),
        not_supported_matters=tuple(_statement_from_dict(item) for item in value["not_supported_matters"]),
        source_assertions=tuple(_statement_from_dict(item) for item in value["source_assertions"]),
        supporting_evidence_keys=tuple(value["supporting_evidence_keys"]),
        adverse_evidence_keys=tuple(value["adverse_evidence_keys"]),
        corroborative_evidence_keys=tuple(value["corroborative_evidence_keys"]),
        neutral_evidence_keys=tuple(value["neutral_evidence_keys"]),
        conflicting_evidence_keys=tuple(value["conflicting_evidence_keys"]),
        disputed_matter_ids=tuple(value["disputed_matter_ids"]),
        evidential_gap_ids=tuple(value["evidential_gap_ids"]),
        unresolved_matters=tuple(value["unresolved_matters"]),
        legal_significance=value["legal_significance"],
        provisional_analysis=value["provisional_analysis"],
    )


def _issue_to_dict(value: IssueMatrixRecord) -> dict[str, Any]:
    return {
        "issue_analysis_id": value.issue_analysis_id,
        "issue_definition_id": value.issue_definition_id,
        "issue_definition_version": value.issue_definition_version,
        "issue_name": value.issue_name,
        "original_user_question": value.original_user_question,
        "issue_summary": value.issue_summary,
        "element_records": [_element_to_dict(item) for item in value.element_records],
        "analyser_version": value.analyser_version,
    }


def _issue_from_dict(value: dict[str, Any]) -> IssueMatrixRecord:
    return IssueMatrixRecord(
        issue_analysis_id=value["issue_analysis_id"],
        issue_definition_id=value["issue_definition_id"],
        issue_definition_version=value["issue_definition_version"],
        issue_name=value["issue_name"],
        original_user_question=value["original_user_question"],
        issue_summary=value["issue_summary"],
        element_records=tuple(_element_from_dict(item) for item in value["element_records"]),
        analyser_version=value["analyser_version"],
    )


def case_matrices_to_dict(value: CaseMatrices) -> dict[str, Any]:
    """Return the durable deterministic JSON-ready M2 representation."""

    validate_case_matrices(value)
    return {
        "schema_version": value.schema_version,
        "matrix_builder_version": value.matrix_builder_version,
        "case_id": value.case_id,
        "synthesis_id": value.synthesis_id,
        "source_analysis_ids": list(value.source_analysis_ids),
        "issue_matrix": [_issue_to_dict(item) for item in value.issue_matrix],
        "evidence_matrix": [_evidence_to_dict(item) for item in value.evidence_matrix],
    }


def case_matrices_from_dict(value: dict[str, Any]) -> CaseMatrices:
    """Restore and validate one M2 matrix object from its durable form."""

    result = CaseMatrices(
        case_id=value["case_id"],
        synthesis_id=value["synthesis_id"],
        source_analysis_ids=tuple(value["source_analysis_ids"]),
        issue_matrix=tuple(_issue_from_dict(item) for item in value["issue_matrix"]),
        evidence_matrix=tuple(_evidence_from_dict(item) for item in value["evidence_matrix"]),
        schema_version=value.get("schema_version", CASE_MATRICES_SCHEMA_VERSION),
        matrix_builder_version=value.get("matrix_builder_version", CASE_MATRIX_BUILDER_VERSION),
    )
    validate_case_matrices(result)
    return result


def dumps_case_matrices(value: CaseMatrices) -> str:
    return json.dumps(
        case_matrices_to_dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def loads_case_matrices(payload: str) -> CaseMatrices:
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("Case matrix JSON must contain an object at the root.")
    return case_matrices_from_dict(parsed)


__all__ = [
    "case_matrices_from_dict",
    "case_matrices_to_dict",
    "dumps_case_matrices",
    "loads_case_matrices",
]
