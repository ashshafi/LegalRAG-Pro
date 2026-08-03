"""Issue-centric frozen-state projection for Sprint 2.4 Milestone 2."""

from __future__ import annotations

from collections.abc import Iterable

from legal_analysis.enums import AnalyticalRole
from legal_analysis.legal_analysis import StructuredLegalAnalysisResult

from .matrices import IssueElementRecord, IssueMatrixRecord


def _keys_by_role(element_assessment, role: AnalyticalRole) -> tuple[str, ...]:
    """Return deterministic stable evidence keys for one authoritative M4 role."""

    return tuple(
        sorted(
            {
                item.mapping.evidence_key
                for item in element_assessment.evidence_assessments
                if item.analytical_role is role
            }
        )
    )


def build_issue_matrix(
    results: Iterable[StructuredLegalAnalysisResult],
) -> tuple[IssueMatrixRecord, ...]:
    """Project resolved frozen M5 analyses into deterministic issue records."""

    records: list[IssueMatrixRecord] = []
    for result in sorted(
        tuple(results),
        key=lambda item: (
            item.issue_definition_id,
            item.issue_definition_version,
            item.issue_analysis_id,
        ),
    ):
        assessment = result.assessment_result
        assessed_analysis = assessment.assessed_analysis
        m4_by_id = {item.element_id: item for item in assessment.element_assessments}
        m1_by_id = {item.element_id: item for item in assessed_analysis.elements}

        expected_ids = tuple(item.element_id for item in result.element_analyses)
        if expected_ids != tuple(item.element_id for item in assessment.element_assessments):
            raise ValueError("Issue Matrix requires exact frozen M4/M5 element order.")

        elements: list[IssueElementRecord] = []
        for m5_element in result.element_analyses:
            m4_element = m4_by_id[m5_element.element_id]
            m1_element = m1_by_id[m5_element.element_id]
            if m5_element.legal_question != m1_element.question_to_determine:
                raise ValueError("M5 legal question does not match the frozen controlled element.")
            elements.append(
                IssueElementRecord(
                    element_id=m5_element.element_id,
                    element_name=m1_element.element_name,
                    legal_question=m5_element.legal_question,
                    analysis_status=m5_element.provisional_status,
                    analysis_confidence=m5_element.analysis_confidence,
                    established_matters=m5_element.established_matters,
                    supported_matters=m5_element.supported_matters,
                    not_supported_matters=m5_element.not_supported_matters,
                    source_assertions=m5_element.source_assertions,
                    supporting_evidence_keys=_keys_by_role(m4_element, AnalyticalRole.SUPPORTING),
                    adverse_evidence_keys=_keys_by_role(m4_element, AnalyticalRole.ADVERSE),
                    corroborative_evidence_keys=_keys_by_role(m4_element, AnalyticalRole.CORROBORATIVE),
                    neutral_evidence_keys=_keys_by_role(m4_element, AnalyticalRole.NEUTRAL),
                    conflicting_evidence_keys=_keys_by_role(m4_element, AnalyticalRole.CONFLICTING),
                    disputed_matter_ids=tuple(
                        item.disputed_matter_id for item in m5_element.disputed_matters
                    ),
                    evidential_gap_ids=tuple(item.gap_id for item in m5_element.evidential_gaps),
                    unresolved_matters=m5_element.unresolved_matters,
                    legal_significance=m5_element.legal_significance,
                    provisional_analysis=m5_element.provisional_analysis,
                )
            )

        records.append(
            IssueMatrixRecord(
                issue_analysis_id=result.issue_analysis_id,
                issue_definition_id=result.issue_definition_id,
                issue_definition_version=result.issue_definition_version,
                issue_name=assessed_analysis.issue_name,
                original_user_question=assessed_analysis.user_question,
                issue_summary=result.issue_synthesis.summary,
                element_records=tuple(elements),
                analyser_version=result.analyser_version,
            )
        )
    return tuple(records)


__all__ = ["build_issue_matrix"]
