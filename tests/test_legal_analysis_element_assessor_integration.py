from __future__ import annotations

import unittest
from uuid import uuid4

from legal_analysis.definitions import INITIAL_ISSUE_DEFINITIONS
from legal_analysis.element_assessor import ElementEvidenceAssessor
from legal_analysis.enums import AnalysisStatus
from legal_analysis.evidence_mapping import ElementMappingResult, MappedIssueAnalysis
from legal_analysis.models import ElementAnalysis, IssueAnalysis


class ElementAssessorIntegrationTests(unittest.TestCase):
    def test_all_four_controlled_definitions_can_be_assessed_without_retrieval(self):
        assessor=ElementEvidenceAssessor()
        for definition in INITIAL_ISSUE_DEFINITIONS:
            analysis=IssueAnalysis(
                case_id=str(uuid4()), issue_definition_id=definition.definition_id,
                issue_definition_version=definition.version, issue_name=definition.name,
                user_question="Synthetic acceptance question", legal_framework=definition.legal_framework,
                elements=tuple(ElementAnalysis(e.element_id,e.name,e.question_to_determine) for e in definition.elements),
            )
            mapped=MappedIssueAnalysis(
                analysis=analysis,
                element_results=tuple(ElementMappingResult(e.element_id,"query",()) for e in definition.elements),
            )
            result=assessor.assess(mapped)
            self.assertEqual(result.assessed_analysis.issue_definition_id,definition.definition_id)
            self.assertEqual(result.assessed_analysis.analysis_status,AnalysisStatus.EVIDENCE_INCOMPLETE)
            self.assertEqual(tuple(e.element_id for e in result.assessed_analysis.elements),tuple(e.element_id for e in definition.elements))

    def test_case_identity_survives_assessment(self):
        definition=INITIAL_ISSUE_DEFINITIONS[0]
        case_id=str(uuid4())
        analysis=IssueAnalysis(
            case_id=case_id, issue_definition_id=definition.definition_id, issue_definition_version=definition.version,
            issue_name=definition.name, user_question="Question", legal_framework=definition.legal_framework,
            elements=tuple(ElementAnalysis(e.element_id,e.name,e.question_to_determine) for e in definition.elements),
        )
        mapped=MappedIssueAnalysis(analysis,tuple(ElementMappingResult(e.element_id,"q",()) for e in definition.elements))
        self.assertEqual(ElementEvidenceAssessor().assess(mapped).assessed_analysis.case_id,case_id)


if __name__ == "__main__":
    unittest.main()
