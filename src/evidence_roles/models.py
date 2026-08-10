"""Deterministic evidence-role models for document-complete inspection.

Evidence roles are an additive U8 concept.  They describe how one immutable
chunk functions inside a governed evidence inspection; they do not replace the
existing ``EvidenceSourceType`` provenance classification and do not alter any
source-evidence identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from evidence_classification import EvidenceSourceType
from evidence_retrieval.models import (
    DocumentEvidenceChunk,
    DocumentEvidenceInspection,
    DocumentEvidencePage,
)


class EvidenceRole(StrEnum):
    """Conservative deterministic role of a governed evidence chunk."""

    PRIMARY_SOURCE = "primary_source"
    COMMENTARY = "commentary"
    CROSS_REFERENCE = "cross_reference"
    COVER_OR_INDEX = "cover_or_index"
    MIXED = "mixed"
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True, slots=True)
class EvidenceRoleClassification:
    """One role decision and the existing provenance facts supporting it."""

    role: EvidenceRole
    rule_id: str
    basis: str
    source_type: EvidenceSourceType
    source_label: str
    provenance_method: str
    primary_tier: int
    primary_label: str


@dataclass(frozen=True, slots=True)
class EvidenceRoleChunk:
    """One immutable U8B chunk paired with its U8C role classification."""

    chunk: DocumentEvidenceChunk
    classification: EvidenceRoleClassification


@dataclass(frozen=True, slots=True)
class EvidenceRolePage:
    """One immutable U8B page and role-classified governed chunks."""

    page: DocumentEvidencePage
    chunks: tuple[EvidenceRoleChunk, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "chunks", tuple(self.chunks))


@dataclass(frozen=True, slots=True)
class EvidenceRoleCount:
    """Deterministic count for one role in canonical enum order."""

    role: EvidenceRole
    count: int


@dataclass(frozen=True, slots=True)
class DocumentEvidenceRoleInspection:
    """Complete U8B document surface plus deterministic U8C role decisions."""

    document: DocumentEvidenceInspection
    document_source_type: EvidenceSourceType
    document_source_label: str
    document_source_method: str
    pages: tuple[EvidenceRolePage, ...]
    role_counts: tuple[EvidenceRoleCount, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "pages", tuple(self.pages))
        object.__setattr__(self, "role_counts", tuple(self.role_counts))


__all__ = [
    "DocumentEvidenceRoleInspection",
    "EvidenceRole",
    "EvidenceRoleChunk",
    "EvidenceRoleClassification",
    "EvidenceRoleCount",
    "EvidenceRolePage",
]
