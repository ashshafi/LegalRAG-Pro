"""Deterministic serialization for Sprint 2.4 Milestone 1 foundation records."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .models import CaseAnalysisFoundation, SourceAnalysisReference


def source_analysis_reference_to_dict(value: SourceAnalysisReference) -> dict[str, Any]:
    """Return a JSON-compatible source-analysis reference."""

    return {
        "case_id": value.case_id,
        "issue_analysis_id": value.issue_analysis_id,
        "issue_definition_id": value.issue_definition_id,
        "issue_definition_version": value.issue_definition_version,
        "issue_name": value.issue_name,
        "issue_analysis_schema_version": value.issue_analysis_schema_version,
        "issue_created_at": value.issue_created_at.isoformat(),
        "element_ids": list(value.element_ids),
        "mapper_version": value.mapper_version,
        "assessor_version": value.assessor_version,
        "analyser_version": value.analyser_version,
    }


def source_analysis_reference_from_dict(data: dict[str, Any]) -> SourceAnalysisReference:
    """Restore a source-analysis reference from JSON-compatible data."""

    return SourceAnalysisReference(
        case_id=str(data["case_id"]),
        issue_analysis_id=str(data["issue_analysis_id"]),
        issue_definition_id=str(data["issue_definition_id"]),
        issue_definition_version=str(data["issue_definition_version"]),
        issue_name=str(data["issue_name"]),
        issue_analysis_schema_version=str(data["issue_analysis_schema_version"]),
        issue_created_at=datetime.fromisoformat(str(data["issue_created_at"])),
        element_ids=tuple(str(item) for item in data.get("element_ids", [])),
        mapper_version=str(data["mapper_version"]),
        assessor_version=str(data["assessor_version"]),
        analyser_version=str(data["analyser_version"]),
    )


def case_analysis_foundation_to_dict(value: CaseAnalysisFoundation) -> dict[str, Any]:
    """Return deterministic JSON-compatible foundation data."""

    return {
        "schema_version": value.schema_version,
        "synthesis_id": value.synthesis_id,
        "case_id": value.case_id,
        "source_analyses": [
            source_analysis_reference_to_dict(item) for item in value.source_analyses
        ],
        "created_at": value.created_at.isoformat(),
        "synthesiser_version": value.synthesiser_version,
    }


def case_analysis_foundation_from_dict(data: dict[str, Any]) -> CaseAnalysisFoundation:
    """Restore and validate a foundation from JSON-compatible data."""

    return CaseAnalysisFoundation(
        schema_version=str(data["schema_version"]),
        synthesis_id=str(data["synthesis_id"]),
        case_id=str(data["case_id"]),
        source_analyses=tuple(
            source_analysis_reference_from_dict(item)
            for item in data.get("source_analyses", [])
        ),
        created_at=datetime.fromisoformat(str(data["created_at"])),
        synthesiser_version=str(data["synthesiser_version"]),
    )


def dumps_case_analysis_foundation(value: CaseAnalysisFoundation) -> str:
    """Return byte-stable JSON for an equivalent M1 foundation."""

    return json.dumps(
        case_analysis_foundation_to_dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def loads_case_analysis_foundation(payload: str) -> CaseAnalysisFoundation:
    """Load a foundation from deterministic JSON and fail closed on invalid data."""

    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("CaseAnalysisFoundation JSON payload must contain an object.")
    return case_analysis_foundation_from_dict(data)


__all__ = [
    "case_analysis_foundation_from_dict",
    "case_analysis_foundation_to_dict",
    "dumps_case_analysis_foundation",
    "loads_case_analysis_foundation",
    "source_analysis_reference_from_dict",
    "source_analysis_reference_to_dict",
]
