from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from evidence_classification import EvidenceSourceType
from legal_analysis.definitions import INITIAL_ISSUE_DEFINITIONS
from legal_analysis.element_assessor import ElementEvidenceAssessor
from legal_analysis.enums import (
    AnalyticalRole,
    Confidence,
    EvidenceStatus,
    ProvenanceBasis,
    ProvenanceConfidence,
)
from legal_analysis.evidence_assessment import AssessedProposition
from legal_analysis.evidence_mapping import (
    ElementMappingResult,
    EvidenceMapping,
    EvidenceRelevance,
    MappedIssueAnalysis,
)
from legal_analysis.legal_analysis import StructuredLegalAnalysisResult
from legal_analysis.legal_analysis_renderer import StructuredLegalAnalysisRenderer
from legal_analysis.models import ElementAnalysis, EvidenceReference, IssueAnalysis

DEFAULT_CASE_ID = "11111111-1111-4111-8111-111111111111"
DEFAULT_CREATED_AT = datetime(2026, 8, 3, 10, 30, tzinfo=timezone.utc)


def definition(issue_id: str):
    return next(item for item in INITIAL_ISSUE_DEFINITIONS if item.definition_id == issue_id)


def evidence(
    *,
    key: str,
    document_name: str = "shared.pdf",
    page: int = 1,
    citation: str | None = None,
    document_id: str | None = "doc-1",
    summary: str = "From HR: We received and discussed the return-to-work information.",
    source_type: EvidenceSourceType = EvidenceSourceType.EMPLOYER_RECORD,
    evidence_status: EvidenceStatus = EvidenceStatus.EMPLOYER_EVIDENCE,
    provenance_type: EvidenceSourceType | None = None,
    provenance_basis: ProvenanceBasis = ProvenanceBasis.EXPLICIT_SENDER,
    provenance_confidence: ProvenanceConfidence = ProvenanceConfidence.HIGH,
    author: str | None = "HR",
    parties: tuple[str, ...] = ("CACI",),
) -> EvidenceReference:
    return EvidenceReference(
        document_id=document_id,
        document_name=document_name,
        page=page,
        chunk_id=key,
        summary=summary,
        source_type=source_type,
        evidence_status=evidence_status,
        analytical_role=AnalyticalRole.NEUTRAL,
        citation=citation or f"{document_name}, p.{page}",
        provenance_type=provenance_type or source_type,
        provenance_basis=provenance_basis,
        provenance_confidence=provenance_confidence,
        author=author,
        parties=parties,
    )


def make_m5_result(
    issue_id: str,
    *,
    evidence_by_element: dict[str, tuple[EvidenceReference, ...]] | None = None,
    case_id: str = DEFAULT_CASE_ID,
    issue_analysis_id: str | None = None,
    created_at: datetime = DEFAULT_CREATED_AT,
    role_overrides: dict[tuple[str, str], AnalyticalRole] | None = None,
    proposition_overrides: dict[str, tuple[AssessedProposition, ...]] | None = None,
) -> StructuredLegalAnalysisResult:
    controlled = definition(issue_id)
    evidence_by_element = evidence_by_element or {}
    elements: list[ElementAnalysis] = []
    results: list[ElementMappingResult] = []
    for element in controlled.elements:
        evidence_items = evidence_by_element.get(element.element_id, ())
        mappings = tuple(
            EvidenceMapping(
                evidence=item,
                issue_definition_id=controlled.definition_id,
                issue_definition_version=controlled.version,
                element_id=element.element_id,
                relevance=EvidenceRelevance.RELEVANT,
                mapping_confidence=Confidence.HIGH,
                mapping_rationale=f"Synthetic M2 mapping for {element.element_id}.",
            )
            for item in evidence_items
        )
        elements.append(
            ElementAnalysis(
                element.element_id,
                element.name,
                element.question_to_determine,
                neutral_evidence=evidence_items,
            )
        )
        results.append(
            ElementMappingResult(
                element_id=element.element_id,
                search_query="Synthetic M2 no-retrieval mapping",
                mappings=mappings,
            )
        )

    mapped = MappedIssueAnalysis(
        analysis=IssueAnalysis(
            case_id=case_id,
            issue_definition_id=controlled.definition_id,
            issue_definition_version=controlled.version,
            issue_name=controlled.name,
            user_question=f"Synthetic M2 question for {issue_id}",
            legal_framework=controlled.legal_framework,
            elements=tuple(elements),
            issue_analysis_id=issue_analysis_id or str(uuid4()),
            created_at=created_at,
        ),
        element_results=tuple(results),
    )
    m4 = ElementEvidenceAssessor().assess(mapped)

    if role_overrides or proposition_overrides:
        role_overrides = role_overrides or {}
        proposition_overrides = proposition_overrides or {}
        replaced_elements = []
        for element in m4.element_assessments:
            assessments = tuple(
                replace(
                    item,
                    analytical_role=role_overrides.get(
                        (element.element_id, item.mapping.evidence_key),
                        item.analytical_role,
                    ),
                )
                for item in element.evidence_assessments
            )
            propositions = proposition_overrides.get(
                element.element_id,
                element.assessed_propositions,
            )
            replaced_elements.append(
                replace(
                    element,
                    evidence_assessments=assessments,
                    assessed_propositions=propositions,
                )
            )
        m4 = replace(m4, element_assessments=tuple(replaced_elements))

    return StructuredLegalAnalysisRenderer().render(m4)


def replace_mapping_evidence(
    result: StructuredLegalAnalysisResult,
    *,
    element_id: str,
    evidence_key: str,
    replacement: EvidenceReference,
) -> StructuredLegalAnalysisResult:
    """Return a synthetically corrupted frozen result without invoking M5 again."""

    assessment = result.assessment_result
    mapped = assessment.mapping_result
    new_element_results = []
    for element_result in mapped.element_results:
        new_mappings = []
        for mapping in element_result.mappings:
            if element_result.element_id == element_id and mapping.evidence_key == evidence_key:
                new_mappings.append(replace(mapping, evidence=replacement))
            else:
                new_mappings.append(mapping)
        new_element_results.append(replace(element_result, mappings=tuple(new_mappings)))
    new_mapped = replace(mapped, element_results=tuple(new_element_results))

    new_element_assessments = []
    for element in assessment.element_assessments:
        new_assessments = []
        for item in element.evidence_assessments:
            if element.element_id == element_id and item.mapping.evidence_key == evidence_key:
                new_assessments.append(replace(item, mapping=replace(item.mapping, evidence=replacement)))
            else:
                new_assessments.append(item)
        new_element_assessments.append(replace(element, evidence_assessments=tuple(new_assessments)))

    new_assessment = replace(
        assessment,
        mapping_result=new_mapped,
        element_assessments=tuple(new_element_assessments),
    )
    return replace(result, assessment_result=new_assessment)
