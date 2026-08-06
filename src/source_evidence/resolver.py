"""Read-only projection-bound resolution of immutable source evidence.

This module consumes the stored M6 projection-binding manifest as the frozen
projection-to-source authority. It never rebuilds projection binding from
current state and never consults Chroma, current PDFs, OCR, retrieval, or the
analytical engine.
"""

from __future__ import annotations

from dataclasses import dataclass

from case_reporting.models import CaseReportProjection, CitationRecord
from case_reporting.validation import validate_case_report_projection

from .identity import canonical_uuid
from .models import (
    BindingClass,
    BoundTextRole,
    ExtractionMethod,
    ProjectionBindingCoverage,
    ProjectionBindingEntry,
    ProjectionEvidenceBindingManifest,
    EvidenceBinding,
    SourceDocumentManifest,
)
from .store import SourceEvidenceStore, SourceEvidenceStoreError
from .validation import (
    validate_evidence_binding,
    validate_projection_evidence_binding_manifest,
    validate_source_document_manifest,
)
from .verified_retrieval import build_singleton_analysis_receipt


class SourceEvidenceResolverError(RuntimeError):
    """Raised when projection-bound source evidence cannot be trusted."""


@dataclass(frozen=True, slots=True)
class ResolvedSourceEvidence:
    """Transient, read-only source material resolved for one projection citation."""

    case_id: str
    report_projection_id: str
    projection_evidence_binding_manifest_id: str
    projection_binding_coverage: ProjectionBindingCoverage
    citation_id: str
    evidence_key: str
    binding_class: BindingClass
    evidence_binding_id: str | None
    source_bound_analysis_receipt_id: str | None
    document_name: str
    document_id: str | None
    page: int | None
    chunk_id: str | None
    chunk_ordinal: int | None
    source_document_instance_id: str | None
    source_snapshot_id: str | None
    bound_text_role: BoundTextRole | None
    bound_text_sha256: str | None
    original_blob_sha256: str | None
    page_text_sha256: str | None
    chunk_text_sha256: str | None
    extraction_profile_id: str | None
    chunking_profile_id: str | None
    extraction_method: ExtractionMethod | None
    exact_bound_text: str | None
    exact_page_text: str | None
    original_pdf_bytes: bytes | None
    original_filename: str | None


def _decode_utf8(content: bytes, *, field_name: str) -> str:
    try:
        return content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SourceEvidenceResolverError(
            f"{field_name} is not valid UTF-8 immutable source text."
        ) from exc


def _find_citation(projection: CaseReportProjection, citation_id: str) -> CitationRecord:
    if not isinstance(citation_id, str) or not citation_id:
        raise SourceEvidenceResolverError("citation_id must identify one projection citation.")
    matches = tuple(item for item in projection.citations if item.citation_id == citation_id)
    if len(matches) != 1:
        raise SourceEvidenceResolverError(
            "The requested citation is not uniquely present in the validated projection."
        )
    return matches[0]


def _validate_projection_binding(
    projection: CaseReportProjection,
    manifest: ProjectionEvidenceBindingManifest,
) -> None:
    validate_projection_evidence_binding_manifest(manifest)
    expected_case = projection.case_header.case_id
    if manifest.case_id != expected_case:
        raise SourceEvidenceResolverError("Projection binding case identity does not match projection.")
    if manifest.report_projection_id != projection.report_projection_id:
        raise SourceEvidenceResolverError("Projection binding report identity does not match projection.")
    if manifest.projection_payload_sha256 != projection.projection_payload_sha256:
        raise SourceEvidenceResolverError("Projection binding payload identity does not match projection.")
    if manifest.manifest_id != projection.manifest.manifest_id:
        raise SourceEvidenceResolverError("Projection binding report-manifest identity does not match projection.")

    expected = tuple((item.citation_id, item.evidence_key) for item in projection.citations)
    actual = tuple((item.citation_id, item.evidence_key) for item in manifest.entries)
    if actual != expected:
        raise SourceEvidenceResolverError(
            "Projection binding citation inventory does not exactly match the projection."
        )


