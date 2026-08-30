from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


DERIVED_SEARCH_DISCOVERY_SCOPE = (
    "candidate_discovery_only"
)


class DerivedSearchRowState(StrEnum):
    MISSING = "missing"
    EXACT = "exact"
    CONFLICTING = "conflicting"


class DerivedSearchIndexAction(StrEnum):
    UNCHANGED = "unchanged"
    ADDED = "added"


@dataclass(frozen=True, slots=True)
class DerivedSearchRowInspection:
    row_id: str
    state: DerivedSearchRowState


@dataclass(frozen=True, slots=True)
class DerivedSearchIndexResult:
    row_id: str
    action: DerivedSearchIndexAction
    final_state: DerivedSearchRowState


@dataclass(frozen=True, slots=True)
class VerifiedDerivedSearchHit:
    row_id: str
    document: str
    metadata: Mapping[str, str | int]
    distance: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(
                dict(
                    self.metadata
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class DerivedSearchQueryResult:
    case_id: str
    query_sha256: str
    discovery_scope: str
    hits: tuple[VerifiedDerivedSearchHit, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "hits",
            tuple(
                self.hits
            ),
        )
