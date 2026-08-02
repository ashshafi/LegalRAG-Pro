from __future__ import annotations

import unittest
from uuid import uuid4

from evidence_classification import EvidenceSourceType
from legal_analysis.enums import Confidence, EvidenceStatus
from legal_analysis.evidence_mapper import (
    ElementEvidenceMapper,
    _RetrievalRow,
    assess_element_relevance,
    evidence_reference_from_retrieval,
)
from legal_analysis.evidence_mapping import EvidenceRelevance
from legal_analysis.search_profiles import DEFAULT_ELEMENT_SEARCH_PROFILE_REGISTRY
from legal_analysis.selector import DeterministicIssueSelector


class FakeRetriever:
    def __init__(self, rows_by_element: dict[str, list[tuple[str, str, dict]]]) -> None:
        self.rows_by_element = rows_by_element
        self.calls: list[tuple[str, str | None, int]] = []

    def __call__(self, question, selected_documents=None, n_results=10, *, case_id=None):
        self.calls.append((question, case_id, n_results))
        element_id = next(
            (key for key in self.rows_by_element if key in question),
            "",
        )
        rows = self.rows_by_element.get(element_id, [])
        return {
            "ids": [[row[0] for row in rows]],
            "documents": [[row[1] for row in rows]],
            "metadatas": [[row[2] for row in rows]],
            "distances": [[0.1 for _ in rows]],
        }


def employer_metadata(file_name="CACI HR email.pdf", page=1):
    return {
        "file": file_name,
        "page": page,
        "case_id": "case-a",
        "evidence_source_type": "employer_record",
        "evidence_source_label": "Employer evidence",
        "evidence_classification_method": "explicit",
        "chunk_source_type": "employer_record",
        "chunk_source_label": "Employer evidence",
        "chunk_provenance_method": "chunk-leading-sender",
    }