def _find_entry(
    manifest: ProjectionEvidenceBindingManifest,
    citation: CitationRecord,
) -> ProjectionBindingEntry:
    matches = tuple(
        item
        for item in manifest.entries
        if item.citation_id == citation.citation_id and item.evidence_key == citation.evidence_key
    )
    if len(matches) != 1:
        raise SourceEvidenceResolverError(
            "The selected projection citation has no unique projection-binding entry."
        )
    return matches[0]


def _validate_binding_compatibility(
    *,
    case_id: str,
    citation: CitationRecord,
    entry: ProjectionBindingEntry,
    binding: EvidenceBinding,
) -> None:
    validate_evidence_binding(binding)
    if binding.case_id != case_id or binding.evidence_key != citation.evidence_key:
        raise SourceEvidenceResolverError("Evidence binding identity does not match the selected citation.")
    if entry.binding_class is not binding.binding_class:
        raise SourceEvidenceResolverError("Projection binding class does not match the evidence binding.")
    if entry.evidence_binding_id != binding.evidence_binding_id:
        raise SourceEvidenceResolverError("Projection binding ID does not match the evidence binding.")
    if binding.document_name != citation.document_name:
        raise SourceEvidenceResolverError("Evidence binding document name does not match the citation.")
    if binding.document_id is not None and binding.document_id != citation.document_id:
        raise SourceEvidenceResolverError("Evidence binding document ID does not match the citation.")
    if binding.page is not None and binding.page != citation.page:
        raise SourceEvidenceResolverError("Evidence binding page does not match the citation.")
    if binding.chunk_id is not None and binding.chunk_id != citation.chunk_id:
        raise SourceEvidenceResolverError("Evidence binding chunk ID does not match the citation.")


def _base_resolution(
    *,
    projection: CaseReportProjection,
    manifest: ProjectionEvidenceBindingManifest,
    citation: CitationRecord,
    entry: ProjectionBindingEntry,
    binding: EvidenceBinding | None,
    exact_bound_text: str | None = None,
    exact_page_text: str | None = None,
    original_pdf_bytes: bytes | None = None,
    original_filename: str | None = None,
    extraction_method: ExtractionMethod | None = None,
) -> ResolvedSourceEvidence:
    return ResolvedSourceEvidence(
        case_id=projection.case_header.case_id,
        report_projection_id=projection.report_projection_id,
        projection_evidence_binding_manifest_id=manifest.projection_evidence_binding_manifest_id,
        projection_binding_coverage=manifest.coverage,
        citation_id=citation.citation_id,
        evidence_key=citation.evidence_key,
        binding_class=entry.binding_class,
        evidence_binding_id=entry.evidence_binding_id,
        source_bound_analysis_receipt_id=entry.source_bound_analysis_receipt_id,
        document_name=citation.document_name,
        document_id=citation.document_id,
        page=citation.page,
        chunk_id=citation.chunk_id,
        chunk_ordinal=binding.chunk_ordinal if binding is not None else None,
        source_document_instance_id=(
            binding.source_document_instance_id if binding is not None else None
        ),
        source_snapshot_id=binding.source_snapshot_id if binding is not None else None,
        bound_text_role=binding.bound_text_role if binding is not None else None,
        bound_text_sha256=binding.bound_text_sha256 if binding is not None else None,
        original_blob_sha256=binding.original_blob_sha256 if binding is not None else None,
        page_text_sha256=binding.page_text_sha256 if binding is not None else None,
        chunk_text_sha256=binding.chunk_text_sha256 if binding is not None else None,
        extraction_profile_id=(binding.extraction_profile_id if binding is not None else None),
        chunking_profile_id=binding.chunking_profile_id if binding is not None else None,
        extraction_method=extraction_method,
        exact_bound_text=exact_bound_text,
        exact_page_text=exact_page_text,
        original_pdf_bytes=original_pdf_bytes,
        original_filename=original_filename,
    )


