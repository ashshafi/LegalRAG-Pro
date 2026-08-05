"""Fail-closed validation for immutable source-evidence core records."""

from __future__ import annotations

from pathlib import PurePath

from .identity import (
    canonical_uuid,
    derive_sha256_id,
    derive_source_document_instance_id,
    validate_sha256_hex,
    validate_sha256_id,
)
from .models import (
    CHUNKING_PROFILE_ID,
    CHUNKING_PROFILE_SCHEMA_VERSION,
    EVIDENCE_BINDING_SCHEMA_VERSION,
    EXTRACTION_PROFILE_ID,
    EXTRACTION_PROFILE_SCHEMA_VERSION,
    PDF_MEDIA_TYPE,
    PROJECTION_EVIDENCE_BINDING_SCHEMA_VERSION,
    SOURCE_BOUND_ANALYSIS_RECEIPT_SCHEMA_VERSION,
    SOURCE_BOUND_RETRIEVAL_VERIFIER_VERSION,
    SOURCE_DOCUMENT_MANIFEST_SCHEMA_VERSION,
    BindingClass,
    BoundTextRole,
    ChunkingProfile,
    EvidenceBinding,
    ExtractionMethod,
    ExtractionProfile,
    ProjectionBindingCoverage,
    ProjectionEvidenceBindingManifest,
    SourceBoundAnalysisReceipt,
    SourceDocumentManifest,
)
from .serialization import (
    evidence_binding_identity_payload_to_dict,
    projection_evidence_binding_manifest_identity_payload_to_dict,
    source_bound_analysis_receipt_identity_payload_to_dict,
    source_document_manifest_identity_payload_to_dict,
)

_GOVERNED_SEPARATORS = ("\n\n", "\n", " ", "")


def _required_text(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must not be empty.")
    return value


def _optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name=field_name)


def _positive_int(value: int, *, field_name: str) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{field_name} must be an integer of 1 or greater.")


