"""Strict canonical JSON serialization for U9C-B1 governed evidential analysis."""

from __future__ import annotations

from dataclasses import asdict
import json
from typing import Any

from governed_issue_evidence.models import GovernedIssueEvidenceMap

from .models import (
    GovernedEvidenceAssessment,
    GovernedEvidenceObservation,
    GovernedEvidenceObservationType,
    GovernedEvidenceUseCoordinate,
    GovernedEvidentialAnalysis,
)
from .validation import validate_governed_evidential_analysis


def dumps_governed_evidential_analysis(
    value: GovernedEvidentialAnalysis,
    source_u9b: GovernedIssueEvidenceMap,
) -> str:
    """Serialize one validated U9C analysis to canonical JSON."""

    validate_governed_evidential_analysis(value, source_u9b)
    return json.dumps(
        asdict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def loads_governed_evidential_analysis(
    payload: str,
    source_u9b: GovernedIssueEvidenceMap,
) -> GovernedEvidentialAnalysis:
    """Load strict U9C JSON and validate it against the supplied frozen U9B map."""

    data = json.loads(payload, object_pairs_hook=_reject_duplicate_object_keys)
    root = _object(data, field_name="root")
    _require_exact_keys(
        root,
        {
            "schema_version",
            "identity_version",
            "case_id",
            "source_u9b_sha256",
            "analysis_id",
            "evidence_assessments",
        },
        field_name="root",
    )

    result = GovernedEvidentialAnalysis(
        schema_version=_string(root["schema_version"], field_name="schema_version"),
        identity_version=_string(root["identity_version"], field_name="identity_version"),
        case_id=_string(root["case_id"], field_name="case_id"),
        source_u9b_sha256=_string(root["source_u9b_sha256"], field_name="source_u9b_sha256"),
        analysis_id=_string(root["analysis_id"], field_name="analysis_id"),
        evidence_assessments=tuple(
            _assessment(item)
            for item in _list(root["evidence_assessments"], field_name="evidence_assessments")
        ),
    )
    validate_governed_evidential_analysis(result, source_u9b)
    return result


def _assessment(data: Any) -> GovernedEvidenceAssessment:
    value = _object(data, field_name="evidence_assessment")
    _require_exact_keys(
        value,
        {"evidence_key", "use_coordinates", "observations"},
        field_name="evidence_assessment",
    )
    return GovernedEvidenceAssessment(
        evidence_key=_string(value["evidence_key"], field_name="evidence_key"),
        use_coordinates=tuple(
            _coordinate(item)
            for item in _list(value["use_coordinates"], field_name="use_coordinates")
        ),
        observations=tuple(
            _observation(item)
            for item in _list(value["observations"], field_name="observations")
        ),
    )


def _coordinate(data: Any) -> GovernedEvidenceUseCoordinate:
    value = _object(data, field_name="use_coordinate")
    _require_exact_keys(
        value,
        {"issue_analysis_id", "element_id", "evidence_key"},
        field_name="use_coordinate",
    )
    return GovernedEvidenceUseCoordinate(
        issue_analysis_id=_string(value["issue_analysis_id"], field_name="issue_analysis_id"),
        element_id=_string(value["element_id"], field_name="element_id"),
        evidence_key=_string(value["evidence_key"], field_name="evidence_key"),
    )


def _observation(data: Any) -> GovernedEvidenceObservation:
    value = _object(data, field_name="observation")
    _require_exact_keys(
        value,
        {"observation_type", "use_coordinate"},
        field_name="observation",
    )
    type_value = _string(value["observation_type"], field_name="observation_type")
    coordinate_value = value["use_coordinate"]
    return GovernedEvidenceObservation(
        observation_type=GovernedEvidenceObservationType(type_value),
        use_coordinate=None if coordinate_value is None else _coordinate(coordinate_value),
    )


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


def _require_exact_keys(value: dict[str, Any], expected: set[str], *, field_name: str) -> None:
    observed = set(value)
    if observed != expected:
        missing = sorted(expected - observed)
        unknown = sorted(observed - expected)
        raise ValueError(
            f"{field_name} has invalid keys; missing={missing}, unknown={unknown}."
        )


def _object(value: Any, *, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object.")
    return value


def _list(value: Any, *, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a JSON array.")
    return value


def _string(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a JSON string.")
    return value


__all__ = [
    "dumps_governed_evidential_analysis",
    "loads_governed_evidential_analysis",
]