def _resolve_weaker_binding(
    *,
    projection: CaseReportProjection,
    manifest: ProjectionEvidenceBindingManifest,
    citation: CitationRecord,
    entry: ProjectionBindingEntry,
    binding: EvidenceBinding,
    store: SourceEvidenceStore,
) -> ResolvedSourceEvidence:
    if entry.source_bound_analysis_receipt_id is not None:
        raise SourceEvidenceResolverError("Weaker projection binding must not carry an M5 receipt.")
    content = store.read_blob(binding.bound_text_sha256)
    text = _decode_utf8(content, field_name="bound_text")
    return _base_resolution(
        projection=projection,
        manifest=manifest,
        citation=citation,
        entry=entry,
        binding=binding,
        exact_bound_text=text,
    )


def _validate_source_manifest(
    *,
    case_id: str,
    binding: EvidenceBinding,
    manifest: SourceDocumentManifest,
) -> None:
    validate_source_document_manifest(manifest)
    if manifest.case_id != case_id:
        raise SourceEvidenceResolverError("Source manifest case identity does not match.")
    if manifest.source_document_instance_id != binding.source_document_instance_id:
        raise SourceEvidenceResolverError("Source manifest document instance does not match binding.")
    if manifest.source_snapshot_id != binding.source_snapshot_id:
        raise SourceEvidenceResolverError("Source manifest snapshot identity does not match binding.")
    if manifest.original_filename != binding.document_name:
        raise SourceEvidenceResolverError("Source manifest filename does not match binding.")
    if manifest.original_blob_sha256 != binding.original_blob_sha256:
        raise SourceEvidenceResolverError("Source manifest original SHA does not match binding.")
    if manifest.extraction_profile.profile_id != binding.extraction_profile_id:
        raise SourceEvidenceResolverError("Source manifest extraction profile does not match binding.")
    if manifest.chunking_profile.profile_id != binding.chunking_profile_id:
        raise SourceEvidenceResolverError("Source manifest chunking profile does not match binding.")


def _resolve_full_chain(
    *,
    projection: CaseReportProjection,
    manifest: ProjectionEvidenceBindingManifest,
    citation: CitationRecord,
    entry: ProjectionBindingEntry,
    binding: EvidenceBinding,
    store: SourceEvidenceStore,
) -> ResolvedSourceEvidence:
    if (
        entry.source_bound_analysis_receipt_id is None
        or binding.chunk_text_sha256 is None
        or binding.source_document_instance_id is None
        or binding.source_snapshot_id is None
        or binding.original_blob_sha256 is None
        or binding.page_text_sha256 is None
        or binding.page is None
        or binding.chunk_ordinal is None
    ):
        raise SourceEvidenceResolverError("FULL_CHAIN binding is missing required frozen coordinates.")

    expected_receipt = build_singleton_analysis_receipt(
        case_id=projection.case_header.case_id,
        evidence_key=citation.evidence_key,
        evidence_binding_id=binding.evidence_binding_id,
        chunk_text_sha256=binding.chunk_text_sha256,
    )
    if (
        entry.source_bound_analysis_receipt_id
        != expected_receipt.source_bound_analysis_receipt_id
    ):
        raise SourceEvidenceResolverError("Projection receipt ID does not match frozen M5 identity.")
    stored_receipt = store.load_analysis_receipt(
        projection.case_header.case_id,
        entry.source_bound_analysis_receipt_id,
    )
    if stored_receipt != expected_receipt:
        raise SourceEvidenceResolverError("Stored M5 singleton receipt does not match expected receipt.")

    source_manifest = store.load_document_manifest(
        projection.case_header.case_id,
        binding.source_document_instance_id,
    )
    _validate_source_manifest(
        case_id=projection.case_header.case_id,
        binding=binding,
        manifest=source_manifest,
    )

    pages = tuple(item for item in source_manifest.pages if item.page_number == binding.page)
    if len(pages) != 1:
        raise SourceEvidenceResolverError("Binding page is not uniquely present in source manifest.")
    page = pages[0]
    if page.page_text_sha256 != binding.page_text_sha256:
        raise SourceEvidenceResolverError("Source page SHA does not match evidence binding.")

    chunks = tuple(
        item for item in page.chunk_snapshots if item.chunk_ordinal == binding.chunk_ordinal
    )
    if len(chunks) != 1:
        raise SourceEvidenceResolverError("Binding chunk is not uniquely present in source manifest.")
    chunk = chunks[0]
    if chunk.chunk_id != citation.evidence_key or chunk.evidence_key != citation.evidence_key:
        raise SourceEvidenceResolverError("Source chunk identity does not match projected evidence key.")
    if chunk.chunk_text_sha256 != binding.chunk_text_sha256:
        raise SourceEvidenceResolverError("Source chunk SHA does not match evidence binding.")

    original_bytes = store.read_blob(source_manifest.original_blob_sha256)
    if len(original_bytes) != source_manifest.original_byte_length:
        raise SourceEvidenceResolverError("Original PDF byte length does not match source manifest.")
    page_bytes = store.read_blob(page.page_text_sha256)
    if len(page_bytes) != page.page_text_byte_length:
        raise SourceEvidenceResolverError("Page-text byte length does not match source manifest.")
    chunk_bytes = store.read_blob(chunk.chunk_text_sha256)
    if len(chunk_bytes) != chunk.chunk_text_byte_length:
        raise SourceEvidenceResolverError("Chunk-text byte length does not match source manifest.")

    page_text = _decode_utf8(page_bytes, field_name="page_text")
    chunk_text = _decode_utf8(chunk_bytes, field_name="chunk_text")

    return _base_resolution(
        projection=projection,
        manifest=manifest,
        citation=citation,
        entry=entry,
        binding=binding,
        exact_bound_text=chunk_text,
        exact_page_text=page_text,
        original_pdf_bytes=original_bytes,
        original_filename=source_manifest.original_filename,
        extraction_method=page.extraction_method,
    )


