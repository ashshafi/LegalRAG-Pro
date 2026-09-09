from __future__ import annotations

from dataclasses import replace
import hashlib

from source_evidence.models import EXTRACTION_PROFILE_ID
from source_evidence.store import SourceEvidenceStore

from .models import (
    DERIVED_PAGE_RENDER_TRANSCRIPTION_RECORD_SCHEMA_VERSION,
    PAGE_RENDER_ARTIFACT_ROLE,
    PAGE_RENDER_OCR_DPI,
    PAGE_RENDER_OCR_LANGUAGE,
    PAGE_RENDER_OCR_PREPROCESSING_STEPS,
    PAGE_RENDER_OCR_PROFILE_ID,
    PAGE_RENDER_OCR_PROFILE_SCHEMA_VERSION,
    PAGE_RENDER_OCR_PSM,
    PageRenderTranscriptionRecord,
)
from .page_render_ocr import transcribe_rendered_pdf_page
from .serialization import derive_record_id
from .store import PageRenderTranscriptionStore
from .validation import (
    validate_page_render_transcription_record,
    validate_raw_sha256,
    validate_sha256_id,
    validate_uuid_text,
)


class PageRenderTranscriptionServiceError(RuntimeError):
    """Raised when source-bound page-render transcription cannot complete."""


