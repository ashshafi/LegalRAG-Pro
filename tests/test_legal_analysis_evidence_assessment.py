from __future__ import annotations

import unittest
from uuid import uuid4

from evidence_classification import EvidenceSourceType
from legal_analysis.enums import AnalyticalRole, Confidence, EvidenceStatus, Materiality
from legal_analysis.evidence_assessment import (
    AssessedProposition,
    ELEMENT_ASSESSOR_VERSION,
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
from legal_analysis.models import ElementAnalysis, EvidenceReference, IssueAnalysis


def evidence(*, chunk_id="c1", role=AnalyticalRole.NEUTRAL) -> EvidenceReference:
    return EvidenceReference(
        document_name="Evidence.pdf",
        summary="CACI received the phased return proposal.",
        source_type=EvidenceSourceType.EMPLOYER_RECORD,
        evidence_status=EvidenceStatus.EMPLOYER_EVIDENCE,
        analytical_role=role,
        citation="Evidence.pdf, p.1",
        chunk_id=chunk_id,
        page=1,
    )


def mapping() -> EvidenceMapping:
    return EvidenceMapping(
        evidence=evidence(),
        issue_definition_id="EK-001",
        issue_definition_version="1.0",
        element_id="EK-DIRECT-KNOWLEDGE",
        relevance=EvidenceRelevance.RELEVANT,
        mapping_confidence=Confidence.HIGH,
        mapping_rationale="Direct receipt is recorded.",
    )


class EvidenceAssessmentModelTests(unittest.TestCase):
    def test_assessor_version_is_explicit(self):
        self.assertEqual(ELEMENT_ASSESSOR_VERSION, "element-assessor/1.0")

    def test_evidence_assessment_rejects_missing_role(self):
        with self.assertRaises(ValueError):
            EvidenceAssessment(mapping(), AnalyticalRole.MISSING, Confidence.HIGH, "Missing")

    def test_assessed_proposition_has_distinct_m4_status(self):
        item = AssessedProposition(
            text="CACI received the proposal.",
            status=PropositionAssessmentStatus.ESTABLISHED_BY_CURRENT_EVIDENCE,
            confidence=Confidence.HIGH,
            evidence_keys=("a", "a"),
            rationale="Direct email.",
        )
        self.assertEqual(item.evidence_keys, ("a",))
        self.assertNotIsInstance(item.status, EvidenceStatus)

    def test_element_assessment_rejects_cross_element_mapping(self):
        assessment = EvidenceAssessment(mapping(), AnalyticalRole.SUPPORTING, Confidence.HIGH, "Direct")
        with self.assertRaises(ValueError):
            ElementEvidenceAssessment(element_id="EK-RECIPIENT", evidence_assessments=(assessment,))

    def test_by_role_filters_assessments(self):
        support = EvidenceAssessment(mapping(), AnalyticalRole.SUPPORTING, Confidence.HIGH, "Direct")
        element = ElementEvidenceAssessment(element_id="EK-DIRECT-KNOWLEDGE", evidence_assessments=(support,))
        self.assertEqual(element.by_role(AnalyticalRole.SUPPORTING), (support,))
        self.assertEqual(element.by_role(AnalyticalRole.ADVERSE), ())

    def test_result_requires_same_analysis_identity(self):
        original = IssueAnalysis(
            case_id=str(uuid4()), issue_definition_id="EK-001", issue_definition_version="1.0",
            issue_name="Knowledge", user_question="What did CACI know?", legal_framework=("EqA",),
            elements=(ElementAnalysis("EK-DIRECT-KNOWLEDGE", "Direct", "What evidence?"),),
        )
        mapped = MappedIssueAnalysis(original, (ElementMappingResult("EK-DIRECT-KNOWLEDGE", "q", (mapping(),)),))
        changed = IssueAnalysis(
            case_id=original.case_id, issue_definition_id="EK-001", issue_definition_version="1.0",
            issue_name="Knowledge", user_question=original.user_question, legal_framework=original.legal_framework,
            elements=original.elements,
        )
        with self.assertRaises(ValueError):
            EvidenceAssessmentResult(mapped, changed, (ElementEvidenceAssessment("EK-DIRECT-KNOWLEDGE"),))


if __name__ == "__main__":
    unittest.main()
