from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from legal_analysis.definitions import INITIAL_ISSUE_DEFINITIONS
from legal_analysis.element_assessor import ElementEvidenceAssessor
from legal_analysis.evidence_mapping import ElementMappingResult, MappedIssueAnalysis
from legal_analysis.legal_analysis import StructuredLegalAnalysisResult
from legal_analysis.legal_analysis_renderer import StructuredLegalAnalysisRenderer
from legal_analysis.models import ElementAnalysis, IssueAnalysis

DEFAULT_CASE_ID = "11111111-1111-4111-8111-111111111111"
DEFAULT_CREATED_AT = datetime(2026, 8, 3, 9, 30, tzinfo=timezone.utc)


def definition(issue_id: str):
    return next(item for item in INITIAL_ISSUE_DEFINITIONS if item.definition_id == issue_id)


def make_m5_result(
    issue_id: str,
    *,
    case_id: str = DEFAULT_CASE_ID,
    issue_analysis_id: str | None = None,
    created_at: datetime = DEFAULT_CREATED_AT,
) -> StructuredLegalAnalysisResult:
    controlled = definition(issue_id)
    elements = tuple(
        ElementAnalysis(
            element.element_id,
            element.name,
            element.question_to_determine,
        )
        for element in controlled.elements
    )
    mapped = MappedIssueAnalysis(
        analysis=IssueAnalysis(
            case_id=case_id,
            issue_definition_id=controlled.definition_id,
            issue_definition_version=controlled.version,
            issue_name=controlled.name,
            user_question=f"Synthetic M1 foundation input for {issue_id}",
            legal_framework=controlled.legal_framework,
            elements=elements,
            issue_analysis_id=issue_analysis_id or str(uuid4()),
            created_at=created_at,
        ),
        element_results=tuple(
            ElementMappingResult(
                element_id=element.element_id,
                search_query="Synthetic no-retrieval mapping",
                mappings=(),
            )
            for element in controlled.elements
        ),
    )
    assessed = ElementEvidenceAssessor().assess(mapped)
    return StructuredLegalAnalysisRenderer().render(assessed)
