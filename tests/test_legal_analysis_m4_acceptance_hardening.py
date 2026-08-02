from __future__ import annotations

import unittest

from evidence_classification import EvidenceSourceType
from legal_analysis.assessment_rules import (
    assess_proposition,
    assessment_role,
    detect_conflict,
    gap_for_element,
)
from legal_analysis.enums import AnalyticalRole, Confidence, EvidenceStatus
from legal_analysis.evidence_assessment import EvidenceAssessment, PropositionAssessmentStatus
from legal_analysis.evidence_mapping import EvidenceMapping, EvidenceRelevance
from legal_analysis.models import EvidenceReference


def evidence(
    text: str,
    *,
    chunk: str,
    document_name: str | None = None,
    source_type: EvidenceSourceType = EvidenceSourceType.EMPLOYER_RECORD,
    status: EvidenceStatus = EvidenceStatus.EMPLOYER_EVIDENCE,
    author: str | None = None,
) -> EvidenceReference:
    return EvidenceReference(
        document_name=document_name or f"{chunk}.pdf",
        summary=text,
        source_type=source_type,
        evidence_status=status,
        analytical_role=AnalyticalRole.NEUTRAL,
        citation=f"{document_name or chunk + '.pdf'}, p.1",
        chunk_id=chunk,
        page=1,
        author=author,
    )


def mapped(
    item: EvidenceReference,
    *,
    element_id: str,
    definition_id: str = "EK-001",
    confidence: Confidence = Confidence.HIGH,
) -> EvidenceMapping:
    return EvidenceMapping(
        evidence=item,
        issue_definition_id=definition_id,
        issue_definition_version="1.0",
        element_id=element_id,
        relevance=EvidenceRelevance.RELEVANT,
        mapping_confidence=confidence,
        mapping_rationale="Synthetic relevant mapping for M4 hardening acceptance.",
    )


def assessed(mapping: EvidenceMapping) -> EvidenceAssessment:
    role, confidence, rationale = assessment_role(mapping)
    return EvidenceAssessment(mapping, role, confidence, rationale)


