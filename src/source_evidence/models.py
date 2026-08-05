"""Immutable core models for the source-evidence authority.

These models carry technical byte identity and provenance only. They do not
extend or reinterpret LegalRAG Pro's frozen analytical/reporting semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

SOURCE_DOCUMENT_MANIFEST_SCHEMA_VERSION: Final[str] = "source-document-manifest/1.0"
EVIDENCE_BINDING_SCHEMA_VERSION: Final[str] = "evidence-binding/1.0"
SOURCE_BOUND_ANALYSIS_RECEIPT_SCHEMA_VERSION: Final[str] = "source-bound-analysis-receipt/1.0"
PROJECTION_EVIDENCE_BINDING_SCHEMA_VERSION: Final[str] = "projection-evidence-binding/1.0"
SOURCE_EVIDENCE_STORE_VERSION: Final[str] = "source-evidence-store/1.0"

EXTRACTION_PROFILE_ID: Final[str] = "pdf-page-extraction/1.0"
EXTRACTION_PROFILE_SCHEMA_VERSION: Final[str] = "1.0"
CHUNKING_PROFILE_ID: Final[str] = "recursive-character-text-splitter/1.0"
CHUNKING_PROFILE_SCHEMA_VERSION: Final[str] = "1.0"
SOURCE_BOUND_RETRIEVAL_VERIFIER_VERSION: Final[str] = "source-bound-retrieval-verifier/1.0"

PDF_MEDIA_TYPE: Final[str] = "application/pdf"


class ExtractionMethod(StrEnum):
    """Governed page extraction methods."""

    PYPDF_TEXT = "pypdf_text"
    PAGE_OCR = "page_ocr"


class BindingClass(StrEnum):
    """Technical source-integrity binding classes."""

    FULL_CHAIN_BOUND = "full_chain_bound"
    ANALYTICAL_TEXT_BOUND = "analytical_text_bound"
    LEGACY_CURRENT_INDEX_SNAPSHOT = "legacy_current_index_snapshot"
    UNBOUND = "unbound"


class ProjectionBindingCoverage(StrEnum):
    """Projection-level technical source-binding coverage."""

    FULLY_SOURCE_BOUND = "fully_source_bound"
    MIXED_BINDING = "mixed_binding"
    UNBOUND = "unbound"


class BoundTextRole(StrEnum):
    """Role of bytes addressed by EvidenceBinding.bound_text_sha256."""

    CHUNK_TEXT = "chunk_text"
    ANALYTICAL_SUMMARY = "analytical_summary"
    LEGACY_CURRENT_INDEX_TEXT = "legacy_current_index_text"


@dataclass(frozen=True, slots=True)
class ExtractionProfile:
    profile_id: str
    profile_schema_version: str
    pypdf_package_version: str
    pdf2image_package_version: str | None
    pytesseract_package_version: str | None
    tesseract_engine_version: str | None
    poppler_version: str | None
    ocr_language: str
    ocr_config: str
    ocr_dpi: int


@dataclass(frozen=True, slots=True)
class ChunkingProfile:
    profile_id: str
    profile_schema_version: str
    library: str
    library_version: str
    chunk_size: int
    chunk_overlap: int
    separators: tuple[str, ...]
    length_function: str
    is_separator_regex: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "separators", tuple(self.separators))


@dataclass(frozen=True, slots=True)
class SourceChunkSnapshot:
    page_number: int
    chunk_ordinal: int
    chunk_id: str
    evidence_key: str
    chunk_text_sha256: str
    chunk_text_byte_length: int


@dataclass(frozen=True, slots=True)
class SourcePageSnapshot:
    page_number: int
    extraction_method: ExtractionMethod
    page_text_sha256: str
    page_text_byte_length: int
    chunk_snapshots: tuple[SourceChunkSnapshot, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "chunk_snapshots", tuple(self.chunk_snapshots))


@dataclass(frozen=True, slots=True)
class SourceDocumentManifest:
    schema_version: str
    case_id: str
    source_document_instance_id: str
    original_filename: str
    media_type: str
    original_blob_sha256: str
    original_byte_length: int
    extraction_profile: ExtractionProfile
    chunking_profile: ChunkingProfile
    pages: tuple[SourcePageSnapshot, ...]
    source_snapshot_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "pages", tuple(self.pages))


@dataclass(frozen=True, slots=True)
class EvidenceBinding:
    schema_version: str
    case_id: str
    evidence_key: str
    chunk_id: str | None
    binding_class: BindingClass
    bound_text_role: BoundTextRole
    source_document_instance_id: str | None
    source_snapshot_id: str | None
    document_name: str
    document_id: str | None
    page: int | None
    chunk_ordinal: int | None
    original_blob_sha256: str | None
    page_text_sha256: str | None
    chunk_text_sha256: str | None
    bound_text_sha256: str
    extraction_profile_id: str | None
    chunking_profile_id: str | None
    evidence_binding_id: str


@dataclass(frozen=True, slots=True)
class VerifiedEvidenceUse:
    evidence_key: str
    evidence_binding_id: str
    chunk_text_sha256: str


@dataclass(frozen=True, slots=True)
class SourceBoundAnalysisReceipt:
    schema_version: str
    case_id: str
    verifier_version: str
    verified_evidence: tuple[VerifiedEvidenceUse, ...]
    source_bound_analysis_receipt_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "verified_evidence", tuple(self.verified_evidence))


@dataclass(frozen=True, slots=True)
class ProjectionBindingEntry:
    citation_id: str
    evidence_key: str
    binding_class: BindingClass
    evidence_binding_id: str | None
    source_bound_analysis_receipt_id: str | None


@dataclass(frozen=True, slots=True)
class ProjectionEvidenceBindingManifest:
    schema_version: str
    case_id: str
    report_projection_id: str
    projection_payload_sha256: str
    manifest_id: str
    coverage: ProjectionBindingCoverage
    entries: tuple[ProjectionBindingEntry, ...]
    projection_evidence_binding_manifest_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(self.entries))


__all__ = [
    "BindingClass",
    "BoundTextRole",
    "CHUNKING_PROFILE_ID",
    "CHUNKING_PROFILE_SCHEMA_VERSION",
    "ChunkingProfile",
    "EVIDENCE_BINDING_SCHEMA_VERSION",
    "EXTRACTION_PROFILE_ID",
    "EXTRACTION_PROFILE_SCHEMA_VERSION",
    "EvidenceBinding",
    "ExtractionMethod",
    "ExtractionProfile",
    "PDF_MEDIA_TYPE",
    "PROJECTION_EVIDENCE_BINDING_SCHEMA_VERSION",
    "ProjectionBindingCoverage",
    "ProjectionBindingEntry",
    "ProjectionEvidenceBindingManifest",
    "SOURCE_BOUND_ANALYSIS_RECEIPT_SCHEMA_VERSION",
    "SOURCE_BOUND_RETRIEVAL_VERIFIER_VERSION",
    "SOURCE_DOCUMENT_MANIFEST_SCHEMA_VERSION",
    "SOURCE_EVIDENCE_STORE_VERSION",
    "SourceBoundAnalysisReceipt",
    "SourceChunkSnapshot",
    "SourceDocumentManifest",
    "SourcePageSnapshot",
    "VerifiedEvidenceUse",
]
