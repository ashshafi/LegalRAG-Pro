from __future__ import annotations

import unittest

from evidence_classification import EvidenceSourceType
from legal_analysis.assessment_rules import (
    apply_corroboration,
    assess_proposition,
    assessment_role,
    detect_conflict,
    evidence_with_role,
    gap_for_element,
)
from legal_analysis.enums import AnalyticalRole, Confidence, EvidenceStatus
from legal_analysis.evidence_assessment import EvidenceAssessment, PropositionAssessmentStatus
from legal_analysis.evidence_mapping import EvidenceMapping, EvidenceRelevance
from legal_analysis.models import EvidenceReference


def ref(
    text: str,
    *,
    source=EvidenceSourceType.EMPLOYER_RECORD,
    status=EvidenceStatus.EMPLOYER_EVIDENCE,
    chunk="x",
) -> EvidenceReference:
    return EvidenceReference(
        document_name=f"{chunk}.pdf", summary=text, source_type=source,
        evidence_status=status, analytical_role=AnalyticalRole.NEUTRAL,
        citation=f"{chunk}.pdf, p.1", chunk_id=chunk, page=1,
    )


def mapping(evidence: EvidenceReference, *, confidence=Confidence.HIGH, element="EK-DIRECT-KNOWLEDGE"):
    return EvidenceMapping(
        evidence=evidence, issue_definition_id="EK-001", issue_definition_version="1.0",
        element_id=element, relevance=EvidenceRelevance.RELEVANT,
        mapping_confidence=confidence, mapping_rationale="Relevant mapped evidence.",
    )


