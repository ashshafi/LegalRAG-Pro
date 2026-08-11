"""Canonical lossless serialization for governed analytical authorities.

The complete ``StructuredLegalAnalysisResult`` serializer is a production promotion
of the frozen Sprint 2.4 M3 Gate-1 serializer.  It preserves semantically meaningful
inner ordering and canonicalises only the outer result set.  No analysis is rebuilt.
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


_M5_RESULT_KEYS = frozenset({
    "assessment_result", "element_analyses", "issue_synthesis",
    "overall_limitations", "analyser_version",
})
_M4_RESULT_KEYS = frozenset({
    "mapping_result", "assessed_analysis", "element_assessments", "assessor_version",
})
_MAPPED_ISSUE_KEYS = frozenset({"analysis", "element_results", "mapper_version"})
_ELEMENT_MAPPING_KEYS = frozenset({"element_id", "search_query", "mappings"})
_EVIDENCE_MAPPING_KEYS = frozenset({
    "evidence", "issue_definition_id", "issue_definition_version", "element_id",
    "relevance", "mapping_confidence", "mapping_rationale", "mapper_version",
})
_ELEMENT_ASSESSMENT_KEYS = frozenset({
    "element_id", "evidence_assessments", "assessed_propositions", "disputed_matters",
    "evidential_gaps", "presently_established", "unresolved_matters",
    "assessment_confidence", "assessment_rationale",
})
_EVIDENCE_ASSESSMENT_KEYS = frozenset({
    "mapping", "analytical_role", "assessment_confidence", "assessment_rationale",
})
_ASSESSED_PROPOSITION_KEYS = frozenset({
    "text", "status", "confidence", "evidence_keys", "rationale",
})
_DISPUTED_MATTER_KEYS = frozenset({
    "disputed_matter_id", "proposition", "claimant_position", "respondent_position",
    "claimant_evidence", "respondent_evidence", "contemporaneous_evidence",
    "presently_established", "remains_unresolved",
})
_GAP_KEYS = frozenset({
    "gap_id", "description", "related_element_id", "materiality", "reason",
    "suggested_evidence_target",
})
_EVIDENCE_BACKED_STATEMENT_KEYS = frozenset({"text", "evidence_keys", "citations"})
_ELEMENT_LEGAL_ANALYSIS_KEYS = frozenset({
    "issue_definition_id", "issue_definition_version", "element_id", "legal_question",
    "current_evidential_position", "established_matters", "supported_matters",
    "not_supported_matters", "source_assertions", "adverse_material",
    "corroborative_material", "contextual_material", "conflicting_material",
    "disputed_matters", "legal_significance", "limitations", "unresolved_matters",
    "evidential_gaps", "provisional_status", "provisional_analysis",
    "analysis_confidence", "analyser_version",
})
_ISSUE_SYNTHESIS_KEYS = frozenset({
    "well_supported_elements", "partially_supported_elements", "disputed_elements",
    "insufficiently_evidenced_elements", "unresolved_elements", "summary",
})
_MANIFEST_KEYS = frozenset({
    "schema_version", "identity_version", "case_id",
    "structured_legal_analysis_results_sha256", "case_matrices_sha256",
    "governed_issue_evidence_map_sha256", "governed_evidential_analysis_sha256",
    "source_analysis_ids", "authority_id",
})
_POINTER_KEYS = frozenset({
    "schema_version", "case_id", "authority_id", "authority_manifest_sha256",
    "activation_id",
})
_ACTIVATION_KEYS = frozenset({
    "schema_version", "case_id", "activation_id", "action", "previous_activation_id",
    "previous_authority_id", "new_authority_id", "previous_active_pointer_sha256",
    "new_active_pointer_sha256",
})


def _require_object(data: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"{label} must contain an object.")
    return data


def _require_list(data: Any, *, label: str) -> list[Any]:
    if not isinstance(data, list):
        raise ValueError(f"{label} must contain a list.")
    return data


def _require_exact_keys(data: dict[str, Any], expected: frozenset[str], *, label: str) -> None:
    observed = frozenset(data)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise ValueError(f"{label} has non-canonical keys; missing={missing}, extra={extra}.")


def _validate_evidence_reference_shape(data: Any) -> None:
    # The frozen public IssueAnalysis serializer owns the exact EvidenceReference schema.
    # Canonical-byte equality after native round-trip detects any accepted extra/defaulted
    # representation without importing its private field helpers.
    _require_object(data, label="EvidenceReference")


def _validate_disputed_matter_shape(data: Any) -> None:
    obj = _require_object(data, label="DisputedMatter")
    _require_exact_keys(obj, _DISPUTED_MATTER_KEYS, label="DisputedMatter")
    for field in ("claimant_evidence", "respondent_evidence", "contemporaneous_evidence"):
        for item in _require_list(obj[field], label=field):
            _validate_evidence_reference_shape(item)


def _validate_gap_shape(data: Any) -> None:
    obj = _require_object(data, label="EvidentialGap")
    _require_exact_keys(obj, _GAP_KEYS, label="EvidentialGap")


def _validate_evidence_mapping_shape(data: Any) -> None:
    obj = _require_object(data, label="EvidenceMapping")
    _require_exact_keys(obj, _EVIDENCE_MAPPING_KEYS, label="EvidenceMapping")
    _validate_evidence_reference_shape(obj["evidence"])


def _validate_mapped_issue_shape(data: Any) -> None:
    obj = _require_object(data, label="MappedIssueAnalysis")
    _require_exact_keys(obj, _MAPPED_ISSUE_KEYS, label="MappedIssueAnalysis")
    _require_object(obj["analysis"], label="MappedIssueAnalysis.analysis")
    for element in _require_list(obj["element_results"], label="element_results"):
        element_obj = _require_object(element, label="ElementMappingResult")
        _require_exact_keys(element_obj, _ELEMENT_MAPPING_KEYS, label="ElementMappingResult")
        for mapping in _require_list(element_obj["mappings"], label="mappings"):
            _validate_evidence_mapping_shape(mapping)


def _validate_element_assessment_shape(data: Any) -> None:
    obj = _require_object(data, label="ElementEvidenceAssessment")
    _require_exact_keys(obj, _ELEMENT_ASSESSMENT_KEYS, label="ElementEvidenceAssessment")
    for item in _require_list(obj["evidence_assessments"], label="evidence_assessments"):
        item_obj = _require_object(item, label="EvidenceAssessment")
        _require_exact_keys(item_obj, _EVIDENCE_ASSESSMENT_KEYS, label="EvidenceAssessment")
        _validate_evidence_mapping_shape(item_obj["mapping"])
    for item in _require_list(obj["assessed_propositions"], label="assessed_propositions"):
        item_obj = _require_object(item, label="AssessedProposition")
        _require_exact_keys(item_obj, _ASSESSED_PROPOSITION_KEYS, label="AssessedProposition")
    for item in _require_list(obj["disputed_matters"], label="disputed_matters"):
        _validate_disputed_matter_shape(item)
    for item in _require_list(obj["evidential_gaps"], label="evidential_gaps"):
        _validate_gap_shape(item)


def _validate_element_legal_analysis_shape(data: Any) -> None:
    obj = _require_object(data, label="ElementLegalAnalysis")
    _require_exact_keys(obj, _ELEMENT_LEGAL_ANALYSIS_KEYS, label="ElementLegalAnalysis")
    for field in (
        "established_matters", "supported_matters", "not_supported_matters",
        "source_assertions", "adverse_material", "corroborative_material",
        "contextual_material", "conflicting_material",
    ):
        for item in _require_list(obj[field], label=field):
            item_obj = _require_object(item, label="EvidenceBackedStatement")
            _require_exact_keys(
                item_obj, _EVIDENCE_BACKED_STATEMENT_KEYS, label="EvidenceBackedStatement"
            )
    for item in _require_list(obj["disputed_matters"], label="disputed_matters"):
        _validate_disputed_matter_shape(item)
    for item in _require_list(obj["evidential_gaps"], label="evidential_gaps"):
        _validate_gap_shape(item)


def _validate_m5_result_shape(data: Any) -> dict[str, Any]:
    obj = _require_object(data, label="StructuredLegalAnalysisResult")
    _require_exact_keys(obj, _M5_RESULT_KEYS, label="StructuredLegalAnalysisResult")
    assessment = _require_object(obj["assessment_result"], label="EvidenceAssessmentResult")
    _require_exact_keys(assessment, _M4_RESULT_KEYS, label="EvidenceAssessmentResult")
    _validate_mapped_issue_shape(assessment["mapping_result"])
    _require_object(assessment["assessed_analysis"], label="assessed_analysis")
    for item in _require_list(assessment["element_assessments"], label="element_assessments"):
        _validate_element_assessment_shape(item)
    for item in _require_list(obj["element_analyses"], label="element_analyses"):
        _validate_element_legal_analysis_shape(item)
    synthesis = _require_object(obj["issue_synthesis"], label="IssueLevelSynthesis")
    _require_exact_keys(synthesis, _ISSUE_SYNTHESIS_KEYS, label="IssueLevelSynthesis")
    return obj


def _result_sort_key(value: StructuredLegalAnalysisResult) -> tuple[str, str, str]:
    return (
        value.issue_definition_id,
        value.issue_definition_version,
        value.issue_analysis_id,
    )


def structured_legal_analysis_results_to_list(
    values: tuple[StructuredLegalAnalysisResult, ...] | list[StructuredLegalAnalysisResult],
) -> list[dict[str, Any]]:
    """Return canonical outer ordering while preserving every inner native order."""

    result_tuple = tuple(values)
    if not result_tuple:
        raise ValueError("StructuredLegalAnalysisResult collection must not be empty.")
    issue_ids = tuple(item.issue_analysis_id for item in result_tuple)
    if len(set(issue_ids)) != len(issue_ids):
        raise ValueError("StructuredLegalAnalysisResult collection contains duplicate issue_analysis_id values.")
    ordered = tuple(sorted(result_tuple, key=_result_sort_key))
    return [structured_legal_analysis_result_to_dict(item) for item in ordered]


def structured_legal_analysis_results_from_list(
    data: list[Any],
) -> tuple[StructuredLegalAnalysisResult, ...]:
    """Restore the complete M5 result set and require canonical outer ordering."""

    items = _require_list(data, label="StructuredLegalAnalysisResult collection")
    if not items:
        raise ValueError("StructuredLegalAnalysisResult collection must not be empty.")
    values = tuple(structured_legal_analysis_result_from_dict(_validate_m5_result_shape(item)) for item in items)
    canonical = tuple(sorted(values, key=_result_sort_key))
    if values != canonical:
        raise ValueError("StructuredLegalAnalysisResult collection is not in canonical outer order.")
    if len({item.issue_analysis_id for item in values}) != len(values):
        raise ValueError("StructuredLegalAnalysisResult collection contains duplicate issue_analysis_id values.")
    return values


def dumps_structured_legal_analysis_results(
    values: tuple[StructuredLegalAnalysisResult, ...] | list[StructuredLegalAnalysisResult],
) -> str:
    """Return canonical UTF-8 JSON text for a complete M5 result set."""

    return json.dumps(
        structured_legal_analysis_results_to_list(values),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def loads_structured_legal_analysis_results(payload: str) -> tuple[StructuredLegalAnalysisResult, ...]:
    """Load only a canonical complete M5 result-set representation."""

    if not isinstance(payload, str):
        raise ValueError("StructuredLegalAnalysisResult collection payload must be text.")
    data = json.loads(payload)
    values = structured_legal_analysis_results_from_list(data)
    if dumps_structured_legal_analysis_results(values) != payload:
        raise ValueError("StructuredLegalAnalysisResult collection JSON is not canonical.")
    return values


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def governed_analytical_authority_manifest_to_dict(value):
    from .models import GovernedAnalyticalAuthorityManifest
    if not isinstance(value, GovernedAnalyticalAuthorityManifest):
        raise ValueError("value must be a GovernedAnalyticalAuthorityManifest.")
    return {
        "schema_version": value.schema_version,
        "identity_version": value.identity_version,
        "case_id": value.case_id,
        "structured_legal_analysis_results_sha256": value.structured_legal_analysis_results_sha256,
        "case_matrices_sha256": value.case_matrices_sha256,
        "governed_issue_evidence_map_sha256": value.governed_issue_evidence_map_sha256,
        "governed_evidential_analysis_sha256": value.governed_evidential_analysis_sha256,
        "source_analysis_ids": list(value.source_analysis_ids),
        "authority_id": value.authority_id,
    }


def dumps_governed_analytical_authority_manifest(value) -> str:
    return _canonical_json(governed_analytical_authority_manifest_to_dict(value))


def loads_governed_analytical_authority_manifest(payload: str):
    from .models import GovernedAnalyticalAuthorityManifest
    data = _require_object(json.loads(payload), label="GovernedAnalyticalAuthorityManifest")
    _require_exact_keys(data, _MANIFEST_KEYS, label="GovernedAnalyticalAuthorityManifest")
    result = GovernedAnalyticalAuthorityManifest(
        schema_version=str(data["schema_version"]),
        identity_version=str(data["identity_version"]),
        case_id=str(data["case_id"]),
        structured_legal_analysis_results_sha256=str(data["structured_legal_analysis_results_sha256"]),
        case_matrices_sha256=str(data["case_matrices_sha256"]),
        governed_issue_evidence_map_sha256=str(data["governed_issue_evidence_map_sha256"]),
        governed_evidential_analysis_sha256=str(data["governed_evidential_analysis_sha256"]),
        source_analysis_ids=tuple(str(item) for item in data["source_analysis_ids"]),
        authority_id=str(data["authority_id"]),
    )
    if dumps_governed_analytical_authority_manifest(result) != payload:
        raise ValueError("Governed analytical-authority manifest JSON is not canonical.")
    return result


def governed_analytical_authority_active_pointer_to_dict(value):
    from .models import GovernedAnalyticalAuthorityActivePointer
    if not isinstance(value, GovernedAnalyticalAuthorityActivePointer):
        raise ValueError("value must be a GovernedAnalyticalAuthorityActivePointer.")
    return {
        "schema_version": value.schema_version,
        "case_id": value.case_id,
        "authority_id": value.authority_id,
        "authority_manifest_sha256": value.authority_manifest_sha256,
        "activation_id": value.activation_id,
    }


def dumps_governed_analytical_authority_active_pointer(value) -> str:
    return _canonical_json(governed_analytical_authority_active_pointer_to_dict(value))


def loads_governed_analytical_authority_active_pointer(payload: str):
    from .models import GovernedAnalyticalAuthorityActivePointer
    data = _require_object(json.loads(payload), label="GovernedAnalyticalAuthorityActivePointer")
    _require_exact_keys(data, _POINTER_KEYS, label="GovernedAnalyticalAuthorityActivePointer")
    result = GovernedAnalyticalAuthorityActivePointer(
        schema_version=str(data["schema_version"]),
        case_id=str(data["case_id"]),
        authority_id=str(data["authority_id"]),
        authority_manifest_sha256=str(data["authority_manifest_sha256"]),
        activation_id=str(data["activation_id"]),
    )
    if dumps_governed_analytical_authority_active_pointer(result) != payload:
        raise ValueError("Governed analytical-authority pointer JSON is not canonical.")
    return result


def governed_analytical_authority_activation_receipt_to_dict(value):
    from .models import GovernedAnalyticalAuthorityActivationReceipt
    if not isinstance(value, GovernedAnalyticalAuthorityActivationReceipt):
        raise ValueError("value must be a GovernedAnalyticalAuthorityActivationReceipt.")
    return {
        "schema_version": value.schema_version,
        "case_id": value.case_id,
        "activation_id": value.activation_id,
        "action": value.action.value,
        "previous_activation_id": value.previous_activation_id,
        "previous_authority_id": value.previous_authority_id,
        "new_authority_id": value.new_authority_id,
        "previous_active_pointer_sha256": value.previous_active_pointer_sha256,
        "new_active_pointer_sha256": value.new_active_pointer_sha256,
    }


def dumps_governed_analytical_authority_activation_receipt(value) -> str:
    return _canonical_json(governed_analytical_authority_activation_receipt_to_dict(value))


def loads_governed_analytical_authority_activation_receipt(payload: str):
    from .models import (
        GovernedAnalyticalAuthorityActivationAction,
        GovernedAnalyticalAuthorityActivationReceipt,
    )
    data = _require_object(json.loads(payload), label="GovernedAnalyticalAuthorityActivationReceipt")
    _require_exact_keys(data, _ACTIVATION_KEYS, label="GovernedAnalyticalAuthorityActivationReceipt")
    result = GovernedAnalyticalAuthorityActivationReceipt(
        schema_version=str(data["schema_version"]),
        case_id=str(data["case_id"]),
        activation_id=str(data["activation_id"]),
        action=GovernedAnalyticalAuthorityActivationAction(str(data["action"])),
        previous_activation_id=(None if data["previous_activation_id"] is None else str(data["previous_activation_id"])),
        previous_authority_id=(None if data["previous_authority_id"] is None else str(data["previous_authority_id"])),
        new_authority_id=str(data["new_authority_id"]),
        previous_active_pointer_sha256=(None if data["previous_active_pointer_sha256"] is None else str(data["previous_active_pointer_sha256"])),
        new_active_pointer_sha256=str(data["new_active_pointer_sha256"]),
    )
    if dumps_governed_analytical_authority_activation_receipt(result) != payload:
        raise ValueError("Governed analytical-authority activation receipt JSON is not canonical.")
    return result


__all__ = [
    "dumps_governed_analytical_authority_activation_receipt",
    "dumps_governed_analytical_authority_active_pointer",
    "dumps_governed_analytical_authority_manifest",
    "dumps_structured_legal_analysis_result",
    "dumps_structured_legal_analysis_results",
    "governed_analytical_authority_activation_receipt_to_dict",
    "governed_analytical_authority_active_pointer_to_dict",
    "governed_analytical_authority_manifest_to_dict",
    "loads_governed_analytical_authority_activation_receipt",
    "loads_governed_analytical_authority_active_pointer",
    "loads_governed_analytical_authority_manifest",
    "loads_structured_legal_analysis_result",
    "loads_structured_legal_analysis_results",
    "structured_legal_analysis_result_from_dict",
    "structured_legal_analysis_result_to_dict",
    "structured_legal_analysis_results_from_list",
    "structured_legal_analysis_results_to_list",
]
