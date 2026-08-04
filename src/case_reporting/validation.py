"""Fail-closed validation for M5.1 deterministic report projections."""

from __future__ import annotations

from hashlib import sha256

from .identity import (
    canonical_json_bytes,
    derive_manifest_id,
    derive_report_projection_id,
)
from .models import CaseReportProjection, SECTION_KEYS
from .serialization import (
    projection_semantic_payload_to_dict,
    report_manifest_semantic_payload_to_dict,
)


def _unique(values, *, field_name: str) -> None:
    values = tuple(values)
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must contain unique values.")


def _citation_ids_from_projection(value: CaseReportProjection) -> set[str]:
    return {item.citation_id for item in value.citations}


def _assert_known_citations(value: CaseReportProjection) -> None:
    known = _citation_ids_from_projection(value)
    linked: set[str] = set()
    for issue in value.issues:
        for element in issue.elements:
            for statement in (
                *element.established_matters,
                *element.supported_matters,
                *element.not_supported_matters,
                *element.source_assertions,
            ):
                linked.update(statement.citation_ids)
        for finding in (*issue.direct_findings, *issue.higher_order_findings):
            linked.update(finding.citation_ids)
            for ref in finding.provenance:
                linked.update(ref.citation_ids)
    for event in value.chronology:
        linked.update(event.citation_ids)
        linked.update(item.citation_id for item in event.assertions)
    for conflict in value.conflicts:
        linked.update(conflict.citation_ids)
    for gap in value.gaps:
        linked.update(gap.citation_ids)
    for risk in value.risks:
        linked.update(risk.citation_ids)
    for question in value.priority_questions:
        linked.update(question.citation_ids)
    unknown = sorted(linked - known)
    if unknown:
        raise ValueError(f"Projection contains unknown citation IDs: {unknown}.")


def _assert_projection_links(value: CaseReportProjection) -> None:
    issue_ids = tuple(item.issue_analysis_id for item in value.issues)
    _unique(issue_ids, field_name="issues")
    finding_by_id = {}
    element_coords: set[tuple[str, str]] = set()
    for issue in value.issues:
        if issue.issue_analysis_id not in value.lineage.source_analysis_ids:
            raise ValueError("IssueReport lies outside the frozen source-analysis set.")
        for element in issue.elements:
            coord = (issue.issue_analysis_id, element.element_id)
            if coord in element_coords:
                raise ValueError(f"Duplicate projected element coordinate {coord!r}.")
            element_coords.add(coord)
        for finding in (*issue.direct_findings, *issue.higher_order_findings):
            existing = finding_by_id.get(finding.finding_id)
            if existing is not None and existing != finding:
                raise ValueError("One finding ID resolves to incompatible report state.")
            finding_by_id[finding.finding_id] = finding
        if tuple(item.finding_id for item in issue.direct_findings) != issue.material_finding_ids:
            raise ValueError("IssueReport direct findings do not preserve material_finding_ids order.")
        if set(issue.material_finding_ids) & {item.finding_id for item in issue.higher_order_findings}:
            raise ValueError("Higher-order findings must not be appended to material_finding_ids.")
    for item in value.cross_issue_findings:
        if item.finding_id not in finding_by_id:
            raise ValueError("Cross-issue finding is absent from issue reporting state.")
    conflict_ids = {item.conflict_id for item in value.conflicts}
    gap_ids = {item.gap_id for item in value.gaps}
    risk_ids = {item.risk_id for item in value.risks}
    finding_ids = set(finding_by_id)
    for issue in value.issues:
        if not set(issue.conflict_ids) <= conflict_ids:
            raise ValueError("IssueReport references an unknown conflict.")
        if not set(issue.gap_ids) <= gap_ids:
            raise ValueError("IssueReport references an unknown gap.")
        if not set(issue.risk_ids) <= risk_ids:
            raise ValueError("IssueReport references an unknown risk.")
    for gap in value.gaps:
        if not set(gap.related_finding_ids) <= finding_ids:
            raise ValueError("GapReport references an unknown finding.")
    for risk in value.risks:
        if not set(risk.basis_finding_ids) <= finding_ids:
            raise ValueError("RiskReport references an unknown finding.")
        if not set(risk.conflict_ids) <= conflict_ids:
            raise ValueError("RiskReport references an unknown conflict.")
        if not set(risk.gap_ids) <= gap_ids:
            raise ValueError("RiskReport references an unknown gap.")
    for question in value.priority_questions:
        if not set(question.finding_ids) <= finding_ids:
            raise ValueError("PriorityQuestionReport references an unknown finding.")
        if not set(question.conflict_ids) <= conflict_ids:
            raise ValueError("PriorityQuestionReport references an unknown conflict.")
        if not set(question.gap_ids) <= gap_ids:
            raise ValueError("PriorityQuestionReport references an unknown gap.")


