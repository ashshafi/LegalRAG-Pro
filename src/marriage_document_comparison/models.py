from __future__ import annotations

from dataclasses import dataclass

from marriage_document_intelligence import (
    MarriageComparisonStatus,
    MarriageFact,
    MarriageFactField,
)


@dataclass(frozen=True)
class MarriageSourceValue:
    source_blob_sha256: str
    original_filenames: tuple[str, ...]
    values: tuple[str, ...]
    candidate_record_ids: tuple[str, ...]


@dataclass(frozen=True)
class MarriageSourceProfile:
    source_blob_sha256: str
    original_filenames: tuple[str, ...]
    source_document_instance_ids: tuple[str, ...]
    candidate_record_ids: tuple[str, ...]
    page_numbers: tuple[int, ...]
    crop_names: tuple[str, ...]
    facts: tuple[MarriageFact, ...]


@dataclass(frozen=True)
class MarriageFieldComparison:
    field: MarriageFactField
    status: MarriageComparisonStatus
    source_values: tuple[MarriageSourceValue, ...]
    summary: str


@dataclass(frozen=True)
class MarriageDocumentComparisonResult:
    source_profiles: tuple[MarriageSourceProfile, ...]
    field_comparisons: tuple[MarriageFieldComparison, ...]
    potential_issues: tuple[str, ...]
    next_professional_actions: tuple[str, ...]
