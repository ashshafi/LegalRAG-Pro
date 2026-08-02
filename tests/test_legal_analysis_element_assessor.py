from __future__ import annotations

import copy
import unittest
from uuid import uuid4

from evidence_classification import EvidenceSourceType
from legal_analysis.element_assessor import ElementEvidenceAssessor, format_assessment_diagnostics
from legal_analysis.enums import AnalysisStatus, AnalyticalRole, Confidence, EvidenceStatus
from legal_analysis.evidence_assessment import PropositionAssessmentStatus
from legal_analysis.evidence_mapping import ElementMappingResult, EvidenceMapping, EvidenceRelevance, MappedIssueAnalysis
from legal_analysis.models import ElementAnalysis, EvidenceReference, IssueAnalysis


def ev(text, *, chunk, source=EvidenceSourceType.EMPLOYER_RECORD, status=EvidenceStatus.EMPLOYER_EVIDENCE):
    return EvidenceReference(
        document_name=f"{chunk}.pdf", summary=text, source_type=source, evidence_status=status,
        analytical_role=AnalyticalRole.NEUTRAL, citation=f"{chunk}.pdf, p.1", chunk_id=chunk, page=1,
    )


def m(evidence, element, *, relevance=EvidenceRelevance.RELEVANT, confidence=Confidence.HIGH):
    return EvidenceMapping(
        evidence=evidence, issue_definition_id="EK-001", issue_definition_version="1.0",
        element_id=element, relevance=relevance, mapping_confidence=confidence,
        mapping_rationale="Mapped to the controlled element.",
    )


def mapped(element_id="EK-DIRECT-KNOWLEDGE", mappings=()):
    analysis=IssueAnalysis(
        case_id=str(uuid4()), issue_definition_id="EK-001", issue_definition_version="1.0",
        issue_name="Employer knowledge", user_question="What did CACI know?", legal_framework=("Equality Act 2010",),
        elements=(ElementAnalysis(element_id, "Direct knowledge", "What direct evidence records knowledge?", neutral_evidence=tuple(x.evidence for x in mappings if x.relevance is EvidenceRelevance.RELEVANT)),),
    )
    return MappedIssueAnalysis(analysis, (ElementMappingResult(element_id, "query", tuple(mappings)),))


