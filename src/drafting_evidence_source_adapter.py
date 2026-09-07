"""Exact immutable source reconstruction for governed Drafting evidence.

No semantic retrieval is performed here. The caller supplies evidence keys
already bounded by persisted R68 provenance and one explicitly governed
analytical element. This module resolves those keys through the immutable
source-evidence store and reconstructs the one-query-row input consumed by
the existing bounded governed-answer batcher.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Iterable
from uuid import UUID

from source_evidence.store import (
    SourceEvidenceStore,
    SourceEvidenceStoreError,
)


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DraftingEvidenceSourceError(ValueError):
    """Exact immutable Drafting evidence could not be established."""


@dataclass(frozen=True)
class DraftingEvidenceRow:
    case_id: str
    evidence_key: str
    evidence_binding_id: str
    source_document_instance_id: str
    source_snapshot_id: str
    document_name: str
    page: int
    chunk_ordinal: int
    bound_text_role: str
    original_blob_sha256: str
    page_text_sha256: str
    chunk_text_sha256: str
    exact_bound_text: str


def _required(value: object, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise DraftingEvidenceSourceError(f"{label} is required.")
    return text


def _canonical_uuid(value: object, label: str) -> str:
    text = _required(value, label)
    try:
        parsed = UUID(text)
    except ValueError as exc:
        raise DraftingEvidenceSourceError(
            f"{label} must be a UUID."
        ) from exc

    canonical = str(parsed)
    if text.lower() != canonical:
        raise DraftingEvidenceSourceError(
            f"{label} must use canonical UUID form."
        )
    return canonical


def _sha256_hex(value: object, label: str) -> str:
    text = _required(value, label).lower()
    if text.startswith("sha256:"):
        text = text[7:]

    if not _SHA256_RE.fullmatch(text):
        raise DraftingEvidenceSourceError(
            f"{label} must contain one SHA256 digest."
        )
    return text


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _enum_text(value: object, label: str) -> str:
    if hasattr(value, "value"):
        value = getattr(value, "value")
    return _required(value, label)


def _collection(value: object, label: str) -> tuple[object, ...]:
    if value is None:
        return ()

    if isinstance(value, (str, bytes)):
        raise DraftingEvidenceSourceError(
            f"{label} must be a collection."
        )

    try:
        return tuple(value)
    except TypeError as exc:
        raise DraftingEvidenceSourceError(
            f"{label} must be a collection."
        ) from exc


def generation_evidence_keys(
    *,
    retrieval_receipt: object,
    element: object,
) -> tuple[str, ...]:
    """Intersect original R68 answer scope with one governed element."""

    answer_scope = tuple(
        _required(key, "R68 answer-scope evidence key")
        for key in _collection(
            getattr(
                retrieval_receipt,
                "answer_scope_evidence_keys",
                (),
            ),
            "R68 answer_scope_evidence_keys",
        )
    )

    if not answer_scope:
        raise DraftingEvidenceSourceError(
            "R68 answer scope contains no evidence keys."
        )

    if len(answer_scope) != len(set(answer_scope)):
        raise DraftingEvidenceSourceError(
            "R68 answer scope contains duplicate evidence keys."
        )

    element_collections = (
        _collection(
            getattr(element, "supporting_evidence_keys", ()),
            "supporting_evidence_keys",
        ),
        _collection(
            getattr(element, "adverse_evidence_keys", ()),
            "adverse_evidence_keys",
        ),
        _collection(
            getattr(element, "corroborative_evidence_keys", ()),
            "corroborative_evidence_keys",
        ),
        _collection(
            getattr(element, "conflicting_evidence_keys", ()),
            "conflicting_evidence_keys",
        ),
    )

    governed_element_keys = {
        _required(key, "governed element evidence key")
        for collection in element_collections
        for key in collection
    }

    if not governed_element_keys:
        raise DraftingEvidenceSourceError(
            "governed element contains no evidence keys."
        )

    permitted = tuple(
        sorted(set(answer_scope) & governed_element_keys)
    )

    if not permitted:
        raise DraftingEvidenceSourceError(
            "R68 answer scope and governed element have no evidence intersection."
        )

    return permitted


def resolve_exact_evidence_row(
    *,
    case_id: str,
    evidence_key: str,
    store: SourceEvidenceStore | None = None,
) -> DraftingEvidenceRow:
    """Resolve one evidence key to its exact immutable governed chunk."""

    canonical_case_id = _canonical_uuid(
        case_id,
        "case_id",
    )
    key = _required(
        evidence_key,
        "evidence_key",
    )
    target_store = store if store is not None else SourceEvidenceStore()

    try:
        binding = target_store.load_evidence_binding(
            canonical_case_id,
            key,
        )
    except (SourceEvidenceStoreError, ValueError, TypeError) as exc:
        raise DraftingEvidenceSourceError(
            "immutable evidence binding could not be loaded."
        ) from exc

    if binding is None:
        raise DraftingEvidenceSourceError(
            "immutable evidence binding is absent."
        )

    binding_case_id = _canonical_uuid(
        getattr(binding, "case_id", ""),
        "binding.case_id",
    )
    binding_key = _required(
        getattr(binding, "evidence_key", ""),
        "binding.evidence_key",
    )

    if binding_case_id != canonical_case_id:
        raise DraftingEvidenceSourceError(
            "immutable evidence binding belongs to another case."
        )

    if binding_key != key:
        raise DraftingEvidenceSourceError(
            "immutable evidence binding has another evidence key."
        )

    chunk_id = _required(
        getattr(binding, "chunk_id", ""),
        "binding.chunk_id",
    )

    if chunk_id != key:
        raise DraftingEvidenceSourceError(
            "immutable binding chunk identity does not equal evidence key."
        )

    source_document_instance_id = _required(
        getattr(binding, "source_document_instance_id", ""),
        "binding.source_document_instance_id",
    )
    source_snapshot_id = _required(
        getattr(binding, "source_snapshot_id", ""),
        "binding.source_snapshot_id",
    )
    evidence_binding_id = _required(
        getattr(binding, "evidence_binding_id", ""),
        "binding.evidence_binding_id",
    )

    original_blob_sha256 = _sha256_hex(
        getattr(binding, "original_blob_sha256", ""),
        "binding.original_blob_sha256",
    )
    page_text_sha256 = _sha256_hex(
        getattr(binding, "page_text_sha256", ""),
        "binding.page_text_sha256",
    )
    chunk_text_sha256 = _sha256_hex(
        getattr(binding, "chunk_text_sha256", ""),
        "binding.chunk_text_sha256",
    )

    page_number = getattr(binding, "page", None)
    chunk_ordinal = getattr(binding, "chunk_ordinal", None)

    if (
        not isinstance(page_number, int)
        or isinstance(page_number, bool)
        or page_number < 1
    ):
        raise DraftingEvidenceSourceError(
            "binding.page must be a positive integer."
        )

    if (
        not isinstance(chunk_ordinal, int)
        or isinstance(chunk_ordinal, bool)
        or chunk_ordinal < 0
    ):
        raise DraftingEvidenceSourceError(
            "binding.chunk_ordinal must be a non-negative integer."
        )

    bound_text_role = _enum_text(
        getattr(binding, "bound_text_role", ""),
        "binding.bound_text_role",
    )

    try:
        manifest = target_store.load_document_manifest(
            canonical_case_id,
            source_document_instance_id,
        )
    except (
        SourceEvidenceStoreError,
        ValueError,
        TypeError,
        UnicodeDecodeError,
    ) as exc:
        raise DraftingEvidenceSourceError(
            "immutable source document manifest could not be loaded."
        ) from exc

    manifest_source_id = getattr(
        manifest,
        "source_document_instance_id",
        None,
    )

    if (
        manifest_source_id is not None
        and str(manifest_source_id) != source_document_instance_id
    ):
        raise DraftingEvidenceSourceError(
            "immutable source manifest identity does not match binding."
        )

    manifest_original_sha = getattr(
        manifest,
        "original_blob_sha256",
        None,
    )

    if manifest_original_sha is not None:
        if (
            _sha256_hex(
                manifest_original_sha,
                "manifest.original_blob_sha256",
            )
            != original_blob_sha256
        ):
            raise DraftingEvidenceSourceError(
                "original source SHA does not match immutable binding."
            )

    pages = tuple(
        item
        for item in _collection(
            getattr(manifest, "pages", ()),
            "manifest.pages",
        )
        if getattr(item, "page_number", None) == page_number
    )

    if len(pages) != 1:
        raise DraftingEvidenceSourceError(
            "binding page is not uniquely present in immutable source manifest."
        )

    page = pages[0]

    manifest_page_sha = _sha256_hex(
        getattr(page, "page_text_sha256", ""),
        "manifest page_text_sha256",
    )

    if manifest_page_sha != page_text_sha256:
        raise DraftingEvidenceSourceError(
            "page-text SHA does not match immutable binding."
        )

    chunks = tuple(
        item
        for item in _collection(
            getattr(page, "chunk_snapshots", ()),
            "page.chunk_snapshots",
        )
        if getattr(item, "chunk_ordinal", None) == chunk_ordinal
    )

    if len(chunks) != 1:
        raise DraftingEvidenceSourceError(
            "binding chunk ordinal is not uniquely present."
        )

    chunk = chunks[0]

    if (
        _required(
            getattr(chunk, "evidence_key", ""),
            "chunk.evidence_key",
        )
        != key
    ):
        raise DraftingEvidenceSourceError(
            "immutable chunk evidence key does not match requested key."
        )

    if (
        _required(
            getattr(chunk, "chunk_id", ""),
            "chunk.chunk_id",
        )
        != key
    ):
        raise DraftingEvidenceSourceError(
            "immutable chunk ID does not match requested evidence key."
        )

    manifest_chunk_sha = _sha256_hex(
        getattr(chunk, "chunk_text_sha256", ""),
        "chunk.chunk_text_sha256",
    )

    if manifest_chunk_sha != chunk_text_sha256:
        raise DraftingEvidenceSourceError(
            "chunk-text SHA does not match immutable binding."
        )

    try:
        page_bytes = target_store.read_blob(page_text_sha256)
        chunk_bytes = target_store.read_blob(chunk_text_sha256)
    except (
        SourceEvidenceStoreError,
        ValueError,
        TypeError,
    ) as exc:
        raise DraftingEvidenceSourceError(
            "immutable source blob could not be read."
        ) from exc

    page_byte_length = getattr(
        page,
        "page_text_byte_length",
        None,
    )

    if (
        page_byte_length is not None
        and len(page_bytes) != page_byte_length
    ):
        raise DraftingEvidenceSourceError(
            "page-text byte length does not match immutable manifest."
        )

    chunk_byte_length = getattr(
        chunk,
        "chunk_text_byte_length",
        None,
    )

    if (
        chunk_byte_length is not None
        and len(chunk_bytes) != chunk_byte_length
    ):
        raise DraftingEvidenceSourceError(
            "chunk-text byte length does not match immutable manifest."
        )

    if _digest(page_bytes) != page_text_sha256:
        raise DraftingEvidenceSourceError(
            "page-text content SHA does not match immutable identity."
        )

    if _digest(chunk_bytes) != chunk_text_sha256:
        raise DraftingEvidenceSourceError(
            "chunk-text content SHA does not match immutable identity."
        )

    try:
        exact_bound_text = chunk_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DraftingEvidenceSourceError(
            "immutable chunk text is not valid UTF-8."
        ) from exc

    if not exact_bound_text.strip():
        raise DraftingEvidenceSourceError(
            "immutable chunk text is empty."
        )

    manifest_name = _required(
        getattr(manifest, "original_filename", ""),
        "manifest.original_filename",
    )

    binding_name = getattr(
        binding,
        "document_name",
        None,
    )

    if binding_name is not None and str(binding_name).strip():
        if str(binding_name).strip() != manifest_name:
            raise DraftingEvidenceSourceError(
                "binding document name does not match immutable manifest."
            )

    return DraftingEvidenceRow(
        case_id=canonical_case_id,
        evidence_key=key,
        evidence_binding_id=evidence_binding_id,
        source_document_instance_id=source_document_instance_id,
        source_snapshot_id=source_snapshot_id,
        document_name=manifest_name,
        page=page_number,
        chunk_ordinal=chunk_ordinal,
        bound_text_role=bound_text_role,
        original_blob_sha256=original_blob_sha256,
        page_text_sha256=page_text_sha256,
        chunk_text_sha256=chunk_text_sha256,
        exact_bound_text=exact_bound_text,
    )


def resolve_exact_evidence_rows(
    *,
    case_id: str,
    evidence_keys: Iterable[str],
    store: SourceEvidenceStore | None = None,
) -> tuple[DraftingEvidenceRow, ...]:
    """Resolve a unique evidence-key collection in canonical key order."""

    if isinstance(evidence_keys, (str, bytes)):
        raise DraftingEvidenceSourceError(
            "evidence_keys must be a collection."
        )

    keys = tuple(
        _required(key, "evidence_key")
        for key in evidence_keys
    )

    if not keys:
        raise DraftingEvidenceSourceError(
            "at least one evidence key is required."
        )

    if len(keys) != len(set(keys)):
        raise DraftingEvidenceSourceError(
            "evidence keys must be unique."
        )

    target_store = store if store is not None else SourceEvidenceStore()

    return tuple(
        resolve_exact_evidence_row(
            case_id=case_id,
            evidence_key=key,
            store=target_store,
        )
        for key in sorted(keys)
    )


def build_bounded_enriched_results(
    rows: Iterable[DraftingEvidenceRow],
) -> dict[str, list[list[object]]]:
    """Build the exact one-query-row contract consumed by bounded batching."""

    if isinstance(rows, (str, bytes)):
        raise DraftingEvidenceSourceError(
            "rows must be a collection."
        )

    materialized = tuple(rows)

    if not materialized:
        raise DraftingEvidenceSourceError(
            "at least one immutable evidence row is required."
        )

    if not all(
        isinstance(row, DraftingEvidenceRow)
        for row in materialized
    ):
        raise DraftingEvidenceSourceError(
            "rows must contain only DraftingEvidenceRow values."
        )

    case_ids = {
        row.case_id
        for row in materialized
    }

    if len(case_ids) != 1:
        raise DraftingEvidenceSourceError(
            "bounded evidence rows must belong to one case."
        )

    evidence_keys = tuple(
        row.evidence_key
        for row in materialized
    )

    if len(evidence_keys) != len(set(evidence_keys)):
        raise DraftingEvidenceSourceError(
            "bounded evidence rows contain duplicate evidence keys."
        )

    ordered = tuple(
        sorted(
            materialized,
            key=lambda row: row.evidence_key,
        )
    )

    ids = [
        row.evidence_key
        for row in ordered
    ]

    documents = [
        row.exact_bound_text
        for row in ordered
    ]

    metadatas = [
        {
            "file": row.document_name,
            "page": row.page,
            "source_document_instance_id":
                row.source_document_instance_id,
            "drafting_bound_text_role":
                row.bound_text_role,
            "drafting_chunk_ordinal":
                row.chunk_ordinal,
            "drafting_chunk_text_sha256":
                row.chunk_text_sha256,
            "drafting_evidence_binding_id":
                row.evidence_binding_id,
        }
        for row in ordered
    ]

    return {
        "ids": [ids],
        "documents": [documents],
        "metadatas": [metadatas],
    }


def reconstruct_bounded_generation_evidence(
    *,
    case_id: str,
    retrieval_receipt: object,
    element: object,
    store: SourceEvidenceStore | None = None,
) -> tuple[
    tuple[str, ...],
    tuple[DraftingEvidenceRow, ...],
    dict[str, list[list[object]]],
]:
    """Reconstruct exact R68-and-element-bounded immutable evidence."""

    keys = generation_evidence_keys(
        retrieval_receipt=retrieval_receipt,
        element=element,
    )

    rows = resolve_exact_evidence_rows(
        case_id=case_id,
        evidence_keys=keys,
        store=store,
    )

    enriched_results = build_bounded_enriched_results(
        rows
    )

    return (
        keys,
        rows,
        enriched_results,
    )


__all__ = [
    "DraftingEvidenceSourceError",
    "DraftingEvidenceRow",
    "generation_evidence_keys",
    "resolve_exact_evidence_row",
    "resolve_exact_evidence_rows",
    "build_bounded_enriched_results",
    "reconstruct_bounded_generation_evidence",
]