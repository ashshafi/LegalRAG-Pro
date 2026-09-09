from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class TargetedCandidateActivationRowState(str, Enum):
    MISSING = "missing"
    EXACT = "exact"
    CONFLICTING = "conflicting"


class TargetedCandidateActivationIndexAction(str, Enum):
    ADDED = "added"
    UNCHANGED = "unchanged"


@dataclass(frozen=True)
class TargetedCandidateActivationInspection:
    state: TargetedCandidateActivationRowState
    reason: str


@dataclass(frozen=True)
class TargetedCandidateActivationIndexResult:
    action: TargetedCandidateActivationIndexAction
    candidate_record_id: str
    state: TargetedCandidateActivationRowState


@dataclass(frozen=True)
class TargetedCandidateActivationQueryHit:
    candidate_record_id: str
    document: str
    metadata: dict[str, Any]
    distance: float | None


@dataclass(frozen=True)
class TargetedCandidateActivationQueryResult:
    hits: tuple[TargetedCandidateActivationQueryHit, ...]
