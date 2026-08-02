from __future__ import annotations

import unittest
from uuid import uuid4

from evidence_classification import EvidenceSourceType
from legal_analysis.enums import (
    AnalyticalRole,
    Confidence,
    EvidenceStatus,
)
from legal_analysis.evidence_mapping import (
    ElementMappingResult,
    EvidenceMapping,
    EvidenceRelevance,
    MappedIssueAnalysis,
    format_mapping_diagnostics,
)
from legal_analysis.models import ElementAnalysis, EvidenceReference, IssueAnalysis


def evidence(chunk_id: str = "chunk-1") -> EvidenceReference:
    return EvidenceReference(
        document_name="CACI email.pdf",
        summary="CACI received the return-to-work proposal.",
        source_type=EvidenceSourceType.EMPLOYER_RECORD,
        evidence_status=EvidenceStatus.EMPLOYER_EVIDENCE,
        analytical_role=AnalyticalRole.NEUTRAL,
        citation="CACI email.pdf, p.1",
        page=1,
        chunk_id=chunk_id,
    )


class EvidenceMappingTests(unittest.TestCase):
    def test_mapping_retains_traceability(self) -> None:
        mapping = EvidenceMapping(
            evidence=evidence(),
            issue_definition_id="EK-001",
            issue_definition_version="1.0",
            element_id="EK-DIRECT-KNOWLEDGE",
            relevance=EvidenceRelevance.RELEVANT,
            mapping_confidence=Confidence.HIGH,
            mapping_rationale="The employer email records receipt.",
        )
        self.assertEqual(mapping.mapper_version, "element-mapper/1.0")
        self.assertEqual(mapping.evidence_key, "chunk-1")

    def test_mapping_rejects_invalid_relevance_type(self) -> None:
        with self.assertRaises(ValueError):
            EvidenceMapping(
                evidence=evidence(),
                issue_definition_id="EK-001",
                issue_definition_version="1.0",
                element_id="EK-DIRECT-KNOWLEDGE",
                relevance="relevant",  # type: ignore[arg-type]
                mapping_confidence=Confidence.HIGH,
                mapping_rationale="Receipt is recorded.",
            )

    def test_element_result_filters_relevant_and_potential(self) -> None:
        relevant = EvidenceMapping(
            evidence=evidence("one"),
            issue_definition_id="EK-001",
            issue_definition_version="1.0",
            element_id="EK-DIRECT-KNOWLEDGE",
            relevance=EvidenceRelevance.RELEVANT,
            mapping_confidence=Confidence.HIGH,
            mapping_rationale="Direct receipt.",
        )
        potential = EvidenceMapping(
            evidence=evidence("two"),
            issue_definition_id="EK-001",
            issue_definition_version="1.0",
            element_id="EK-DIRECT-KNOWLEDGE",
            relevance=EvidenceRelevance.POTENTIALLY_RELEVANT,
            mapping_confidence=Confidence.LOW,
            mapping_rationale="Context only.",
        )
        result = ElementMappingResult(
            element_id="EK-DIRECT-KNOWLEDGE",
            search_query="query",
            mappings=(relevant, potential),
        )
        self.assertEqual(result.relevant, (relevant,))
        self.assertEqual(result.potentially_relevant, (potential,))

    def test_element_result_rejects_wrong_element_mapping(self) -> None:
        mapping = EvidenceMapping(
            evidence=evidence(),
            issue_definition_id="EK-001",
            issue_definition_version="1.0",
            element_id="EK-RECIPIENT",
            relevance=EvidenceRelevance.RELEVANT,
            mapping_confidence=Confidence.MEDIUM,
            mapping_rationale="Recipient identified.",
        )
        with self.assertRaises(ValueError):
            ElementMappingResult(
                element_id="EK-DIRECT-KNOWLEDGE",
                search_query="query",
                mappings=(mapping,),
            )

    def test_mapped_analysis_wrapper_preserves_frozen_issue_analysis(self) -> None:
        case_id = str(uuid4())
        element = ElementAnalysis(
            element_id="X",
            element_name="Example",
            question_to_determine="What happened?",
        )
        analysis = IssueAnalysis(
            case_id=case_id,
            issue_definition_id="EK-001",
            issue_definition_version="1.0",
            issue_name="Employer knowledge of disability",
            user_question="What did CACI know?",
            legal_framework=("Equality Act 2010",),
            elements=(element,),
        )
        result = MappedIssueAnalysis(
            analysis=analysis,
            element_results=(ElementMappingResult("X", "query", ()),),
        )
        self.assertIs(result.analysis, analysis)
        self.assertEqual(result.mapper_version, "element-mapper/1.0")

    def test_diagnostic_output_is_human_readable_and_non_merits(self) -> None:
        case_id = str(uuid4())
        element = ElementAnalysis(
            element_id="X",
            element_name="Example",
            question_to_determine="What happened?",
            neutral_evidence=(evidence(),),
        )
        analysis = IssueAnalysis(
            case_id=case_id,
            issue_definition_id="EK-001",
            issue_definition_version="1.0",
            issue_name="Employer knowledge of disability",
            user_question="What did CACI know?",
            legal_framework=("Equality Act 2010",),
            elements=(element,),
        )
        mapping = EvidenceMapping(
            evidence=evidence(),
            issue_definition_id="EK-001",
            issue_definition_version="1.0",
            element_id="X",
            relevance=EvidenceRelevance.RELEVANT,
            mapping_confidence=Confidence.HIGH,
            mapping_rationale="The record concerns this controlled element.",
        )
        result = MappedIssueAnalysis(
            analysis=analysis,
            element_results=(ElementMappingResult("X", "query", (mapping,)),),
        )
        text = format_mapping_diagnostics(result)
        self.assertIn("Issue: EK-001/1.0", text)
        self.assertIn("Mapper: element-mapper/1.0", text)
        self.assertIn("Element: X", text)
        self.assertIn("Mapping confidence: HIGH", text)
        self.assertNotIn("claim succeeds", text.casefold())


if __name__ == "__main__":
    unittest.main()
