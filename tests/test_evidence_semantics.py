"""Tests for Sprint 2.2 Milestone 4 evidence semantics."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from evidence_semantics import (  # noqa: E402
    KNOWLEDGE_SIGNAL_KEY,
    PROVENANCE_BASIS_KEY,
    PROVENANCE_CONFIDENCE_KEY,
    PROVENANCE_WARNING_KEY,
    SEMANTIC_SOURCE_LABEL_KEY,
    SEMANTIC_SOURCE_TYPE_KEY,
    assess_evidence_semantics,
    enrich_evidence_semantics,
)
from evidence_classification import EvidenceSourceType  # noqa: E402


class EvidenceSemanticsTests(unittest.TestCase):
    def test_explicit_sender_is_high_confidence(self) -> None:
        assessment = assess_evidence_semantics(
            {
                "file": "Appendix H5.pdf",
                "chunk_source_type": "employer_record",
                "chunk_provenance_method": "chunk-leading-sender",
                "evidence_classification_method": "automatic",
            },
            text="From: HR Director\nWe are writing regarding your return to work.",
        )

        self.assertEqual(assessment.source_type, EvidenceSourceType.EMPLOYER_RECORD)
        self.assertEqual(assessment.basis, "explicit_sender")
        self.assertEqual(assessment.confidence, "high")

    def test_signature_is_high_confidence(self) -> None:
        assessment = assess_evidence_semantics(
            {
                "file": "Appendix H5.pdf",
                "chunk_source_type": "insurer_record",
                "chunk_provenance_method": "chunk-signature",
            },
            text="Kind regards\nUnum Claims Assessor",
        )

        self.assertEqual(assessment.basis, "signature")
        self.assertEqual(assessment.confidence, "high")

    def test_witness_statement_known_author_is_not_downgraded_by_subject(self) -> None:
        assessment = assess_evidence_semantics(
            {
                "file": "Appendix J - Witness Statement of Mr Arshad Shafi.pdf",
                "chunk_source_type": "claimant_witness_statement",
                "chunk_provenance_method": "document-authorship-inherited",
                "evidence_classification_method": "automatic",
            },
            text="I refer to Occupational Health, CACI and Unum.",
        )

        self.assertEqual(
            assessment.source_type,
            EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT,
        )
        self.assertEqual(assessment.basis, "known_document_author")
        self.assertEqual(assessment.confidence, "high")

    def test_l5_automatic_oh_container_is_downgraded_semantically(self) -> None:
        assessment = assess_evidence_semantics(
            {
                "file": "Appendix L5 - Leadership Continuity (Weir and Khaira).pdf",
                "chunk_source_type": "occupational_health",
                "chunk_provenance_method": "document-inherited",
                "evidence_classification_method": "automatic",
            },
            text=(
                "Leadership continuity materials refer to historical HR and "
                "Occupational Health records."
            ),
        )

        self.assertEqual(assessment.source_type, EvidenceSourceType.OTHER)
        self.assertEqual(assessment.label, "Unclassified evidence")
        self.assertEqual(assessment.basis, "container_fallback")
        self.assertEqual(assessment.confidence, "low")
        self.assertIn("does not establish", assessment.warning)

    def test_real_oh_filename_can_retain_medium_container_provenance(self) -> None:
        assessment = assess_evidence_semantics(
            {
                "file": "Occupational Health Report 12 May 2005.pdf",
                "chunk_source_type": "occupational_health",
                "chunk_provenance_method": "document-inherited",
                "evidence_classification_method": "automatic",
            },
            text="Clinical assessment text.",
        )

        self.assertEqual(
            assessment.source_type,
            EvidenceSourceType.OCCUPATIONAL_HEALTH,
        )
        self.assertEqual(assessment.confidence, "medium")
        self.assertEqual(assessment.basis, "container_fallback")

    def test_mixed_bundle_remains_mixed_with_medium_confidence(self) -> None:
        assessment = assess_evidence_semantics(
            {
                "file": "Appendix H4 - Unum correspondence.pdf",
                "chunk_source_type": "mixed_correspondence",
                "chunk_provenance_method": "mixed-container-fallback",
            },
            text="CACI and Unum exchanged correspondence.",
        )

        self.assertEqual(
            assessment.source_type,
            EvidenceSourceType.MIXED_CORRESPONDENCE,
        )
        self.assertEqual(assessment.basis, "mixed")
        self.assertEqual(assessment.confidence, "medium")

    def test_manual_provenance_is_high_confidence(self) -> None:
        assessment = assess_evidence_semantics(
            {
                "file": "Bundle.pdf",
                "chunk_source_type": "employer_record",
                "chunk_provenance_method": "manual",
            },
            text="Manual source attribution.",
        )

        self.assertEqual(assessment.basis, "manual")
        self.assertEqual(assessment.confidence, "high")

    def test_claimant_response_with_explicit_sender_is_claimant_evidence(self) -> None:
        assessment = assess_evidence_semantics(
            {
                "file": "CACI Employment correspondence July 2026.pdf",
                "chunk_source_type": "claimant_correspondence",
                "chunk_provenance_method": "chunk-leading-sender",
                "evidence_source_type": "employer_record",
            },
            text=(
                "From: You\nTo: Alison Brooks\nPlease refer me to Occupational "
                "Health and consider reasonable adjustments."
            ),
        )

        self.assertEqual(
            assessment.source_type,
            EvidenceSourceType.CLAIMANT_CORRESPONDENCE,
        )
        self.assertEqual(assessment.confidence, "high")

    def test_claimant_named_response_filename_overrides_weak_container(self) -> None:
        assessment = assess_evidence_semantics(
            {
                "file": "Arshad Shafi - Response to Capability Review - 24 July 2026 (1).pdf",
                "chunk_source_type": "other",
                "chunk_provenance_method": "document-inherited",
                "evidence_classification_method": "automatic",
            },
            text="I request an Occupational Health referral and reasonable adjustments.",
        )

        self.assertEqual(
            assessment.source_type,
            EvidenceSourceType.CLAIMANT_CORRESPONDENCE,
        )
        self.assertEqual(assessment.label, "Claimant evidence")
        self.assertEqual(assessment.basis, "known_document_author")
        self.assertEqual(assessment.confidence, "high")

    def test_employer_container_does_not_override_claimant_first_person_response(self) -> None:
        assessment = assess_evidence_semantics(
            {
                "file": "CACI_Letter_24_July_2026 v2.pdf",
                "chunk_source_type": "employer_record",
                "chunk_provenance_method": "document-inherited",
                "evidence_classification_method": "automatic",
            },
            text=(
                "Dear Ms Brooks, Thank you for your email. Please find attached "
                "my response to your letter dated 17 July 2026 regarding the "
                "capability review process. I welcome the opportunity to engage "
                "constructively with the Company's capability review."
            ),
        )

        self.assertEqual(
            assessment.source_type,
            EvidenceSourceType.CLAIMANT_CORRESPONDENCE,
        )
        self.assertEqual(assessment.label, "Claimant evidence")
        self.assertEqual(assessment.basis, "known_document_author")
        self.assertEqual(assessment.confidence, "medium")
        self.assertIn("container ownership", assessment.warning.casefold())

    def test_claimant_signature_overrides_weak_employer_container(self) -> None:
        assessment = assess_evidence_semantics(
            {
                "file": "CACI correspondence bundle.pdf",
                "chunk_source_type": "employer_record",
                "chunk_provenance_method": "document-inherited",
                "evidence_classification_method": "automatic",
            },
            text=(
                "Please refer me to Occupational Health before any decision.\n\n"
                "Kind regards\nArshad Shafi"
            ),
        )

        self.assertEqual(
            assessment.source_type,
            EvidenceSourceType.CLAIMANT_CORRESPONDENCE,
        )
        self.assertEqual(assessment.basis, "signature")
        self.assertEqual(assessment.confidence, "high")

    def test_employer_first_person_letter_is_not_reclassified_as_claimant(self) -> None:
        assessment = assess_evidence_semantics(
            {
                "file": "CACI capability review letter.pdf",
                "chunk_source_type": "employer_record",
                "chunk_provenance_method": "document-inherited",
                "evidence_classification_method": "automatic",
            },
            text=(
                "I am writing regarding your employment and your current fitness "
                "for work. We request that you provide medical evidence."
            ),
        )

        self.assertEqual(assessment.source_type, EvidenceSourceType.EMPLOYER_RECORD)
        self.assertEqual(assessment.label, "Employer evidence")
        self.assertEqual(assessment.basis, "container_fallback")

    def test_awareness_statement_is_identified_as_source_assertion_signal(self) -> None:
        assessment = assess_evidence_semantics(
            {
                "file": "Witness statement.pdf",
                "chunk_source_type": "claimant_witness_statement",
                "chunk_provenance_method": "document-authorship-inherited",
            },
            text="CACI was fully aware of the medical recommendations.",
        )

        self.assertEqual(assessment.knowledge_signal, "source_assertion")
        self.assertIn("assertion", assessment.knowledge_signal_label.casefold())

    def test_direct_receipt_language_is_only_an_indicator(self) -> None:
        assessment = assess_evidence_semantics(
            {
                "file": "CACI HR email.pdf",
                "chunk_source_type": "employer_record",
                "chunk_provenance_method": "chunk-leading-sender",
            },
            text="From: HR Director\nWe received the OH report on 12 May 2005.",
        )

        self.assertEqual(
            assessment.knowledge_signal,
            "direct_communication_indicator",
        )
        self.assertIn("indicator", assessment.knowledge_signal_label.casefold())

    def test_enrichment_preserves_order_and_frozen_ranking_metadata(self) -> None:
        results = {
            "documents": [["first", "second"]],
            "metadatas": [[
                {
                    "file": "One.pdf",
                    "chunk_source_type": "employer_record",
                    "chunk_provenance_method": "chunk-leading-sender",
                    "primary_source_tier": 4,
                    "retrieval_original_rank": 5,
                    "retrieval_rerank_rank": 2,
                },
                {
                    "file": "Two.pdf",
                    "chunk_source_type": "claimant_witness_statement",
                    "chunk_provenance_method": "document-authorship-inherited",
                    "primary_source_tier": 1,
                    "retrieval_original_rank": 2,
                    "retrieval_rerank_rank": 5,
                },
            ]],
        }

        enriched = enrich_evidence_semantics(results)

        self.assertEqual(enriched["documents"][0], ["first", "second"])
        self.assertEqual(
            [m["file"] for m in enriched["metadatas"][0]],
            ["One.pdf", "Two.pdf"],
        )
        self.assertEqual(enriched["metadatas"][0][0]["primary_source_tier"], 4)
        self.assertEqual(enriched["metadatas"][0][0]["retrieval_rerank_rank"], 2)
        self.assertIn(SEMANTIC_SOURCE_TYPE_KEY, enriched["metadatas"][0][0])
        self.assertIn(SEMANTIC_SOURCE_LABEL_KEY, enriched["metadatas"][0][0])
        self.assertIn(PROVENANCE_BASIS_KEY, enriched["metadatas"][0][0])
        self.assertIn(PROVENANCE_CONFIDENCE_KEY, enriched["metadatas"][0][0])
        self.assertIn(PROVENANCE_WARNING_KEY, enriched["metadatas"][0][0])
        self.assertIn(KNOWLEDGE_SIGNAL_KEY, enriched["metadatas"][0][0])


if __name__ == "__main__":
    unittest.main()
