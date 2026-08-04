"""Canonical JSON serialization for M5.1 reporting artifacts."""

from __future__ import annotations

import json
import types
from dataclasses import fields, is_dataclass
from typing import Any, get_args, get_origin, get_type_hints

from .models import (
    AnalyticalLineageReport,
    CaseHeaderReport,
    CaseReportMetadata,
    CaseReportProjection,
    CitationRecord,
    ConflictReport,
    ElementReport,
    EventAssertionReport,
    EventReport,
    FindingReport,
    GapReport,
    GlossaryEntry,
    ManifestSection,
    OverallStateReport,
    PriorityQuestionReport,
    ReportManifest,
    ReportStatement,
    ResolvedProvenance,
    RiskReport,
    StatusView,
    TemporalExtentReport,
    IssueReport,
)

_ALLOWED_DATACLASSES = frozenset(
    {
        AnalyticalLineageReport,
        CaseHeaderReport,
        CaseReportMetadata,
        CaseReportProjection,
        CitationRecord,
        ConflictReport,
        ElementReport,
        EventAssertionReport,
        EventReport,
        FindingReport,
        GapReport,
        GlossaryEntry,
        IssueReport,
        ManifestSection,
        OverallStateReport,
        PriorityQuestionReport,
        ReportManifest,
        ReportStatement,
        ResolvedProvenance,
        RiskReport,
        StatusView,
        TemporalExtentReport,
    }
)


def _encode(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _encode(item) for key, item in value.items()}
    value_type = type(value)
    if is_dataclass(value) and value_type in _ALLOWED_DATACLASSES:
        return {field.name: _encode(getattr(value, field.name)) for field in fields(value)}
    raise TypeError(f"Unsupported report serialization value {value_type!r}.")


def _decode(annotation: Any, value: Any) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)

    if annotation is Any:
        return value
    if origin in (types.UnionType, getattr(__import__('typing'), 'Union')):
        if value is None and type(None) in args:
            return None
        non_none = tuple(item for item in args if item is not type(None))
        if len(non_none) != 1:
            raise ValueError(f"Unsupported report union annotation {annotation!r}.")
        return _decode(non_none[0], value)
    if origin is tuple:
        if not isinstance(value, list):
            raise ValueError("Tuple report field must be encoded as a JSON array.")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode(args[0], item) for item in value)
        if len(args) != len(value):
            raise ValueError("Fixed tuple report field has the wrong length.")
        return tuple(_decode(item_type, item) for item_type, item in zip(args, value))
    if isinstance(annotation, type) and annotation in _ALLOWED_DATACLASSES:
        if not isinstance(value, dict):
            raise ValueError(f"{annotation.__name__} must be encoded as a JSON object.")
        hints = get_type_hints(annotation)
        expected = {field.name for field in fields(annotation)}
        if set(value) != expected:
            missing = sorted(expected - set(value))
            extra = sorted(set(value) - expected)
            raise ValueError(
                f"{annotation.__name__} fields do not match schema; missing={missing}, extra={extra}."
            )
        kwargs = {
            field.name: _decode(hints[field.name], value[field.name])
            for field in fields(annotation)
        }
        return annotation(**kwargs)
    if annotation in (str, int, bool):
        if not isinstance(value, annotation):
            raise ValueError(f"Expected {annotation.__name__} report value.")
        return value
    raise ValueError(f"Unsupported report field annotation {annotation!r}.")


def case_report_projection_to_dict(value: CaseReportProjection) -> dict[str, Any]:
    encoded = _encode(value)
    if not isinstance(encoded, dict):
        raise AssertionError("CaseReportProjection must encode to an object.")
    return encoded


def case_report_projection_from_dict(data: dict[str, Any]) -> CaseReportProjection:
    value = _decode(CaseReportProjection, data)
    from .validation import validate_case_report_projection

    validate_case_report_projection(value)
    return value


def projection_semantic_payload_to_dict(value: CaseReportProjection) -> dict[str, Any]:
    """Return the semantic payload excluding IDs, payload hash and manifest."""

    return {
        "schema_version": value.schema_version,
        "projector_version": value.projector_version,
        "source_synthesis_id": value.source_synthesis_id,
        "source_foundation_sha256": value.source_foundation_sha256,
        "source_matrices_sha256": value.source_matrices_sha256,
        "source_chronology_sha256": value.source_chronology_sha256,
        "source_synthesis_sha256": value.source_synthesis_sha256,
        "source_metadata_sha256": value.source_metadata_sha256,
        "case_header": _encode(value.case_header),
        "lineage": _encode(value.lineage),
        "overall_state": _encode(value.overall_state),
        "issues": _encode(value.issues),
        "chronology": _encode(value.chronology),
        "cross_issue_findings": _encode(value.cross_issue_findings),
        "conflicts": _encode(value.conflicts),
        "gaps": _encode(value.gaps),
        "risks": _encode(value.risks),
        "priority_questions": _encode(value.priority_questions),
        "citations": _encode(value.citations),
        "glossary": _encode(value.glossary),
    }


def projection_semantic_payload_from_parts(**parts: Any) -> dict[str, Any]:
    """Encode the exact pre-identity projection payload built by the projector."""

    return {key: _encode(value) for key, value in parts.items()}


def report_manifest_to_dict(value: ReportManifest) -> dict[str, Any]:
    encoded = _encode(value)
    if not isinstance(encoded, dict):
        raise AssertionError("ReportManifest must encode to an object.")
    return encoded


def report_manifest_semantic_payload_to_dict(value: ReportManifest) -> dict[str, Any]:
    data = report_manifest_to_dict(value)
    data.pop("manifest_id")
    return data


def dumps_case_report_projection(value: CaseReportProjection) -> str:
    return json.dumps(
        case_report_projection_to_dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def loads_case_report_projection(payload: str) -> CaseReportProjection:
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("CaseReportProjection JSON root must be an object.")
    return case_report_projection_from_dict(data)


__all__ = [
    "case_report_projection_from_dict",
    "case_report_projection_to_dict",
    "dumps_case_report_projection",
    "loads_case_report_projection",
    "projection_semantic_payload_from_parts",
    "projection_semantic_payload_to_dict",
    "report_manifest_semantic_payload_to_dict",
    "report_manifest_to_dict",
]
