"""Deterministic immutable source capture for case-scoped PDF evidence."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path, PurePath

from case_management.document_context import build_document_id

from .chunking import build_chunking_profile, split_page_text
from .extraction import extract_pdf_pages
from .identity import (
    canonical_uuid,
    derive_sha256_id,
    derive_source_document_instance_id,
    sha256_bytes,
)
from .models import (
    CHUNKING_PROFILE_ID,
    EVIDENCE_BINDING_SCHEMA_VERSION,
    EXTRACTION_PROFILE_ID,
    PDF_MEDIA_TYPE,
    SOURCE_DOCUMENT_MANIFEST_SCHEMA_VERSION,
    BindingClass,
    BoundTextRole,
    EvidenceBinding,
    SourceChunkSnapshot,
    SourceDocumentManifest,
    SourcePageSnapshot,
)
from .serialization import (
    evidence_binding_identity_payload_to_dict,
    source_document_manifest_identity_payload_to_dict,
)
from .store import SourceEvidenceStore
from .validation import validate_evidence_binding, validate_source_document_manifest


class SourceEvidenceCaptureError(RuntimeError):
    """Raised when deterministic immutable PDF source capture cannot complete."""


def _validate_original_filename(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("original_filename must not be empty.")
    if PurePath(value).name != value or "/" in value or "\\" in value or value in (".", ".."):
        raise ValueError("original_filename must be a plain filename without directories.")
    if not value.lower().endswith(".pdf"):
        raise ValueError("original_filename must use a .pdf filename.")
    return value


def _put_verified_blob(store: SourceEvidenceStore, content: bytes) -> str:
    expected = sha256_bytes(content)
    actual = store.put_blob(content)
    if actual != expected:
        raise SourceEvidenceCaptureError(
            "Immutable source-evidence blob publication returned an unexpected SHA-256."
        )
    return actual


def _build_manifest(
    *,
    case_id: str,
    source_document_instance_id: str,
    original_filename: str,
    original_blob_sha256: str,
    original_byte_length: int,
    extraction_profile,
    chunking_profile,
    pages: tuple[SourcePageSnapshot, ...],
) -> SourceDocumentManifest:
    provisional = SourceDocumentManifest(
        schema_version=SOURCE_DOCUMENT_MANIFEST_SCHEMA_VERSION,
        case_id=case_id,
        source_document_instance_id=source_document_instance_id,
        original_filename=original_filename,
        media_type=PDF_MEDIA_TYPE,
        original_blob_sha256=original_blob_sha256,
        original_byte_length=original_byte_length,
        extraction_profile=extraction_profile,
        chunking_profile=chunking_profile,
        pages=pages,
        source_snapshot_id="sha256:" + "0" * 64,
    )
    manifest = replace(
        provisional,
        source_snapshot_id=derive_sha256_id(
            source_document_manifest_identity_payload_to_dict(provisional)
        ),
    )
    validate_source_document_manifest(manifest)
    return manifest


def _build_binding(
    *,
    manifest: SourceDocumentManifest,
    page: SourcePageSnapshot,
    chunk: SourceChunkSnapshot,
) -> EvidenceBinding:
    provisional = EvidenceBinding(
        schema_version=EVIDENCE_BINDING_SCHEMA_VERSION,
        case_id=manifest.case_id,
        evidence_key=chunk.evidence_key,
        chunk_id=chunk.chunk_id,
        binding_class=BindingClass.FULL_CHAIN_BOUND,
        bound_text_role=BoundTextRole.CHUNK_TEXT,
        source_document_instance_id=manifest.source_document_instance_id,
        source_snapshot_id=manifest.source_snapshot_id,
        document_name=manifest.original_filename,
        document_id=None,
        page=page.page_number,
        chunk_ordinal=chunk.chunk_ordinal,
        original_blob_sha256=manifest.original_blob_sha256,
        page_text_sha256=page.page_text_sha256,
        chunk_text_sha256=chunk.chunk_text_sha256,
        bound_text_sha256=chunk.chunk_text_sha256,
        extraction_profile_id=EXTRACTION_PROFILE_ID,
        chunking_profile_id=CHUNKING_PROFILE_ID,
        evidence_binding_id="sha256:" + "0" * 64,
    )
    binding = replace(
        provisional,
        evidence_binding_id=derive_sha256_id(
            evidence_binding_identity_payload_to_dict(provisional)
        ),
    )
    validate_evidence_binding(binding)
    return binding


def capture_pdf_source(
    pdf_path: str | Path,
    *,
    case_id: str,
    original_filename: str | None = None,
    store: SourceEvidenceStore | None = None,
) -> SourceDocumentManifest:
    """Capture one PDF into immutable original/page/chunk lineage and bindings."""

    canonical_case_id = canonical_uuid(case_id, field_name="case_id")
    input_path = Path(pdf_path)
    filename = _validate_original_filename(
        input_path.name if original_filename is None else original_filename
    )

    try:
        # The source path is read exactly once. Every derivation below consumes
        # this in-memory byte sequence, never the mutable external path again.
        original_bytes = input_path.read_bytes()
    except OSError as exc:
        raise SourceEvidenceCaptureError("PDF source bytes could not be read.") from exc
    if not original_bytes:
        raise SourceEvidenceCaptureError("PDF source bytes must not be empty.")

    target_store = store if store is not None else SourceEvidenceStore()

    try:
        original_blob_sha256 = _put_verified_blob(target_store, original_bytes)
        source_document_instance_id = derive_source_document_instance_id(
            case_id=canonical_case_id,
            original_filename=filename,
            original_blob_sha256=original_blob_sha256,
        )

        extraction = extract_pdf_pages(original_bytes)
        chunking_profile = build_chunking_profile()
        page_snapshots: list[SourcePageSnapshot] = []

        for extracted_page in extraction.pages:
            page_bytes = extracted_page.text.encode("utf-8")
            page_sha = _put_verified_blob(target_store, page_bytes)
            chunks = split_page_text(extracted_page.text)
            chunk_snapshots: list[SourceChunkSnapshot] = []
            for chunk_ordinal, chunk_text in enumerate(chunks):
                chunk_bytes = chunk_text.encode("utf-8")
                chunk_sha = _put_verified_blob(target_store, chunk_bytes)
                chunk_id = build_document_id(
                    pdf_path=Path(filename),
                    page_number=extracted_page.page_number,
                    chunk_number=chunk_ordinal,
                    case_id=canonical_case_id,
                )
                chunk_snapshots.append(
                    SourceChunkSnapshot(
                        page_number=extracted_page.page_number,
                        chunk_ordinal=chunk_ordinal,
                        chunk_id=chunk_id,
                        evidence_key=chunk_id,
                        chunk_text_sha256=chunk_sha,
                        chunk_text_byte_length=len(chunk_bytes),
                    )
                )
            page_snapshots.append(
                SourcePageSnapshot(
                    page_number=extracted_page.page_number,
                    extraction_method=extracted_page.extraction_method,
                    page_text_sha256=page_sha,
                    page_text_byte_length=len(page_bytes),
                    chunk_snapshots=tuple(chunk_snapshots),
                )
            )

        manifest = _build_manifest(
            case_id=canonical_case_id,
            source_document_instance_id=source_document_instance_id,
            original_filename=filename,
            original_blob_sha256=original_blob_sha256,
            original_byte_length=len(original_bytes),
            extraction_profile=extraction.extraction_profile,
            chunking_profile=chunking_profile,
            pages=tuple(page_snapshots),
        )
        bindings = tuple(
            _build_binding(manifest=manifest, page=page, chunk=chunk)
            for page in manifest.pages
            for chunk in page.chunk_snapshots
        )

        target_store.publish_document_manifest(manifest)
        for binding in bindings:
            target_store.publish_evidence_binding(binding)
        return manifest
    except ValueError:
        raise
    except SourceEvidenceCaptureError:
        raise
    except Exception as exc:
        raise SourceEvidenceCaptureError(
            "Immutable PDF source capture could not be completed."
        ) from exc


__all__ = ["SourceEvidenceCaptureError", "capture_pdf_source"]
