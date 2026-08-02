from __future__ import annotations

import copy
from dataclasses import replace
from uuid import uuid4

import pytest

from evidence_classification import EvidenceSourceType
from legal_analysis.definitions import INITIAL_ISSUE_DEFINITIONS
from legal_analysis.element_assessor import ElementEvidenceAssessor
from legal_analysis.enums import AnalyticalRole, Confidence, EvidenceStatus, ProvenanceConfidence
from legal_analysis.evidence_mapping import (
    ElementMappingResult,
    EvidenceMapping,
    EvidenceRelevance,
    MappedIssueAnalysis,
)
from legal_analysis.legal_analysis_renderer import StructuredLegalAnalysisRenderer
from legal_analysis.models import ElementAnalysis, EvidenceReference, IssueAnalysis


def _definition(issue_id: str):
    return next(d for d in INITIAL_ISSUE_DEFINITIONS if d.definition_id == issue_id)


def _evidence(
    *,
    chunk_id: str,
    summary: str,
    document_name: str = "shared.pdf",
    document_id: str | None = "doc-1",
    page: int = 2,
    citation: str = "shared.pdf, p.2",
    provenance_confidence: ProvenanceConfidence = ProvenanceConfidence.HIGH,
) -> EvidenceReference:
    return EvidenceReference(
        document_id=document_id,
        document_name=document_name,
        page=page,
        chunk_id=chunk_id,
        summary=summary,
        source_type=EvidenceSourceType.EMPLOYER_RECORD,
        evidence_status=EvidenceStatus.EMPLOYER_EVIDENCE,
        analytical_role=AnalyticalRole.NEUTRAL,
        citation=citation,
        provenance_confidence=provenance_confidence,
    )


def _mapped_with_shared_key(
    first: EvidenceReference,
    second: EvidenceReference,
) -> MappedIssueAnalysis:
    definition = _definition("EK-001")
    target_ids = ("EK-RECIPIENT", "EK-DIRECT-KNOWLEDGE")
    evidence_by_element = {
        target_ids[0]: (first,),
        target_ids[1]: (second,),
    }

    elements: list[ElementAnalysis] = []
    element_results: list[ElementMappingResult] = []
    for element in definition.elements:
        evidence_items = evidence_by_element.get(element.element_id, ())
        mappings = tuple(
            EvidenceMapping(
                evidence=evidence,
                issue_definition_id=definition.definition_id,
                issue_definition_version=definition.version,
                element_id=element.element_id,
                relevance=EvidenceRelevance.RELEVANT,
                mapping_confidence=Confidence.HIGH,
                mapping_rationale="Synthetic cross-element reuse fixture.",
            )
            for evidence in evidence_items
        )
        elements.append(
            ElementAnalysis(
                element.element_id,
                element.name,
                element.question_to_determine,
                neutral_evidence=evidence_items,
            )
        )
        element_results.append(
            ElementMappingResult(
                element_id=element.element_id,
                search_query=f"fixture {element.element_id}",
                mappings=mappings,
            )
        )

    analysis = IssueAnalysis(
        case_id=str(uuid4()),
        issue_definition_id=definition.definition_id,
        issue_definition_version=definition.version,
        issue_name=definition.name,
        user_question="What evidence shows CACI knew about my disability?",
        legal_framework=definition.legal_framework,
        elements=tuple(elements),
    )
    return MappedIssueAnalysis(analysis, tuple(element_results))


def test_same_key_compatible_identity_allows_non_identity_differences():
    first = _evidence(
        chunk_id="shared-chunk",
        summary="From HR: We received and discussed the return-to-work information.",
        provenance_confidence=ProvenanceConfidence.HIGH,
    )
    second = replace(
        first,
        summary="The same underlying chunk represented with different descriptive wording.",
        provenance_confidence=ProvenanceConfidence.MEDIUM,
    )

    mapped = _mapped_with_shared_key(first, second)
    assessed = ElementEvidenceAssessor().assess(mapped)

    result = StructuredLegalAnalysisRenderer().render(assessed)

    assert result.issue_analysis_id == assessed.assessed_analysis.issue_analysis_id


def test_same_key_incompatible_document_or_page_identity_still_raises():
    first = _evidence(
        chunk_id="shared-chunk",
        summary="From HR: We received and discussed the return-to-work information.",
    )
    second = _evidence(
        chunk_id="shared-chunk",
        summary="Different source identity using the same key.",
        document_name="different.pdf",
        document_id="doc-2",
        page=7,
        citation="different.pdf, p.7",
    )

    assessed = ElementEvidenceAssessor().assess(_mapped_with_shared_key(first, second))

    with pytest.raises(ValueError, match="incompatible stable evidence identity"):
        StructuredLegalAnalysisRenderer().render(assessed)


def test_one_chunk_reused_across_multiple_elements_renders_successfully():
    first = _evidence(
        chunk_id="shared-chunk",
        summary="From HR: We received and discussed the return-to-work information.",
    )
    second = replace(
        first,
        summary="Same source reused for the direct-knowledge element.",
    )

    assessed = ElementEvidenceAssessor().assess(_mapped_with_shared_key(first, second))
    result = StructuredLegalAnalysisRenderer().render(assessed)

    element_ids = {item.element_id for item in result.element_analyses}
    assert "EK-RECIPIENT" in element_ids
    assert "EK-DIRECT-KNOWLEDGE" in element_ids


def test_canonicalised_duplicate_key_preserves_stable_citation_traceability():
    first = _evidence(
        chunk_id="shared-chunk",
        summary="From HR: We received and discussed the return-to-work information.",
        citation="Appendix H4, p.2",
        document_name="Appendix H4.pdf",
    )
    second = replace(
        first,
        summary="Same source occurrence with harmless non-identity differences.",
        provenance_confidence=ProvenanceConfidence.MEDIUM,
    )

    assessed = ElementEvidenceAssessor().assess(_mapped_with_shared_key(first, second))
    result = StructuredLegalAnalysisRenderer().render(assessed)

    statements = [
        statement
        for element in result.element_analyses
        for statement in (*element.established_matters, *element.supported_matters)
        if "shared-chunk" in statement.evidence_keys
    ]
    assert statements
    assert all(statement.citations == ("Appendix H4, p.2",) for statement in statements)


def test_duplicate_key_canonicalisation_does_not_mutate_frozen_m4_input():
    first = _evidence(
        chunk_id="shared-chunk",
        summary="From HR: We received and discussed the return-to-work information.",
    )
    second = replace(
        first,
        summary="Same underlying source with another descriptive representation.",
    )

    assessed = ElementEvidenceAssessor().assess(_mapped_with_shared_key(first, second))
    before = copy.deepcopy(assessed)

    StructuredLegalAnalysisRenderer().render(assessed)

    assert assessed == before
