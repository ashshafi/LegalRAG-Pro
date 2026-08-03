"""Fail-closed validation for Sprint 2.4 Milestone 2 matrices."""

from __future__ import annotations

from collections.abc import Iterable

from legal_analysis.legal_analysis import StructuredLegalAnalysisResult

from ..models import CaseAnalysisFoundation
from ..validation import source_reference_from_result, validate_foundation, validate_source_analysis_results


def resolve_foundation_results(
    foundation: CaseAnalysisFoundation,
    results: Iterable[StructuredLegalAnalysisResult],
) -> tuple[StructuredLegalAnalysisResult, ...]:
    """Resolve exactly the frozen M5 analyses referenced by one M1 foundation."""

    validate_foundation(foundation)
    supplied = tuple(results)
    supplied_refs = validate_source_analysis_results(supplied)

    by_id: dict[str, StructuredLegalAnalysisResult] = {}
    for result in supplied:
        issue_id = result.issue_analysis_id
        if issue_id in by_id:
            raise ValueError(f"Duplicate source analysis {issue_id!r} supplied to M2.")
        by_id[issue_id] = result

    expected_by_id = {item.issue_analysis_id: item for item in foundation.source_analyses}
    if set(by_id) != set(expected_by_id):
        missing = sorted(set(expected_by_id) - set(by_id))
        extra = sorted(set(by_id) - set(expected_by_id))
        details: list[str] = []
        if missing:
            details.append(f"missing={missing}")
        if extra:
            details.append(f"extra={extra}")
        raise ValueError(
            "M2 source analyses must match the CaseAnalysisFoundation exactly"
            + (f" ({'; '.join(details)})" if details else "")
            + "."
        )

    supplied_ref_by_id = {item.issue_analysis_id: item for item in supplied_refs}
    for issue_id, expected in expected_by_id.items():
        actual = supplied_ref_by_id[issue_id]
        if actual != expected:
            raise ValueError(
                f"Source analysis {issue_id!r} does not match its frozen foundation lineage."
            )
        # Re-project the actual object explicitly so a future change in M1
        # validation cannot accidentally bypass exact reference equality here.
        if source_reference_from_result(by_id[issue_id]) != expected:
            raise ValueError(
                f"Source analysis {issue_id!r} failed exact frozen source-reference matching."
            )

    return tuple(
        sorted(
            by_id.values(),
            key=lambda item: (
                item.issue_definition_id,
                item.issue_definition_version,
                item.issue_analysis_id,
            ),
        )
    )


def validate_case_matrices(value, *, foundation: CaseAnalysisFoundation | None = None) -> None:
    """Validate cross-matrix M2 invariants without reopening analytical state."""

    from .matrices import CaseMatrices

    if not isinstance(value, CaseMatrices):
        raise ValueError("value must be a CaseMatrices instance.")
    if foundation is not None:
        validate_foundation(foundation)
        if value.case_id != foundation.case_id:
            raise ValueError("CaseMatrices.case_id does not match the frozen foundation.")
        if value.synthesis_id != foundation.synthesis_id:
            raise ValueError("CaseMatrices.synthesis_id does not match the frozen foundation.")
        if value.source_analysis_ids != foundation.source_issue_analysis_ids:
            raise ValueError("CaseMatrices source identities do not match the frozen foundation.")

    evidence_by_key = {item.evidence_key: item for item in value.evidence_matrix}
    if len(evidence_by_key) != len(value.evidence_matrix):
        raise ValueError("Evidence Matrix must contain one canonical record per evidence_key.")

    all_use_identities: set[tuple[str, str, str]] = set()
    for record in value.evidence_matrix:
        for use in record.uses:
            if use.identity in all_use_identities:
                raise ValueError(f"Duplicate EvidenceUse identity detected: {use.identity!r}.")
            all_use_identities.add(use.identity)
            if use.issue_analysis_id not in value.source_analysis_ids:
                raise ValueError("EvidenceUse references an analysis outside the frozen source set.")

    issue_ids = tuple(item.issue_analysis_id for item in value.issue_matrix)
    if tuple(sorted(issue_ids)) != tuple(sorted(value.source_analysis_ids)):
        raise ValueError("Issue Matrix does not cover the exact frozen source-analysis set.")

    for issue in value.issue_matrix:
        for element in issue.element_records:
            bucket_keys = (
                *element.supporting_evidence_keys,
                *element.adverse_evidence_keys,
                *element.corroborative_evidence_keys,
                *element.neutral_evidence_keys,
                *element.conflicting_evidence_keys,
            )
            for key in bucket_keys:
                if key not in evidence_by_key:
                    raise ValueError(
                        f"Issue Matrix evidence key {key!r} has no canonical Evidence Matrix record."
                    )
                identity = (issue.issue_analysis_id, element.element_id, key)
                if identity not in all_use_identities:
                    raise ValueError(
                        f"Issue Matrix evidence relationship {identity!r} has no EvidenceUse."
                    )


__all__ = ["resolve_foundation_results", "validate_case_matrices"]
