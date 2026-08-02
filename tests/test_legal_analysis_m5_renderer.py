from __future__ import annotations

import copy
from dataclasses import replace
from uuid import uuid4

import pytest

from evidence_classification import EvidenceSourceType
from legal_analysis.definitions import INITIAL_ISSUE_DEFINITIONS
from legal_analysis.element_assessor import ElementEvidenceAssessor
from legal_analysis.enums import AnalyticalRole, Confidence, EvidenceStatus
from legal_analysis.evidence_assessment import AssessedProposition, PropositionAssessmentStatus
from legal_analysis.evidence_mapping import (
    ElementMappingResult,
    EvidenceMapping,
    EvidenceRelevance,
    MappedIssueAnalysis,
)
from legal_analysis.legal_analysis import ElementAnalysisStatus
from legal_analysis.legal_analysis_renderer import StructuredLegalAnalysisRenderer
from legal_analysis.models import ElementAnalysis, EvidenceReference, IssueAnalysis


def _definition(issue_id: str):
    return next(d for d in INITIAL_ISSUE_DEFINITIONS if d.definition_id == issue_id)


def _mapped(
    issue_id: str,
    evidence_by_element: dict[str, tuple[EvidenceReference, ...]],
    *,
    confidence: Confidence = Confidence.HIGH,
) -> MappedIssueAnalysis:
    definition = _definition(issue_id)
    elements = []
    results = []
    for element in definition.elements:
        evidence_items = evidence_by_element.get(element.element_id, ())
        mappings = tuple(
            EvidenceMapping(
                evidence=evidence,
                issue_definition_id=definition.definition_id,
                issue_definition_version=definition.version,
                element_id=element.element_id,
                relevance=EvidenceRelevance.RELEVANT,
                mapping_confidence=confidence,
                mapping_rationale="Synthetic M5 mapping.",
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
        results.append(ElementMappingResult(element.element_id, "query", mappings))
    return MappedIssueAnalysis(
        IssueAnalysis(
            case_id=str(uuid4()),
            issue_definition_id=definition.definition_id,
            issue_definition_version=definition.version,
            issue_name=definition.name,
            user_question="Synthetic M5 question",
            legal_framework=definition.legal_framework,
            elements=tuple(elements),
        ),
        tuple(results),
    )


def _ev(
    text: str,
    chunk: str,
    *,
    source: EvidenceSourceType = EvidenceSourceType.EMPLOYER_RECORD,
    status: EvidenceStatus = EvidenceStatus.EMPLOYER_EVIDENCE,
) -> EvidenceReference:
    return EvidenceReference(
        document_name=f"{chunk}.pdf",
        summary=text,
        source_type=source,
        evidence_status=status,
        analytical_role=AnalyticalRole.NEUTRAL,
        citation=f"{chunk}.pdf, p.1",
        chunk_id=chunk,
        page=1,
    )


def _render(issue_id: str, evidence_by_element: dict[str, tuple[EvidenceReference, ...]]):
    m4 = ElementEvidenceAssessor().assess(_mapped(issue_id, evidence_by_element))
    return m4, StructuredLegalAnalysisRenderer().render(m4)


def test_renderer_does_not_mutate_frozen_m4():
    m4 = ElementEvidenceAssessor().assess(
        _mapped("EK-001", {"EK-DIRECT-KNOWLEDGE": (_ev("From HR: We received and discussed the return-to-work information.", "hr"),)})
    )
    before = copy.deepcopy(m4)
    StructuredLegalAnalysisRenderer().render(m4)
    assert m4 == before


def test_renderer_preserves_case_and_analysis_identity_via_frozen_m4():
    m4, result = _render("EK-001", {})
    assert result.case_id == m4.assessed_analysis.case_id
    assert result.issue_analysis_id == m4.assessed_analysis.issue_analysis_id
    assert result.issue_definition_id == "EK-001"
    assert result.issue_definition_version == "1.0"


def test_established_proposition_keeps_evidence_key_and_citation():
    m4, result = _render(
        "EK-001",
        {"EK-DIRECT-KNOWLEDGE": (_ev("From HR: We received and discussed the return-to-work information.", "hr"),)},
    )
    element = next(x for x in result.element_analyses if x.element_id == "EK-DIRECT-KNOWLEDGE")
    if element.established_matters:
        statement = element.established_matters[0]
        assert statement.evidence_keys == ("hr",)
        assert statement.citations == ("hr.pdf, p.1",)


def test_source_assertion_remains_explicitly_qualified():
    _, result = _render(
        "EK-001",
        {
            "EK-DIRECT-KNOWLEDGE": (
                _ev(
                    "Appendix asserts that CACI knew of the recommendation.",
                    "assertion",
                    source=EvidenceSourceType.MIXED_CORRESPONDENCE,
                    status=EvidenceStatus.SOURCE_ASSERTION,
                ),
            )
        },
    )
    element = next(x for x in result.element_analyses if x.element_id == "EK-DIRECT-KNOWLEDGE")
    assert element.source_assertions
    assert element.source_assertions[0].text.startswith("Source assertion:")
    assert any("do not independently establish" in limit for limit in element.limitations)


def test_adverse_material_is_not_suppressed():
    _, result = _render(
        "LIM-001",
        {
            "LIM-RESPONDENT-POSITION": (
                _ev(
                    "The respondent denies any continuing act and says the claim is out of time.",
                    "et3",
                    source=EvidenceSourceType.RESPONDENT_SUBMISSION,
                    status=EvidenceStatus.RESPONDENT_EVIDENCE,
                ),
            )
        },
    )
    element = next(x for x in result.element_analyses if x.element_id == "LIM-RESPONDENT-POSITION")
    assert element.adverse_material
    assert "out of time" in element.adverse_material[0].text.casefold()


def test_m4_gaps_and_unresolved_matters_are_carried_forward():
    m4, result = _render("EK-001", {})
    m4_element = next(x for x in m4.element_assessments if x.element_id == "EK-DIRECT-KNOWLEDGE")
    m5_element = next(x for x in result.element_analyses if x.element_id == "EK-DIRECT-KNOWLEDGE")
    assert m5_element.evidential_gaps == m4_element.evidential_gaps
    assert m5_element.unresolved_matters == m4_element.unresolved_matters


def test_renderer_leaves_m1_legal_analysis_field_untouched():
    m4, _ = _render("RA-001", {})
    assert all(element.legal_analysis is None for element in m4.assessed_analysis.elements)


def test_unknown_evidence_key_fails_closed():
    m4 = ElementEvidenceAssessor().assess(
        _mapped("EK-001", {"EK-DIRECT-KNOWLEDGE": (_ev("Appendix asserts CACI knew.", "a", source=EvidenceSourceType.MIXED_CORRESPONDENCE, status=EvidenceStatus.SOURCE_ASSERTION),)})
    )
    target = next(x for x in m4.element_assessments if x.element_id == "EK-DIRECT-KNOWLEDGE")
    bad_prop = replace(target.assessed_propositions[0], evidence_keys=("missing-key",))
    bad_target = replace(target, assessed_propositions=(bad_prop,))
    bad_result = replace(
        m4,
        element_assessments=tuple(bad_target if x.element_id == target.element_id else x for x in m4.element_assessments),
    )
    with pytest.raises(ValueError, match="fails closed"):
        StructuredLegalAnalysisRenderer().render(bad_result)


def test_changed_controlled_legal_question_fails_closed():
    m4 = ElementEvidenceAssessor().assess(_mapped("EK-001", {}))
    elements = list(m4.assessed_analysis.elements)
    elements[0] = replace(elements[0], question_to_determine="A rewritten legal test?")
    bad_analysis = replace(m4.assessed_analysis, elements=tuple(elements))
    bad = replace(m4, assessed_analysis=bad_analysis)
    with pytest.raises(ValueError, match="changed controlled legal question"):
        StructuredLegalAnalysisRenderer().render(bad)


def test_issue_synthesis_is_not_a_liability_score():
    _, result = _render("RA-001", {})
    text = result.issue_synthesis.summary.casefold()
    assert "not a merits score" in text
    assert "claim succeeds" not in text


def test_m5_status_is_never_more_optimistic_than_partial_when_source_assertion_only():
    _, result = _render(
        "RA-001",
        {"RA-REASONABLENESS": (_ev("Appendix asserts home working was reasonable.", "a", source=EvidenceSourceType.MIXED_CORRESPONDENCE, status=EvidenceStatus.SOURCE_ASSERTION),)},
    )
    element = next(x for x in result.element_analyses if x.element_id == "RA-REASONABLENESS")
    assert element.provisional_status is ElementAnalysisStatus.PARTIALLY_SUPPORTED
    assert element.analysis_confidence in {Confidence.LOW, Confidence.MEDIUM}
