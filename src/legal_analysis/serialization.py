"""Deterministic serialization for Sprint 2.3 structured analysis records."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from evidence_classification import EvidenceSourceType

from .enums import (
    AnalysisStatus,
    AnalyticalRole,
    Confidence,
    EvidenceStatus,
    Materiality,
    ProvenanceBasis,
    ProvenanceConfidence,
)
from .models import (
    DisputedMatter,
    ElementAnalysis,
    EvidentialGap,
    EvidenceReference,
    IssueAnalysis,
    Proposition,
)


def evidence_reference_to_dict(value: EvidenceReference) -> dict[str, Any]:
    """Serialize an EvidenceReference into JSON-compatible data."""

    return {
        "document_id": value.document_id,
        "document_name": value.document_name,
        "page": value.page,
        "chunk_id": value.chunk_id,
        "summary": value.summary,
        "source_type": value.source_type.value,
        "provenance_type": value.provenance_type.value if value.provenance_type else None,
        "provenance_basis": value.provenance_basis.value,
        "provenance_confidence": value.provenance_confidence.value,
        "evidence_status": value.evidence_status.value,
        "analytical_role": value.analytical_role.value,
        "date": value.date.isoformat() if value.date else None,
        "author": value.author,
        "parties": list(value.parties),
        "citation": value.citation,
    }


def evidence_reference_from_dict(data: dict[str, Any]) -> EvidenceReference:
    """Deserialize an EvidenceReference."""

    return EvidenceReference(
        document_id=data.get("document_id"),
        document_name=str(data["document_name"]),
        page=data.get("page"),
        chunk_id=data.get("chunk_id"),
        summary=str(data["summary"]),
        source_type=EvidenceSourceType(str(data["source_type"])),
        provenance_type=(
            EvidenceSourceType(str(data["provenance_type"]))
            if data.get("provenance_type") is not None
            else None
        ),
        provenance_basis=ProvenanceBasis(str(data["provenance_basis"])),
        provenance_confidence=ProvenanceConfidence(
            str(data["provenance_confidence"])
        ),
        evidence_status=EvidenceStatus(str(data["evidence_status"])),
        analytical_role=AnalyticalRole(str(data["analytical_role"])),
        date=date.fromisoformat(str(data["date"])) if data.get("date") else None,
        author=data.get("author"),
        parties=tuple(str(item) for item in data.get("parties", [])),
        citation=str(data["citation"]),
    )


def _proposition_to_dict(value: Proposition) -> dict[str, Any]:
    return {
        "proposition_id": value.proposition_id,
        "text": value.text,
        "status": value.status.value,
        "confidence": value.confidence.value,
        "evidence": [evidence_reference_to_dict(item) for item in value.evidence],
    }


def _proposition_from_dict(data: dict[str, Any]) -> Proposition:
    return Proposition(
        proposition_id=str(data["proposition_id"]),
        text=str(data["text"]),
        status=EvidenceStatus(str(data["status"])),
        confidence=Confidence(str(data["confidence"])),
        evidence=tuple(
            evidence_reference_from_dict(item) for item in data.get("evidence", [])
        ),
    )


def _disputed_matter_to_dict(value: DisputedMatter) -> dict[str, Any]:
    return {
        "disputed_matter_id": value.disputed_matter_id,
        "proposition": value.proposition,
        "claimant_position": value.claimant_position,
        "respondent_position": value.respondent_position,
        "claimant_evidence": [
            evidence_reference_to_dict(item) for item in value.claimant_evidence
        ],
        "respondent_evidence": [
            evidence_reference_to_dict(item) for item in value.respondent_evidence
        ],
        "contemporaneous_evidence": [
            evidence_reference_to_dict(item) for item in value.contemporaneous_evidence
        ],
        "presently_established": value.presently_established,
        "remains_unresolved": value.remains_unresolved,
    }


def _disputed_matter_from_dict(data: dict[str, Any]) -> DisputedMatter:
    return DisputedMatter(
        disputed_matter_id=str(data["disputed_matter_id"]),
        proposition=str(data["proposition"]),
        claimant_position=data.get("claimant_position"),
        respondent_position=data.get("respondent_position"),
        claimant_evidence=tuple(
            evidence_reference_from_dict(item)
            for item in data.get("claimant_evidence", [])
        ),
        respondent_evidence=tuple(
            evidence_reference_from_dict(item)
            for item in data.get("respondent_evidence", [])
        ),
        contemporaneous_evidence=tuple(
            evidence_reference_from_dict(item)
            for item in data.get("contemporaneous_evidence", [])
        ),
        presently_established=data.get("presently_established"),
        remains_unresolved=data.get("remains_unresolved"),
    )


def _gap_to_dict(value: EvidentialGap) -> dict[str, Any]:
    return {
        "gap_id": value.gap_id,
        "description": value.description,
        "related_element_id": value.related_element_id,
        "materiality": value.materiality.value,
        "reason": value.reason,
        "suggested_evidence_target": value.suggested_evidence_target,
    }


def _gap_from_dict(data: dict[str, Any]) -> EvidentialGap:
    return EvidentialGap(
        gap_id=str(data["gap_id"]),
        description=str(data["description"]),
        related_element_id=str(data["related_element_id"]),
        materiality=Materiality(str(data["materiality"])),
        reason=str(data["reason"]),
        suggested_evidence_target=data.get("suggested_evidence_target"),
    )


def _element_to_dict(value: ElementAnalysis) -> dict[str, Any]:
    return {
        "element_id": value.element_id,
        "element_name": value.element_name,
        "question_to_determine": value.question_to_determine,
        "propositions": [_proposition_to_dict(item) for item in value.propositions],
        "supporting_evidence": [
            evidence_reference_to_dict(item) for item in value.supporting_evidence
        ],
        "adverse_evidence": [
            evidence_reference_to_dict(item) for item in value.adverse_evidence
        ],
        "corroborative_evidence": [
            evidence_reference_to_dict(item) for item in value.corroborative_evidence
        ],
        "neutral_evidence": [
            evidence_reference_to_dict(item) for item in value.neutral_evidence
        ],
        "conflicting_evidence": [
            evidence_reference_to_dict(item) for item in value.conflicting_evidence
        ],
        "disputed_matters": [
            _disputed_matter_to_dict(item) for item in value.disputed_matters
        ],
        "inferences": [_proposition_to_dict(item) for item in value.inferences],
        "evidential_gaps": [_gap_to_dict(item) for item in value.evidential_gaps],
        "respondent_position": list(value.respondent_position),
        "legal_analysis": value.legal_analysis,
        "assessment": value.assessment,
        "confidence": value.confidence.value if value.confidence else None,
    }


def _element_from_dict(data: dict[str, Any]) -> ElementAnalysis:
    return ElementAnalysis(
        element_id=str(data["element_id"]),
        element_name=str(data["element_name"]),
        question_to_determine=str(data["question_to_determine"]),
        propositions=tuple(
            _proposition_from_dict(item) for item in data.get("propositions", [])
        ),
        supporting_evidence=tuple(
            evidence_reference_from_dict(item)
            for item in data.get("supporting_evidence", [])
        ),
        adverse_evidence=tuple(
            evidence_reference_from_dict(item)
            for item in data.get("adverse_evidence", [])
        ),
        corroborative_evidence=tuple(
            evidence_reference_from_dict(item)
            for item in data.get("corroborative_evidence", [])
        ),
        neutral_evidence=tuple(
            evidence_reference_from_dict(item)
            for item in data.get("neutral_evidence", [])
        ),
        conflicting_evidence=tuple(
            evidence_reference_from_dict(item)
            for item in data.get("conflicting_evidence", [])
        ),
        disputed_matters=tuple(
            _disputed_matter_from_dict(item)
            for item in data.get("disputed_matters", [])
        ),
        inferences=tuple(
            _proposition_from_dict(item) for item in data.get("inferences", [])
        ),
        evidential_gaps=tuple(
            _gap_from_dict(item) for item in data.get("evidential_gaps", [])
        ),
        respondent_position=tuple(
            str(item) for item in data.get("respondent_position", [])
        ),
        legal_analysis=data.get("legal_analysis"),
        assessment=data.get("assessment"),
        confidence=(
            Confidence(str(data["confidence"])) if data.get("confidence") else None
        ),
    )


def issue_analysis_to_dict(value: IssueAnalysis) -> dict[str, Any]:
    """Serialize IssueAnalysis deterministically to JSON-compatible data."""

    return {
        "schema_version": value.schema_version,
        "issue_analysis_id": value.issue_analysis_id,
        "case_id": value.case_id,
        "issue_definition_id": value.issue_definition_id,
        "issue_definition_version": value.issue_definition_version,
        "issue_name": value.issue_name,
        "user_question": value.user_question,
        "legal_framework": list(value.legal_framework),
        "analysis_status": value.analysis_status.value,
        "elements": [_element_to_dict(item) for item in value.elements],
        "created_at": value.created_at.isoformat(),
    }


def issue_analysis_from_dict(data: dict[str, Any]) -> IssueAnalysis:
    """Deserialize an IssueAnalysis from JSON-compatible data."""

    return IssueAnalysis(
        schema_version=str(data["schema_version"]),
        issue_analysis_id=str(data["issue_analysis_id"]),
        case_id=str(data["case_id"]),
        issue_definition_id=str(data["issue_definition_id"]),
        issue_definition_version=str(data["issue_definition_version"]),
        issue_name=str(data["issue_name"]),
        user_question=str(data["user_question"]),
        legal_framework=tuple(str(item) for item in data.get("legal_framework", [])),
        analysis_status=AnalysisStatus(str(data["analysis_status"])),
        elements=tuple(_element_from_dict(item) for item in data.get("elements", [])),
        created_at=datetime.fromisoformat(str(data["created_at"])),
    )


def dumps_issue_analysis(value: IssueAnalysis) -> str:
    """Return a deterministic JSON representation of IssueAnalysis."""

    return json.dumps(
        issue_analysis_to_dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def loads_issue_analysis(payload: str) -> IssueAnalysis:
    """Load IssueAnalysis from deterministic JSON."""

    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("IssueAnalysis JSON payload must contain an object.")
    return issue_analysis_from_dict(data)
