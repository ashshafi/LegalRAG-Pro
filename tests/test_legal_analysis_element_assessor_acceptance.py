from __future__ import annotations

from uuid import uuid4

from evidence_classification import EvidenceSourceType
from legal_analysis.definitions import INITIAL_ISSUE_DEFINITIONS
from legal_analysis.element_assessor import ElementEvidenceAssessor, format_assessment_diagnostics
from legal_analysis.enums import AnalyticalRole, Confidence, EvidenceStatus
from legal_analysis.evidence_mapping import ElementMappingResult, EvidenceMapping, EvidenceRelevance, MappedIssueAnalysis
from legal_analysis.models import ElementAnalysis, EvidenceReference, IssueAnalysis

DEFS={d.definition_id:d for d in INITIAL_ISSUE_DEFINITIONS}


def mapped_with_evidence(issue_id: str, element_id: str, text: str, *, source=EvidenceSourceType.EMPLOYER_RECORD, status=EvidenceStatus.EMPLOYER_EVIDENCE):
    definition=DEFS[issue_id]
    evidence=EvidenceReference(
        document_name="Acceptance evidence.pdf", summary=text, source_type=source,
        evidence_status=status, analytical_role=AnalyticalRole.NEUTRAL,
        citation="Acceptance evidence.pdf, p.1", chunk_id=f"{issue_id}-{element_id}", page=1,
    )
    mapping=EvidenceMapping(
        evidence=evidence, issue_definition_id=issue_id, issue_definition_version=definition.version,
        element_id=element_id, relevance=EvidenceRelevance.RELEVANT, mapping_confidence=Confidence.HIGH,
        mapping_rationale="Synthetic frozen acceptance mapping.",
    )
    elements=[]
    results=[]
    for item in definition.elements:
        item_mappings=(mapping,) if item.element_id==element_id else ()
        elements.append(ElementAnalysis(item.element_id,item.name,item.question_to_determine,neutral_evidence=(evidence,) if item_mappings else ()))
        results.append(ElementMappingResult(item.element_id,"query",item_mappings))
    analysis=IssueAnalysis(
        case_id=str(uuid4()), issue_definition_id=issue_id, issue_definition_version=definition.version,
        issue_name=definition.name, user_question="Synthetic acceptance", legal_framework=definition.legal_framework,
        elements=tuple(elements),
    )
    return MappedIssueAnalysis(analysis,tuple(results))


def test_ek_acceptance_preserves_direct_record_without_legal_knowledge_conclusion():
    result=ElementEvidenceAssessor().assess(mapped_with_evidence("EK-001","EK-DIRECT-KNOWLEDGE","From HR: We received and discussed the return-to-work information."))
    text=format_assessment_diagnostics(result).casefold()
    assert "supporting" in text
    assert "legally knew" not in text


def test_ra_acceptance_source_assertion_does_not_decide_reasonableness():
    mapped=mapped_with_evidence(
        "RA-001","RA-REASONABLENESS","The appendix asserts that home working was a reasonable adjustment.",
        source=EvidenceSourceType.MIXED_CORRESPONDENCE,status=EvidenceStatus.SOURCE_ASSERTION,
    )
    text=format_assessment_diagnostics(ElementEvidenceAssessor().assess(mapped)).casefold()
    assert "source_assertion" in text
    assert "home working was legally reasonable" not in text
    assert "element is satisfied" not in text


def test_lim_acceptance_does_not_decide_continuing_act():
    mapped=mapped_with_evidence(
        "LIM-001","LIM-CONTINUING-CONDUCT","The claimant states the omission continued after 2005.",
        source=EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT,status=EvidenceStatus.CLAIMANT_EVIDENCE,
    )
    text=format_assessment_diagnostics(ElementEvidenceAssessor().assess(mapped)).casefold()
    assert "supporting" in text
    assert "continuing act exists" not in text
    assert "claim is in time" not in text


def test_da_acceptance_does_not_decide_section_15():
    mapped=mapped_with_evidence(
        "DA-001","DA-CAUSATION","The claimant states the treatment followed disability-related absence.",
        source=EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT,status=EvidenceStatus.CLAIMANT_EVIDENCE,
    )
    text=format_assessment_diagnostics(ElementEvidenceAssessor().assess(mapped)).casefold()
    assert "supporting" in text
    assert "section 15 is established" not in text
