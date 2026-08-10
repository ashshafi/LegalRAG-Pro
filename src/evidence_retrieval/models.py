"""Read-only models for governed document-complete evidence inspection.

The U8 retrieval layer is additive.  These models expose immutable source
content that has already been captured and bound by ``source_evidence``;
they do not redefine source-evidence identities or analytical semantics.
"""

from __future__ import annotations

from dataclasses import dataclass

from source_evidence.models import BindingClass, BoundTextRole, ExtractionMethod


@dataclass(frozen=True, slots=True)
class DocumentEvidenceChunk:
    """One fully verified immutable chunk in document order."""

    page_number: int
    chunk_ordinal: int
    chunk_id: str
    evidence_key: str
    evidence_binding_id: str
    binding_class: BindingClass
    bound_text_role: BoundTextRole
    chunk_text_sha256: str
    chunk_text_byte_length: int
    text: str


@dataclass(frozen=True, slots=True)
class DocumentEvidencePage:
    """One immutable extracted page and all governed chunks on that page."""

    page_number: int
    extraction_method: ExtractionMethod
    page_text_sha256: str
    page_text_byte_length: int
    text: str
    chunks: tuple[DocumentEvidenceChunk, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "chunks", tuple(self.chunks))


@dataclass(frozen=True, slots=True)
class DocumentEvidenceInspection:
    """Complete verified immutable evidence surface for one governed document."""

    case_id: str
    source_document_instance_id: str
    source_snapshot_id: str
    original_filename: str
    original_blob_sha256: str
    original_byte_length: int
    extraction_profile_id: str
    chunking_profile_id: str
    page_count: int
    evidence_chunk_count: int
    pages: tuple[DocumentEvidencePage, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "pages", tuple(self.pages))


__all__ = [
    "DocumentEvidenceChunk",
    "DocumentEvidenceInspection",
    "DocumentEvidencePage",
]