class ElementAssessorTests(unittest.TestCase):
    def test_only_relevant_mappings_are_assessed(self):
        relevant=m(ev("CACI received the report.",chunk="r"),"EK-DIRECT-KNOWLEDGE")
        potential=m(ev("Background mention.",chunk="p"),"EK-DIRECT-KNOWLEDGE",relevance=EvidenceRelevance.POTENTIALLY_RELEVANT,confidence=Confidence.LOW)
        result=ElementEvidenceAssessor().assess(mapped(mappings=(relevant,potential)))
        assessments=result.element_assessments[0].evidence_assessments
        self.assertEqual([x.mapping.evidence_key for x in assessments],["r"])

    def test_m3_mapping_result_is_not_mutated(self):
        mapping=m(ev("CACI received the report.",chunk="r"),"EK-DIRECT-KNOWLEDGE")
        original=mapped(mappings=(mapping,))
        before=copy.deepcopy(original)
        result=ElementEvidenceAssessor().assess(original)
        self.assertEqual(original,before)
        self.assertEqual(original.analysis.elements[0].neutral_evidence[0].analytical_role,AnalyticalRole.NEUTRAL)
        self.assertEqual(result.assessed_analysis.elements[0].supporting_evidence[0].analytical_role,AnalyticalRole.SUPPORTING)

    def test_issue_analysis_identity_is_preserved(self):
        original=mapped()
        result=ElementEvidenceAssessor().assess(original)
        for field in ("issue_analysis_id","case_id","issue_definition_id","issue_definition_version","schema_version","created_at"):
            self.assertEqual(getattr(result.assessed_analysis,field),getattr(original.analysis,field))

    def test_direct_record_can_establish_only_source_level_proposition(self):
        mapping=m(ev("From HR: We received and discussed the return-to-work recommendation.",chunk="r"),"EK-DIRECT-KNOWLEDGE")
        result=ElementEvidenceAssessor().assess(mapped(mappings=(mapping,)))
        prop=result.element_assessments[0].assessed_propositions[0]
        self.assertEqual(prop.status,PropositionAssessmentStatus.ESTABLISHED_BY_CURRENT_EVIDENCE)
        self.assertIn("direct correspondence records",prop.text)
        self.assertNotIn("legally knew",prop.text.casefold())

    def test_source_assertion_never_establishes_truth(self):
        mapping=m(ev("Appendix asserts that CACI knew of the recommendations.",chunk="a",source=EvidenceSourceType.MIXED_CORRESPONDENCE,status=EvidenceStatus.SOURCE_ASSERTION),"EK-DIRECT-KNOWLEDGE",confidence=Confidence.HIGH)
        result=ElementEvidenceAssessor().assess(mapped(mappings=(mapping,)))
        prop=result.element_assessments[0].assessed_propositions[0]
        self.assertEqual(prop.status,PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED)

    def test_empty_element_remains_valid_and_conservative(self):
        result=ElementEvidenceAssessor().assess(mapped())
        element=result.assessed_analysis.elements[0]
        self.assertEqual(element.supporting_evidence,())
        self.assertEqual(result.element_assessments[0].assessment_confidence,Confidence.LOW)
        self.assertTrue(result.element_assessments[0].unresolved_matters)

    def test_knowledge_empty_element_can_create_specific_gap(self):
        result=ElementEvidenceAssessor().assess(mapped())
        self.assertEqual(len(result.element_assessments[0].evidential_gaps),1)

    def test_conflict_changes_analysis_status(self):
        c=m(ev("I sent CACI the medical recommendation and it was received.",chunk="c",source=EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT,status=EvidenceStatus.CLAIMANT_EVIDENCE),"EK-DIRECT-KNOWLEDGE",confidence=Confidence.MEDIUM)
        r=m(ev("CACI denies it received the medical recommendation.",chunk="r",source=EvidenceSourceType.RESPONDENT_SUBMISSION,status=EvidenceStatus.RESPONDENT_EVIDENCE),"EK-DIRECT-KNOWLEDGE",confidence=Confidence.MEDIUM)
        result=ElementEvidenceAssessor().assess(mapped(mappings=(c,r)))
        self.assertEqual(result.assessed_analysis.analysis_status,AnalysisStatus.CONFLICTING_EVIDENCE)
        self.assertEqual(len(result.assessed_analysis.elements[0].conflicting_evidence),2)
        self.assertEqual(len(result.element_assessments[0].disputed_matters),1)

    def test_no_conflict_status_when_no_explicit_contradiction(self):
        c=m(ev("I sent CACI the report.",chunk="c",source=EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT,status=EvidenceStatus.CLAIMANT_EVIDENCE),"EK-DIRECT-KNOWLEDGE",confidence=Confidence.MEDIUM)
        e=m(ev("CACI records a meeting date.",chunk="e"),"EK-DIRECT-KNOWLEDGE",confidence=Confidence.MEDIUM)
        result=ElementEvidenceAssessor().assess(mapped(mappings=(c,e)))
        self.assertEqual(result.assessed_analysis.analysis_status,AnalysisStatus.EVIDENCE_INCOMPLETE)

    def test_legal_analysis_field_remains_empty(self):
        result=ElementEvidenceAssessor().assess(mapped())
        self.assertIsNone(result.assessed_analysis.elements[0].legal_analysis)

    def test_diagnostics_show_roles_gaps_and_no_merits_conclusion(self):
        mapping=m(ev("Appendix asserts CACI knew.",chunk="a",source=EvidenceSourceType.MIXED_CORRESPONDENCE,status=EvidenceStatus.SOURCE_ASSERTION),"EK-DIRECT-KNOWLEDGE",confidence=Confidence.MEDIUM)
        text=format_assessment_diagnostics(ElementEvidenceAssessor().assess(mapped(mappings=(mapping,))))
        self.assertIn("Assessor: element-assessor/1.0",text)
        self.assertIn("SUPPORTING",text)
        self.assertIn("EVIDENTIAL GAPS",text)
        self.assertNotIn("element is satisfied",text.casefold())
        self.assertNotIn("claim succeeds",text.casefold())


if __name__ == "__main__":
    unittest.main()
