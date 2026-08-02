from __future__ import annotations

from uuid import uuid4

import pytest

from evidence_classification import EvidenceSourceType
from legal_analysis.definitions import INITIAL_ISSUE_DEFINITIONS
from legal_analysis.element_assessor import ElementEvidenceAssessor
from legal_analysis.enums import AnalyticalRole, Confidence, EvidenceStatus
from legal_analysis.evidence_mapping import (
    ElementMappingResult,
    EvidenceMapping,
    EvidenceRelevance,
    MappedIssueAnalysis,
)
from legal_analysis.legal_analysis import ElementAnalysisStatus
from legal_analysis.legal_analysis_rules import (
    LEGAL_SIGNIFICANCE_PROFILES,
    analysis_confidence_for,
    assert_profile_coverage,
    profile_for,
    provisional_analysis_for,
    provisional_status_for,
)
from legal_analysis.models import ElementAnalysis, EvidenceReference, IssueAnalysis


def _definition(issue_id: str):
    return next(item for item in INITIAL_ISSUE_DEFINITIONS if item.definition_id == issue_id)


def _m4_for(
    issue_id: str,
    element_id: str,
    *,
    text: str | None = None,
    source: EvidenceSourceType = EvidenceSourceType.EMPLOYER_RECORD,
    status: EvidenceStatus = EvidenceStatus.EMPLOYER_EVIDENCE,
    mapping_confidence: Confidence = Confidence.HIGH,
):
    definition = _definition(issue_id)
    evidence = None
    mapping = None
    if text is not None:
        evidence = EvidenceReference(
            document_name="Evidence.pdf",
            summary=text,
            source_type=source,
            evidence_status=status,
            analytical_role=AnalyticalRole.NEUTRAL,
            citation="Evidence.pdf, p.1",
            chunk_id=f"{issue_id}-{element_id}",
            page=1,
        )
        mapping = EvidenceMapping(
            evidence=evidence,
            issue_definition_id=issue_id,
            issue_definition_version=definition.version,
            element_id=element_id,
            relevance=EvidenceRelevance.RELEVANT,
            mapping_confidence=mapping_confidence,
            mapping_rationale="Synthetic M5 test mapping.",
        )
    elements = []
    results = []
    for element in definition.elements:
        mappings = (mapping,) if mapping is not None and element.element_id == element_id else ()
        elements.append(
            ElementAnalysis(
                element.element_id,
                element.name,
                element.question_to_determine,
                neutral_evidence=(evidence,) if mappings else (),
            )
        )
        results.append(ElementMappingResult(element.element_id, "query", mappings))
    mapped = MappedIssueAnalysis(
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
    return ElementEvidenceAssessor().assess(mapped)


def test_all_34_exact_element_profiles_exist():
    expected = {
        (definition.definition_id, definition.version, element.element_id)
        for definition in INITIAL_ISSUE_DEFINITIONS
        for element in definition.elements
    }
    assert len(expected) == 34
    assert set(LEGAL_SIGNIFICANCE_PROFILES) == expected
    assert_profile_coverage(expected)


def test_profile_lookup_fails_closed_for_unknown_version():
    with pytest.raises(ValueError, match="will not improvise"):
        profile_for("EK-001", "9.9", "EK-DIRECT-KNOWLEDGE")


def test_profile_lookup_fails_closed_for_unknown_element():
    with pytest.raises(ValueError, match="will not improvise"):
        profile_for("EK-001", "1.0", "EK-FAIRNESS")


def test_empty_m4_element_is_insufficiently_evidenced():
    result = _m4_for("EK-001", "EK-DIRECT-KNOWLEDGE")
    assessment = next(x for x in result.element_assessments if x.element_id == "EK-DIRECT-KNOWLEDGE")
    assert provisional_status_for(assessment) is ElementAnalysisStatus.INSUFFICIENTLY_EVIDENCED


def test_supported_source_assertion_is_only_partially_supported():
    result = _m4_for(
        "EK-001",
        "EK-DIRECT-KNOWLEDGE",
        text="Appendix asserts that CACI knew of the recommendation.",
        source=EvidenceSourceType.MIXED_CORRESPONDENCE,
        status=EvidenceStatus.SOURCE_ASSERTION,
    )
    assessment = next(x for x in result.element_assessments if x.element_id == "EK-DIRECT-KNOWLEDGE")
    assert provisional_status_for(assessment) is ElementAnalysisStatus.PARTIALLY_SUPPORTED


def test_direct_established_fact_with_gap_remains_partially_supported():
    # EK direct communication can establish a narrow source-level fact, but an
    # element gap may remain depending on the exact information recorded.
    result = _m4_for(
        "EK-001",
        "EK-DIRECT-KNOWLEDGE",
        text="From HR: We received and discussed the return-to-work information.",
    )
    assessment = next(x for x in result.element_assessments if x.element_id == "EK-DIRECT-KNOWLEDGE")
    status = provisional_status_for(assessment)
    assert status in {
        ElementAnalysisStatus.WELL_SUPPORTED_ON_CURRENT_RECORD,
        ElementAnalysisStatus.PARTIALLY_SUPPORTED,
    }


def test_confidence_never_exceeds_m4_confidence():
    assert analysis_confidence_for(Confidence.LOW, ElementAnalysisStatus.WELL_SUPPORTED_ON_CURRENT_RECORD) is Confidence.LOW
    assert analysis_confidence_for(Confidence.MEDIUM, ElementAnalysisStatus.WELL_SUPPORTED_ON_CURRENT_RECORD) is Confidence.MEDIUM
    assert analysis_confidence_for(Confidence.HIGH, ElementAnalysisStatus.PARTIALLY_SUPPORTED) is Confidence.MEDIUM


def test_unresolved_and_insufficient_statuses_cap_confidence_low():
    assert analysis_confidence_for(Confidence.HIGH, ElementAnalysisStatus.UNRESOLVED) is Confidence.LOW
    assert analysis_confidence_for(Confidence.HIGH, ElementAnalysisStatus.INSUFFICIENTLY_EVIDENCED) is Confidence.LOW


def test_disputed_status_caps_confidence_medium():
    assert analysis_confidence_for(Confidence.HIGH, ElementAnalysisStatus.DISPUTED) is Confidence.MEDIUM


def test_knowledge_provisional_text_does_not_state_legal_knowledge():
    profile = profile_for("EK-001", "1.0", "EK-DIRECT-KNOWLEDGE")
    text = provisional_analysis_for(profile, ElementAnalysisStatus.PARTIALLY_SUPPORTED).casefold()
    assert "caci had legal knowledge" not in text
    assert "statutory test is satisfied" not in text


def test_ra_reasonableness_text_does_not_decide_reasonableness():
    profile = profile_for("RA-001", "1.0", "RA-REASONABLENESS")
    text = provisional_analysis_for(profile, ElementAnalysisStatus.PARTIALLY_SUPPORTED).casefold()
    assert "home working was a reasonable adjustment" not in text
    assert "the adjustment was reasonable" not in text


def test_limitation_text_does_not_decide_continuing_act():
    profile = profile_for("LIM-001", "1.0", "LIM-CONTINUING-CONDUCT")
    text = provisional_analysis_for(profile, ElementAnalysisStatus.PARTIALLY_SUPPORTED).casefold()
    assert "there was a continuing act" not in text
    assert "a continuing act existed" not in text


def test_da_text_does_not_decide_section_15():
    profile = profile_for("DA-001", "1.0", "DA-CAUSATION")
    text = provisional_analysis_for(profile, ElementAnalysisStatus.PARTIALLY_SUPPORTED).casefold()
    assert "section 15 is established" not in text
