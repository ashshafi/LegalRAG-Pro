"""Immutable Finance F5 document-evidence bridge models."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final
from source_evidence.models import ExtractionMethod, ExtractionProfile

FINANCE_SOURCE_DOCUMENT_SCHEMA_VERSION: Final[str] = "finance-source-document/1.0"
OBSERVATION_EVIDENCE_BINDING_SCHEMA_VERSION: Final[str] = "finance-observation-evidence-binding/1.0"
FINANCE_OBSERVATION_EVIDENCE_MANIFEST_SCHEMA_VERSION: Final[str] = "finance-observation-evidence-manifest/1.0"
FINANCE_EVIDENCE_IDENTITY_VERSION: Final[str] = "1.0"
PDF_MEDIA_TYPE: Final[str] = "application/pdf"

class ObservationSourceChannel(StrEnum):
    DOCUMENT = "DOCUMENT"
    STRUCTURED_PROVIDER = "STRUCTURED_PROVIDER"
    MARKET = "MARKET"

class ObservationDocumentBindingClass(StrEnum):
    DOCUMENT_TEXT_BOUND = "DOCUMENT_TEXT_BOUND"
    DOCUMENT_UNBOUND = "DOCUMENT_UNBOUND"
    NOT_APPLICABLE = "NOT_APPLICABLE"

class FinanceDocumentEvidenceCoverage(StrEnum):
    FULLY_DOCUMENT_BOUND = "FULLY_DOCUMENT_BOUND"
    MIXED_DOCUMENT_BINDING = "MIXED_DOCUMENT_BINDING"
    DOCUMENT_UNBOUND = "DOCUMENT_UNBOUND"
    NOT_APPLICABLE = "NOT_APPLICABLE"

@dataclass(frozen=True, slots=True)
class FinanceSourcePageSnapshot:
    page_number: int
    extraction_method: ExtractionMethod
    page_text_sha256: str
    page_text_byte_length: int

@dataclass(frozen=True, slots=True)
class FinanceSourceDocumentManifest:
    schema_version: str
    workspace_id: str
    company_id: str
    provider: str
    source_id: str
    source_version: str
    publication_at: datetime | None
    original_filename: str
    media_type: str
    original_blob_sha256: str
    original_byte_length: int
    extraction_profile: ExtractionProfile
    pages: tuple[FinanceSourcePageSnapshot, ...]
    document_snapshot_id: str
    def __post_init__(self) -> None:
        object.__setattr__(self, "pages", tuple(self.pages))

@dataclass(frozen=True, slots=True)
class ObservationEvidenceBinding:
    schema_version: str
    workspace_id: str
    company_id: str
    observation_id: str
    source_channel: ObservationSourceChannel
    binding_class: ObservationDocumentBindingClass
    document_snapshot_id: str | None
    page_number: int | None
    page_byte_start: int | None
    page_byte_end: int | None
    bound_text_sha256: str | None
    note: str | None
    evidence_binding_id: str

@dataclass(frozen=True, slots=True)
class FinanceObservationEvidenceManifest:
    schema_version: str
    identity_version: str
    workspace_id: str
    source_analysis_id: str
    as_of: datetime
    observation_ids: tuple[str, ...]
    documents: tuple[FinanceSourceDocumentManifest, ...]
    entries: tuple[ObservationEvidenceBinding, ...]
    coverage: FinanceDocumentEvidenceCoverage
    document_evidence_manifest_id: str
    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_ids", tuple(self.observation_ids))
        object.__setattr__(self, "documents", tuple(self.documents))
        object.__setattr__(self, "entries", tuple(self.entries))

@dataclass(frozen=True, slots=True)
class ResolvedFinanceObservationEvidence:
    workspace_id: str
    source_analysis_id: str
    observation_id: str
    source_channel: ObservationSourceChannel
    binding_class: ObservationDocumentBindingClass
    document_snapshot_id: str
    original_filename: str
    page_number: int
    original_blob_sha256: str
    page_text_sha256: str
    bound_text_sha256: str
    exact_bound_text: str
    exact_page_text: str
    original_pdf_bytes: bytes
