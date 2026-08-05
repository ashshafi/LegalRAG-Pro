"""Canonical fail-closed JSON serialization for immutable source evidence."""

from __future__ import annotations

import json
import types
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any, get_args, get_origin, get_type_hints

from .identity import canonical_json_bytes
from .models import (
    BindingClass,
    BoundTextRole,
    ChunkingProfile,
    EvidenceBinding,
    ExtractionMethod,
    ExtractionProfile,
    ProjectionBindingCoverage,
    ProjectionBindingEntry,
    ProjectionEvidenceBindingManifest,
    SourceBoundAnalysisReceipt,
    SourceChunkSnapshot,
    SourceDocumentManifest,
    SourcePageSnapshot,
    VerifiedEvidenceUse,
)

_ALLOWED_DATACLASSES = frozenset(
    {
        ChunkingProfile,
        EvidenceBinding,
        ExtractionProfile,
        ProjectionBindingEntry,
        ProjectionEvidenceBindingManifest,
        SourceBoundAnalysisReceipt,
        SourceChunkSnapshot,
        SourceDocumentManifest,
        SourcePageSnapshot,
        VerifiedEvidenceUse,
    }
)
_ALLOWED_ENUMS = frozenset(
    {
        BindingClass,
        BoundTextRole,
        ExtractionMethod,
        ProjectionBindingCoverage,
    }
)


def _encode(value: Any) -> Any:
    if value is None or type(value) in (str, int, bool):
        return value
    if isinstance(value, Enum) and type(value) in _ALLOWED_ENUMS:
        return value.value
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    value_type = type(value)
    if is_dataclass(value) and value_type in _ALLOWED_DATACLASSES:
        return {field.name: _encode(getattr(value, field.name)) for field in fields(value)}
    raise TypeError(f"Unsupported source-evidence serialization value {value_type!r}.")


def _decode(annotation: Any, value: Any) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (types.UnionType, getattr(__import__("typing"), "Union")):
        if value is None and type(None) in args:
            return None
        non_none = tuple(item for item in args if item is not type(None))
        if len(non_none) != 1:
            raise ValueError(f"Unsupported source-evidence union annotation {annotation!r}.")
        return _decode(non_none[0], value)
    if origin is tuple:
        if not isinstance(value, list):
            raise ValueError("Tuple source-evidence field must be encoded as a JSON array.")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode(args[0], item) for item in value)
        if len(args) != len(value):
            raise ValueError("Fixed tuple source-evidence field has the wrong length.")
        return tuple(_decode(item_type, item) for item_type, item in zip(args, value))
    if isinstance(annotation, type) and annotation in _ALLOWED_ENUMS:
        if not isinstance(value, str):
            raise ValueError(f"{annotation.__name__} must be encoded as a JSON string.")
        try:
            return annotation(value)
        except ValueError as exc:
            raise ValueError(f"Unknown {annotation.__name__} value {value!r}.") from exc
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
        if type(value) is not annotation:
            raise ValueError(f"Expected {annotation.__name__} source-evidence value.")
        return value
    raise ValueError(f"Unsupported source-evidence field annotation {annotation!r}.")


def _loads_json_object(payload: str) -> dict[str, Any]:
    if not isinstance(payload, str):
        raise ValueError("Source-evidence JSON payload must be text.")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON object key {key!r} is not allowed.")
            result[key] = value
        return result

    try:
        data = json.loads(payload, object_pairs_hook=reject_duplicates)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid source-evidence JSON.") from exc
    if not isinstance(data, dict):
        raise ValueError("Source-evidence JSON root must be an object.")
    return data


def _to_dict(value: Any) -> dict[str, Any]:
    encoded = _encode(value)
    if not isinstance(encoded, dict):
        raise AssertionError("Source-evidence record must encode to a JSON object.")
    return encoded


def _dumps(value: Any) -> str:
    return canonical_json_bytes(_to_dict(value)).decode("utf-8")