def resolve_projection_citation_source(
    projection: CaseReportProjection,
    *,
    case_id: str,
    citation_id: str,
    store: SourceEvidenceStore | None = None,
) -> ResolvedSourceEvidence | None:
    """Resolve one validated projection citation to its frozen source authority.

    ``None`` means that no M6 projection-binding manifest exists for this frozen
    projection. A present manifest is always consumed exactly as stored: M7 never
    rebuilds or silently upgrades its binding classifications from current state.
    """

    try:
        validate_case_report_projection(projection)
        canonical_case_id = canonical_uuid(case_id, field_name="case_id")
        if canonical_case_id != projection.case_header.case_id:
            raise SourceEvidenceResolverError("Active case does not match the report projection.")
        citation = _find_citation(projection, citation_id)
        target_store = store if store is not None else SourceEvidenceStore()
        manifest = target_store.load_projection_binding(
            canonical_case_id,
            projection.report_projection_id,
        )
        if manifest is None:
            return None
        _validate_projection_binding(projection, manifest)
        entry = _find_entry(manifest, citation)

        if entry.binding_class is BindingClass.UNBOUND:
            return _base_resolution(
                projection=projection,
                manifest=manifest,
                citation=citation,
                entry=entry,
                binding=None,
            )

        binding = target_store.load_evidence_binding(canonical_case_id, citation.evidence_key)
        if binding is None:
            raise SourceEvidenceResolverError(
                "Projection binding references a missing immutable EvidenceBinding."
            )
        _validate_binding_compatibility(
            case_id=canonical_case_id,
            citation=citation,
            entry=entry,
            binding=binding,
        )

        if entry.binding_class in {
            BindingClass.ANALYTICAL_TEXT_BOUND,
            BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT,
        }:
            return _resolve_weaker_binding(
                projection=projection,
                manifest=manifest,
                citation=citation,
                entry=entry,
                binding=binding,
                store=target_store,
            )
        if entry.binding_class is BindingClass.FULL_CHAIN_BOUND:
            return _resolve_full_chain(
                projection=projection,
                manifest=manifest,
                citation=citation,
                entry=entry,
                binding=binding,
                store=target_store,
            )
        raise SourceEvidenceResolverError("Unsupported projection binding class.")
    except SourceEvidenceResolverError:
        raise
    except (SourceEvidenceStoreError, ValueError, TypeError, UnicodeDecodeError) as exc:
        raise SourceEvidenceResolverError(
            "Source evidence resolution failed integrity validation."
        ) from exc


__all__ = [
    "ResolvedSourceEvidence",
    "SourceEvidenceResolverError",
    "resolve_projection_citation_source",
]