def _nonnegative_int(value: int, *, field_name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer.")


def _optional_sha(value: str | None, *, field_name: str) -> None:
    if value is not None:
        validate_sha256_hex(value, field_name=field_name)


def _optional_sha_id(value: str | None, *, field_name: str) -> None:
    if value is not None:
        validate_sha256_id(value, field_name=field_name)


def _validate_plain_pdf_filename(value: str) -> None:
    _required_text(value, field_name="original_filename")
    if PurePath(value).name != value or "/" in value or "\\" in value or value in (".", ".."):
        raise ValueError("original_filename must be a plain filename without directories.")
    if not value.lower().endswith(".pdf"):
        raise ValueError("original_filename must use a .pdf filename.")


def validate_extraction_profile(value: ExtractionProfile, *, requires_ocr: bool = False) -> None:
    if not isinstance(value, ExtractionProfile):
        raise ValueError("value must be an ExtractionProfile instance.")
    if value.profile_id != EXTRACTION_PROFILE_ID:
        raise ValueError("ExtractionProfile.profile_id is not the frozen v1 value.")
    if value.profile_schema_version != EXTRACTION_PROFILE_SCHEMA_VERSION:
        raise ValueError("ExtractionProfile.profile_schema_version is not the frozen v1 value.")
    _required_text(value.pypdf_package_version, field_name="pypdf_package_version")
    if value.ocr_language != "eng":
        raise ValueError("ExtractionProfile.ocr_language must be 'eng'.")
    if value.ocr_config != "":
        raise ValueError("ExtractionProfile.ocr_config must be the frozen empty string.")
    if type(value.ocr_dpi) is not int or value.ocr_dpi != 200:
        raise ValueError("ExtractionProfile.ocr_dpi must be 200.")
    for field_name in (
        "pdf2image_package_version",
        "pytesseract_package_version",
        "tesseract_engine_version",
        "poppler_version",
    ):
        _optional_text(getattr(value, field_name), field_name=field_name)
    if requires_ocr:
        for field_name in (
            "pdf2image_package_version",
            "pytesseract_package_version",
            "tesseract_engine_version",
            "poppler_version",
        ):
            _required_text(getattr(value, field_name), field_name=field_name)


def validate_chunking_profile(value: ChunkingProfile) -> None:
    if not isinstance(value, ChunkingProfile):
        raise ValueError("value must be a ChunkingProfile instance.")
    if value.profile_id != CHUNKING_PROFILE_ID:
        raise ValueError("ChunkingProfile.profile_id is not the frozen v1 value.")
    if value.profile_schema_version != CHUNKING_PROFILE_SCHEMA_VERSION:
        raise ValueError("ChunkingProfile.profile_schema_version is not the frozen v1 value.")
    if value.library != "langchain-text-splitters":
        raise ValueError("ChunkingProfile.library is not the frozen v1 value.")
    _required_text(value.library_version, field_name="library_version")
    if type(value.chunk_size) is not int or value.chunk_size != 1000:
        raise ValueError("ChunkingProfile.chunk_size must be 1000.")
    if type(value.chunk_overlap) is not int or value.chunk_overlap != 200:
        raise ValueError("ChunkingProfile.chunk_overlap must be 200.")
    if value.separators != _GOVERNED_SEPARATORS:
        raise ValueError("ChunkingProfile.separators do not match the frozen v1 policy.")
    if value.length_function != "len":
        raise ValueError("ChunkingProfile.length_function must be 'len'.")
    if type(value.is_separator_regex) is not bool or value.is_separator_regex:
        raise ValueError("ChunkingProfile.is_separator_regex must be False.")


def validate_source_document_manifest(value: SourceDocumentManifest) -> None:
    if not isinstance(value, SourceDocumentManifest):
        raise ValueError("value must be a SourceDocumentManifest instance.")
    if value.schema_version != SOURCE_DOCUMENT_MANIFEST_SCHEMA_VERSION:
        raise ValueError("Unsupported SourceDocumentManifest schema_version.")
    canonical_uuid(value.case_id, field_name="case_id")
    canonical_uuid(value.source_document_instance_id, field_name="source_document_instance_id")
    _validate_plain_pdf_filename(value.original_filename)
    expected_document_id = derive_source_document_instance_id(
        case_id=value.case_id,
        original_filename=value.original_filename,
        original_blob_sha256=value.original_blob_sha256,
    )
    if value.source_document_instance_id != expected_document_id:
        raise ValueError(
            "source_document_instance_id does not match the v1 case/name/content identity."
        )
    if value.media_type != PDF_MEDIA_TYPE:
        raise ValueError("SourceDocumentManifest.media_type must be 'application/pdf'.")
    validate_sha256_hex(value.original_blob_sha256, field_name="original_blob_sha256")
    _positive_int(value.original_byte_length, field_name="original_byte_length")

    if not value.pages:
        raise ValueError("SourceDocumentManifest.pages must not be empty for a PDF.")
    expected_page_numbers = tuple(range(1, len(value.pages) + 1))
    actual_page_numbers = tuple(page.page_number for page in value.pages)
    if actual_page_numbers != expected_page_numbers:
        raise ValueError("SourceDocumentManifest pages must be exactly 1..N in order.")

    requires_ocr = any(page.extraction_method is ExtractionMethod.PAGE_OCR for page in value.pages)
    validate_extraction_profile(value.extraction_profile, requires_ocr=requires_ocr)
    validate_chunking_profile(value.chunking_profile)

    seen_chunk_ids: set[str] = set()
    seen_evidence_keys: set[str] = set()
    for page in value.pages:
        _positive_int(page.page_number, field_name="page_number")
        if not isinstance(page.extraction_method, ExtractionMethod):
            raise ValueError("SourcePageSnapshot.extraction_method must be ExtractionMethod.")
        validate_sha256_hex(page.page_text_sha256, field_name="page_text_sha256")
        _nonnegative_int(page.page_text_byte_length, field_name="page_text_byte_length")
        ordinals = tuple(chunk.chunk_ordinal for chunk in page.chunk_snapshots)
        if ordinals != tuple(range(len(page.chunk_snapshots))):
            raise ValueError("Chunk ordinals must be contiguous from zero within each page.")
        for chunk in page.chunk_snapshots:
            if chunk.page_number != page.page_number:
                raise ValueError("SourceChunkSnapshot.page_number must equal its parent page.")
            _nonnegative_int(chunk.chunk_ordinal, field_name="chunk_ordinal")
            _required_text(chunk.chunk_id, field_name="chunk_id")
            _required_text(chunk.evidence_key, field_name="evidence_key")
            if chunk.chunk_id != chunk.evidence_key:
                raise ValueError("SourceChunkSnapshot.chunk_id must equal evidence_key in v1.")
            validate_sha256_hex(chunk.chunk_text_sha256, field_name="chunk_text_sha256")
            _nonnegative_int(chunk.chunk_text_byte_length, field_name="chunk_text_byte_length")
            if chunk.chunk_id in seen_chunk_ids:
                raise ValueError("SourceDocumentManifest chunk IDs must be unique.")
            if chunk.evidence_key in seen_evidence_keys:
                raise ValueError("SourceDocumentManifest evidence keys must be unique.")
            seen_chunk_ids.add(chunk.chunk_id)
            seen_evidence_keys.add(chunk.evidence_key)

    validate_sha256_id(value.source_snapshot_id, field_name="source_snapshot_id")
    expected_id = derive_sha256_id(source_document_manifest_identity_payload_to_dict(value))
    if value.source_snapshot_id != expected_id:
        raise ValueError("source_snapshot_id does not match the canonical manifest identity payload.")


def validate_evidence_binding(value: EvidenceBinding) -> None:
    if not isinstance(value, EvidenceBinding):
        raise ValueError("value must be an EvidenceBinding instance.")
    if value.schema_version != EVIDENCE_BINDING_SCHEMA_VERSION:
        raise ValueError("Unsupported EvidenceBinding schema_version.")
    canonical_uuid(value.case_id, field_name="case_id")
    _required_text(value.evidence_key, field_name="evidence_key")
    _optional_text(value.chunk_id, field_name="chunk_id")
    if not isinstance(value.binding_class, BindingClass) or value.binding_class is BindingClass.UNBOUND:
        raise ValueError("EvidenceBinding must use a concrete non-UNBOUND binding_class.")
    if not isinstance(value.bound_text_role, BoundTextRole):
        raise ValueError("EvidenceBinding.bound_text_role must be BoundTextRole.")
    _required_text(value.document_name, field_name="document_name")
    _optional_text(value.document_id, field_name="document_id")
    if value.page is not None:
        _positive_int(value.page, field_name="page")
    if value.chunk_ordinal is not None:
        _nonnegative_int(value.chunk_ordinal, field_name="chunk_ordinal")
    for field_name in (
        "original_blob_sha256",
        "page_text_sha256",
        "chunk_text_sha256",
    ):
        _optional_sha(getattr(value, field_name), field_name=field_name)
    validate_sha256_hex(value.bound_text_sha256, field_name="bound_text_sha256")
    _optional_text(value.extraction_profile_id, field_name="extraction_profile_id")
    _optional_text(value.chunking_profile_id, field_name="chunking_profile_id")
    if value.source_document_instance_id is not None:
        canonical_uuid(value.source_document_instance_id, field_name="source_document_instance_id")
    _optional_sha_id(value.source_snapshot_id, field_name="source_snapshot_id")

    if value.binding_class is BindingClass.FULL_CHAIN_BOUND:
        if value.bound_text_role is not BoundTextRole.CHUNK_TEXT:
            raise ValueError("FULL_CHAIN_BOUND requires bound_text_role=CHUNK_TEXT.")
        required = {
            "chunk_id": value.chunk_id,
            "source_document_instance_id": value.source_document_instance_id,
            "source_snapshot_id": value.source_snapshot_id,
            "page": value.page,
            "chunk_ordinal": value.chunk_ordinal,
            "original_blob_sha256": value.original_blob_sha256,
            "page_text_sha256": value.page_text_sha256,
            "chunk_text_sha256": value.chunk_text_sha256,
            "extraction_profile_id": value.extraction_profile_id,
            "chunking_profile_id": value.chunking_profile_id,
        }
        missing = sorted(name for name, item in required.items() if item is None)
        if missing:
            raise ValueError(f"FULL_CHAIN_BOUND is missing required fields: {missing}.")
        if value.chunk_id != value.evidence_key:
            raise ValueError("FULL_CHAIN_BOUND requires chunk_id == evidence_key.")
        if value.bound_text_sha256 != value.chunk_text_sha256:
            raise ValueError("FULL_CHAIN_BOUND requires bound_text_sha256 == chunk_text_sha256.")
        if value.extraction_profile_id != EXTRACTION_PROFILE_ID:
            raise ValueError("FULL_CHAIN_BOUND extraction_profile_id is not the frozen v1 profile.")
        if value.chunking_profile_id != CHUNKING_PROFILE_ID:
            raise ValueError("FULL_CHAIN_BOUND chunking_profile_id is not the frozen v1 profile.")
    elif value.binding_class is BindingClass.ANALYTICAL_TEXT_BOUND:
        if value.bound_text_role is not BoundTextRole.ANALYTICAL_SUMMARY:
            raise ValueError("ANALYTICAL_TEXT_BOUND requires bound_text_role=ANALYTICAL_SUMMARY.")
    elif value.binding_class is BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT:
        if value.bound_text_role is not BoundTextRole.LEGACY_CURRENT_INDEX_TEXT:
            raise ValueError(
                "LEGACY_CURRENT_INDEX_SNAPSHOT requires bound_text_role=LEGACY_CURRENT_INDEX_TEXT."
            )

    validate_sha256_id(value.evidence_binding_id, field_name="evidence_binding_id")
    expected_id = derive_sha256_id(evidence_binding_identity_payload_to_dict(value))
    if value.evidence_binding_id != expected_id:
        raise ValueError("evidence_binding_id does not match the canonical binding identity payload.")


def validate_source_bound_analysis_receipt(value: SourceBoundAnalysisReceipt) -> None:
    if not isinstance(value, SourceBoundAnalysisReceipt):
        raise ValueError("value must be a SourceBoundAnalysisReceipt instance.")
    if value.schema_version != SOURCE_BOUND_ANALYSIS_RECEIPT_SCHEMA_VERSION:
        raise ValueError("Unsupported SourceBoundAnalysisReceipt schema_version.")
    canonical_uuid(value.case_id, field_name="case_id")
    if value.verifier_version != SOURCE_BOUND_RETRIEVAL_VERIFIER_VERSION:
        raise ValueError("SourceBoundAnalysisReceipt.verifier_version is not the frozen v1 value.")
    seen: set[str] = set()
    for item in value.verified_evidence:
        _required_text(item.evidence_key, field_name="evidence_key")
        validate_sha256_id(item.evidence_binding_id, field_name="evidence_binding_id")
        validate_sha256_hex(item.chunk_text_sha256, field_name="chunk_text_sha256")
        if item.evidence_key in seen:
            raise ValueError("SourceBoundAnalysisReceipt evidence keys must be unique.")
        seen.add(item.evidence_key)
    validate_sha256_id(
        value.source_bound_analysis_receipt_id,
        field_name="source_bound_analysis_receipt_id",
    )
    expected_id = derive_sha256_id(source_bound_analysis_receipt_identity_payload_to_dict(value))
    if value.source_bound_analysis_receipt_id != expected_id:
        raise ValueError("source_bound_analysis_receipt_id does not match its canonical payload.")


def _expected_coverage(value: ProjectionEvidenceBindingManifest) -> ProjectionBindingCoverage:
    if not value.entries or all(item.binding_class is BindingClass.UNBOUND for item in value.entries):
        return ProjectionBindingCoverage.UNBOUND
    if all(item.binding_class is BindingClass.FULL_CHAIN_BOUND for item in value.entries):
        return ProjectionBindingCoverage.FULLY_SOURCE_BOUND
    return ProjectionBindingCoverage.MIXED_BINDING


def validate_projection_evidence_binding_manifest(
    value: ProjectionEvidenceBindingManifest,
) -> None:
    if not isinstance(value, ProjectionEvidenceBindingManifest):
        raise ValueError("value must be a ProjectionEvidenceBindingManifest instance.")
    if value.schema_version != PROJECTION_EVIDENCE_BINDING_SCHEMA_VERSION:
        raise ValueError("Unsupported ProjectionEvidenceBindingManifest schema_version.")
    canonical_uuid(value.case_id, field_name="case_id")
    canonical_uuid(value.report_projection_id, field_name="report_projection_id")
    validate_sha256_hex(value.projection_payload_sha256, field_name="projection_payload_sha256")
    canonical_uuid(value.manifest_id, field_name="manifest_id")
    if not isinstance(value.coverage, ProjectionBindingCoverage):
        raise ValueError("coverage must be ProjectionBindingCoverage.")

    seen: set[str] = set()
    for entry in value.entries:
        _required_text(entry.citation_id, field_name="citation_id")
        _required_text(entry.evidence_key, field_name="evidence_key")
        if entry.citation_id != entry.evidence_key:
            raise ValueError("ProjectionBindingEntry.citation_id must equal evidence_key.")
        if entry.evidence_key in seen:
            raise ValueError("Projection binding entries must use unique evidence keys.")
        seen.add(entry.evidence_key)
        if not isinstance(entry.binding_class, BindingClass):
            raise ValueError("ProjectionBindingEntry.binding_class must be BindingClass.")
        if entry.binding_class is BindingClass.UNBOUND:
            if entry.evidence_binding_id is not None or entry.source_bound_analysis_receipt_id is not None:
                raise ValueError("UNBOUND projection entries must not carry binding or receipt IDs.")
        else:
            if entry.evidence_binding_id is None:
                raise ValueError("Bound projection entries require evidence_binding_id.")
            validate_sha256_id(entry.evidence_binding_id, field_name="evidence_binding_id")
            if entry.binding_class is BindingClass.FULL_CHAIN_BOUND:
                if entry.source_bound_analysis_receipt_id is None:
                    raise ValueError("FULL_CHAIN_BOUND projection entries require a receipt ID.")
                validate_sha256_id(
                    entry.source_bound_analysis_receipt_id,
                    field_name="source_bound_analysis_receipt_id",
                )
            elif entry.source_bound_analysis_receipt_id is not None:
                raise ValueError("Only FULL_CHAIN_BOUND projection entries may carry receipt IDs.")

    expected_coverage = _expected_coverage(value)
    if value.coverage is not expected_coverage:
        raise ValueError("Projection binding coverage does not match entry binding classes.")
    validate_sha256_id(
        value.projection_evidence_binding_manifest_id,
        field_name="projection_evidence_binding_manifest_id",
    )
    expected_id = derive_sha256_id(
        projection_evidence_binding_manifest_identity_payload_to_dict(value)
    )
    if value.projection_evidence_binding_manifest_id != expected_id:
        raise ValueError(
            "projection_evidence_binding_manifest_id does not match the canonical identity payload."
        )


__all__ = [
    "validate_chunking_profile",
    "validate_evidence_binding",
    "validate_extraction_profile",
    "validate_projection_evidence_binding_manifest",
    "validate_source_bound_analysis_receipt",
    "validate_source_document_manifest",
]