def _loads(payload: str, model_type: type[Any], validator_name: str) -> Any:
    data = _loads_json_object(payload)
    value = _decode(model_type, data)
    from . import validation as validation_module

    getattr(validation_module, validator_name)(value)
    canonical = _dumps(value)
    if payload != canonical:
        raise ValueError("Source-evidence JSON is not in the exact canonical v1 form.")
    return value


def source_document_manifest_to_dict(value: SourceDocumentManifest) -> dict[str, Any]:
    return _to_dict(value)


def source_document_manifest_identity_payload_to_dict(value: SourceDocumentManifest) -> dict[str, Any]:
    data = source_document_manifest_to_dict(value)
    data.pop("source_snapshot_id")
    return data


def dumps_source_document_manifest(value: SourceDocumentManifest) -> str:
    return _dumps(value)


def loads_source_document_manifest(payload: str) -> SourceDocumentManifest:
    return _loads(payload, SourceDocumentManifest, "validate_source_document_manifest")


def evidence_binding_to_dict(value: EvidenceBinding) -> dict[str, Any]:
    return _to_dict(value)


def evidence_binding_identity_payload_to_dict(value: EvidenceBinding) -> dict[str, Any]:
    data = evidence_binding_to_dict(value)
    data.pop("evidence_binding_id")
    return data


def dumps_evidence_binding(value: EvidenceBinding) -> str:
    return _dumps(value)


def loads_evidence_binding(payload: str) -> EvidenceBinding:
    return _loads(payload, EvidenceBinding, "validate_evidence_binding")


def source_bound_analysis_receipt_to_dict(value: SourceBoundAnalysisReceipt) -> dict[str, Any]:
    return _to_dict(value)


def source_bound_analysis_receipt_identity_payload_to_dict(
    value: SourceBoundAnalysisReceipt,
) -> dict[str, Any]:
    data = source_bound_analysis_receipt_to_dict(value)
    data.pop("source_bound_analysis_receipt_id")
    return data


def dumps_source_bound_analysis_receipt(value: SourceBoundAnalysisReceipt) -> str:
    return _dumps(value)


def loads_source_bound_analysis_receipt(payload: str) -> SourceBoundAnalysisReceipt:
    return _loads(payload, SourceBoundAnalysisReceipt, "validate_source_bound_analysis_receipt")


def projection_evidence_binding_manifest_to_dict(
    value: ProjectionEvidenceBindingManifest,
) -> dict[str, Any]:
    return _to_dict(value)


def projection_evidence_binding_manifest_identity_payload_to_dict(
    value: ProjectionEvidenceBindingManifest,
) -> dict[str, Any]:
    data = projection_evidence_binding_manifest_to_dict(value)
    data.pop("projection_evidence_binding_manifest_id")
    return data


def dumps_projection_evidence_binding_manifest(
    value: ProjectionEvidenceBindingManifest,
) -> str:
    return _dumps(value)


def loads_projection_evidence_binding_manifest(
    payload: str,
) -> ProjectionEvidenceBindingManifest:
    return _loads(
        payload,
        ProjectionEvidenceBindingManifest,
        "validate_projection_evidence_binding_manifest",
    )


__all__ = [
    "dumps_evidence_binding",
    "dumps_projection_evidence_binding_manifest",
    "dumps_source_bound_analysis_receipt",
    "dumps_source_document_manifest",
    "evidence_binding_identity_payload_to_dict",
    "evidence_binding_to_dict",
    "loads_evidence_binding",
    "loads_projection_evidence_binding_manifest",
    "loads_source_bound_analysis_receipt",
    "loads_source_document_manifest",
    "projection_evidence_binding_manifest_identity_payload_to_dict",
    "projection_evidence_binding_manifest_to_dict",
    "source_bound_analysis_receipt_identity_payload_to_dict",
    "source_bound_analysis_receipt_to_dict",
    "source_document_manifest_identity_payload_to_dict",
    "source_document_manifest_to_dict",
]
