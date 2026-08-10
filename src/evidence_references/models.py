"""Deterministic models for governed evidence-reference reconciliation.

U8F-C1 is additive and consumes the already-complete U8D search surface.  It
records explicit references found in governed evidence text and reconciles
those references against the completely inspected evidence corpus without
redefining source-evidence identities or legal-analysis semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from evidence_search import EvidenceSearchMode


class EvidenceReferenceKind(StrEnum):
    """Deterministic reference kinds recognised by U8F-C1."""

    APPENDIX = "appendix"
    COMMUNICATION = "communication"


class EvidenceReferenceResolutionStatus(StrEnum):
    """Fail-closed reconciliation status for one explicit reference."""

    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    POSSIBLE_REFERENCED_BUT_NOT_LOCATED = "possible_referenced_but_not_located"
    UNRESOLVED_REFERENCE = "unresolved_reference"


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """One explicit deterministic reference extracted from governed text."""

    reference_id: str
    source_document_instance_id: str
    source_filename: str
    source_evidence_key: str
    source_page_number: int
    source_chunk_ordinal: int
    source_reference_ordinal: int
    kind: EvidenceReferenceKind
    raw_reference_text: str
    normalized_target: str
    appendix_label: str | None = None
    communication_type: str | None = None
    person_text: str | None = None
    date_text: str | None = None
    canonical_date: str | None = None

    def __post_init__(self) -> None:
        if not self.reference_id.startswith("sha256:"):
            raise ValueError("Evidence-reference identity must be a sha256-prefixed digest.")
        if self.source_page_number < 1:
            raise ValueError("Evidence-reference page number must be positive.")
        if self.source_chunk_ordinal < 0:
            raise ValueError("Evidence-reference chunk ordinal must be non-negative.")
        if self.source_reference_ordinal < 0:
            raise ValueError("Evidence-reference ordinal must be non-negative.")
        if not self.raw_reference_text.strip():
            raise ValueError("Evidence-reference text must not be empty.")
        if not self.normalized_target.strip():
            raise ValueError("Evidence-reference normalized target must not be empty.")
        if self.kind is EvidenceReferenceKind.APPENDIX:
            if not self.appendix_label:
                raise ValueError("Appendix references require appendix_label.")
            if any(
                value is not None
                for value in (
                    self.communication_type,
                    self.person_text,
                    self.date_text,
                    self.canonical_date,
                )
            ):
                raise ValueError("Appendix references cannot carry communication fields.")
        elif self.kind is EvidenceReferenceKind.COMMUNICATION:
            if not self.communication_type:
                raise ValueError("Communication references require communication_type.")
            if self.appendix_label is not None:
                raise ValueError("Communication references cannot carry appendix_label.")
            if self.canonical_date is not None and self.date_text is None:
                raise ValueError("Canonical communication dates require date_text.")


@dataclass(frozen=True, slots=True)
class EvidenceReferenceResolution:
    """One reference plus deterministic target reconciliation result."""

    reference: EvidenceReference
    status: EvidenceReferenceResolutionStatus
    matched_document_ids: tuple[str, ...]
    matched_evidence_keys: tuple[str, ...]
    basis: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "matched_document_ids", tuple(self.matched_document_ids))
        object.__setattr__(self, "matched_evidence_keys", tuple(self.matched_evidence_keys))
        if not self.basis.strip():
            raise ValueError("Reference-resolution basis must not be empty.")
        if self.status is EvidenceReferenceResolutionStatus.RESOLVED:
            if len(self.matched_evidence_keys) != 1:
                raise ValueError("RESOLVED references require exactly one matched evidence key.")
            if len(self.matched_document_ids) != 1:
                raise ValueError("RESOLVED references require exactly one matched document.")
        elif self.status is EvidenceReferenceResolutionStatus.AMBIGUOUS:
            if len(self.matched_evidence_keys) < 2:
                raise ValueError("AMBIGUOUS references require at least two matched evidence keys.")
            if not self.matched_document_ids:
                raise ValueError("AMBIGUOUS references require matched documents.")
        else:
            if self.matched_document_ids or self.matched_evidence_keys:
                raise ValueError("Unlocated/unresolved references cannot carry matched targets.")


@dataclass(frozen=True, slots=True)
class EvidenceReferenceResolutionReceipt:
    """Coverage receipt proving the basis for reference-resolution findings."""

    schema_version: str
    case_id: str
    search_mode: EvidenceSearchMode
    searched_document_ids: tuple[str, ...]
    documents_completely_expanded: int
    pages_inspected: int
    chunks_inspected: int
    case_corpus_complete: bool
    possible_not_located_permitted: bool
    reference_count: int
    resolved_count: int
    ambiguous_count: int
    possible_not_located_count: int
    unresolved_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "searched_document_ids", tuple(self.searched_document_ids))
        self._validate()

    def _validate(self) -> None:
        counts = (
            self.documents_completely_expanded,
            self.pages_inspected,
            self.chunks_inspected,
            self.reference_count,
            self.resolved_count,
            self.ambiguous_count,
            self.possible_not_located_count,
            self.unresolved_count,
        )
        if any(value < 0 for value in counts):
            raise ValueError("Reference-resolution receipt counts must be non-negative.")
        if self.documents_completely_expanded != len(self.searched_document_ids):
            raise ValueError("Reference receipt document count must match searched_document_ids.")
        if (
            self.resolved_count
            + self.ambiguous_count
            + self.possible_not_located_count
            + self.unresolved_count
            != self.reference_count
        ):
            raise ValueError("Reference-resolution status counts must sum to reference_count.")
        if self.possible_not_located_count and not self.possible_not_located_permitted:
            raise ValueError(
                "POSSIBLE_REFERENCED_BUT_NOT_LOCATED requires complete case-corpus authority."
            )
        if self.possible_not_located_permitted is not self.case_corpus_complete:
            raise ValueError(
                "possible_not_located_permitted must exactly reflect case-corpus completeness."
            )


@dataclass(frozen=True, slots=True)
class CaseEvidenceReferenceResolution:
    """Deterministic reference resolutions derived from one complete U8D result."""

    case_id: str
    resolutions: tuple[EvidenceReferenceResolution, ...]
    receipt: EvidenceReferenceResolutionReceipt

    def __post_init__(self) -> None:
        object.__setattr__(self, "resolutions", tuple(self.resolutions))
        if self.receipt.case_id != self.case_id:
            raise ValueError("Reference-resolution receipt case_id mismatch.")
        if len(self.resolutions) != self.receipt.reference_count:
            raise ValueError("Reference-resolution count does not match its receipt.")


__all__ = [
    "CaseEvidenceReferenceResolution",
    "EvidenceReference",
    "EvidenceReferenceKind",
    "EvidenceReferenceResolution",
    "EvidenceReferenceResolutionReceipt",
    "EvidenceReferenceResolutionStatus",
]
