"""Tests for Sprint 2.2 Milestone 2 evidence-source classification."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from evidence_classification import (  # noqa: E402
    EVIDENCE_CLASSIFICATION_METHOD_KEY,
    EVIDENCE_SOURCE_LABEL_KEY,
    EVIDENCE_SOURCE_TYPE_KEY,
    EvidenceSourceType,
    add_classification_to_metadata,
    classify_evidence_source,
    enrich_retrieval_metadata,
)


class EvidenceClassificationTests(unittest.TestCase):
    def test_claimant_witness_statement_uses_document_hint(self) -> None:
        classification = classify_evidence_source(
            file_name="Supplementary Witness Statement.pdf",
            text="Paragraph 32. There was no further contact.",
            document_hint="I am the Claimant in these proceedings.",
        )

        self.assertEqual(
            classification.source_type,
            EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT,
        )
        self.assertEqual(classification.label, "Claimant evidence")

    def test_ambiguous_witness_statement_is_not_assigned_to_a_party(self) -> None:
        classification = classify_evidence_source(
            file_name="Witness Statement.pdf",
            text="I make this statement from matters within my knowledge.",
        )

        self.assertEqual(
            classification.source_type,
            EvidenceSourceType.WITNESS_STATEMENT,
        )
        self.assertEqual(classification.label, "Witness evidence")

    def test_independent_medical_evidence_is_identified(self) -> None:
        classification = classify_evidence_source(
            file_name="Consultant Psychiatrist Report.pdf",
            text="Clinical assessment and diagnosis.",
        )

        self.assertEqual(
            classification.source_type,
            EvidenceSourceType.INDEPENDENT_MEDICAL,
        )
        self.assertEqual(classification.label, "Independent medical evidence")

    def test_occupational_health_is_not_upgraded_to_independent_medical(self) -> None:
        classification = classify_evidence_source(
            file_name="Occupational Health Report.pdf",
            text="The occupational physician advised a phased return.",
        )

        self.assertEqual(
            classification.source_type,
            EvidenceSourceType.OCCUPATIONAL_HEALTH,
        )
        self.assertEqual(classification.label, "Occupational-health evidence")

    def test_insurer_record_is_identified(self) -> None:
        classification = classify_evidence_source(
            file_name="Unum correspondence.pdf",
            text="Income protection benefit remains payable.",
        )

        self.assertEqual(
            classification.source_type,
            EvidenceSourceType.INSURER_RECORD,
        )

    def test_employer_name_alone_does_not_force_employer_classification(self) -> None:
        classification = classify_evidence_source(
            file_name="Appendix H correspondence.pdf",
            text="Dear CACI, I am writing in response to your letter.",
        )

        self.assertEqual(
            classification.source_type,
            EvidenceSourceType.MIXED_CORRESPONDENCE,
        )

    def test_explicit_classification_override_is_supported(self) -> None:
        classification = classify_evidence_source(
            file_name="Ambiguous.pdf",
            text="Mixed text",
            explicit_source_type="employer_record",
        )

        self.assertEqual(
            classification.source_type,
            EvidenceSourceType.EMPLOYER_RECORD,
        )
        self.assertEqual(classification.method, "explicit")

    def test_existing_valid_metadata_is_preserved(self) -> None:
        metadata = {
            "file": "Bundle.pdf",
            "page": 2,
            EVIDENCE_SOURCE_TYPE_KEY: "claimant_submission",
            EVIDENCE_CLASSIFICATION_METHOD_KEY: "explicit",
        }

        enriched = add_classification_to_metadata(
            metadata,
            text="This chunk looks like something else.",
        )

        self.assertEqual(
            enriched[EVIDENCE_SOURCE_TYPE_KEY],
            "claimant_submission",
        )
        self.assertEqual(enriched[EVIDENCE_SOURCE_LABEL_KEY], "Claimant submission")
        self.assertEqual(
            enriched[EVIDENCE_CLASSIFICATION_METHOD_KEY],
            "explicit",
        )

    def test_legacy_retrieval_is_enriched_without_reindexing(self) -> None:
        results = {
            "documents": [[
                "Paragraph 10.",
                "I am the Claimant in these proceedings.",
                "We are writing regarding your employment with the Company.",
            ]],
            "metadatas": [[
                {"file": "Supplementary Witness Statement.pdf", "page": 2},
                {"file": "Supplementary Witness Statement.pdf", "page": 1},
                {"file": "HR letter.pdf", "page": 1},
            ]],
            "ids": [["a", "b", "c"]],
        }

        enriched = enrich_retrieval_metadata(results)

        self.assertEqual(
            enriched["metadatas"][0][0][EVIDENCE_SOURCE_TYPE_KEY],
            "claimant_witness_statement",
        )
        self.assertEqual(
            enriched["metadatas"][0][2][EVIDENCE_SOURCE_LABEL_KEY],
            "Employer evidence",
        )
        self.assertNotIn(EVIDENCE_SOURCE_TYPE_KEY, results["metadatas"][0][0])


if __name__ == "__main__":
    unittest.main()
