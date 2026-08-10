"""Deterministic document-complete retrieval from immutable source evidence.

This module deliberately does not query Chroma, invoke OpenAI, rerun
extraction/OCR, or publish source-evidence records.  Once a governed document
identity is known, the immutable ``SourceDocumentManifest`` is the completeness
authority and every governed page/chunk is read and verified in manifest order.
"""

from __future__ import annotations

from source_evidence.identity import canonical_uuid
from source_evidence.models import (
    BindingClass,
    BoundTextRole,
    EvidenceBinding,
    SourceChunkSnapshot,
    SourceDocumentManifest,
    SourcePageSnapshot,
)
from source_evidence.store import SourceEvidenceStore, SourceEvidenceStoreError
from source_evidence.validation import (
    validate_evidence_binding,
    validate_source_document_manifest,
)

from .models import (
    DocumentEvidenceChunk,
    DocumentEvidenceInspection,
    DocumentEvidencePage,
)


class DocumentCompleteRetrievalError(RuntimeError):
    """Raised when a complete governed document cannot be proved exactly."""


def inspect_document_complete(
    *,
    case_id: str,
    source_document_instance_id: str,
    store: SourceEvidenceStore | None = None,
) -> DocumentEvidenceInspection:
    """Return every governed page and chunk for one source-bound document.

    Args:
        case_id: Canonical case UUID.
        source_document_instance_id: Canonical governed document UUID.
        store: Optional read-only source-evidence store dependency.  When
            omitted, the configured production ``SourceEvidenceStore`` is used.

    Returns:
        A deterministic immutable inspection in manifest page/chunk order.

    Raises:
        DocumentCompleteRetrievalError: If any manifest, binding, blob, identity,
            byte length, UTF-8 payload, or source coordinate cannot be proved.
    """

    try:
        case = canonical_uuid(case_id, field_name="case_id")
        document_id = canonical_uuid(
            source_document_instance_id,
            field_name="source_document_instance_id",
        )
    except ValueError as exc:
        raise DocumentCompleteRetrievalError(
            "Document-complete retrieval requires canonical case and document UUIDs."
        ) from exc

    source_store = store if store is not None else SourceEvidenceStore()

    try:
        manifest = source_store.load_document_manifest(case, document_id)
        validate_source_document_manifest(manifest)
        _require_manifest_identity(manifest, case=case, document_id=document_id)

        pages: list[DocumentEvidencePage] = []
        evidence_chunk_count = 0

        for page in manifest.pages:
            page_text = _read_strict_text_blob(
                source_store,
                digest=page.page_text_sha256,
                expected_byte_length=page.page_text_byte_length,
                label=f"page {page.page_number} text",
            )

            chunks: list[DocumentEvidenceChunk] = []
            for chunk in page.chunk_snapshots:
                binding = source_store.load_evidence_binding(case, chunk.evidence_key)
                if binding is None:
                    raise DocumentCompleteRetrievalError(
                        "Document-complete retrieval is incomplete: "
                        f"missing EvidenceBinding for {chunk.evidence_key!r}."
                    )

                validate_evidence_binding(binding)
                _require_full_chain_binding(
                    manifest=manifest,
                    page=page,
                    chunk=chunk,
                    binding=binding,
                )

                chunk_text = _read_strict_text_blob(
                    source_store,
                    digest=chunk.chunk_text_sha256,
                    expected_byte_length=chunk.chunk_text_byte_length,
                    label=f"chunk {chunk.evidence_key!r}",
                )

                chunks.append(
                    DocumentEvidenceChunk(
                        page_number=chunk.page_number,
                        chunk_ordinal=chunk.chunk_ordinal,
                        chunk_id=chunk.chunk_id,
                        evidence_key=chunk.evidence_key,
                        evidence_binding_id=binding.evidence_binding_id,
                        binding_class=binding.binding_class,
                        bound_text_role=binding.bound_text_role,
                        chunk_text_sha256=chunk.chunk_text_sha256,
                        chunk_text_byte_length=chunk.chunk_text_byte_length,
                        text=chunk_text,
                    )
                )
                evidence_chunk_count += 1

            pages.append(
                DocumentEvidencePage(
                    page_number=page.page_number,
                    extraction_method=page.extraction_method,
                    page_text_sha256=page.page_text_sha256,
                    page_text_byte_length=page.page_text_byte_length,
                    text=page_text,
                    chunks=tuple(chunks),
                )
            )

        expected_chunks = sum(len(page.chunk_snapshots) for page in manifest.pages)
        if evidence_chunk_count != expected_chunks:
            raise DocumentCompleteRetrievalError(
                "Document-complete retrieval did not enumerate every manifest chunk."
            )

        return DocumentEvidenceInspection(
            case_id=manifest.case_id,
            source_document_instance_id=manifest.source_document_instance_id,
            source_snapshot_id=manifest.source_snapshot_id,
            original_filename=manifest.original_filename,
            original_blob_sha256=manifest.original_blob_sha256,
            original_byte_length=manifest.original_byte_length,
            extraction_profile_id=manifest.extraction_profile.profile_id,
            chunking_profile_id=manifest.chunking_profile.profile_id,
            page_count=len(manifest.pages),
            evidence_chunk_count=evidence_chunk_count,
            pages=tuple(pages),
        )
    except DocumentCompleteRetrievalError:
        raise
    except (SourceEvidenceStoreError, ValueError, UnicodeError) as exc:
        raise DocumentCompleteRetrievalError(
            "Document-complete retrieval could not prove the immutable source-evidence chain: "
            f"{exc}"
        ) from exc