class EvidenceMapperTests(unittest.TestCase):
    def test_reference_conversion_preserves_semantic_metadata(self) -> None:
        row = _RetrievalRow(
            "chunk-42",
            "From: HR Director\nWe received the medical report.",
            {
                **employer_metadata(page=4),
                "semantic_source_type": "employer_record",
                "provenance_basis": "explicit_sender",
                "provenance_confidence": "high",
                "knowledge_signal": "direct_communication_indicator",
                "document_id": "doc-1",
                "author": "HR Director",
                "date": "2005-06-14",
                "parties": "CACI, Arshad Shafi",
            },
        )
        ref = evidence_reference_from_retrieval(row)
        self.assertEqual(ref.chunk_id, "chunk-42")
        self.assertEqual(ref.document_id, "doc-1")
        self.assertEqual(ref.page, 4)
        self.assertEqual(ref.source_type, EvidenceSourceType.EMPLOYER_RECORD)
        self.assertEqual(ref.evidence_status, EvidenceStatus.EMPLOYER_EVIDENCE)
        self.assertEqual(ref.author, "HR Director")
        self.assertEqual(ref.parties, ("CACI", "Arshad Shafi"))
        self.assertEqual(ref.date.isoformat(), "2005-06-14")

    def test_source_assertion_is_not_upgraded(self) -> None:
        row = _RetrievalRow(
            "chunk-assertion",
            "The appendix says CACI was fully aware of the recommendations.",
            {
                "file": "Appendix H5.pdf",
                "page": 2,
                "semantic_source_type": "mixed_correspondence",
                "provenance_basis": "mixed",
                "provenance_confidence": "medium",
                "knowledge_signal": "source_assertion",
            },
        )
        ref = evidence_reference_from_retrieval(row)
        self.assertEqual(ref.evidence_status, EvidenceStatus.SOURCE_ASSERTION)

    def test_direct_knowledge_requires_direct_signal(self) -> None:
        profile = DEFAULT_ELEMENT_SEARCH_PROFILE_REGISTRY.get_profile(
            "EK-001", "1.0", "EK-DIRECT-KNOWLEDGE"
        )
        row = _RetrievalRow(
            "medical",
            "The claimant has a psychiatric disability and long-term symptoms.",
            {
                "file": "Medical report.pdf",
                "page": 1,
                "semantic_source_type": "independent_medical",
                "provenance_basis": "known_document_author",
                "provenance_confidence": "high",
            },
        )
        ref = evidence_reference_from_retrieval(row)
        relevance, confidence, _ = assess_element_relevance(
            evidence=ref, raw_text=row.text, profile=profile
        )
        self.assertNotEqual(relevance, EvidenceRelevance.RELEVANT)
        self.assertEqual(confidence, Confidence.LOW)

    def test_phased_return_can_map_to_adjustment(self) -> None:
        profile = DEFAULT_ELEMENT_SEARCH_PROFILE_REGISTRY.get_profile(
            "RA-001", "1.0", "RA-ADJUSTMENT"
        )
        row = _RetrievalRow(
            "rtw",
            "CACI discussed a seven-week phased return with reduced hours and support.",
            employer_metadata(),
        )
        ref = evidence_reference_from_retrieval(row)
        relevance, confidence, _ = assess_element_relevance(
            evidence=ref, raw_text=row.text, profile=profile
        )
        self.assertEqual(relevance, EvidenceRelevance.RELEVANT)
        self.assertIn(confidence, {Confidence.MEDIUM, Confidence.HIGH})

    def test_mapper_builds_valid_analysis_and_keeps_empty_elements(self) -> None:
        case_id = str(uuid4())
        selector = DeterministicIssueSelector()
        selection = selector.select(
            "What evidence shows CACI knew about my disability?", case_id=case_id
        )
        retriever = FakeRetriever(
            {
                "EK-DIRECT-KNOWLEDGE": [
                    (
                        "direct-1",
                        "From: HR Director\nWe received and discussed the medical information.",
                        employer_metadata(),
                    )
                ]
            }
        )
        result = ElementEvidenceMapper(retrieval_callable=retriever).map_primary_issue(
            case_id=case_id,
            user_question=selection.user_question,
            selection=selection,
        )
        self.assertEqual(result.analysis.issue_definition_id, "EK-001")
        self.assertEqual(len(result.analysis.elements), 9)
        direct = next(
            element
            for element in result.analysis.elements
            if element.element_id == "EK-DIRECT-KNOWLEDGE"
        )
        self.assertEqual(len(direct.neutral_evidence), 1)
        self.assertEqual(direct.evidential_gaps, ())
        empty = next(
            element
            for element in result.analysis.elements
            if element.element_id == "EK-INFORMATION"
        )
        self.assertEqual(empty.neutral_evidence, ())
        self.assertEqual(empty.evidential_gaps, ())

    def test_mapper_rejects_selection_without_primary_issue(self) -> None:
        selection = DeterministicIssueSelector().select("Did CACI breach my employment contract?")
        with self.assertRaises(ValueError):
            ElementEvidenceMapper(retrieval_callable=FakeRetriever({})).map_primary_issue(
                case_id=str(uuid4()),
                user_question=selection.user_question,
                selection=selection,
            )

    def test_mapper_rejects_question_mismatch(self) -> None:
        case_id = str(uuid4())
        selection = DeterministicIssueSelector().select(
            "What evidence shows CACI knew about my disability?", case_id=case_id
        )
        with self.assertRaises(ValueError):
            ElementEvidenceMapper(retrieval_callable=FakeRetriever({})).map_primary_issue(
                case_id=case_id,
                user_question="Different question",
                selection=selection,
            )

    def test_mapper_rejects_case_mismatch(self) -> None:
        selection = DeterministicIssueSelector().select(
            "What evidence shows CACI knew about my disability?", case_id=str(uuid4())
        )
        with self.assertRaises(ValueError):
            ElementEvidenceMapper(retrieval_callable=FakeRetriever({})).map_primary_issue(
                case_id=str(uuid4()),
                user_question=selection.user_question,
                selection=selection,
            )


if __name__ == "__main__":
    unittest.main()