def validate_case_report_projection(value: CaseReportProjection) -> None:
    """Validate internal identity, payload, manifest and cross-reference integrity."""

    if not isinstance(value, CaseReportProjection):
        raise ValueError("value must be a CaseReportProjection instance.")
    expected_projection_id = derive_report_projection_id(
        case_id=value.case_header.case_id,
        source_synthesis_id=value.source_synthesis_id,
        source_foundation_sha256=value.source_foundation_sha256,
        source_matrices_sha256=value.source_matrices_sha256,
        source_chronology_sha256=value.source_chronology_sha256,
        source_synthesis_sha256=value.source_synthesis_sha256,
        source_metadata_sha256=value.source_metadata_sha256,
        schema_version=value.schema_version,
        projector_version=value.projector_version,
    )
    if value.report_projection_id != expected_projection_id:
        raise ValueError("report_projection_id does not match the frozen reporting source set.")

    payload = projection_semantic_payload_to_dict(value)
    expected_payload_sha = sha256(canonical_json_bytes(payload)).hexdigest()
    if value.projection_payload_sha256 != expected_payload_sha:
        raise ValueError("projection_payload_sha256 does not match the semantic payload.")

    from .projection import _build_manifest

    expected_manifest = _build_manifest(
        report_projection_id=value.report_projection_id,
        projection_payload_sha256=value.projection_payload_sha256,
        case_header=value.case_header,
        lineage=value.lineage,
        overall_state=value.overall_state,
        issues=value.issues,
        chronology=value.chronology,
        cross_issue_findings=value.cross_issue_findings,
        conflicts=value.conflicts,
        gaps=value.gaps,
        risks=value.risks,
        questions=value.priority_questions,
        citations=value.citations,
        glossary=value.glossary,
    )
    if value.manifest != expected_manifest:
        raise ValueError("Embedded ReportManifest is not the exact canonical projection manifest.")
    manifest_payload_sha = sha256(
        canonical_json_bytes(report_manifest_semantic_payload_to_dict(value.manifest))
    ).hexdigest()
    expected_manifest_id = derive_manifest_id(
        report_projection_id=value.report_projection_id,
        projection_payload_sha256=value.projection_payload_sha256,
        manifest_payload_sha256=manifest_payload_sha,
        schema_version=value.manifest.schema_version,
        builder_version=value.manifest.builder_version,
    )
    if value.manifest.manifest_id != expected_manifest_id:
        raise ValueError("manifest_id does not match the canonical manifest semantic payload.")
    if value.manifest.ordered_section_ids != SECTION_KEYS:
        raise ValueError("ReportManifest section order is not the frozen M5.1 order.")
    if tuple(item.section_key for item in value.manifest.sections) != SECTION_KEYS:
        raise ValueError("ReportManifest section records do not match controlled section order.")

    _unique((item.citation_id for item in value.citations), field_name="citations")
    if tuple(item.citation_id for item in value.citations) != tuple(sorted(item.citation_id for item in value.citations)):
        raise ValueError("Citation catalogue must use canonical evidence-key order.")
    _assert_known_citations(value)
    _assert_projection_links(value)


__all__ = ["validate_case_report_projection"]