def _require_manifest_identity(
    manifest: SourceDocumentManifest,
    *,
    case: str,
    document_id: str,
) -> None:
    if manifest.case_id != case:
        raise DocumentCompleteRetrievalError(
            "Loaded source manifest does not match the requested case."
        )
    if manifest.source_document_instance_id != document_id:
        raise DocumentCompleteRetrievalError(
            "Loaded source manifest does not match the requested document."
        )


def _require_full_chain_binding(
    *,
    manifest: SourceDocumentManifest,
    page: SourcePageSnapshot,
    chunk: SourceChunkSnapshot,
    binding: EvidenceBinding,
) -> None:
    if binding.binding_class is not BindingClass.FULL_CHAIN_BOUND:
        raise DocumentCompleteRetrievalError(
            f"Evidence {chunk.evidence_key!r} is not FULL_CHAIN_BOUND."
        )
    if binding.bound_text_role is not BoundTextRole.CHUNK_TEXT:
        raise DocumentCompleteRetrievalError(
            f"Evidence {chunk.evidence_key!r} is not bound to immutable chunk text."
        )

    expected = {
        "case_id": manifest.case_id,
        "evidence_key": chunk.evidence_key,
        "chunk_id": chunk.chunk_id,
        "source_document_instance_id": manifest.source_document_instance_id,
        "source_snapshot_id": manifest.source_snapshot_id,
        "document_name": manifest.original_filename,
        "page": page.page_number,
        "chunk_ordinal": chunk.chunk_ordinal,
        "original_blob_sha256": manifest.original_blob_sha256,
        "page_text_sha256": page.page_text_sha256,
        "chunk_text_sha256": chunk.chunk_text_sha256,
        "bound_text_sha256": chunk.chunk_text_sha256,
        "extraction_profile_id": manifest.extraction_profile.profile_id,
        "chunking_profile_id": manifest.chunking_profile.profile_id,
    }

    for field_name, expected_value in expected.items():
        if getattr(binding, field_name) != expected_value:
            raise DocumentCompleteRetrievalError(
                f"Evidence {chunk.evidence_key!r} binding field "
                f"{field_name!r} does not match its immutable manifest coordinate."
            )

    if chunk.page_number != page.page_number:
        raise DocumentCompleteRetrievalError(
            f"Evidence {chunk.evidence_key!r} page coordinate is inconsistent."
        )


def _read_strict_text_blob(
    store: SourceEvidenceStore,
    *,
    digest: str,
    expected_byte_length: int,
    label: str,
) -> str:
    data = store.read_blob(digest)
    if len(data) != expected_byte_length:
        raise DocumentCompleteRetrievalError(
            f"Immutable {label} byte length does not match its manifest."
        )
    try:
        return data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise DocumentCompleteRetrievalError(
            f"Immutable {label} is not strict UTF-8 text."
        ) from exc


__all__ = [
    "DocumentCompleteRetrievalError",
    "inspect_document_complete",
]
