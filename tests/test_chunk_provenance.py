"""Tests for Sprint 2.2 Milestone 3 chunk-level provenance."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from chunk_provenance import (  # noqa: E402
    CHUNK_PROVENANCE_METHOD_KEY,
    CHUNK_SOURCE_LABEL_KEY,
    CHUNK_SOURCE_TYPE_KEY,
    PRIMARY_SOURCE_LABEL_KEY,
    PRIMARY_SOURCE_TIER_KEY,
    add_chunk_provenance_to_metadata,
    classify_chunk_provenance,
    enrich_chunk_provenance,
)
from evidence_classification import EvidenceSourceType  # noqa: E402


class ChunkProvenanceTests(unittest.TestCase):
    def test_employer_email_inside_insurer_bundle_uses_chunk_sender(self) -> None:
        provenance = classify_chunk_provenance(
            file_name="Appendix H4 - Unum correspondence.pdf",
            text=(
                "From: Alison Brooks (HR Director)\n"
                "To: Unum Claims\n"
                "We are writing regarding the employee's absence."
            ),
            document_source_type="insurer_record",
        )

        self.assertEqual(provenance.source_type, EvidenceSourceType.EMPLOYER_RECORD)
        self.assertEqual(provenance.label, "Employer evidence")
        self.assertEqual(provenance.method, "chunk-leading-sender")

    def test_insurer_email_inside_mixed_bundle_uses_chunk_sender(self) -> None:
        provenance = classify_chunk_provenance(
            file_name="Appendix H5 - Return to work correspondence.pdf",
            text=(
                "From: Unum Claims Assessor\n"
                "To: Human Resources\n"
                "The income protection benefit remains under review."
            ),
            document_source_type="mixed_correspondence",
        )

        self.assertEqual(provenance.source_type, EvidenceSourceType.INSURER_RECORD)
        self.assertEqual(provenance.label, "Insurer evidence")

    def test_ambiguous_mixed_chunk_is_not_upgraded_to_insurer(self) -> None:
        provenance = classify_chunk_provenance(
            file_name="Appendix H4 - Unum correspondence.pdf",
            text=(
                "Human Resources discussed the proposed return to work with Unum. "
                "Unum later discussed the income protection benefit with HR."
            ),
            document_source_type="insurer_record",
        )

        self.assertEqual(
            provenance.source_type,
            EvidenceSourceType.MIXED_CORRESPONDENCE,
        )
        self.assertEqual(provenance.label, "Mixed / composite evidence")

    def test_single_subject_reference_without_authorship_stays_mixed(self) -> None:
        provenance = classify_chunk_provenance(
            file_name="Appendix H5 - Return to work correspondence.pdf",
            text="The proposed plan was later sent to Unum for consideration.",
            document_source_type="insurer_record",
        )

        self.assertEqual(
            provenance.source_type,
            EvidenceSourceType.MIXED_CORRESPONDENCE,
        )

    def test_ambiguous_correspondence_container_falls_back_to_mixed(self) -> None:
        provenance = classify_chunk_provenance(
            file_name="Appendix H4 - Unum correspondence.pdf",
            text="The parties exchanged further correspondence on 12 May 2005.",
            document_source_type="insurer_record",
        )

        self.assertEqual(
            provenance.source_type,
            EvidenceSourceType.MIXED_CORRESPONDENCE,
        )
        self.assertEqual(provenance.method, "mixed-container-fallback")

    def test_non_mixed_witness_statement_inherits_document_classification(self) -> None:
        provenance = classify_chunk_provenance(
            file_name="Supplementary Witness Statement.pdf",
            text="Paragraph 35. There was no further contact.",
            document_source_type="claimant_witness_statement",
        )

        self.assertEqual(
            provenance.source_type,
            EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT,
        )
        self.assertEqual(provenance.primary_tier, 1)

    def test_claimant_witness_statement_mentioning_oh_keeps_claimant_authorship(self) -> None:
        provenance = classify_chunk_provenance(
            file_name="Appendix J - Witness Statement of Mr Arshad Shafi.pdf",
            text=(
                "I explain that Occupational Health discussed my return to work "
                "and that Unum later contacted Human Resources."
            ),
            document_source_type="claimant_witness_statement",
        )

        self.assertEqual(
            provenance.source_type,
            EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT,
        )
        self.assertEqual(provenance.label, "Claimant evidence")
        self.assertEqual(provenance.method, "document-authorship-inherited")

    def test_generic_witness_statement_mentioning_oh_keeps_witness_authorship(self) -> None:
        provenance = classify_chunk_provenance(
            file_name="Appendix J - Witness Statement.pdf",
            text=(
                "Occupational Health recommended a phased return and CACI Human "
                "Resources later discussed that recommendation with Unum."
            ),
            document_source_type="witness_statement",
        )

        self.assertEqual(
            provenance.source_type,
            EvidenceSourceType.WITNESS_STATEMENT,
        )
        self.assertEqual(provenance.label, "Witness evidence")

    def test_claimant_witness_statement_mentioning_caci_keeps_claimant_authorship(self) -> None:
        provenance = classify_chunk_provenance(
            file_name="Appendix J - Witness Statement.pdf",
            text=(
                "CACI Human Resources did not contact me after the relapse and "
                "the employer did not arrange a further OH review."
            ),
            document_source_type="claimant_witness_statement",
        )

        self.assertEqual(
            provenance.source_type,
            EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT,
        )

    def test_claimant_correspondence_mentions_other_sources_without_changing_authorship(self) -> None:
        provenance = classify_chunk_provenance(
            file_name="Claimant response dated 24 July 2026.pdf",
            text=(
                "I ask CACI to refer me to Occupational Health and to consider "
                "the Unum medical material before making any decision."
            ),
            document_source_type="claimant_correspondence",
        )

        self.assertEqual(
            provenance.source_type,
            EvidenceSourceType.CLAIMANT_CORRESPONDENCE,
        )
        self.assertEqual(provenance.label, "Claimant evidence")

    def test_outlook_you_sender_is_claimant_correspondence(self) -> None:
        provenance = classify_chunk_provenance(
            file_name="Appendix H5 - Return to work correspondence.pdf",
            text=(
                "From: You\n"
                "To: Alison Brooks (HR Director)\n"
                "Please refer me to Occupational Health before any decision."
            ),
            document_source_type="mixed_correspondence",
        )

        self.assertEqual(
            provenance.source_type,
            EvidenceSourceType.CLAIMANT_CORRESPONDENCE,
        )
        self.assertEqual(provenance.method, "chunk-leading-sender")

    def test_employer_signature_beats_body_mentions_of_unum_and_oh(self) -> None:
        provenance = classify_chunk_provenance(
            file_name="Appendix H5 - Return to work correspondence.pdf",
            text=(
                "We have considered the Unum material and the Occupational "
                "Health recommendations.\n\nKind regards\nAlison Brooks\nHR Director"
            ),
            document_source_type="mixed_correspondence",
        )

        self.assertEqual(provenance.source_type, EvidenceSourceType.EMPLOYER_RECORD)
        self.assertEqual(provenance.method, "chunk-signature")

    def test_oh_signature_beats_employer_subject_matter(self) -> None:
        provenance = classify_chunk_provenance(
            file_name="Medical assessment pack.pdf",
            text=(
                "CACI asked whether a phased return might be possible.\n\n"
                "Yours sincerely\nOccupational Health Adviser"
            ),
            document_source_type="insurer_record",
        )

        self.assertEqual(
            provenance.source_type,
            EvidenceSourceType.OCCUPATIONAL_HEALTH,
        )
        self.assertEqual(provenance.method, "chunk-signature")

    def test_direct_records_receive_highest_primary_source_tier(self) -> None:
        provenance = classify_chunk_provenance(
            file_name="HR letter.pdf",
            text="From: HR Director\nWe are writing regarding your employment.",
            document_source_type="employer_record",
        )

        self.assertEqual(provenance.primary_tier, 4)
        self.assertEqual(provenance.primary_label, "Primary/direct record")

    def test_stored_chunk_provenance_is_preserved(self) -> None:
        metadata = {
            "file": "Bundle.pdf",
            "page": 2,
            "evidence_source_type": "insurer_record",
            CHUNK_SOURCE_TYPE_KEY: "employer_record",
            CHUNK_PROVENANCE_METHOD_KEY: "manual",
        }

        enriched = add_chunk_provenance_to_metadata(
            metadata,
            text="This text mentions Unum but the stored local source is authoritative.",
        )

        self.assertEqual(enriched[CHUNK_SOURCE_TYPE_KEY], "employer_record")
        self.assertEqual(enriched[CHUNK_SOURCE_LABEL_KEY], "Employer evidence")
        self.assertEqual(enriched[CHUNK_PROVENANCE_METHOD_KEY], "manual")
        self.assertEqual(enriched[PRIMARY_SOURCE_TIER_KEY], 4)
        self.assertEqual(enriched[PRIMARY_SOURCE_LABEL_KEY], "Primary/direct record")

    def test_stale_automatic_provenance_is_recomputed(self) -> None:
        metadata = {
            "file": "Appendix J - Witness Statement.pdf",
            "page": 1,
            "evidence_source_type": "witness_statement",
            CHUNK_SOURCE_TYPE_KEY: "occupational_health",
            CHUNK_PROVENANCE_METHOD_KEY: "chunk-content",
        }

        enriched = add_chunk_provenance_to_metadata(
            metadata,
            text="Occupational Health and CACI are discussed in this paragraph.",
        )

        self.assertEqual(enriched[CHUNK_SOURCE_TYPE_KEY], "witness_statement")
        self.assertEqual(enriched[CHUNK_SOURCE_LABEL_KEY], "Witness evidence")
        self.assertEqual(
            enriched[CHUNK_PROVENANCE_METHOD_KEY],
            "document-authorship-inherited",
        )

    def test_retrieval_enrichment_does_not_overwrite_document_classification(self) -> None:
        results = {
            "documents": [[
                "From: HR Director\nWe are writing regarding your employment."
            ]],
            "metadatas": [[{
                "file": "Appendix H4 - Unum correspondence.pdf",
                "page": 3,
                "case_id": "case-a",
                "evidence_source_type": "insurer_record",
                "evidence_source_label": "Insurer evidence",
            }]],
        }

        enriched = enrich_chunk_provenance(results)
        metadata = enriched["metadatas"][0][0]

        self.assertEqual(metadata["evidence_source_type"], "insurer_record")
        self.assertEqual(metadata[CHUNK_SOURCE_TYPE_KEY], "employer_record")
        self.assertEqual(metadata["case_id"], "case-a")


if __name__ == "__main__":
    unittest.main()
