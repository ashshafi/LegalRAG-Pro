"""Recoverable source-bound ingestion for the governed embedded Chroma index.

Chroma remains derived infrastructure. Success is determined by exact
post-write row verification, not by an assumed database rollback guarantee.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Sequence

from case_management.document_context import build_chunk_metadata
from chunk_provenance import add_chunk_provenance_to_metadata
from evidence_classification import EvidenceSourceType, classify_evidence_source

from .capture import capture_pdf_source
from .chroma_lock import ChromaWriterLock, ChromaWriterLockError
from .identity import canonical_uuid, validate_sha256_hex
from .models import (
    BindingClass,
    BoundTextRole,
    EvidenceBinding,
    SourceChunkSnapshot,
    SourceDocumentManifest,
    SourcePageSnapshot,
)
from .store import SourceEvidenceStore
from .validation import validate_evidence_binding, validate_source_document_manifest

LOGGER = logging.getLogger(__name__)

_DEFAULT_TENANT = "default_tenant"
_DEFAULT_DATABASE = "default_database"
_GOVERNED_COLLECTION_NAME = "legal_documents"


class SourceBoundIndexRowState(StrEnum):
    """Exact observable state of one expected source-bound Chroma row."""

    EXACT_PRESENT = "exact_present"
    MISSING = "missing"
    CONFLICTING = "conflicting"


@dataclass(frozen=True, slots=True)
class SourceBoundIndexRowDiagnostic:
    """Controlled diagnostic result for one expected evidence key."""

    evidence_key: str
    state: SourceBoundIndexRowState
    reason: str


@dataclass(frozen=True, slots=True)
class SourceBoundIndexDiagnostic:
    """Read-only exact/missing/conflicting state for one immutable manifest."""

    case_id: str
    source_snapshot_id: str
    total_rows: int
    exact_present_count: int
    missing_count: int
    conflicting_count: int
    rows: tuple[SourceBoundIndexRowDiagnostic, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", tuple(self.rows))


class SourceEvidenceIngestionError(RuntimeError):
    """Raised when source-bound indexing cannot complete under the M4 contract."""


class SourceEvidenceIngestionConflictError(SourceEvidenceIngestionError):
    """Raised when a positional Chroma ID contains different text or metadata."""


class SourceEvidenceIngestionIncompleteError(SourceEvidenceIngestionError):
    """Raised when exact rows are retained but one or more expected rows are missing."""

    def __init__(
        self,
        message: str,
        diagnostic: SourceBoundIndexDiagnostic,
    ) -> None:
        super().__init__(message)
        self.diagnostic = diagnostic


@dataclass(frozen=True, slots=True)
class _PreparedRow:
    row_id: str
    document: str
    metadata: dict[str, str | int]


@dataclass(frozen=True, slots=True)
class _Runtime:
    chroma_client: Any
    collection: Any
    openai_client: Any
    embedding_model: str
    db_path: Path
    tenant: str
    database: str
    collection_name: str


def _load_runtime() -> _Runtime:
    """Load external services lazily so module import remains side-effect free."""

    from config import chroma_client, collection, openai_client
    from models import EMBEDDING_MODEL

    collection_name = getattr(collection, "name", None)
    if collection_name != _GOVERNED_COLLECTION_NAME:
        raise SourceEvidenceIngestionError(
            "Configured Chroma collection does not match the governed collection."
        )
    return _Runtime(
        chroma_client=chroma_client,
        collection=collection,
        openai_client=openai_client,
        embedding_model=EMBEDDING_MODEL,
        db_path=Path("db").expanduser().resolve(strict=False),
        tenant=_DEFAULT_TENANT,
        database=_DEFAULT_DATABASE,
        collection_name=_GOVERNED_COLLECTION_NAME,
    )


def _read_text_blob(
    store: SourceEvidenceStore,
    *,
    sha256_hex: str,
    expected_byte_length: int,
    label: str,
) -> str:
    data = store.read_blob(sha256_hex)
    if len(data) != expected_byte_length:
        raise SourceEvidenceIngestionError(
            f"Immutable {label} byte length does not match its source manifest."
        )
    try:
        return data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SourceEvidenceIngestionError(
            f"Immutable {label} bytes are not valid UTF-8."
        ) from exc


def _build_document_hint(
    manifest: SourceDocumentManifest,
    store: SourceEvidenceStore,
    *,
    max_chars: int = 6000,
) -> str:
    parts: list[str] = []
    source_chars = 0
    for page in manifest.pages[:3]:
        text = _read_text_blob(
            store,
            sha256_hex=page.page_text_sha256,
            expected_byte_length=page.page_text_byte_length,
            label="page text",
        )
        if text.strip():
            part = text.strip()
            parts.append(part)
            source_chars += len(part)
        if source_chars >= max_chars:
            break
    return "\n".join(parts)[:max_chars]


def _require_full_chain_binding(
    *,
    manifest: SourceDocumentManifest,
    page: SourcePageSnapshot,
    chunk: SourceChunkSnapshot,
    binding: EvidenceBinding | None,
) -> EvidenceBinding:
    if binding is None:
        raise SourceEvidenceIngestionError(
            "An immutable source-evidence binding required for ingestion is missing."
        )
    validate_evidence_binding(binding)
    expected = {
        "case_id": manifest.case_id,
        "evidence_key": chunk.evidence_key,
        "chunk_id": chunk.chunk_id,
        "binding_class": BindingClass.FULL_CHAIN_BOUND,
        "bound_text_role": BoundTextRole.CHUNK_TEXT,
        "source_document_instance_id": manifest.source_document_instance_id,
        "source_snapshot_id": manifest.source_snapshot_id,
        "document_name": manifest.original_filename,
        "document_id": None,
        "page": page.page_number,
        "chunk_ordinal": chunk.chunk_ordinal,
        "original_blob_sha256": manifest.original_blob_sha256,
        "page_text_sha256": page.page_text_sha256,
        "chunk_text_sha256": chunk.chunk_text_sha256,
        "bound_text_sha256": chunk.chunk_text_sha256,
        "extraction_profile_id": manifest.extraction_profile.profile_id,
        "chunking_profile_id": manifest.chunking_profile.profile_id,
    }
    if any(getattr(binding, name) != expected_value for name, expected_value in expected.items()):
        raise SourceEvidenceIngestionError(
            "Immutable source-evidence binding does not match its manifest chunk."
        )
    return binding


def _prepare_rows(
    *,
    manifest: SourceDocumentManifest,
    store: SourceEvidenceStore,
    evidence_source_type: EvidenceSourceType | str | None,
) -> tuple[_PreparedRow, ...]:
    validate_source_document_manifest(manifest)
    document_hint = _build_document_hint(manifest, store)
    rows: list[_PreparedRow] = []
    seen_ids: set[str] = set()
    for page in manifest.pages:
        for chunk in page.chunk_snapshots:
            binding = _require_full_chain_binding(
                manifest=manifest,
                page=page,
                chunk=chunk,
                binding=store.load_evidence_binding(manifest.case_id, chunk.evidence_key),
            )
            chunk_text = _read_text_blob(
                store,
                sha256_hex=chunk.chunk_text_sha256,
                expected_byte_length=chunk.chunk_text_byte_length,
                label="chunk text",
            )
            classification = classify_evidence_source(
                file_name=manifest.original_filename,
                text=chunk_text,
                document_hint=document_hint,
                explicit_source_type=evidence_source_type,
            )
            metadata = build_chunk_metadata(
                pdf_path=Path(manifest.original_filename),
                page_number=page.page_number,
                chunk_number=chunk.chunk_ordinal,
                case_id=manifest.case_id,
                evidence_source_type=classification.source_type.value,
                evidence_source_label=classification.label,
                evidence_classification_method=classification.method,
            )
            metadata = add_chunk_provenance_to_metadata(metadata, text=chunk_text)
            metadata.update(
                {
                    "source_evidence_binding_id": binding.evidence_binding_id,
                    "source_snapshot_id": manifest.source_snapshot_id,
                    "source_document_instance_id": manifest.source_document_instance_id,
                    "source_chunk_sha256": chunk.chunk_text_sha256,
                    "source_page_text_sha256": page.page_text_sha256,
                    "source_original_blob_sha256": manifest.original_blob_sha256,
                    "source_binding_class": BindingClass.FULL_CHAIN_BOUND.value,
                }
            )
            if chunk.chunk_id in seen_ids:
                raise SourceEvidenceIngestionError(
                    "Source-bound manifest contains duplicate Chroma row IDs."
                )
            seen_ids.add(chunk.chunk_id)
            rows.append(
                _PreparedRow(
                    row_id=chunk.chunk_id,
                    document=chunk_text,
                    metadata=metadata,
                )
            )
    return tuple(rows)


def _read_chroma_rows(collection: Any, rows: Sequence[_PreparedRow]) -> Mapping[str, Any]:
    try:
        result = collection.get(
            ids=[row.row_id for row in rows],
            include=["documents", "metadatas"],
        )
    except Exception as exc:
        raise SourceEvidenceIngestionError(
            "Chroma source-bound state inspection failed."
        ) from exc
    if not isinstance(result, Mapping):
        raise SourceEvidenceIngestionError(
            "Chroma returned an invalid source-bound record response."
        )
    return result


def _classify_rows(
    *,
    manifest: SourceDocumentManifest,
    rows: Sequence[_PreparedRow],
    collection: Any,
) -> SourceBoundIndexDiagnostic:
    if not rows:
        return SourceBoundIndexDiagnostic(
            case_id=manifest.case_id,
            source_snapshot_id=manifest.source_snapshot_id,
            total_rows=0,
            exact_present_count=0,
            missing_count=0,
            conflicting_count=0,
            rows=(),
        )
    expected_by_id = {row.row_id: row for row in rows}
    if len(expected_by_id) != len(rows):
        raise SourceEvidenceIngestionError(
            "Source-bound manifest contains duplicate Chroma row IDs."
        )
    result = _read_chroma_rows(collection, rows)
    ids = result.get("ids")
    documents = result.get("documents")
    metadatas = result.get("metadatas")
    if ids is None:
        ids = []
    if not isinstance(ids, list) or any(not isinstance(item, str) for item in ids):
        raise SourceEvidenceIngestionError(
            "Chroma returned invalid source-bound record IDs."
        )
    if len(ids) != len(set(ids)):
        raise SourceEvidenceIngestionError(
            "Chroma returned duplicate source-bound record IDs."
        )
    if ids:
        if not isinstance(documents, list) or not isinstance(metadatas, list):
            raise SourceEvidenceIngestionError(
                "Chroma omitted required source-bound record fields."
            )
        if len(documents) != len(ids) or len(metadatas) != len(ids):
            raise SourceEvidenceIngestionError(
                "Chroma returned misaligned source-bound record columns."
            )
    else:
        if documents not in (None, []) or metadatas not in (None, []):
            raise SourceEvidenceIngestionError(
                "Chroma returned inconsistent empty source-bound record columns."
            )
        documents = []
        metadatas = []

    observed: dict[str, tuple[object, object]] = {}
    for row_id, document, metadata in zip(ids, documents, metadatas):
        if row_id not in expected_by_id:
            raise SourceEvidenceIngestionError(
                "Chroma returned an unexpected source-bound record ID."
            )
        if not isinstance(document, str) or not isinstance(metadata, dict):
            raise SourceEvidenceIngestionError(
                "Chroma returned invalid source-bound record content."
            )
        observed[row_id] = (document, metadata)

    diagnostics: list[SourceBoundIndexRowDiagnostic] = []
    for row in rows:
        current = observed.get(row.row_id)
        if current is None:
            diagnostics.append(
                SourceBoundIndexRowDiagnostic(
                    evidence_key=row.row_id,
                    state=SourceBoundIndexRowState.MISSING,
                    reason="requested Chroma row is absent",
                )
            )
            continue
        document, metadata = current
        if document != row.document:
            diagnostics.append(
                SourceBoundIndexRowDiagnostic(
                    evidence_key=row.row_id,
                    state=SourceBoundIndexRowState.CONFLICTING,
                    reason="stored Chroma document differs from immutable chunk text",
                )
            )
        elif metadata != row.metadata:
            diagnostics.append(
                SourceBoundIndexRowDiagnostic(
                    evidence_key=row.row_id,
                    state=SourceBoundIndexRowState.CONFLICTING,
                    reason="stored Chroma metadata differs from intended source-bound metadata",
                )
            )
        else:
            diagnostics.append(
                SourceBoundIndexRowDiagnostic(
                    evidence_key=row.row_id,
                    state=SourceBoundIndexRowState.EXACT_PRESENT,
                    reason="stored Chroma document and metadata are exact",
                )
            )

    exact_count = sum(
        item.state is SourceBoundIndexRowState.EXACT_PRESENT for item in diagnostics
    )
    missing_count = sum(item.state is SourceBoundIndexRowState.MISSING for item in diagnostics)
    conflicting_count = sum(
        item.state is SourceBoundIndexRowState.CONFLICTING for item in diagnostics
    )
    return SourceBoundIndexDiagnostic(
        case_id=manifest.case_id,
        source_snapshot_id=manifest.source_snapshot_id,
        total_rows=len(rows),
        exact_present_count=exact_count,
        missing_count=missing_count,
        conflicting_count=conflicting_count,
        rows=tuple(diagnostics),
    )


def inspect_source_bound_index(
    manifest: SourceDocumentManifest,
    *,
    evidence_source_type: EvidenceSourceType | str | None = None,
    store: SourceEvidenceStore | None = None,
    collection: object | None = None,
) -> SourceBoundIndexDiagnostic:
    """Return an observational exact/missing/conflicting Chroma snapshot."""

    target_store = store if store is not None else SourceEvidenceStore()
    try:
        validate_source_document_manifest(manifest)
        rows = _prepare_rows(
            manifest=manifest,
            store=target_store,
            evidence_source_type=evidence_source_type,
        )
        if not rows:
            return _classify_rows(
                manifest=manifest,
                rows=rows,
                collection=collection,
            )
        target_collection = collection
        if target_collection is None:
            target_collection = _load_runtime().collection
        return _classify_rows(
            manifest=manifest,
            rows=rows,
            collection=target_collection,
        )
    except (ValueError, TypeError, SourceEvidenceIngestionError):
        raise
    except Exception as exc:
        raise SourceEvidenceIngestionError(
            "Source-bound index inspection could not be completed."
        ) from exc


def _create_embedding(openai_client: Any, *, model: str, text: str) -> list[float]:
    try:
        response = openai_client.embeddings.create(model=model, input=text)
        data = response.data
    except Exception as exc:
        raise SourceEvidenceIngestionError(
            "Embedding creation failed before Chroma writer-lock acquisition."
        ) from exc
    if not isinstance(data, (list, tuple)) or len(data) != 1:
        raise SourceEvidenceIngestionError(
            "Embedding service returned an invalid response shape."
        )
    embedding = getattr(data[0], "embedding", None)
    if not isinstance(embedding, (list, tuple)) or not embedding:
        raise SourceEvidenceIngestionError(
            "Embedding service returned no usable embedding."
        )
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in embedding):
        raise SourceEvidenceIngestionError(
            "Embedding service returned invalid embedding values."
        )
    return [float(value) for value in embedding]


def _raise_if_conflicting(diagnostic: SourceBoundIndexDiagnostic) -> None:
    if diagnostic.conflicting_count == 0:
        return
    first = next(
        item
        for item in diagnostic.rows
        if item.state is SourceBoundIndexRowState.CONFLICTING
    )
    raise SourceEvidenceIngestionConflictError(
        "A Chroma row conflicts with immutable source evidence "
        f"for evidence key {first.evidence_key}."
    )


def _missing_ids(diagnostic: SourceBoundIndexDiagnostic) -> tuple[str, ...]:
    return tuple(
        item.evidence_key
        for item in diagnostic.rows
        if item.state is SourceBoundIndexRowState.MISSING
    )


def _max_batch_size(chroma_client: Any) -> int:
    try:
        value = chroma_client.get_max_batch_size()
    except Exception as exc:
        raise SourceEvidenceIngestionError(
            "Chroma maximum batch size could not be established."
        ) from exc
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SourceEvidenceIngestionError(
            "Chroma returned an invalid maximum batch size."
        )
    return value


def index_case_pdf_source_bound(
    pdf_path: str | Path,
    *,
    case_id: str,
    evidence_source_type: EvidenceSourceType | str | None = None,
    store: SourceEvidenceStore | None = None,
    expected_original_sha256: str | None = None,
) -> int:
    """Capture and recoverably index exact immutable PDF chunks for one case."""

    canonical_case_id = canonical_uuid(case_id, field_name="case_id")
    expected_upload_sha = (
        validate_sha256_hex(
            expected_original_sha256,
            field_name="expected_original_sha256",
        )
        if expected_original_sha256 is not None
        else None
    )
    target_store = store if store is not None else SourceEvidenceStore()
    try:
        manifest = capture_pdf_source(
            pdf_path,
            case_id=canonical_case_id,
            original_filename=Path(pdf_path).name,
            store=target_store,
        )
        validate_source_document_manifest(manifest)
        if manifest.case_id != canonical_case_id:
            raise SourceEvidenceIngestionError(
                "Captured source manifest does not match the requested case."
            )
        if expected_upload_sha is not None and manifest.original_blob_sha256 != expected_upload_sha:
            raise SourceEvidenceIngestionError(
                "Captured source bytes do not match the exact uploaded PDF bytes."
            )

        total_chunks = sum(len(page.chunk_snapshots) for page in manifest.pages)
        if total_chunks == 0:
            return 0
        rows = _prepare_rows(
            manifest=manifest,
            store=target_store,
            evidence_source_type=evidence_source_type,
        )
        if len(rows) != total_chunks:
            raise SourceEvidenceIngestionError(
                "Prepared Chroma rows do not match the immutable manifest chunk count."
            )

        runtime = _load_runtime()
        ordinary = _classify_rows(
            manifest=manifest,
            rows=rows,
            collection=runtime.collection,
        )
        _raise_if_conflicting(ordinary)
        row_by_id = {row.row_id: row for row in rows}
        embeddings_by_id = {
            row_id: _create_embedding(
                runtime.openai_client,
                model=runtime.embedding_model,
                text=row_by_id[row_id].document,
            )
            for row_id in _missing_ids(ordinary)
        }

        lock = ChromaWriterLock(
            db_path=runtime.db_path,
            tenant=runtime.tenant,
            database=runtime.database,
            collection_name=runtime.collection_name,
        )
        try:
            with lock:
                authoritative = _classify_rows(
                    manifest=manifest,
                    rows=rows,
                    collection=runtime.collection,
                )
                _raise_if_conflicting(authoritative)
                authoritative_missing = _missing_ids(authoritative)
                missing_without_embedding = tuple(
                    row_id
                    for row_id in authoritative_missing
                    if row_id not in embeddings_by_id
                )
                if missing_without_embedding:
                    raise SourceEvidenceIngestionIncompleteError(
                        "A previously exact Chroma row disappeared before the locked write phase.",
                        authoritative,
                    )
                if not authoritative_missing:
                    return total_chunks

                maximum = _max_batch_size(runtime.chroma_client)
                if len(authoritative_missing) > maximum:
                    raise SourceEvidenceIngestionError(
                        "The source-bound missing row set exceeds Chroma's maximum batch size."
                    )
                rows_to_add = [row_by_id[row_id] for row_id in authoritative_missing]
                add_error: Exception | None = None
                try:
                    runtime.collection.add(
                        ids=[row.row_id for row in rows_to_add],
                        embeddings=[embeddings_by_id[row.row_id] for row in rows_to_add],
                        documents=[row.document for row in rows_to_add],
                        metadatas=[row.metadata for row in rows_to_add],
                    )
                except Exception as exc:
                    add_error = exc

                post_write = _classify_rows(
                    manifest=manifest,
                    rows=rows,
                    collection=runtime.collection,
                )
                if post_write.conflicting_count:
                    try:
                        _raise_if_conflicting(post_write)
                    except SourceEvidenceIngestionConflictError as conflict:
                        if add_error is not None:
                            raise conflict from add_error
                        raise
                if post_write.missing_count:
                    incomplete = SourceEvidenceIngestionIncompleteError(
                        "Source-bound Chroma ingestion is incomplete but recoverable.",
                        post_write,
                    )
                    if add_error is not None:
                        raise incomplete from add_error
                    raise incomplete
                if add_error is not None:
                    LOGGER.warning(
                        "Chroma add raised after all source-bound rows became exact for case %s "
                        "and source snapshot %s.",
                        manifest.case_id,
                        manifest.source_snapshot_id,
                    )
                return total_chunks
        except ChromaWriterLockError as exc:
            raise SourceEvidenceIngestionError(
                "The governed Chroma writer lock could not be acquired or released."
            ) from exc
    except (
        ValueError,
        TypeError,
        SourceEvidenceIngestionError,
    ):
        raise
    except Exception as exc:
        raise SourceEvidenceIngestionError(
            "Source-bound PDF ingestion could not be completed."
        ) from exc


__all__ = [
    "SourceBoundIndexDiagnostic",
    "SourceBoundIndexRowDiagnostic",
    "SourceBoundIndexRowState",
    "SourceEvidenceIngestionConflictError",
    "SourceEvidenceIngestionError",
    "SourceEvidenceIngestionIncompleteError",
    "index_case_pdf_source_bound",
    "inspect_source_bound_index",
]