class M4AcceptanceHardeningTests(unittest.TestCase):
    def test_high_confidence_outlook_fragment_is_not_established_for_recipient_without_receipt_fact(self):
        item = evidence(
            "From: Terry Williamson <tw@caci.co.uk> To: Arshad Shafi Subject: Return to work. The report may conclude I am fit or unfit for work.",
            chunk="outlook",
        )
        mapping = mapped(item, element_id="EK-RECIPIENT")
        role, _, _ = assessment_role(mapping)
        proposition = assess_proposition(mapping, role, element_id="EK-RECIPIENT")
        self.assertEqual(proposition.status, PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED)
        self.assertNotIn("From:", proposition.text)
        self.assertNotIn("fit or unfit", proposition.text)

    def test_generic_fitness_fragment_is_not_established_for_ra_reasonableness(self):
        item = evidence(
            "The assessment will conclude I am fit or unfit for work and may comment on return to work.",
            chunk="fitness",
        )
        mapping = mapped(item, element_id="RA-REASONABLENESS", definition_id="RA-001")
        role, _, _ = assessment_role(mapping)
        proposition = assess_proposition(mapping, role, element_id="RA-REASONABLENESS")
        self.assertEqual(proposition.status, PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED)
        self.assertNotIn("fit or unfit", proposition.text)

    def test_explicit_health_receipt_record_establishes_concise_element_specific_fact(self):
        item = evidence(
            "From HR: We received and discussed the medical recommendation concerning the phased return.",
            chunk="receipt",
        )
        mapping = mapped(item, element_id="EK-DIRECT-KNOWLEDGE")
        role, _, _ = assessment_role(mapping)
        proposition = assess_proposition(mapping, role, element_id="EK-DIRECT-KNOWLEDGE")
        self.assertEqual(proposition.status, PropositionAssessmentStatus.ESTABLISHED_BY_CURRENT_EVIDENCE)
        self.assertIn("direct correspondence records", proposition.text.casefold())
        self.assertNotIn("from hr", proposition.text.casefold())

    def test_line_manager_email_does_not_become_claimant_side_of_limitation_conflict(self):
        line_manager = mapped(
            evidence(
                "From Terry Williamson. We discussed the proposed return to work on 14 June 2005.",
                chunk="h3",
                document_name="Appendix H3 - Email from Line Manager (Terry Williamson).pdf",
                source_type=EvidenceSourceType.CLAIMANT_CORRESPONDENCE,
                status=EvidenceStatus.CLAIMANT_EVIDENCE,
                author="Terry Williamson",
            ),
            element_id="LIM-ACTS",
            definition_id="LIM-001",
            confidence=Confidence.MEDIUM,
        )
        et3 = mapped(
            evidence(
                "The Respondent says the claim is out of time and the alleged matters were historic.",
                chunk="et3",
                document_name="ET3 and Grounds of Resistance.pdf",
                source_type=EvidenceSourceType.RESPONDENT_SUBMISSION,
                status=EvidenceStatus.RESPONDENT_EVIDENCE,
            ),
            element_id="LIM-ACTS",
            definition_id="LIM-001",
            confidence=Confidence.MEDIUM,
        )
        converted, dispute = detect_conflict("LIM-ACTS", (assessed(line_manager), assessed(et3)))
        self.assertIsNone(dispute)
        self.assertFalse(any(item.analytical_role is AnalyticalRole.CONFLICTING for item in converted))

    def test_conflict_requires_shared_receipt_proposition_with_incompatible_positions(self):
        claimant = mapped(
            evidence(
                "I sent CACI the medical recommendation and it was received.",
                chunk="claimant",
                source_type=EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT,
                status=EvidenceStatus.CLAIMANT_EVIDENCE,
                author="Arshad Shafi",
            ),
            element_id="EK-DIRECT-KNOWLEDGE",
            confidence=Confidence.MEDIUM,
        )
        respondent = mapped(
            evidence(
                "CACI denies it received the medical recommendation.",
                chunk="respondent",
                source_type=EvidenceSourceType.RESPONDENT_SUBMISSION,
                status=EvidenceStatus.RESPONDENT_EVIDENCE,
            ),
            element_id="EK-DIRECT-KNOWLEDGE",
            confidence=Confidence.MEDIUM,
        )
        converted, dispute = detect_conflict(
            "EK-DIRECT-KNOWLEDGE",
            (assessed(claimant), assessed(respondent)),
        )
        self.assertIsNotNone(dispute)
        self.assertIn("received by CACI", dispute.proposition)
        self.assertTrue(all(item.analytical_role is AnalyticalRole.CONFLICTING for item in converted))

    def test_respondent_pleading_present_but_limitation_fact_missing_gets_fact_specific_gap(self):
        et3 = mapped(
            evidence(
                "The Respondent denies liability and reserves its position.",
                chunk="et3",
                document_name="ET3 - Grounds of Resistance.pdf",
                source_type=EvidenceSourceType.RESPONDENT_SUBMISSION,
                status=EvidenceStatus.RESPONDENT_EVIDENCE,
            ),
            element_id="LIM-RESPONDENT-POSITION",
            definition_id="LIM-001",
            confidence=Confidence.MEDIUM,
        )
        gap = gap_for_element("LIM-RESPONDENT-POSITION", (assessed(et3),))
        self.assertIsNotNone(gap)
        self.assertIn("within the mapped respondent", gap.description.casefold())
        self.assertIn("is present", gap.reason.casefold())
        self.assertNotIn("does not contain a clear respondent statement", gap.reason.casefold())

    def test_clear_respondent_limitation_position_prevents_gap(self):
        et3 = mapped(
            evidence(
                "The Respondent's position is that the claim is out of time under section 123 and there was no continuing act.",
                chunk="et3-limit",
                document_name="ET3 - Grounds of Resistance.pdf",
                source_type=EvidenceSourceType.RESPONDENT_SUBMISSION,
                status=EvidenceStatus.RESPONDENT_EVIDENCE,
            ),
            element_id="LIM-RESPONDENT-POSITION",
            definition_id="LIM-001",
            confidence=Confidence.MEDIUM,
        )
        self.assertIsNone(gap_for_element("LIM-RESPONDENT-POSITION", (assessed(et3),)))

    def test_acas_source_present_without_date_gets_fact_specific_not_source_missing_gap(self):
        acas = mapped(
            evidence(
                "ACAS Early Conciliation Form concerning Shafi v CACI Ltd.",
                chunk="acas",
                document_name="ACAS Early Conciliation Form.pdf",
                source_type=EvidenceSourceType.TRIBUNAL_RECORD,
                status=EvidenceStatus.TRIBUNAL_RECORD,
            ),
            element_id="LIM-PRESENTATION",
            definition_id="LIM-001",
        )
        gap = gap_for_element("LIM-PRESENTATION", (assessed(acas),))
        self.assertIsNotNone(gap)
        self.assertIn("within the mapped procedural", gap.description.casefold())
        self.assertIn("is present", gap.reason.casefold())

    def test_acas_source_with_explicit_date_prevents_presentation_gap(self):
        acas = mapped(
            evidence(
                "ACAS Early Conciliation certificate records 12 May 2025 and the ET1 was presented on 20 May 2025.",
                chunk="acas-date",
                document_name="ACAS Early Conciliation Certificate.pdf",
                source_type=EvidenceSourceType.TRIBUNAL_RECORD,
                status=EvidenceStatus.TRIBUNAL_RECORD,
            ),
            element_id="LIM-PRESENTATION",
            definition_id="LIM-001",
        )
        self.assertIsNone(gap_for_element("LIM-PRESENTATION", (assessed(acas),)))


if __name__ == "__main__":
    unittest.main()
