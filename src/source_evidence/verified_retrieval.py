"""Deterministic verification of source-bound structured-analysis retrieval.

This module verifies that every candidate admitted across the structured legal-
analysis retrieval boundary resolves to the frozen immutable source-evidence
chain.  It does not alter retrieval ranking, metadata, analytical semantics, or
source content.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .identity import (
    canonical_uuid,
    derive_sha256_id,
    validate_sha256_hex,
    validate_sha256_id,
)
from .models import (
    SOURCE_BOUND_ANALYSIS_RECEIPT_SCHEMA_VERSION,
    SOURCE_BOUND_RETRIEVAL_VERIFIER_VERSION,
    BindingClass,
    BoundTextRole,
    EvidenceBinding,
    SourceBoundAnalysisReceipt,
    SourceDocumentManifest,
    VerifiedEvidenceUse,
)
from .serialization import source_bound_analysis_receipt_identity_payload_to_dict
from .store import SourceEvidenceStore
from .validation import (
    validate_evidence_binding,
    validate_source_bound_analysis_receipt,
    validate_source_document_manifest,
)

_REQUIRED_SOURCE_METADATA = (
    "source_evidence_binding_id",
    "source_snapshot_id",
    "source_document_instance_id",
    "source_chunk_sha256",
    "source_page_text_sha256",
    "source_original_blob_sha256",
    "source_binding_class",
)
_REQUIRED_NAVIGATION_METADATA = ("case_id", "file", "page", "chunk")


class SourceBoundRetrievalVerificationError(RuntimeError):
    """Raised when a structured-analysis retrieval result cannot be source-verified."""


def build_singleton_analysis_receipt(
    *,
    case_id: str,
    evidence_key: str,
    evidence_binding_id: str,
    chunk_text_sha256: str,
) -> SourceBoundAnalysisReceipt:
    """Build one deterministic receipt for one verified candidate row.

    The receipt proves only that the exact candidate passed the frozen v1
    source-bound retrieval verifier and was admitted across the structured
    legal-analysis retrieval boundary.  It does not prove mapper relevance,
    analytical completion, projection membership, or report use.
    """

    try:
        canonical_case_id = canonical_uuid(case_id, field_name="case_id")
        if not isinstance(evidence_key, str) or not evidence_key:
            raise ValueError("evidence_key must not be empty.")
        validate_sha256_id(evidence_binding_id, field_name="evidence_binding_id")
        validate_sha256_hex(chunk_text_sha256, field_name="chunk_text_sha256")

        verified_use = VerifiedEvidenceUse(
            evidence_key=evidence_key,
            evidence_binding_id=evidence_binding_id,
            chunk_text_sha256=chunk_text_sha256,
        )
        provisional = SourceBoundAnalysisReceipt(
            schema_version=SOURCE_BOUND_ANALYSIS_RECEIPT_SCHEMA_VERSION,
            case_id=canonical_case_id,
            verifier_version=SOURCE_BOUND_RETRIEVAL_VERIFIER_VERSION,
            verified_evidence=(verified_use,),
            source_bound_analysis_receipt_id="sha256:" + ("0" * 64),
        )
        receipt = replace(
            provisional,
            source_bound_analysis_receipt_id=derive_sha256_id(
                source_bound_analysis_receipt_identity_payload_to_dict(provisional)
            ),
        )
        validate_source_bound_analysis_receipt(receipt)
        if len(receipt.verified_evidence) != 1:
            raise ValueError("M5 receipts must contain exactly one verified evidence use.")
        return receipt
    except SourceBoundRetrievalVerificationError:
        raise
    except Exception as exc:
        raise SourceBoundRetrievalVerificationError(
            "Unable to build a canonical singleton source-bound analysis receipt."
        ) from exc


def verify_source_bound_retrieval_results(
    results: dict[str, object],
    *,
    case_id: str,
    store: SourceEvidenceStore | None = None,
) -> dict[str, object]:
    """Verify every final structured-analysis candidate against immutable source evidence.

    Verification is fail-closed.  The full candidate batch is verified before
    any singleton receipt is published.  On success the original retrieval
    dictionary is returned without mutation, reordering, filtering, or receipt
    metadata injection.
    """

    try:
        canonical_case_id = canonical_uuid(case_id, field_name="case_id")
        rows = _parse_single_query_result(results)
        if not rows:
            return results

        target_store = store if store is not None else SourceEvidenceStore()
        caches = _VerificationCaches()
        receipts: list[SourceBoundAnalysisReceipt] = []

        for row_id, document, metadata in rows:
            binding = _verified_binding(
                target_store,
                canonical_case_id,
                row_id,
                metadata,
                caches,
            )
            manifest = _verified_manifest(
                target_store,
                canonical_case_id,
                binding,
                caches,
            )
            _verify_full_chain_text(
                target_store,
                row_id,
                document,
                metadata,
                binding,
                manifest,
                caches,
            )
            receipts.append(
                build_singleton_analysis_receipt(
                    case_id=canonical_case_id,
                    evidence_key=row_id,
                    evidence_binding_id=binding.evidence_binding_id,
                    chunk_text_sha256=_required_binding_text(
                        binding.chunk_text_sha256,
                        field_name="chunk_text_sha256",
                    ),
                )
            )

        for receipt in receipts:
            target_store.publish_analysis_receipt(receipt)

        return results
    except SourceBoundRetrievalVerificationError:
        raise
    except Exception as exc:
        raise SourceBoundRetrievalVerificationError(
            "Source-bound structured-analysis retrieval verification failed."
        ) from exc


class _VerificationCaches:
    """Per-call immutable verification caches."""

    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}
        self.bindings: dict[tuple[str, str], EvidenceBinding] = {}
        self.manifests: dict[tuple[str, str], SourceDocumentManifest] = {}


def _parse_single_query_result(
    results: dict[str, object],
) -> tuple[tuple[str, str, dict[str, Any]], ...]:
    if not isinstance(results, dict):
        raise SourceBoundRetrievalVerificationError("Retrieval result must be a dictionary.")

    outer_rows: list[list[object]] = []
    for name in ("ids", "documents", "metadatas"):
        value = results.get(name)
        if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], list):
            raise SourceBoundRetrievalVerificationError(
                f"Retrieval result {name!r} must contain exactly one query row."
            )
        outer_rows.append(value[0])

    ids, documents, metadatas = outer_rows
    if not (len(ids) == len(documents) == len(metadatas)):
        raise SourceBoundRetrievalVerificationError(
            "Retrieval result IDs, documents, and metadatas must have equal candidate counts."
        )

    seen_ids: set[str] = set()
    parsed: list[tuple[str, str, dict[str, Any]]] = []
    for index, (row_id, document, metadata) in enumerate(zip(ids, documents, metadatas)):
        if not isinstance(row_id, str) or not row_id:
            raise SourceBoundRetrievalVerificationError(
                f"Retrieval candidate {index} has an invalid evidence ID."
            )
        if row_id in seen_ids:
            raise SourceBoundRetrievalVerificationError("Retrieval result contains a duplicate evidence ID.")
        seen_ids.add(row_id)
        if not isinstance(document, str):
            raise SourceBoundRetrievalVerificationError(
                f"Retrieval candidate {row_id!r} document must be text."
            )
        if not isinstance(metadata, dict):
            raise SourceBoundRetrievalVerificationError(
                f"Retrieval candidate {row_id!r} metadata must be a dictionary."
            )
        parsed.append((row_id, document, metadata))
    return tuple(parsed)


def _verified_binding(
    store: SourceEvidenceStore,
    case_id: str,
    row_id: str,
    metadata: dict[str, Any],
    caches: _VerificationCaches,
) -> EvidenceBinding:
    _require_metadata_shape(metadata, row_id=row_id)
    if metadata["case_id"] != case_id:
        raise SourceBoundRetrievalVerificationError(
            f"Retrieval candidate {row_id!r} does not belong to the requested case."
        )

    cache_key = (case_id, row_id)
    binding = caches.bindings.get(cache_key)
    if binding is None:
        binding = store.load_evidence_binding(case_id, row_id)
        if binding is None:
            raise SourceBoundRetrievalVerificationError(
                f"Retrieval candidate {row_id!r} has no immutable evidence binding."
            )
        validate_evidence_binding(binding)
        caches.bindings[cache_key] = binding

    if binding.case_id != case_id:
        raise SourceBoundRetrievalVerificationError(
            f"Retrieval candidate {row_id!r} binding case does not match the request."
        )
    if binding.evidence_key != row_id or binding.chunk_id != row_id:
        raise SourceBoundRetrievalVerificationError(
            f"Retrieval candidate {row_id!r} does not match its binding navigation identity."
        )
    if binding.binding_class is not BindingClass.FULL_CHAIN_BOUND:
        raise SourceBoundRetrievalVerificationError(
            f"Retrieval candidate {row_id!r} is not FULL_CHAIN_BOUND."
        )
    if binding.bound_text_role is not BoundTextRole.CHUNK_TEXT:
        raise SourceBoundRetrievalVerificationError(
            f"Retrieval candidate {row_id!r} is not bound to chunk text."
        )

    expected_metadata = {
        "source_evidence_binding_id": binding.evidence_binding_id,
        "source_snapshot_id": _required_binding_text(binding.source_snapshot_id, field_name="source_snapshot_id"),
        "source_document_instance_id": _required_binding_text(
            binding.source_document_instance_id,
            field_name="source_document_instance_id",
        ),
        "source_chunk_sha256": _required_binding_text(binding.chunk_text_sha256, field_name="chunk_text_sha256"),
        "source_page_text_sha256": _required_binding_text(
            binding.page_text_sha256,
            field_name="page_text_sha256",
        ),
        "source_original_blob_sha256": _required_binding_text(
            binding.original_blob_sha256,
            field_name="original_blob_sha256",
        ),
        "source_binding_class": BindingClass.FULL_CHAIN_BOUND.value,
        "file": binding.document_name,
        "page": _required_binding_int(binding.page, field_name="page"),
        "chunk": _required_binding_int(binding.chunk_ordinal, field_name="chunk_ordinal"),
    }
    for name, expected in expected_metadata.items():
        if type(metadata[name]) is not type(expected) or metadata[name] != expected:
            raise SourceBoundRetrievalVerificationError(
                f"Retrieval candidate {row_id!r} metadata field {name!r} does not match immutable binding."
            )
    return binding


def _require_metadata_shape(metadata: dict[str, Any], *, row_id: str) -> None:
    for name in (*_REQUIRED_NAVIGATION_METADATA, *_REQUIRED_SOURCE_METADATA):
        if name not in metadata:
            raise SourceBoundRetrievalVerificationError(
                f"Retrieval candidate {row_id!r} is missing required metadata field {name!r}."
            )
    for name in (
        "case_id",
        "file",
        "source_evidence_binding_id",
        "source_snapshot_id",
        "source_document_instance_id",
        "source_chunk_sha256",
        "source_page_text_sha256",
        "source_original_blob_sha256",
        "source_binding_class",
    ):
        if not isinstance(metadata[name], str) or not metadata[name]:
            raise SourceBoundRetrievalVerificationError(
                f"Retrieval candidate {row_id!r} metadata field {name!r} must be non-empty text."
            )
    if type(metadata["page"]) is not int or metadata["page"] < 1:
        raise SourceBoundRetrievalVerificationError(
            f"Retrieval candidate {row_id!r} metadata page is invalid."
        )
    if type(metadata["chunk"]) is not int or metadata["chunk"] < 0:
        raise SourceBoundRetrievalVerificationError(
            f"Retrieval candidate {row_id!r} metadata chunk is invalid."
        )


def _verified_manifest(
    store: SourceEvidenceStore,
    case_id: str,
    binding: EvidenceBinding,
    caches: _VerificationCaches,
) -> SourceDocumentManifest:
    document_id = _required_binding_text(
        binding.source_document_instance_id,
        field_name="source_document_instance_id",
    )
    cache_key = (case_id, document_id)
    manifest = caches.manifests.get(cache_key)
    if manifest is None:
        manifest = store.load_document_manifest(case_id, document_id)
        validate_source_document_manifest(manifest)
        caches.manifests[cache_key] = manifest

    expected = {
        "case_id": case_id,
        "source_document_instance_id": document_id,
        "source_snapshot_id": _required_binding_text(binding.source_snapshot_id, field_name="source_snapshot_id"),
        "original_filename": binding.document_name,
        "original_blob_sha256": _required_binding_text(
            binding.original_blob_sha256,
            field_name="original_blob_sha256",
        ),
    }
    for name, expected_value in expected.items():
        if getattr(manifest, name) != expected_value:
            raise SourceBoundRetrievalVerificationError(
                f"Source manifest field {name!r} does not match the retrieval binding."
            )
    if manifest.extraction_profile.profile_id != binding.extraction_profile_id:
        raise SourceBoundRetrievalVerificationError(
            "Source manifest extraction profile does not match the retrieval binding."
        )
    if manifest.chunking_profile.profile_id != binding.chunking_profile_id:
        raise SourceBoundRetrievalVerificationError(
            "Source manifest chunking profile does not match the retrieval binding."
        )
    return manifest


def _verify_full_chain_text(
    store: SourceEvidenceStore,
    row_id: str,
    document: str,
    metadata: dict[str, Any],
    binding: EvidenceBinding,
    manifest: SourceDocumentManifest,
    caches: _VerificationCaches,
) -> None:
    page_number = _required_binding_int(binding.page, field_name="page")
    chunk_ordinal = _required_binding_int(binding.chunk_ordinal, field_name="chunk_ordinal")

    pages = [page for page in manifest.pages if page.page_number == page_number]
    if len(pages) != 1:
        raise SourceBoundRetrievalVerificationError(
            f"Retrieval candidate {row_id!r} does not resolve to exactly one manifest page."
        )
    page = pages[0]
    if page.page_text_sha256 != binding.page_text_sha256:
        raise SourceBoundRetrievalVerificationError(
            f"Retrieval candidate {row_id!r} page hash does not match its binding."
        )

    chunks = [chunk for chunk in page.chunk_snapshots if chunk.chunk_ordinal == chunk_ordinal]
    if len(chunks) != 1:
        raise SourceBoundRetrievalVerificationError(
            f"Retrieval candidate {row_id!r} does not resolve to exactly one manifest chunk."
        )
    chunk = chunks[0]
    if chunk.chunk_id != row_id or chunk.evidence_key != row_id:
        raise SourceBoundRetrievalVerificationError(
            f"Retrieval candidate {row_id!r} does not match its manifest chunk identity."
        )
    if chunk.chunk_text_sha256 != binding.chunk_text_sha256:
        raise SourceBoundRetrievalVerificationError(
            f"Retrieval candidate {row_id!r} chunk hash does not match its binding."
        )

    original_bytes = _read_blob_cached(store, manifest.original_blob_sha256, caches)
    if len(original_bytes) != manifest.original_byte_length:
        raise SourceBoundRetrievalVerificationError("Original immutable PDF blob length is invalid.")

    page_bytes = _read_blob_cached(store, page.page_text_sha256, caches)
    if len(page_bytes) != page.page_text_byte_length:
        raise SourceBoundRetrievalVerificationError("Immutable page-text blob length is invalid.")
    try:
        page_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SourceBoundRetrievalVerificationError("Immutable page-text blob is not strict UTF-8.") from exc

    chunk_bytes = _read_blob_cached(store, chunk.chunk_text_sha256, caches)
    if len(chunk_bytes) != chunk.chunk_text_byte_length:
        raise SourceBoundRetrievalVerificationError("Immutable chunk-text blob length is invalid.")
    try:
        immutable_chunk_text = chunk_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SourceBoundRetrievalVerificationError("Immutable chunk-text blob is not strict UTF-8.") from exc

    if document != immutable_chunk_text:
        raise SourceBoundRetrievalVerificationError(
            f"Retrieval candidate {row_id!r} text does not exactly match immutable chunk bytes."
        )

    if metadata["source_chunk_sha256"] != chunk.chunk_text_sha256:
        raise SourceBoundRetrievalVerificationError(
            f"Retrieval candidate {row_id!r} metadata chunk hash does not match its manifest chunk."
        )
    if metadata["source_page_text_sha256"] != page.page_text_sha256:
        raise SourceBoundRetrievalVerificationError(
            f"Retrieval candidate {row_id!r} metadata page hash does not match its manifest page."
        )
    if metadata["source_original_blob_sha256"] != manifest.original_blob_sha256:
        raise SourceBoundRetrievalVerificationError(
            f"Retrieval candidate {row_id!r} metadata original hash does not match its manifest."
        )


def _read_blob_cached(
    store: SourceEvidenceStore,
    digest: str,
    caches: _VerificationCaches,
) -> bytes:
    value = caches.blobs.get(digest)
    if value is None:
        value = store.read_blob(digest)
        caches.blobs[digest] = value
    return value


def _required_binding_text(value: str | None, *, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise SourceBoundRetrievalVerificationError(
            f"FULL_CHAIN binding field {field_name!r} is missing or invalid."
        )
    return value


def _required_binding_int(value: int | None, *, field_name: str) -> int:
    if type(value) is not int:
        raise SourceBoundRetrievalVerificationError(
            f"FULL_CHAIN binding field {field_name!r} is missing or invalid."
        )
    return value


__all__ = [
    "SourceBoundRetrievalVerificationError",
    "build_singleton_analysis_receipt",
    "verify_source_bound_retrieval_results",
]
