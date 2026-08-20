"""Canonical serialization for Finance F7A report projections."""
from __future__ import annotations

import json
import types
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, get_args, get_origin, get_type_hints

from finance_calculations import AnalyticalStatus, CalculationClassification
from finance_comps import CellValueClassification, ComparableRole, PeerInclusionState, TargetPeerRelationship
from finance_domain.identity import canonical_decimal_text, canonical_json_bytes
from finance_evidence import FinanceDocumentEvidenceCoverage, ObservationDocumentBindingClass, ObservationSourceChannel

from .models import *

_ALLOWED_DATACLASSES = frozenset({
    FinanceReportHeader, FinanceReportMember, FinanceReportMetricCell, FinanceReportPeerSummary,
    FinanceReportTargetPosition, FinanceReportCalculation, FinanceReportEvidenceRecord,
    FinanceReportLimitation, FinanceReportManifestSection, FinanceReportManifest, FinanceReportProjection,
})
_ALLOWED_ENUMS = frozenset({
    AnalyticalStatus, CalculationClassification, CellValueClassification, ComparableRole,
    PeerInclusionState, TargetPeerRelationship, FinanceDocumentEvidenceCoverage,
    ObservationDocumentBindingClass, ObservationSourceChannel, FinanceReportLimitationType,
})

def _dt(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
        raise ValueError("F7A datetime must be UTC-aware.")
    text = value.astimezone(timezone.utc).isoformat(timespec="microseconds")
    return text[:-6] + "Z" if text.endswith("+00:00") else text

def _encode(value: Any) -> Any:
    if value is None or type(value) in (str, int, bool):
        return value
    if isinstance(value, Decimal):
        return canonical_decimal_text(value)
    if isinstance(value, datetime):
        return _dt(value)
    if isinstance(value, Enum) and type(value) in _ALLOWED_ENUMS:
        return value.value
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    if is_dataclass(value) and type(value) in _ALLOWED_DATACLASSES:
        return {f.name: _encode(getattr(value, f.name)) for f in fields(value)}
    raise TypeError(f"Unsupported F7A serialization value {type(value)!r}.")

def _decode(annotation: Any, value: Any) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (types.UnionType, getattr(__import__("typing"), "Union")):
        if value is None and type(None) in args:
            return None
        non_none = tuple(item for item in args if item is not type(None))
        if len(non_none) != 1:
            raise ValueError("Unsupported F7A union annotation.")
        return _decode(non_none[0], value)
    if origin is tuple:
        if not isinstance(value, list):
            raise ValueError("F7A tuple field must be a JSON array.")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode(args[0], item) for item in value)
        if len(args) != len(value):
            raise ValueError("F7A fixed tuple length mismatch.")
        return tuple(_decode(t, item) for t, item in zip(args, value))
    if isinstance(annotation, type) and annotation in _ALLOWED_ENUMS:
        if not isinstance(value, str):
            raise ValueError(f"{annotation.__name__} must be JSON text.")
        try:
            return annotation(value)
        except ValueError as exc:
            raise ValueError(f"Unknown {annotation.__name__} value.") from exc
    if isinstance(annotation, type) and annotation in _ALLOWED_DATACLASSES:
        if not isinstance(value, dict):
            raise ValueError(f"{annotation.__name__} must be an object.")
        expected = {f.name for f in fields(annotation)}
        if set(value) != expected:
            raise ValueError(f"{annotation.__name__} fields are not exact.")
        hints = get_type_hints(annotation)
        return annotation(**{f.name: _decode(hints[f.name], value[f.name]) for f in fields(annotation)})
    if annotation is Decimal:
        if not isinstance(value, str):
            raise ValueError("F7A Decimal must be JSON text.")
        try:
            result = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("Invalid F7A Decimal.") from exc
        if canonical_decimal_text(result) != value:
            raise ValueError("F7A Decimal is not canonical.")
        return result
    if annotation is datetime:
        if not isinstance(value, str) or not value.endswith("Z"):
            raise ValueError("F7A datetime must use canonical UTC Z form.")
        try:
            result = datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as exc:
            raise ValueError("Invalid F7A datetime.") from exc
        if _dt(result) != value:
            raise ValueError("F7A datetime is not canonical.")
        return result
    if annotation in (str, int, bool):
        if type(value) is not annotation:
            raise ValueError(f"Expected {annotation.__name__} F7A value.")
        return value
    raise ValueError(f"Unsupported F7A field annotation {annotation!r}.")

def finance_report_projection_to_dict(value: FinanceReportProjection) -> dict[str, Any]:
    encoded = _encode(value)
    if not isinstance(encoded, dict):
        raise AssertionError("F7A projection must encode to object.")
    return encoded

def projection_semantic_payload_to_dict(value: FinanceReportProjection) -> dict[str, Any]:
    data = finance_report_projection_to_dict(value)
    data.pop("report_projection_id")
    data.pop("projection_payload_sha256")
    data.pop("manifest")
    return data

def finance_report_manifest_identity_payload_to_dict(value: FinanceReportManifest) -> dict[str, Any]:
    encoded = _encode(value)
    encoded.pop("manifest_id")
    return encoded

def dumps_finance_report_projection(value: FinanceReportProjection) -> str:
    from .validation import validate_finance_report_projection
    validate_finance_report_projection(value)
    return canonical_json_bytes(finance_report_projection_to_dict(value)).decode("utf-8")

def _loads_obj(payload: str) -> dict[str, Any]:
    if not isinstance(payload, str):
        raise ValueError("F7A payload must be text.")
    def reject_duplicates(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError(f"Duplicate JSON object key {key!r} is not allowed.")
            out[key] = value
        return out
    try:
        value = json.loads(payload, object_pairs_hook=reject_duplicates)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid F7A JSON.") from exc
    if not isinstance(value, dict):
        raise ValueError("F7A JSON root must be an object.")
    return value

def loads_finance_report_projection(payload: str) -> FinanceReportProjection:
    data = _loads_obj(payload)
    try:
        value = _decode(FinanceReportProjection, data)
    except (TypeError, ValueError, KeyError) as exc:
        raise ValueError("Invalid FinanceReportProjection payload.") from exc
    from .validation import validate_finance_report_projection
    validate_finance_report_projection(value)
    if dumps_finance_report_projection(value) != payload:
        raise ValueError("F7A payload is not canonical JSON.")
    return value

__all__ = [
    "dumps_finance_report_projection", "finance_report_manifest_identity_payload_to_dict",
    "finance_report_projection_to_dict", "loads_finance_report_projection",
    "projection_semantic_payload_to_dict",
]
