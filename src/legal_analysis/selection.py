"""Durable issue-selection models for Sprint 2.3 Milestone 2.

The models in this module describe *routing only*. They deliberately do not
contain evidence, merits assessments, or legal conclusions.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Iterable

from .enums import Confidence
from .registry import IssueDefinitionRegistry

ISSUE_SELECTOR_VERSION = "issue-selector/1.0"
_SELECTOR_VERSION_RE = re.compile(r"^issue-selector/\d+\.\d+(?:\.\d+)?$")
_VERSION_RE = re.compile(r"^\d+\.\d+(?:\.\d+)?$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_required(value: str, *, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty.")
    return cleaned


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_strings(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(cleaned for value in values if (cleaned := value.strip()))


class IssueSelectionRole(StrEnum):
    """Role assigned to one registered issue during routing."""

    PRIMARY = "primary"
    RELATED = "related"
    NOT_SELECTED = "not_selected"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class SelectedIssue:
    """Reference one exact registered issue-definition version."""

    issue_definition_id: str
    issue_definition_version: str
    issue_name: str
    selection_role: IssueSelectionRole
    selection_rationale: str
    confidence: Confidence

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "issue_definition_id",
            _clean_required(
                self.issue_definition_id, field_name="issue_definition_id"
            ).upper(),
        )
        object.__setattr__(
            self,
            "issue_definition_version",
            _clean_required(
                self.issue_definition_version, field_name="issue_definition_version"
            ),
        )
        object.__setattr__(
            self,
            "issue_name",
            _clean_required(self.issue_name, field_name="issue_name"),
        )
        object.__setattr__(
            self,
            "selection_rationale",
            _clean_required(
                self.selection_rationale, field_name="selection_rationale"
            ),
        )
        if not _VERSION_RE.fullmatch(self.issue_definition_version):
            raise ValueError(
                "issue_definition_version must use numeric version form such as '1.0'."
            )
        if not isinstance(self.selection_role, IssueSelectionRole):
            raise ValueError("selection_role must be an IssueSelectionRole.")
        if not isinstance(self.confidence, Confidence):
            raise ValueError("confidence must be a Confidence.")

    @property
    def key(self) -> tuple[str, str]:
        """Return the exact controlled-definition key."""

        return self.issue_definition_id, self.issue_definition_version


@dataclass(frozen=True, slots=True)
class IssueSelectionAmbiguity:
    """Record uncertainty that prevents safe deterministic routing."""

    description: str
    candidate_issue_definition_ids: tuple[str, ...]
    reason: str
    materiality: Confidence = Confidence.MEDIUM

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "description",
            _clean_required(self.description, field_name="ambiguity description"),
        )
        object.__setattr__(
            self,
            "reason",
            _clean_required(self.reason, field_name="ambiguity reason"),
        )
        candidates = tuple(
            dict.fromkeys(item.strip().upper() for item in self.candidate_issue_definition_ids if item.strip())
        )
        if not candidates:
            raise ValueError("candidate_issue_definition_ids must not be empty.")
        object.__setattr__(self, "candidate_issue_definition_ids", candidates)
        if not isinstance(self.materiality, Confidence):
            raise ValueError("materiality must be a Confidence.")


@dataclass(frozen=True, slots=True)
class IssueSelection:
    """Structured result of routing one user question to controlled issues."""

    user_question: str
    primary_issue: SelectedIssue | None
    related_issues: tuple[SelectedIssue, ...] = ()
    not_selected_issues: tuple[SelectedIssue, ...] = ()
    ambiguities: tuple[IssueSelectionAmbiguity, ...] = ()
    selection_rationale: str = ""
    confidence: Confidence = Confidence.LOW
    selector_version: str = ISSUE_SELECTOR_VERSION
    normalized_question: str | None = None
    case_id: str | None = None
    created_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "user_question",
            _clean_required(self.user_question, field_name="user_question"),
        )
        object.__setattr__(
            self,
            "selection_rationale",
            _clean_required(
                self.selection_rationale, field_name="selection_rationale"
            ),
        )
        object.__setattr__(
            self, "normalized_question", _clean_optional(self.normalized_question)
        )
        object.__setattr__(self, "case_id", _clean_optional(self.case_id))
        object.__setattr__(self, "related_issues", tuple(self.related_issues))
        object.__setattr__(self, "not_selected_issues", tuple(self.not_selected_issues))
        object.__setattr__(self, "ambiguities", tuple(self.ambiguities))

        if not isinstance(self.confidence, Confidence):
            raise ValueError("IssueSelection.confidence must be a Confidence.")
        if not _SELECTOR_VERSION_RE.fullmatch(self.selector_version):
            raise ValueError(
                "selector_version must use form 'issue-selector/1.0'."
            )
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware.")

        if self.primary_issue is not None and self.primary_issue.selection_role is not IssueSelectionRole.PRIMARY:
            raise ValueError("primary_issue must have PRIMARY selection_role.")
        if any(item.selection_role is not IssueSelectionRole.RELATED for item in self.related_issues):
            raise ValueError("related_issues must all have RELATED selection_role.")
        if any(item.selection_role is not IssueSelectionRole.NOT_SELECTED for item in self.not_selected_issues):
            raise ValueError(
                "not_selected_issues must all have NOT_SELECTED selection_role."
            )

        keys: list[tuple[str, str]] = []
        if self.primary_issue is not None:
            keys.append(self.primary_issue.key)
        keys.extend(item.key for item in self.related_issues)
        keys.extend(item.key for item in self.not_selected_issues)
        if len(keys) != len(set(keys)):
            raise ValueError("An issue definition cannot appear in multiple selection roles.")

    def all_selected_issues(self) -> tuple[SelectedIssue, ...]:
        """Return primary and related selections in user-facing order."""

        primary = (self.primary_issue,) if self.primary_issue is not None else ()
        return primary + self.related_issues


def validate_selection_against_registry(
    selection: IssueSelection,
    registry: IssueDefinitionRegistry,
) -> None:
    """Validate all issue references and ambiguity candidates against a registry."""

    for item in (
        (() if selection.primary_issue is None else (selection.primary_issue,))
        + selection.related_issues
        + selection.not_selected_issues
    ):
        definition = registry.get_definition(
            item.issue_definition_id,
            item.issue_definition_version,
        )
        if definition.name != item.issue_name:
            raise ValueError(
                f"Selected issue name mismatch for {item.issue_definition_id}/{item.issue_definition_version}."
            )

    registered_ids = {
        definition.definition_id for definition in registry.list_definitions()
    }
    for ambiguity in selection.ambiguities:
        unknown = set(ambiguity.candidate_issue_definition_ids) - registered_ids
        if unknown:
            raise ValueError(
                "Ambiguity references unregistered issue definition(s): "
                + ", ".join(sorted(unknown))
            )


def selected_issue_to_dict(value: SelectedIssue) -> dict[str, Any]:
    return {
        "issue_definition_id": value.issue_definition_id,
        "issue_definition_version": value.issue_definition_version,
        "issue_name": value.issue_name,
        "selection_role": value.selection_role.value,
        "selection_rationale": value.selection_rationale,
        "confidence": value.confidence.value,
    }


def selected_issue_from_dict(data: dict[str, Any]) -> SelectedIssue:
    return SelectedIssue(
        issue_definition_id=str(data["issue_definition_id"]),
        issue_definition_version=str(data["issue_definition_version"]),
        issue_name=str(data["issue_name"]),
        selection_role=IssueSelectionRole(str(data["selection_role"])),
        selection_rationale=str(data["selection_rationale"]),
        confidence=Confidence(str(data["confidence"])),
    )


def ambiguity_to_dict(value: IssueSelectionAmbiguity) -> dict[str, Any]:
    return {
        "description": value.description,
        "candidate_issue_definition_ids": list(
            value.candidate_issue_definition_ids
        ),
        "reason": value.reason,
        "materiality": value.materiality.value,
    }


def ambiguity_from_dict(data: dict[str, Any]) -> IssueSelectionAmbiguity:
    return IssueSelectionAmbiguity(
        description=str(data["description"]),
        candidate_issue_definition_ids=tuple(
            str(item) for item in data.get("candidate_issue_definition_ids", [])
        ),
        reason=str(data["reason"]),
        materiality=Confidence(str(data["materiality"])),
    )


def issue_selection_to_dict(value: IssueSelection) -> dict[str, Any]:
    """Serialize an IssueSelection deterministically to JSON-compatible data."""

    return {
        "user_question": value.user_question,
        "normalized_question": value.normalized_question,
        "case_id": value.case_id,
        "primary_issue": (
            selected_issue_to_dict(value.primary_issue)
            if value.primary_issue is not None
            else None
        ),
        "related_issues": [selected_issue_to_dict(item) for item in value.related_issues],
        "not_selected_issues": [
            selected_issue_to_dict(item) for item in value.not_selected_issues
        ],
        "ambiguities": [ambiguity_to_dict(item) for item in value.ambiguities],
        "selection_rationale": value.selection_rationale,
        "confidence": value.confidence.value,
        "selector_version": value.selector_version,
        "created_at": value.created_at.isoformat(),
    }


def issue_selection_from_dict(data: dict[str, Any]) -> IssueSelection:
    """Deserialize an IssueSelection without mutating or requiring a registry."""

    primary_data = data.get("primary_issue")
    return IssueSelection(
        user_question=str(data["user_question"]),
        normalized_question=data.get("normalized_question"),
        case_id=data.get("case_id"),
        primary_issue=(
            selected_issue_from_dict(primary_data)
            if isinstance(primary_data, dict)
            else None
        ),
        related_issues=tuple(
            selected_issue_from_dict(item) for item in data.get("related_issues", [])
        ),
        not_selected_issues=tuple(
            selected_issue_from_dict(item)
            for item in data.get("not_selected_issues", [])
        ),
        ambiguities=tuple(
            ambiguity_from_dict(item) for item in data.get("ambiguities", [])
        ),
        selection_rationale=str(data["selection_rationale"]),
        confidence=Confidence(str(data["confidence"])),
        selector_version=str(data["selector_version"]),
        created_at=datetime.fromisoformat(str(data["created_at"])),
    )


def dumps_issue_selection(value: IssueSelection) -> str:
    """Return deterministic JSON for an IssueSelection."""

    return json.dumps(
        issue_selection_to_dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def loads_issue_selection(payload: str) -> IssueSelection:
    """Load an IssueSelection from deterministic JSON."""

    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("IssueSelection JSON payload must contain an object.")
    return issue_selection_from_dict(data)


__all__ = [
    "ISSUE_SELECTOR_VERSION",
    "IssueSelection",
    "IssueSelectionAmbiguity",
    "IssueSelectionRole",
    "SelectedIssue",
    "ambiguity_from_dict",
    "ambiguity_to_dict",
    "dumps_issue_selection",
    "issue_selection_from_dict",
    "issue_selection_to_dict",
    "loads_issue_selection",
    "selected_issue_from_dict",
    "selected_issue_to_dict",
    "validate_selection_against_registry",
]