def create_page_render_transcription(
    *,
    case_id: str,
    source_document_instance_id: str,
    source_snapshot_id: str,
    page_number: int,
    expected_original_blob_sha256: str,
    expected_source_page_text_sha256: str,
    source_store: SourceEvidenceStore,
    derived_store: PageRenderTranscriptionStore,
    tesseract_cmd: str | None = None,
    pdfinfo_cmd: str | None = None,
) -> PageRenderTranscriptionRecord:
    """Create one immutable candidate-only page-render transcription sidecar."""

    case = validate_uuid_text(case_id, field_name="case_id")
    document = validate_uuid_text(
        source_document_instance_id,
        field_name="source_document_instance_id",
    )
    snapshot = validate_sha256_id(source_snapshot_id, field_name="source_snapshot_id")
    original_sha = validate_raw_sha256(
        expected_original_blob_sha256,
        field_name="expected_original_blob_sha256",
    )
    page_sha = validate_raw_sha256(
        expected_source_page_text_sha256,
        field_name="expected_source_page_text_sha256",
    )
    if type(page_number) is not int or page_number < 1:
        raise ValueError("page_number must be a positive integer.")

    try:
        manifest = source_store.load_document_manifest(case, document)
    except Exception as exc:
        raise PageRenderTranscriptionServiceError(
            "Source manifest could not be loaded."
        ) from exc

    if manifest.case_id != case:
        raise PageRenderTranscriptionServiceError("Source manifest case identity differs.")
    if manifest.source_document_instance_id != document:
        raise PageRenderTranscriptionServiceError(
            "Source manifest document identity differs."
        )
    if manifest.source_snapshot_id != snapshot:
        raise PageRenderTranscriptionServiceError(
            "Source snapshot identity does not match authorized coordinates."
        )
    if manifest.original_blob_sha256 != original_sha:
        raise PageRenderTranscriptionServiceError(
            "Original PDF SHA-256 does not match authorized coordinates."
        )
    if manifest.extraction_profile.profile_id != EXTRACTION_PROFILE_ID:
        raise PageRenderTranscriptionServiceError(
            "Page-render transcription requires a frozen-v1 source manifest."
        )

    pages = tuple(page for page in manifest.pages if page.page_number == page_number)
    if len(pages) != 1:
        raise PageRenderTranscriptionServiceError(
            "Selected source page is not uniquely present in the manifest."
        )
    page = pages[0]

    if page.page_text_sha256 != page_sha:
        raise PageRenderTranscriptionServiceError(
            "Source page-text SHA-256 does not match authorized coordinates."
        )

    extraction_method = getattr(page.extraction_method, "value", None)
    if extraction_method not in {"pypdf_text", "page_ocr"}:
        raise PageRenderTranscriptionServiceError(
            "Selected source page extraction method is unsupported."
        )

    try:
        original_bytes = source_store.read_blob(manifest.original_blob_sha256)
        page_text_bytes = source_store.read_blob(page.page_text_sha256)
    except Exception as exc:
        raise PageRenderTranscriptionServiceError(
            "Immutable source blobs could not be read."
        ) from exc

    if len(original_bytes) != manifest.original_byte_length:
        raise PageRenderTranscriptionServiceError(
            "Immutable original PDF byte length is invalid."
        )
    if hashlib.sha256(original_bytes).hexdigest() != manifest.original_blob_sha256:
        raise PageRenderTranscriptionServiceError(
            "Immutable original PDF hash is invalid."
        )
    if len(page_text_bytes) != page.page_text_byte_length:
        raise PageRenderTranscriptionServiceError(
            "Immutable source page-text byte length is invalid."
        )
    if hashlib.sha256(page_text_bytes).hexdigest() != page.page_text_sha256:
        raise PageRenderTranscriptionServiceError(
            "Immutable source page-text hash is invalid."
        )

    result = transcribe_rendered_pdf_page(
        original_bytes,
        page_number=page_number,
        tesseract_cmd=tesseract_cmd,
        pdfinfo_cmd=pdfinfo_cmd,
    )

    transcription_bytes = result.transcription_text.encode("utf-8")
    if hashlib.sha256(transcription_bytes).hexdigest() != result.transcription_sha256:
        raise PageRenderTranscriptionServiceError(
            "OCR result transcription hash is inconsistent."
        )
    if (
        hashlib.sha256(result.derived_artifact_bytes).hexdigest()
        != result.derived_artifact_sha256
    ):
        raise PageRenderTranscriptionServiceError(
            "OCR result rendered-page artifact hash is inconsistent."
        )

    provisional = PageRenderTranscriptionRecord(
        schema_version=DERIVED_PAGE_RENDER_TRANSCRIPTION_RECORD_SCHEMA_VERSION,
        record_id="sha256:" + ("0" * 64),
        case_id=case,
        source_document_instance_id=document,
        source_snapshot_id=snapshot,
        original_filename=manifest.original_filename,
        original_blob_sha256=manifest.original_blob_sha256,
        original_byte_length=manifest.original_byte_length,
        page_number=page_number,
        source_extraction_method=extraction_method,
        source_page_text_sha256=page.page_text_sha256,
        source_page_text_byte_length=page.page_text_byte_length,
        profile_id=PAGE_RENDER_OCR_PROFILE_ID,
        profile_schema_version=PAGE_RENDER_OCR_PROFILE_SCHEMA_VERSION,
        artifact_role=PAGE_RENDER_ARTIFACT_ROLE,
        derived_artifact_sha256=result.derived_artifact_sha256,
        derived_artifact_byte_length=len(result.derived_artifact_bytes),
        derived_artifact_width=result.derived_artifact_width,
        derived_artifact_height=result.derived_artifact_height,
        render_dpi=PAGE_RENDER_OCR_DPI,
        preprocessing_steps=PAGE_RENDER_OCR_PREPROCESSING_STEPS,
        ocr_language=PAGE_RENDER_OCR_LANGUAGE,
        ocr_psm=PAGE_RENDER_OCR_PSM,
        pdf2image_package_version=result.pdf2image_package_version,
        pillow_package_version=result.pillow_package_version,
        pytesseract_package_version=result.pytesseract_package_version,
        tesseract_command=result.tesseract_command,
        tesseract_executable_sha256=result.tesseract_executable_sha256,
        tesseract_engine_version=result.tesseract_engine_version,
        poppler_version=result.poppler_version,
        transcription_sha256=result.transcription_sha256,
        transcription_byte_length=len(transcription_bytes),
    )
    record = replace(provisional, record_id=derive_record_id(provisional))
    validate_page_render_transcription_record(record)

    artifact_digest = derived_store.put_blob(result.derived_artifact_bytes)
    if artifact_digest != result.derived_artifact_sha256:
        raise PageRenderTranscriptionServiceError(
            "Published rendered-page artifact digest is inconsistent."
        )

    transcription_digest = derived_store.put_blob(transcription_bytes)
    if transcription_digest != result.transcription_sha256:
        raise PageRenderTranscriptionServiceError(
            "Published transcription digest is inconsistent."
        )

    derived_store.publish_record(record)
    loaded = derived_store.load_record(
        case_id=case,
        source_document_instance_id=document,
        page_number=page_number,
        record_id=record.record_id,
    )
    if loaded != record:
        raise PageRenderTranscriptionServiceError(
            "Published page-render record did not round-trip exactly."
        )
    if derived_store.read_transcription(record) != result.transcription_text:
        raise PageRenderTranscriptionServiceError(
            "Published page-render transcription did not round-trip exactly."
        )
    if derived_store.read_derived_artifact(record) != result.derived_artifact_bytes:
        raise PageRenderTranscriptionServiceError(
            "Published rendered-page artifact did not round-trip exactly."
        )

    return record


__all__ = [
    "PageRenderTranscriptionServiceError",
    "create_page_render_transcription",
]