class AssessmentRuleTests(unittest.TestCase):
    def test_high_confidence_direct_record_is_supporting(self):
        role, confidence, _ = assessment_role(mapping(ref("From HR: We received the medical information.")))
        self.assertEqual(role, AnalyticalRole.SUPPORTING)
        self.assertEqual(confidence, Confidence.HIGH)

    def test_source_assertion_remains_supporting_but_capped(self):
        ev = ref("Appendix asserts CACI knew.", source=EvidenceSourceType.MIXED_CORRESPONDENCE, status=EvidenceStatus.SOURCE_ASSERTION)
        role, confidence, _ = assessment_role(mapping(ev))
        self.assertEqual(role, AnalyticalRole.SUPPORTING)
        self.assertEqual(confidence, Confidence.MEDIUM)
        proposition = assess_proposition(mapping(ev), role)
        self.assertEqual(proposition.status, PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED)

    def test_claimant_evidence_is_not_independent_fact(self):
        ev = ref("I told CACI about my condition.", source=EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT, status=EvidenceStatus.CLAIMANT_EVIDENCE)
        role, confidence, _ = assessment_role(mapping(ev))
        self.assertEqual(role, AnalyticalRole.SUPPORTING)
        self.assertEqual(confidence, Confidence.MEDIUM)
        self.assertEqual(assess_proposition(mapping(ev), role).status, PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED)

    def test_respondent_denial_is_adverse(self):
        ev = ref("The Respondent denies that it received the recommendation.", source=EvidenceSourceType.RESPONDENT_SUBMISSION, status=EvidenceStatus.RESPONDENT_EVIDENCE)
        role, _, _ = assessment_role(mapping(ev))
        self.assertEqual(role, AnalyticalRole.ADVERSE)

    def test_silence_is_not_adverse(self):
        ev = ref("The letter records the meeting date but says nothing about receipt.")
        role, _, _ = assessment_role(mapping(ev, confidence=Confidence.MEDIUM))
        self.assertNotEqual(role, AnalyticalRole.ADVERSE)

    def test_role_copy_preserves_source_identity(self):
        ev = ref("CACI received the proposal.")
        copied = evidence_with_role(ev, AnalyticalRole.SUPPORTING)
        self.assertEqual(copied.source_type, ev.source_type)
        self.assertEqual(copied.evidence_status, ev.evidence_status)
        self.assertEqual(copied.chunk_id, ev.chunk_id)
        self.assertEqual(ev.analytical_role, AnalyticalRole.NEUTRAL)

    def test_independent_source_not_corrobative_without_overlap(self):
        insurer = mapping(ref("Unum records a rehabilitation review.", source=EvidenceSourceType.INSURER_RECORD, status=EvidenceStatus.INSURER_EVIDENCE, chunk="i"), confidence=Confidence.MEDIUM)
        role, conf, rationale = assessment_role(insurer)
        assessed = (EvidenceAssessment(insurer, role, conf, rationale),)
        self.assertEqual(apply_corroboration(assessed)[0].analytical_role, AnalyticalRole.SUPPORTING)

    def test_independent_source_becomes_corroborative_with_material_overlap(self):
        claimant = mapping(ref("A phased return meeting with CACI took place on 14 June 2005.", source=EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT, status=EvidenceStatus.CLAIMANT_EVIDENCE, chunk="c"), confidence=Confidence.MEDIUM)
        insurer = mapping(ref("Unum records the phased return meeting with CACI on 14 June 2005.", source=EvidenceSourceType.INSURER_RECORD, status=EvidenceStatus.INSURER_EVIDENCE, chunk="i"), confidence=Confidence.MEDIUM)
        items=[]
        for m in (claimant, insurer):
            role, conf, rationale=assessment_role(m)
            items.append(EvidenceAssessment(m, role, conf, rationale))
        result=apply_corroboration(items)
        insurer_result=next(x for x in result if x.mapping.evidence.chunk_id=="i")
        self.assertEqual(insurer_result.analytical_role, AnalyticalRole.CORROBORATIVE)

    def test_derivative_claimant_sources_do_not_create_independent_corroboration(self):
        a = mapping(ref("I told CACI about the phased return meeting.", source=EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT, status=EvidenceStatus.CLAIMANT_EVIDENCE, chunk="a"), confidence=Confidence.MEDIUM)
        b = mapping(ref("The claimant says he told CACI about the phased return meeting.", source=EvidenceSourceType.CLAIMANT_SUBMISSION, status=EvidenceStatus.CLAIMANT_EVIDENCE, chunk="b"), confidence=Confidence.MEDIUM)
        items=[]
        for m in (a,b):
            role, conf, rationale=assessment_role(m)
            items.append(EvidenceAssessment(m, role, conf, rationale))
        self.assertTrue(all(x.analytical_role is AnalyticalRole.SUPPORTING for x in apply_corroboration(items)))

    def test_explicit_opposing_accounts_create_dispute(self):
        claimant = mapping(ref("I sent CACI the medical recommendation and it was received.", source=EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT, status=EvidenceStatus.CLAIMANT_EVIDENCE, chunk="c"), confidence=Confidence.MEDIUM)
        respondent = mapping(ref("CACI denies it received the medical recommendation.", source=EvidenceSourceType.RESPONDENT_SUBMISSION, status=EvidenceStatus.RESPONDENT_EVIDENCE, chunk="r"), confidence=Confidence.MEDIUM)
        items=[]
        for m in (claimant,respondent):
            role,conf,rationale=assessment_role(m)
            items.append(EvidenceAssessment(m,role,conf,rationale))
        converted, dispute=detect_conflict("EK-DIRECT-KNOWLEDGE", items)
        self.assertIsNotNone(dispute)
        self.assertTrue(all(x.analytical_role is AnalyticalRole.CONFLICTING for x in converted))

    def test_unrelated_denial_does_not_create_conflict(self):
        claimant = mapping(ref("I sent CACI a psychiatric report about my condition.", source=EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT, status=EvidenceStatus.CLAIMANT_EVIDENCE, chunk="c"), confidence=Confidence.MEDIUM)
        respondent = mapping(ref("CACI denies the office car park was unavailable.", source=EvidenceSourceType.RESPONDENT_SUBMISSION, status=EvidenceStatus.RESPONDENT_EVIDENCE, chunk="r"), confidence=Confidence.MEDIUM)
        items=[]
        for m in (claimant,respondent):
            role,conf,rationale=assessment_role(m)
            items.append(EvidenceAssessment(m,role,conf,rationale))
        _, dispute=detect_conflict("EK-DIRECT-KNOWLEDGE", items)
        self.assertIsNone(dispute)

    def test_specific_gap_created_when_direct_knowledge_evidence_absent(self):
        claimant = mapping(ref("I say CACI knew.", source=EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT, status=EvidenceStatus.CLAIMANT_EVIDENCE, chunk="c"), confidence=Confidence.MEDIUM)
        role,conf,rationale=assessment_role(claimant)
        gap=gap_for_element("EK-DIRECT-KNOWLEDGE", (EvidenceAssessment(claimant,role,conf,rationale),))
        self.assertIsNotNone(gap)
        self.assertEqual(gap.related_element_id, "EK-DIRECT-KNOWLEDGE")

    def test_direct_record_prevents_gap(self):
        direct = mapping(ref("From HR: We received and discussed the medical recommendation."), confidence=Confidence.HIGH)
        role,conf,rationale=assessment_role(direct)
        gap=gap_for_element("EK-DIRECT-KNOWLEDGE", (EvidenceAssessment(direct,role,conf,rationale),))
        self.assertIsNone(gap)

    def test_no_gap_inflation_for_unconfigured_element(self):
        self.assertIsNone(gap_for_element("RA-DISABILITY", ()))


if __name__ == "__main__":
    unittest.main()
