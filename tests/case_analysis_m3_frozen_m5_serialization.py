"""Harness-only lossless serialization for Sprint 2.4 M3 frozen M5 inputs.

This module deliberately lives under ``tests``.  It serializes the complete
``StructuredLegalAnalysisResult`` graph for acceptance-harness use without
modifying frozen Sprint 2.3 or production M3 runtime code.
"""

from __future__ import annotations

import json
from typing import Any

from legal_analysis.enums import AnalyticalRole, Confidence, Materiality
from legal_analysis.evidence_assessment import (
    AssessedProposition,
    ElementEvidenceAssessment,
    EvidenceAssessment,
    EvidenceAssessmentResult,
    PropositionAssessmentStatus,
)
from legal_analysis.evidence_mapping import (
    ElementMappingResult,
    EvidenceMapping,
    EvidenceRelevance,
    MappedIssueAnalysis,
)
from legal_analysis.legal_analysis import (
    ElementAnalysisStatus,
    ElementLegalAnalysis,
    EvidenceBackedStatement,
    IssueLevelSynthesis,
    StructuredLegalAnalysisResult,
)
from legal_analysis.models import DisputedMatter, EvidentialGap
from legal_analysis.serialization import (
    evidence_reference_from_dict,
    evidence_reference_to_dict,
    issue_analysis_from_dict,
    issue_analysis_to_dict,
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
            evidence_reference_to_dict(item)
            for item in value.contemporaneous_evidence
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


def _evidence_mapping_to_dict(value: EvidenceMapping) -> dict[str, Any]:
    return {
        "evidence": evidence_reference_to_dict(value.evidence),
        "issue_definition_id": value.issue_definition_id,
        "issue_definition_version": value.issue_definition_version,
        "element_id": value.element_id,
        "relevance": value.relevance.value,
        "mapping_confidence": value.mapping_confidence.value,
        "mapping_rationale": value.mapping_rationale,
        "mapper_version": value.mapper_version,
    }


def _evidence_mapping_from_dict(data: dict[str, Any]) -> EvidenceMapping:
    return EvidenceMapping(
        evidence=evidence_reference_from_dict(data["evidence"]),
        issue_definition_id=str(data["issue_definition_id"]),
        issue_definition_version=str(data["issue_definition_version"]),
        element_id=str(data["element_id"]),
        relevance=EvidenceRelevance(str(data["relevance"])),
        mapping_confidence=Confidence(str(data["mapping_confidence"])),
        mapping_rationale=str(data["mapping_rationale"]),
        mapper_version=str(data["mapper_version"]),
    )


def _element_mapping_result_to_dict(value: ElementMappingResult) -> dict[str, Any]:
    return {
        "element_id": value.element_id,
        "search_query": value.search_query,
        "mappings": [_evidence_mapping_to_dict(item) for item in value.mappings],
    }


def _element_mapping_result_from_dict(data: dict[str, Any]) -> ElementMappingResult:
    return ElementMappingResult(
        element_id=str(data["element_id"]),
        search_query=str(data["search_query"]),
        mappings=tuple(
            _evidence_mapping_from_dict(item) for item in data.get("mappings", [])
        ),
    )


def _mapped_issue_analysis_to_dict(value: MappedIssueAnalysis) -> dict[str, Any]:
    return {
        "analysis": issue_analysis_to_dict(value.analysis),
        "element_results": [
            _element_mapping_result_to_dict(item) for item in value.element_results
        ],
        "mapper_version": value.mapper_version,
    }


def _mapped_issue_analysis_from_dict(data: dict[str, Any]) -> MappedIssueAnalysis:
    return MappedIssueAnalysis(
        analysis=issue_analysis_from_dict(data["analysis"]),
        element_results=tuple(
            _element_mapping_result_from_dict(item)
            for item in data.get("element_results", [])
        ),
        mapper_version=str(data["mapper_version"]),
    )


def _evidence_assessment_to_dict(value: EvidenceAssessment) -> dict[str, Any]:
    return {
        "mapping": _evidence_mapping_to_dict(value.mapping),
        "analytical_role": value.analytical_role.value,
        "assessment_confidence": value.assessment_confidence.value,
        "assessment_rationale": value.assessment_rationale,
    }


def _evidence_assessment_from_dict(data: dict[str, Any]) -> EvidenceAssessment:
    return EvidenceAssessment(
        mapping=_evidence_mapping_from_dict(data["mapping"]),
        analytical_role=AnalyticalRole(str(data["analytical_role"])),
        assessment_confidence=Confidence(str(data["assessment_confidence"])),
        assessment_rationale=str(data["assessment_rationale"]),
    )


def _assessed_proposition_to_dict(value: AssessedProposition) -> dict[str, Any]:
    return {
        "text": value.text,
        "status": value.status.value,
        "confidence": value.confidence.value,
        "evidence_keys": list(value.evidence_keys),
        "rationale": value.rationale,
    }


def _assessed_proposition_from_dict(data: dict[str, Any]) -> AssessedProposition:
    return AssessedProposition(
        text=str(data["text"]),
        status=PropositionAssessmentStatus(str(data["status"])),
        confidence=Confidence(str(data["confidence"])),
        evidence_keys=tuple(str(item) for item in data.get("evidence_keys", [])),
        rationale=str(data["rationale"]),
    )


def _element_evidence_assessment_to_dict(
    value: ElementEvidenceAssessment,
) -> dict[str, Any]:
    return {
        "element_id": value.element_id,
        "evidence_assessments": [
            _evidence_assessment_to_dict(item) for item in value.evidence_assessments
        ],
        "assessed_propositions": [
            _assessed_proposition_to_dict(item) for item in value.assessed_propositions
        ],
        "disputed_matters": [
            _disputed_matter_to_dict(item) for item in value.disputed_matters
        ],
        "evidential_gaps": [_gap_to_dict(item) for item in value.evidential_gaps],
        "presently_established": list(value.presently_established),
        "unresolved_matters": list(value.unresolved_matters),
        "assessment_confidence": value.assessment_confidence.value,
        "assessment_rationale": value.assessment_rationale,
    }


def _element_evidence_assessment_from_dict(
    data: dict[str, Any],
) -> ElementEvidenceAssessment:
    return ElementEvidenceAssessment(
        element_id=str(data["element_id"]),
        evidence_assessments=tuple(
            _evidence_assessment_from_dict(item)
            for item in data.get("evidence_assessments", [])
        ),
        assessed_propositions=tuple(
            _assessed_proposition_from_dict(item)
            for item in data.get("assessed_propositions", [])
        ),
        disputed_matters=tuple(
            _disputed_matter_from_dict(item)
            for item in data.get("disputed_matters", [])
        ),
        evidential_gaps=tuple(
            _gap_from_dict(item) for item in data.get("evidential_gaps", [])
        ),
        presently_established=tuple(
            str(item) for item in data.get("presently_established", [])
        ),
        unresolved_matters=tuple(
            str(item) for item in data.get("unresolved_matters", [])
        ),
        assessment_confidence=Confidence(str(data["assessment_confidence"])),
        assessment_rationale=str(data["assessment_rationale"]),
    )


def _evidence_assessment_result_to_dict(
    value: EvidenceAssessmentResult,
) -> dict[str, Any]:
    return {
        "mapping_result": _mapped_issue_analysis_to_dict(value.mapping_result),
        "assessed_analysis": issue_analysis_to_dict(value.assessed_analysis),
        "element_assessments": [
            _element_evidence_assessment_to_dict(item)
            for item in value.element_assessments
        ],
        "assessor_version": value.assessor_version,
    }


def _evidence_assessment_result_from_dict(
    data: dict[str, Any],
) -> EvidenceAssessmentResult:
    return EvidenceAssessmentResult(
        mapping_result=_mapped_issue_analysis_from_dict(data["mapping_result"]),
        assessed_analysis=issue_analysis_from_dict(data["assessed_analysis"]),
        element_assessments=tuple(
            _element_evidence_assessment_from_dict(item)
            for item in data.get("element_assessments", [])
        ),
        assessor_version=str(data["assessor_version"]),
    )


def _evidence_backed_statement_to_dict(
    value: EvidenceBackedStatement,
) -> dict[str, Any]:
    return {
        "text": value.text,
        "evidence_keys": list(value.evidence_keys),
        "citations": list(value.citations),
    }


def _evidence_backed_statement_from_dict(
    data: dict[str, Any],
) -> EvidenceBackedStatement:
    return EvidenceBackedStatement(
        text=str(data["text"]),
        evidence_keys=tuple(str(item) for item in data.get("evidence_keys", [])),
        citations=tuple(str(item) for item in data.get("citations", [])),
    )


def _element_legal_analysis_to_dict(value: ElementLegalAnalysis) -> dict[str, Any]:
    statement_fields = (
        "established_matters",
        "supported_matters",
        "not_supported_matters",
        "source_assertions",
        "adverse_material",
        "corroborative_material",
        "contextual_material",
        "conflicting_material",
    )
    data: dict[str, Any] = {
        "issue_definition_id": value.issue_definition_id,
        "issue_definition_version": value.issue_definition_version,
        "element_id": value.element_id,
        "legal_question": value.legal_question,
        "current_evidential_position": value.current_evidential_position,
        "disputed_matters": [
            _disputed_matter_to_dict(item) for item in value.disputed_matters
        ],
        "legal_significance": value.legal_significance,
        "limitations": list(value.limitations),
        "unresolved_matters": list(value.unresolved_matters),
        "evidential_gaps": [_gap_to_dict(item) for item in value.evidential_gaps],
        "provisional_status": value.provisional_status.value,
        "provisional_analysis": value.provisional_analysis,
        "analysis_confidence": value.analysis_confidence.value,
        "analyser_version": value.analyser_version,
    }
    for field_name in statement_fields:
        data[field_name] = [
            _evidence_backed_statement_to_dict(item)
            for item in getattr(value, field_name)
        ]
    return data


def _element_legal_analysis_from_dict(data: dict[str, Any]) -> ElementLegalAnalysis:
    def statements(field_name: str) -> tuple[EvidenceBackedStatement, ...]:
        return tuple(
            _evidence_backed_statement_from_dict(item)
            for item in data.get(field_name, [])
        )

    return ElementLegalAnalysis(
        issue_definition_id=str(data["issue_definition_id"]),
        issue_definition_version=str(data["issue_definition_version"]),
        element_id=str(data["element_id"]),
        legal_question=str(data["legal_question"]),
        current_evidential_position=str(data["current_evidential_position"]),
        established_matters=statements("established_matters"),
        supported_matters=statements("supported_matters"),
        not_supported_matters=statements("not_supported_matters"),
        source_assertions=statements("source_assertions"),
        adverse_material=statements("adverse_material"),
        corroborative_material=statements("corroborative_material"),
        contextual_material=statements("contextual_material"),
        conflicting_material=statements("conflicting_material"),
        disputed_matters=tuple(
            _disputed_matter_from_dict(item)
            for item in data.get("disputed_matters", [])
        ),
        legal_significance=str(data["legal_significance"]),
        limitations=tuple(str(item) for item in data.get("limitations", [])),
        unresolved_matters=tuple(
            str(item) for item in data.get("unresolved_matters", [])
        ),
        evidential_gaps=tuple(
            _gap_from_dict(item) for item in data.get("evidential_gaps", [])
        ),
        provisional_status=ElementAnalysisStatus(str(data["provisional_status"])),
        provisional_analysis=str(data["provisional_analysis"]),
        analysis_confidence=Confidence(str(data["analysis_confidence"])),
        analyser_version=str(data["analyser_version"]),
    )


def _issue_synthesis_to_dict(value: IssueLevelSynthesis) -> dict[str, Any]:
    return {
        "well_supported_elements": list(value.well_supported_elements),
        "partially_supported_elements": list(value.partially_supported_elements),
        "disputed_elements": list(value.disputed_elements),
        "insufficiently_evidenced_elements": list(
            value.insufficiently_evidenced_elements
        ),
        "unresolved_elements": list(value.unresolved_elements),
        "summary": value.summary,
    }


def _issue_synthesis_from_dict(data: dict[str, Any]) -> IssueLevelSynthesis:
    return IssueLevelSynthesis(
        well_supported_elements=tuple(
            str(item) for item in data.get("well_supported_elements", [])
        ),
        partially_supported_elements=tuple(
            str(item) for item in data.get("partially_supported_elements", [])
        ),
        disputed_elements=tuple(
            str(item) for item in data.get("disputed_elements", [])
        ),
        insufficiently_evidenced_elements=tuple(
            str(item) for item in data.get("insufficiently_evidenced_elements", [])
        ),
        unresolved_elements=tuple(
            str(item) for item in data.get("unresolved_elements", [])
        ),
        summary=str(data["summary"]),
    )


def structured_legal_analysis_result_to_dict(
    value: StructuredLegalAnalysisResult,
) -> dict[str, Any]:
    """Serialize one complete M5 result graph to JSON-compatible data."""

    return {
        "assessment_result": _evidence_assessment_result_to_dict(
            value.assessment_result
        ),
        "element_analyses": [
            _element_legal_analysis_to_dict(item) for item in value.element_analyses
        ],
        "issue_synthesis": _issue_synthesis_to_dict(value.issue_synthesis),
        "overall_limitations": list(value.overall_limitations),
        "analyser_version": value.analyser_version,
    }


def structured_legal_analysis_result_from_dict(
    data: dict[str, Any],
) -> StructuredLegalAnalysisResult:
    """Deserialize one complete M5 result graph from JSON-compatible data."""

    return StructuredLegalAnalysisResult(
        assessment_result=_evidence_assessment_result_from_dict(
            data["assessment_result"]
        ),
        element_analyses=tuple(
            _element_legal_analysis_from_dict(item)
            for item in data.get("element_analyses", [])
        ),
        issue_synthesis=_issue_synthesis_from_dict(data["issue_synthesis"]),
        overall_limitations=tuple(
            str(item) for item in data.get("overall_limitations", [])
        ),
        analyser_version=str(data["analyser_version"]),
    )


def dumps_structured_legal_analysis_result(
    value: StructuredLegalAnalysisResult,
) -> str:
    """Return canonical deterministic JSON for one complete M5 result."""

    return json.dumps(
        structured_legal_analysis_result_to_dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def loads_structured_legal_analysis_result(
    payload: str,
) -> StructuredLegalAnalysisResult:
    """Load one complete M5 result from canonical JSON."""

    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("StructuredLegalAnalysisResult payload must contain an object.")
    return structured_legal_analysis_result_from_dict(data)


__all__ = [
    "dumps_structured_legal_analysis_result",
    "loads_structured_legal_analysis_result",
    "structured_legal_analysis_result_from_dict",
    "structured_legal_analysis_result_to_dict",
]
