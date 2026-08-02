from __future__ import annotations

import unittest
from uuid import uuid4

from legal_analysis.evidence_mapper import ElementEvidenceMapper
from legal_analysis.selector import DeterministicIssueSelector


class CaseAwareFakeRetriever:
    def __init__(self) -> None:
        self.case_ids: list[str | None] = []

    def __call__(self, question, selected_documents=None, n_results=10, *, case_id=None):
        self.case_ids.append(case_id)
        if "EK-DIRECT-KNOWLEDGE" in question:
            rows = [
                (
                    f"{case_id}-chunk",
                    "From: HR Director\nWe received and discussed the claimant's health information.",
                    {
                        "file": f"{case_id}-CACI-email.pdf",
                        "page": 1,
                        "case_id": case_id,
                        "evidence_source_type": "employer_record",
                        "evidence_source_label": "Employer evidence",
                        "evidence_classification_method": "explicit",
                        "chunk_source_type": "employer_record",
                        "chunk_source_label": "Employer evidence",
                        "chunk_provenance_method": "chunk-leading-sender",
                    },
                )
            ]
        else:
            rows = []
        return {
            "ids": [[row[0] for row in rows]],
            "documents": [[row[1] for row in rows]],
            "metadatas": [[row[2] for row in rows]],
            "distances": [[0.1 for _ in rows]],
        }


class MapperIntegrationTests(unittest.TestCase):
    def test_every_element_retrieval_is_case_scoped(self) -> None:
        case_id = str(uuid4())
        retriever = CaseAwareFakeRetriever()
        selection = DeterministicIssueSelector().select(
            "What evidence shows CACI knew about my disability?", case_id=case_id
        )
        result = ElementEvidenceMapper(retrieval_callable=retriever).map_primary_issue(
            case_id=case_id,
            user_question=selection.user_question,
            selection=selection,
        )
        self.assertEqual(len(retriever.case_ids), 9)
        self.assertEqual(set(retriever.case_ids), {case_id})
        self.assertEqual(result.analysis.case_id, case_id)

    def test_two_cases_never_share_fake_retrieved_evidence(self) -> None:
        retriever = CaseAwareFakeRetriever()
        mapper = ElementEvidenceMapper(retrieval_callable=retriever)
        case_a = str(uuid4())
        case_b = str(uuid4())
        question = "What evidence shows CACI knew about my disability?"
        result_a = mapper.map_primary_issue(
            case_id=case_a,
            user_question=question,
            selection=DeterministicIssueSelector().select(question, case_id=case_a),
        )
        result_b = mapper.map_primary_issue(
            case_id=case_b,
            user_question=question,
            selection=DeterministicIssueSelector().select(question, case_id=case_b),
        )
        direct_a = next(e for e in result_a.analysis.elements if e.element_id == "EK-DIRECT-KNOWLEDGE")
        direct_b = next(e for e in result_b.analysis.elements if e.element_id == "EK-DIRECT-KNOWLEDGE")
        self.assertEqual(direct_a.neutral_evidence[0].chunk_id, f"{case_a}-chunk")
        self.assertEqual(direct_b.neutral_evidence[0].chunk_id, f"{case_b}-chunk")
        self.assertNotEqual(direct_a.neutral_evidence[0].chunk_id, direct_b.neutral_evidence[0].chunk_id)

    def test_one_chunk_can_legitimately_map_to_multiple_elements(self) -> None:
        case_id = str(uuid4())

        class ReuseRetriever:
            def __call__(self, question, selected_documents=None, n_results=10, *, case_id=None):
                if "RA-KNOWLEDGE" in question or "RA-ADJUSTMENT" in question or "RA-TIMING" in question:
                    rows = [(
                        "shared-rtw-chunk",
                        "From: CACI HR\nOn 14 June 2005 we discussed and received the seven-week phased return proposal and reduced hours adjustment.",
                        {
                            "file": "CACI RTW email.pdf",
                            "page": 2,
                            "case_id": case_id,
                            "evidence_source_type": "employer_record",
                            "evidence_source_label": "Employer evidence",
                            "evidence_classification_method": "explicit",
                            "chunk_source_type": "employer_record",
                            "chunk_source_label": "Employer evidence",
                            "chunk_provenance_method": "chunk-leading-sender",
                        },
                    )]
                else:
                    rows = []
                return {
                    "ids": [[row[0] for row in rows]],
                    "documents": [[row[1] for row in rows]],
                    "metadatas": [[row[2] for row in rows]],
                    "distances": [[0.1 for _ in rows]],
                }

        question = "Should CACI have allowed me to work from home because of my disability?"
        selection = DeterministicIssueSelector().select(question, case_id=case_id)
        result = ElementEvidenceMapper(retrieval_callable=ReuseRetriever()).map_primary_issue(
            case_id=case_id,
            user_question=question,
            selection=selection,
        )
        mapped_ids = {
            element.element_id
            for element in result.analysis.elements
            if any(item.chunk_id == "shared-rtw-chunk" for item in element.neutral_evidence)
        }
        self.assertIn("RA-KNOWLEDGE", mapped_ids)
        self.assertIn("RA-ADJUSTMENT", mapped_ids)
        self.assertIn("RA-TIMING", mapped_ids)

    def test_salary_only_excerpt_does_not_contaminate_direct_knowledge(self) -> None:
        case_id = str(uuid4())

        class SalaryRetriever:
            def __call__(self, question, selected_documents=None, n_results=10, *, case_id=None):
                rows = [(
                    "salary",
                    "Annual salary £60,000. Employee: Arshad Shafi.",
                    {
                        "file": "P60.pdf",
                        "page": 1,
                        "case_id": case_id,
                        "evidence_source_type": "employer_record",
                        "evidence_source_label": "Employer evidence",
                        "evidence_classification_method": "explicit",
                        "chunk_source_type": "employer_record",
                        "chunk_source_label": "Employer evidence",
                        "chunk_provenance_method": "document-inherited",
                    },
                )]
                return {
                    "ids": [[row[0] for row in rows]],
                    "documents": [[row[1] for row in rows]],
                    "metadatas": [[row[2] for row in rows]],
                    "distances": [[0.1]],
                }

        question = "What evidence shows CACI knew about my disability?"
        result = ElementEvidenceMapper(retrieval_callable=SalaryRetriever()).map_primary_issue(
            case_id=case_id,
            user_question=question,
            selection=DeterministicIssueSelector().select(question, case_id=case_id),
        )
        direct = next(e for e in result.analysis.elements if e.element_id == "EK-DIRECT-KNOWLEDGE")
        self.assertEqual(direct.neutral_evidence, ())
        self.assertEqual(direct.evidential_gaps, ())


