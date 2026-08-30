from __future__ import annotations

from dataclasses import replace
import hashlib

from source_evidence.models import (
    EXTRACTION_PROFILE_ID,
)
from source_evidence.store import (
    SourceEvidenceStore,
)

from .models import (
    DERIVED_TRANSCRIPTION_RECORD_SCHEMA_VERSION,
    PHOTO_IMAGE_SELECTION_ID,
    PHOTO_OCR_LANGUAGE,
    PHOTO_OCR_PREPROCESSING_STEPS,
    PHOTO_OCR_PROFILE_ID,
    PHOTO_OCR_PROFILE_SCHEMA_VERSION,
    PHOTO_OCR_PSM,
    DerivedTranscriptionRecord,
)
from .photo_ocr import (
    transcribe_embedded_photo_page,
)
from .serialization import (
    derive_record_id,
)
from .store import (
    DerivedTranscriptionStore,
)
from .validation import (
    validate_derived_transcription_record,
    validate_raw_sha256,
    validate_sha256_id,
    validate_uuid_text,
)


class DerivedTranscriptionServiceError(RuntimeError):
    """Raised when source-bound derived transcription cannot complete."""


def create_photo_derived_transcription(
    *,
    case_id: str,
    source_document_instance_id: str,
    source_snapshot_id: str,
    page_number: int,
    expected_original_blob_sha256: str,
    expected_source_page_text_sha256: str,
    source_store: SourceEvidenceStore,
    derived_store: DerivedTranscriptionStore,
    expected_embedded_image_sha256: str | None = None,
    tesseract_cmd: str | None = None,
) -> DerivedTranscriptionRecord:
    """Create one immutable transcription without modifying M1 state."""

    case = validate_uuid_text(
        case_id,
        field_name="case_id",
    )

    document = validate_uuid_text(
        source_document_instance_id,
        field_name="source_document_instance_id",
    )

    snapshot = validate_sha256_id(
        source_snapshot_id,
        field_name="source_snapshot_id",
    )

    original_sha = validate_raw_sha256(
        expected_original_blob_sha256,
        field_name="expected_original_blob_sha256",
    )

    page_sha = validate_raw_sha256(
        expected_source_page_text_sha256,
        field_name="expected_source_page_text_sha256",
    )

    if type(page_number) is not int or page_number < 1:
        raise ValueError(
            "page_number must be a positive integer."
        )

    if expected_embedded_image_sha256 is not None:
        expected_embedded_image_sha256 = (
            validate_raw_sha256(
                expected_embedded_image_sha256,
                field_name="expected_embedded_image_sha256",
            )
        )

    try:
        manifest = source_store.load_document_manifest(
            case,
            document,
        )
    except Exception as exc:
        raise DerivedTranscriptionServiceError(
            "Source manifest could not be loaded."
        ) from exc

    if manifest.case_id != case:
        raise DerivedTranscriptionServiceError(
            "Source manifest case identity does not match."
        )

    if manifest.source_document_instance_id != document:
        raise DerivedTranscriptionServiceError(
            "Source manifest document identity does not match."
        )

    if manifest.source_snapshot_id != snapshot:
        raise DerivedTranscriptionServiceError(
            "Source snapshot identity does not match the authorized coordinates."
        )

    if manifest.original_blob_sha256 != original_sha:
        raise DerivedTranscriptionServiceError(
            "Original PDF SHA-256 does not match the authorized coordinates."
        )

    if (
        manifest.extraction_profile.profile_id
        != EXTRACTION_PROFILE_ID
    ):
        raise DerivedTranscriptionServiceError(
            "Derived transcription requires a frozen-v1 source manifest."
        )

    pages = tuple(
        page
        for page in manifest.pages
        if page.page_number == page_number
    )

    if len(pages) != 1:
        raise DerivedTranscriptionServiceError(
            "Selected source page is not uniquely present in the manifest."
        )

    page = pages[0]

    if page.page_text_sha256 != page_sha:
        raise DerivedTranscriptionServiceError(
            "Source page-text SHA-256 does not match the authorized coordinates."
        )

    extraction_method = getattr(
        page.extraction_method,
        "value",
        None,
    )

    if extraction_method != "page_ocr":
        raise DerivedTranscriptionServiceError(
            "PHOTO-OCR-C1 requires a frozen-v1 page_ocr source page."
        )

    if page.page_text_byte_length != 0:
        raise DerivedTranscriptionServiceError(
            "PHOTO-OCR-C1 requires zero-byte frozen-v1 page text."
        )

    chunk_snapshots = getattr(
        page,
        "chunk_snapshots",
        None,
    )

    if not isinstance(chunk_snapshots, tuple):
        raise DerivedTranscriptionServiceError(
            "Source page chunk coordinates are unavailable."
        )

    if chunk_snapshots:
        raise DerivedTranscriptionServiceError(
            "PHOTO-OCR-C1 requires a source page with zero searchable chunks."
        )

    try:
        original_bytes = source_store.read_blob(
            manifest.original_blob_sha256
        )

        page_text_bytes = source_store.read_blob(
            page.page_text_sha256
        )
    except Exception as exc:
        raise DerivedTranscriptionServiceError(
            "Immutable source blobs could not be read."
        ) from exc

    if len(original_bytes) != manifest.original_byte_length:
        raise DerivedTranscriptionServiceError(
            "Immutable original PDF byte length is invalid."
        )

    if (
        hashlib.sha256(original_bytes).hexdigest()
        != manifest.original_blob_sha256
    ):
        raise DerivedTranscriptionServiceError(
            "Immutable original PDF hash is invalid."
        )

    if len(page_text_bytes) != page.page_text_byte_length:
        raise DerivedTranscriptionServiceError(
            "Immutable source page-text byte length is invalid."
        )

    if (
        hashlib.sha256(page_text_bytes).hexdigest()
        != page.page_text_sha256
    ):
        raise DerivedTranscriptionServiceError(
            "Immutable source page-text hash is invalid."
        )

    result = transcribe_embedded_photo_page(
        original_bytes,
        page_number=page_number,
        tesseract_cmd=tesseract_cmd,
    )

    if (
        expected_embedded_image_sha256 is not None
        and result.embedded_image_sha256
        != expected_embedded_image_sha256
    ):
        raise DerivedTranscriptionServiceError(
            "Embedded image SHA-256 does not match the authorized image identity."
        )

    transcription_bytes = (
        result.transcription_text.encode(
            "utf-8"
        )
    )

    if (
        hashlib.sha256(
            transcription_bytes
        ).hexdigest()
        != result.transcription_sha256
    ):
        raise DerivedTranscriptionServiceError(
            "OCR result transcription hash is inconsistent."
        )

    if (
        hashlib.sha256(
            result.embedded_image_bytes
        ).hexdigest()
        != result.embedded_image_sha256
    ):
        raise DerivedTranscriptionServiceError(
            "OCR result embedded-image hash is inconsistent."
        )

    provisional = DerivedTranscriptionRecord(
        schema_version=(
            DERIVED_TRANSCRIPTION_RECORD_SCHEMA_VERSION
        ),
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
        profile_id=PHOTO_OCR_PROFILE_ID,
        profile_schema_version=(
            PHOTO_OCR_PROFILE_SCHEMA_VERSION
        ),
        image_selection_id=PHOTO_IMAGE_SELECTION_ID,
        embedded_image_name=result.embedded_image_name,
        embedded_image_sha256=result.embedded_image_sha256,
        embedded_image_byte_length=len(
            result.embedded_image_bytes
        ),
        embedded_image_width=result.embedded_image_width,
        embedded_image_height=result.embedded_image_height,
        preprocessing_steps=(
            PHOTO_OCR_PREPROCESSING_STEPS
        ),
        ocr_language=PHOTO_OCR_LANGUAGE,
        ocr_psm=PHOTO_OCR_PSM,
        pypdf_package_version=result.pypdf_package_version,
        pillow_package_version=result.pillow_package_version,
        pytesseract_package_version=(
            result.pytesseract_package_version
        ),
        tesseract_command=result.tesseract_command,
        tesseract_executable_sha256=(
            result.tesseract_executable_sha256
        ),
        tesseract_engine_version=(
            result.tesseract_engine_version
        ),
        transcription_sha256=(
            result.transcription_sha256
        ),
        transcription_byte_length=len(
            transcription_bytes
        ),
    )

    record = replace(
        provisional,
        record_id=derive_record_id(
            provisional
        ),
    )

    validate_derived_transcription_record(
        record
    )

    # C1 commit discipline:
    # no derived-store publication occurs until every source-coordinate,
    # OCR-result, and canonical-record semantic check above has passed.
    embedded_digest = derived_store.put_blob(
        result.embedded_image_bytes
    )

    if embedded_digest != result.embedded_image_sha256:
        raise DerivedTranscriptionServiceError(
            "Published embedded image digest is inconsistent."
        )

    transcription_digest = derived_store.put_blob(
        transcription_bytes
    )

    if transcription_digest != result.transcription_sha256:
        raise DerivedTranscriptionServiceError(
            "Published transcription digest is inconsistent."
        )

    # The record is the immutable commit marker for the already-published
    # content-addressed blobs. Unreferenced blobs are never evidence records.
    derived_store.publish_record(
        record
    )

    loaded = derived_store.load_record(
        case_id=case,
        source_document_instance_id=document,
        page_number=page_number,
        record_id=record.record_id,
    )

    if loaded != record:
        raise DerivedTranscriptionServiceError(
            "Published derived-transcription record did not round-trip exactly."
        )

    if (
        derived_store.read_transcription(record)
        != result.transcription_text
    ):
        raise DerivedTranscriptionServiceError(
            "Published transcription text did not round-trip exactly."
        )

    if (
        derived_store.read_embedded_image(record)
        != result.embedded_image_bytes
    ):
        raise DerivedTranscriptionServiceError(
            "Published embedded image did not round-trip exactly."
        )

    return record


__all__ = [
    "DerivedTranscriptionServiceError",
    "create_photo_derived_transcription",
]
