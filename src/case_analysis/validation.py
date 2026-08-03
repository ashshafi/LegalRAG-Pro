"""Validation helpers for Sprint 2.4 Milestone 1 foundation inputs."""

from __future__ import annotations

from collections.abc import Iterable

from legal_analysis.legal_analysis import StructuredLegalAnalysisResult

from .models import CaseAnalysisFoundation, SourceAnalysisReference


def source_reference_from_result(result: StructuredLegalAnalysisResult) -> SourceAnalysisReference:
    """Project one frozen M5 result into a durable lineage reference.

    The projection reads identities/version lineage only.  It does not mutate or
    serialize the underlying Sprint 2.3 analytical graph.
    """

    assessment = result.assessment_result
    mapped = assessment.mapping_result
    original = mapped.analysis
    assessed = assessment.assessed_analysis

    identity_fields = (
        "issue_analysis_id",
        "case_id",
        "issue_definition_id",
        "issue_definition_version",
        "schema_version",
        "created_at",
    )
    for field_name in identity_fields:
        if getattr(original, field_name) != getattr(assessed, field_name):
            raise ValueError(f"Frozen M3/M4 identity mismatch for {field_name}.")

    m3_element_ids = tuple(item.element_id for item in original.elements)
    m4_element_ids = tuple(item.element_id for item in assessment.element_assessments)
    m5_element_ids = tuple(item.element_id for item in result.element_analyses)
    if m3_element_ids != m4_element_ids or m3_element_ids != m5_element_ids:
        raise ValueError("Frozen M3/M4/M5 element order or identity is inconsistent.")

    if result.issue_definition_id != assessed.issue_definition_id:
        raise ValueError("M5 issue-definition ID does not match the frozen analysis.")
    if result.issue_definition_version != assessed.issue_definition_version:
        raise ValueError("M5 issue-definition version does not match the frozen analysis.")

    return SourceAnalysisReference(
        case_id=result.case_id,
        issue_analysis_id=result.issue_analysis_id,
        issue_definition_id=result.issue_definition_id,
        issue_definition_version=result.issue_definition_version,
        issue_name=assessed.issue_name,
        issue_analysis_schema_version=assessed.schema_version,
        issue_created_at=assessed.created_at,
        element_ids=m5_element_ids,
        mapper_version=mapped.mapper_version,
        assessor_version=assessment.assessor_version,
        analyser_version=result.analyser_version,
    )


def validate_source_analysis_results(
    results: Iterable[StructuredLegalAnalysisResult],
) -> tuple[SourceAnalysisReference, ...]:
    """Validate and project a same-case set of frozen M5 analyses.

    Mixed cases and duplicate issue-analysis identities fail closed.  Input order
    is deliberately discarded in favour of deterministic issue-analysis order.
    """

    references = tuple(source_reference_from_result(item) for item in results)
    if not references:
        raise ValueError("At least one StructuredLegalAnalysisResult is required.")

    case_ids = {item.case_id for item in references}
    if len(case_ids) != 1:
        raise ValueError("Sprint 2.4 foundation input must contain exactly one case_id.")

    issue_ids = tuple(item.issue_analysis_id for item in references)
    if len(issue_ids) != len(set(issue_ids)):
        raise ValueError("Duplicate issue_analysis_id values are not permitted.")

    return tuple(sorted(references, key=lambda item: item.issue_analysis_id))


def validate_foundation(value: CaseAnalysisFoundation) -> None:
    """Re-check the durable M1 foundation invariants.

    ``CaseAnalysisFoundation`` validates itself on construction.  This public
    helper gives callers an explicit validation entry point without depending on
    private Sprint 2.3 validation internals.
    """

    # Accessing these properties also documents the expected durable invariants.
    if not value.source_issue_analysis_ids:
        raise ValueError("CaseAnalysisFoundation must contain source analyses.")
    if any(item.case_id != value.case_id for item in value.source_analyses):
        raise ValueError("CaseAnalysisFoundation contains a mixed-case source reference.")


__all__ = [
    "source_reference_from_result",
    "validate_foundation",
    "validate_source_analysis_results",
]