if __name__ == "__main__":
    unittest.main()


class FrozenQueryAcceptanceTests(unittest.TestCase):
    def _map_with_element_rows(self, question: str, rows_by_element: dict[str, tuple[str, str, dict]]):
        case_id = str(uuid4())

        class Retriever:
            def __call__(self, query, selected_documents=None, n_results=10, *, case_id=None):
                rows = [row for element_id, row in rows_by_element.items() if element_id in query]
                return {
                    "ids": [[row[0] for row in rows]],
                    "documents": [[row[1] for row in rows]],
                    "metadatas": [[{**row[2], "case_id": case_id} for row in rows]],
                    "distances": [[0.1 for _ in rows]],
                }

        selection = DeterministicIssueSelector().select(question, case_id=case_id)
        return ElementEvidenceMapper(retrieval_callable=Retriever()).map_primary_issue(
            case_id=case_id,
            user_question=question,
            selection=selection,
        )

    @staticmethod
    def _employer(file_name: str) -> dict:
        return {
            "file": file_name,
            "page": 1,
            "evidence_source_type": "employer_record",
            "evidence_source_label": "Employer evidence",
            "evidence_classification_method": "explicit",
            "chunk_source_type": "employer_record",
            "chunk_source_label": "Employer evidence",
            "chunk_provenance_method": "chunk-leading-sender",
        }

    def test_frozen_query_ek_maps_direct_knowledge_without_merits_decision(self) -> None:
        result = self._map_with_element_rows(
            "What evidence shows CACI knew about my disability?",
            {
                "EK-DIRECT-KNOWLEDGE": (
                    "ek-direct",
                    "From: CACI HR\nWe received and discussed the claimant's medical information.",
                    self._employer("CACI HR knowledge email.pdf"),
                )
            },
        )
        direct = next(e for e in result.analysis.elements if e.element_id == "EK-DIRECT-KNOWLEDGE")
        self.assertEqual([item.chunk_id for item in direct.neutral_evidence], ["ek-direct"])
        self.assertIsNone(direct.legal_analysis)
        self.assertIsNone(direct.assessment)

    def test_frozen_query_ra_maps_adjustment_to_adjustment_element(self) -> None:
        result = self._map_with_element_rows(
            "Should CACI have allowed me to work from home because of my disability?",
            {
                "RA-ADJUSTMENT": (
                    "ra-adjustment",
                    "The claimant requested home working and a phased return with reduced hours.",
                    self._employer("CACI RTW correspondence.pdf"),
                )
            },
        )
        adjustment = next(e for e in result.analysis.elements if e.element_id == "RA-ADJUSTMENT")
        self.assertEqual([item.chunk_id for item in adjustment.neutral_evidence], ["ra-adjustment"])
        self.assertIsNone(adjustment.legal_analysis)

    def test_frozen_query_lim_maps_continuing_material_without_deciding_limitation(self) -> None:
        result = self._map_with_element_rows(
            "Is my claim out of time if the failures continued?",
            {
                "LIM-CONTINUING-CONDUCT": (
                    "lim-continuing",
                    "The claimant alleges a continuing omission and no contact since 2005.",
                    {
                        "file": "Claimant chronology.pdf",
                        "page": 2,
                        "evidence_source_type": "claimant_submission",
                        "chunk_source_type": "claimant_submission",
                        "chunk_provenance_method": "document-authorship-inherited",
                    },
                )
            },
        )
        element = next(e for e in result.analysis.elements if e.element_id == "LIM-CONTINUING-CONDUCT")
        self.assertEqual([item.chunk_id for item in element.neutral_evidence], ["lim-continuing"])
        self.assertIsNone(element.legal_analysis)
        self.assertIsNone(element.assessment)

    def test_frozen_query_da_maps_unfavourable_treatment_without_merits_decision(self) -> None:
        result = self._map_with_element_rows(
            "Was I treated unfavourably because of something arising from my disability?",
            {
                "DA-UNFAVOURABLE-TREATMENT": (
                    "da-treatment",
                    "CACI commenced a capability review concerning long-term sickness absence.",
                    self._employer("CACI capability review.pdf"),
                )
            },
        )
        treatment = next(e for e in result.analysis.elements if e.element_id == "DA-UNFAVOURABLE-TREATMENT")
        self.assertEqual([item.chunk_id for item in treatment.neutral_evidence], ["da-treatment"])
        self.assertIsNone(treatment.legal_analysis)
        self.assertIsNone(treatment.assessment)
