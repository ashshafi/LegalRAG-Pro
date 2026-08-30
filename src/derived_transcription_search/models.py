from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


DERIVED_SEARCH_CANDIDATE_SCHEMA_VERSION = (
    "derived-transcription-search-candidate/1.0"
)

DERIVED_SEARCH_ROW_SCHEMA_VERSION = (
    "derived-transcription-search-row/1.0"
)

DERIVED_SEARCH_AUTHORITY_KIND = (
    "derived_transcription"
)

# Disposable candidate collection contract only.
# D1 does not create or open this collection.
DERIVED_SEARCH_COLLECTION_NAME = (
    "derived_transcriptions_v1"
)


MetadataValue = str | int


@dataclass(frozen=True, slots=True)
class DerivedTranscriptionSearchCandidate:
    schema_version: str
    candidate_id: str
    authority_kind: str

    case_id: str
    source_document_instance_id: str
    source_snapshot_id: str
    page_number: int

    original_filename: str
    original_blob_sha256: str
    original_byte_length: int

    source_extraction_method: str
    source_page_text_sha256: str
    source_page_text_byte_length: int

    derived_record_schema_version: str
    derived_record_id: str
    transcription_sha256: str
    transcription_byte_length: int

    profile_id: str
    profile_schema_version: str
    embedded_image_sha256: str

    ocr_language: str
    ocr_psm: int
    preprocessing_steps: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "preprocessing_steps",
            tuple(
                self.preprocessing_steps
            ),
        )


@dataclass(frozen=True, slots=True)
class DerivedTranscriptionSearchRow:
    row_schema_version: str
    row_id: str
    candidate: DerivedTranscriptionSearchCandidate
    document: str
    metadata: Mapping[str, MetadataValue]

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
