from __future__ import annotations

from uuid import uuid4

from evidence_classification import EvidenceSourceType
from legal_analysis.definitions import INITIAL_ISSUE_DEFINITIONS
from legal_analysis.element_assessor import ElementEvidenceAssessor
from legal_analysis.enums import AnalyticalRole, Confidence, EvidenceStatus
from legal_analysis.evidence_mapping import ElementMappingResult, EvidenceMapping, EvidenceRelevance, MappedIssueAnalysis
from legal_analysis.legal_analysis_renderer import StructuredLegalAnalysisRenderer, format_legal_analysis_diagnostics
from legal_analysis.models import ElementAnalysis, EvidenceReference, IssueAnalysis

DEFS = {d.definition_id: d for d in INITIAL_ISSUE_DEFINITIONS}


def _render(issue_id: str, element_id: str, text: str, *, source=EvidenceSourceType.EMPLOYER_RECORD, status=EvidenceStatus.EMPLOYER_EVIDENCE):
    definition = DEFS[issue_id]
    evidence = EvidenceReference(
        document_name="Acceptance evidence.pdf",
        summary=text,
        source_type=source,
        evidence_status=status,
        analytical_role=AnalyticalRole.NEUTRAL,
        citation="Acceptance evidence.pdf, p.1",
        chunk_id=f"{issue_id}-{element_id}",
        page=1,
    )
    mapping = EvidenceMapping(
        evidence=evidence,
        issue_definition_id=issue_id,
        issue_definition_version=definition.version,
        element_id=element_id,
        relevance=EvidenceRelevance.RELEVANT,
        mapping_confidence=Confidence.HIGH,
        mapping_rationale="Frozen M5 synthetic acceptance mapping.",
    )
    elements = []
    results = []
    for item in definition.elements:
        mappings = (mapping,) if item.element_id == element_id else ()
        elements.append(ElementAnalysis(item.element_id, item.name, item.question_to_determine, neutral_evidence=(evidence,) if mappings else ()))
        results.append(ElementMappingResult(item.element_id, "query", mappings))
    mapped = MappedIssueAnalysis(
        IssueAnalysis(
            case_id=str(uuid4()),
            issue_definition_id=issue_id,
            issue_definition_version=definition.version,
            issue_name=definition.name,
            user_question="Synthetic acceptance",
            legal_framework=definition.legal_framework,
            elements=tuple(elements),
        ),
        tuple(results),
    )
    m4 = ElementEvidenceAssessor().assess(mapped)
    return StructuredLegalAnalysisRenderer().render(m4)


def test_ek_acceptance_interprets_knowledge_without_declaring_legal_knowledge():
    result = _render("EK-001", "EK-DIRECT-KNOWLEDGE", "From HR: We received and discussed the return-to-work information.")
    text = format_legal_analysis_diagnostics(result).casefold()
    assert "legal significance" in text
    assert "provisional analysis" in text
    assert "caci had legal knowledge" not in text
    assert "statutory test is satisfied" not in text


def test_ra_acceptance_does_not_decide_adjustment_reasonableness():
    result = _render(
        "RA-001",
        "RA-REASONABLENESS",
        "The appendix asserts that home working was a reasonable adjustment.",
        source=EvidenceSourceType.MIXED_CORRESPONDENCE,
        status=EvidenceStatus.SOURCE_ASSERTION,
    )
    text = format_legal_analysis_diagnostics(result).casefold()
    assert "source assertions" in text
    assert "home working was a reasonable adjustment" in text  # only the source's assertion itself
    assert "home working was a reasonable adjustment." in result.element_analyses[5].source_assertions[0].text.casefold()
    # M5's own legal significance/provisional analysis must not adopt it as a conclusion.
    own = (result.element_analyses[5].legal_significance + " " + result.element_analyses[5].provisional_analysis).casefold()
    assert "home working was a reasonable adjustment" not in own


def test_lim_acceptance_supports_argument_without_deciding_continuing_act():
    result = _render(
        "LIM-001",
        "LIM-CONTINUING-CONDUCT",
        "The claimant states the omission continued after 2005.",
        source=EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT,
        status=EvidenceStatus.CLAIMANT_EVIDENCE,
    )
    element = next(x for x in result.element_analyses if x.element_id == "LIM-CONTINUING-CONDUCT")
    own = (element.legal_significance + " " + element.provisional_analysis).casefold()
    assert "continuing-conduct argument" in own
    assert "there was a continuing act" not in own
    assert "claim is in time" not in own


def test_da_acceptance_does_not_convert_factual_causation_material_into_section_15_liability():
    result = _render(
        "DA-001",
        "DA-CAUSATION",
        "The claimant states the treatment followed disability-related absence.",
        source=EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT,
        status=EvidenceStatus.CLAIMANT_EVIDENCE,
    )
    element = next(x for x in result.element_analyses if x.element_id == "DA-CAUSATION")
    own = (element.legal_significance + " " + element.provisional_analysis).casefold()
    assert "factual causation" in own
    assert "section 15 is established" not in own


def test_issue_level_synthesis_never_aggregates_elements_into_liability():
    result = _render("EK-001", "EK-DIRECT-KNOWLEDGE", "From HR: We received and discussed the return-to-work information.")
    text = result.issue_synthesis.summary.casefold()
    assert "not a merits score" in text
    assert "claim succeeds" not in text
    assert "liability" in text
