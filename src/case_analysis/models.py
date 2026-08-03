"""Durable domain models for Sprint 2.4 Milestone 1.

Milestone 1 deliberately models only the immutable case-wide source set.  It
must not embed or reinterpret the Sprint 2.3 analytical object graph.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Iterable
from uuid import UUID, uuid5

CASE_SYNTHESIS_SCHEMA_VERSION: Final[str] = "case-synthesis-schema/1.0"
CASE_SYNTHESISER_VERSION: Final[str] = "case-synthesiser/1.0"
CASE_SYNTHESIS_NAMESPACE: Final[UUID] = UUID("53fe782f-69cb-5ac0-b7eb-33a7d924d32f")

_DEFINITION_ID_RE = re.compile(r"^[A-Z]{2,5}-\d{3}$")
_VERSION_RE = re.compile(r"^\d+\.\d+(?:\.\d+)?$")


def _clean_required(value: str, *, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty.")
    return cleaned


def _normalise_uuid(value: str, *, field_name: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"{field_name} must be a valid UUID string.") from exc


def _ensure_timezone_aware(value: datetime, *, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")


def _clean_unique_strings(values: Iterable[str], *, field_name: str) -> tuple[str, ...]:
    cleaned = tuple(item.strip() for item in values if item.strip())
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty.")
    if len(cleaned) != len(set(cleaned)):
        raise ValueError(f"{field_name} must contain unique values.")
    return cleaned


def derive_synthesis_id(
    *,
    case_id: str,
    source_issue_analysis_ids: Iterable[str],
    schema_version: str = CASE_SYNTHESIS_SCHEMA_VERSION,
    synthesiser_version: str = CASE_SYNTHESISER_VERSION,
) -> str:
    """Derive a deterministic identity for one immutable analytical source set.

    ``created_at`` is intentionally excluded.  The same case and same sorted set
    of source issue-analysis IDs therefore produce the same synthesis identity
    regardless of construction order or construction time.
    """

    normalised_case_id = _normalise_uuid(case_id, field_name="case_id")
    normalised_ids = tuple(
        sorted(
            _normalise_uuid(item, field_name="source_issue_analysis_id")
            for item in source_issue_analysis_ids
        )
    )
    if not normalised_ids:
        raise ValueError("source_issue_analysis_ids must not be empty.")
    if len(normalised_ids) != len(set(normalised_ids)):
        raise ValueError("source_issue_analysis_ids must be unique.")

    schema = _clean_required(schema_version, field_name="schema_version")
    synthesiser = _clean_required(synthesiser_version, field_name="synthesiser_version")
    name = "|".join((schema, synthesiser, normalised_case_id, *normalised_ids))
    return str(uuid5(CASE_SYNTHESIS_NAMESPACE, name))


@dataclass(frozen=True, slots=True)
class SourceAnalysisReference:
    """Durable reference to one frozen Sprint 2.3 M5 analysis.

    The record preserves analytical lineage and identity without embedding the
    complete M3/M4/M5 object graph.
    """

    case_id: str
    issue_analysis_id: str
    issue_definition_id: str
    issue_definition_version: str
    issue_name: str
    issue_analysis_schema_version: str
    issue_created_at: datetime
    element_ids: tuple[str, ...]
    mapper_version: str
    assessor_version: str
    analyser_version: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "case_id",
            _normalise_uuid(self.case_id, field_name="SourceAnalysisReference.case_id"),
        )
        object.__setattr__(
            self,
            "issue_analysis_id",
            _normalise_uuid(
                self.issue_analysis_id,
                field_name="SourceAnalysisReference.issue_analysis_id",
            ),
        )

        definition_id = _clean_required(
            self.issue_definition_id,
            field_name="SourceAnalysisReference.issue_definition_id",
        )
        if not _DEFINITION_ID_RE.fullmatch(definition_id):
            raise ValueError("issue_definition_id must use a form such as 'RA-001'.")
        object.__setattr__(self, "issue_definition_id", definition_id)

        definition_version = _clean_required(
            self.issue_definition_version,
            field_name="SourceAnalysisReference.issue_definition_version",
        )
        if not _VERSION_RE.fullmatch(definition_version):
            raise ValueError("issue_definition_version must use numeric version form such as '1.0'.")
        object.__setattr__(self, "issue_definition_version", definition_version)

        object.__setattr__(
            self,
            "issue_name",
            _clean_required(self.issue_name, field_name="SourceAnalysisReference.issue_name"),
        )

        schema = _clean_required(
            self.issue_analysis_schema_version,
            field_name="SourceAnalysisReference.issue_analysis_schema_version",
        )
        if not schema.startswith("issue-analysis-schema/"):
            raise ValueError("issue_analysis_schema_version must identify the issue-analysis schema.")
        object.__setattr__(self, "issue_analysis_schema_version", schema)

        _ensure_timezone_aware(
            self.issue_created_at,
            field_name="SourceAnalysisReference.issue_created_at",
        )

        object.__setattr__(
            self,
            "element_ids",
            _clean_unique_strings(
                self.element_ids,
                field_name="SourceAnalysisReference.element_ids",
            ),
        )

        for field_name in ("mapper_version", "assessor_version", "analyser_version"):
            object.__setattr__(
                self,
                field_name,
                _clean_required(
                    str(getattr(self, field_name)),
                    field_name=f"SourceAnalysisReference.{field_name}",
                ),
            )


@dataclass(frozen=True, slots=True)
class CaseAnalysisFoundation:
    """Deterministic case-wide identity over frozen Sprint 2.3 analyses."""

    synthesis_id: str
    case_id: str
    source_analyses: tuple[SourceAnalysisReference, ...]
    created_at: datetime
    schema_version: str = CASE_SYNTHESIS_SCHEMA_VERSION
    synthesiser_version: str = CASE_SYNTHESISER_VERSION

    def __post_init__(self) -> None:
        case_id = _normalise_uuid(self.case_id, field_name="CaseAnalysisFoundation.case_id")
        object.__setattr__(self, "case_id", case_id)
        object.__setattr__(
            self,
            "synthesis_id",
            _normalise_uuid(
                self.synthesis_id,
                field_name="CaseAnalysisFoundation.synthesis_id",
            ),
        )
        _ensure_timezone_aware(self.created_at, field_name="CaseAnalysisFoundation.created_at")

        schema = _clean_required(self.schema_version, field_name="schema_version")
        if schema != CASE_SYNTHESIS_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported case synthesis schema {schema!r}; expected {CASE_SYNTHESIS_SCHEMA_VERSION!r}."
            )
        object.__setattr__(self, "schema_version", schema)

        synthesiser = _clean_required(self.synthesiser_version, field_name="synthesiser_version")
        if synthesiser != CASE_SYNTHESISER_VERSION:
            raise ValueError(
                f"Unsupported case synthesiser {synthesiser!r}; expected {CASE_SYNTHESISER_VERSION!r}."
            )
        object.__setattr__(self, "synthesiser_version", synthesiser)

        sources = tuple(sorted(self.source_analyses, key=lambda item: item.issue_analysis_id))
        if not sources:
            raise ValueError("CaseAnalysisFoundation.source_analyses must not be empty.")
        if any(item.case_id != case_id for item in sources):
            raise ValueError("All source analyses must belong to CaseAnalysisFoundation.case_id.")

        issue_ids = tuple(item.issue_analysis_id for item in sources)
        if len(issue_ids) != len(set(issue_ids)):
            raise ValueError("Duplicate issue_analysis_id values are not permitted.")
        object.__setattr__(self, "source_analyses", sources)

        expected_id = derive_synthesis_id(
            case_id=case_id,
            source_issue_analysis_ids=issue_ids,
            schema_version=schema,
            synthesiser_version=synthesiser,
        )
        if self.synthesis_id != expected_id:
            raise ValueError("synthesis_id does not match the immutable analytical source set.")

    @property
    def source_issue_analysis_ids(self) -> tuple[str, ...]:
        """Return source issue-analysis IDs in deterministic order."""

        return tuple(item.issue_analysis_id for item in self.source_analyses)


__all__ = [
    "CASE_SYNTHESIS_NAMESPACE",
    "CASE_SYNTHESIS_SCHEMA_VERSION",
    "CASE_SYNTHESISER_VERSION",
    "CaseAnalysisFoundation",
    "SourceAnalysisReference",
    "derive_synthesis_id",
]
