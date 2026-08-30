from __future__ import annotations

import re
from uuid import UUID

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
from .serialization import derive_record_id


_RAW_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA256_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def validate_uuid_text(
    value: str,
    *,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"{field_name} must be canonical UUID text."
        )

    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValueError(
            f"{field_name} must be canonical UUID text."
        ) from exc

    canonical = str(parsed)

    if canonical != value:
        raise ValueError(
            f"{field_name} must be lowercase canonical UUID text."
        )

    return canonical


def validate_raw_sha256(
    value: str,
    *,
    field_name: str,
) -> str:
    if (
        not isinstance(value, str)
        or _RAW_SHA256_RE.fullmatch(value) is None
    ):
        raise ValueError(
            f"{field_name} must be lowercase SHA-256 hex."
        )

    return value


def validate_sha256_id(
    value: str,
    *,
    field_name: str,
) -> str:
    if (
        not isinstance(value, str)
        or _SHA256_ID_RE.fullmatch(value) is None
    ):
        raise ValueError(
            f"{field_name} must be a sha256: identifier."
        )

    return value


def _required_text(
    value: str,
    *,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field_name} must be non-empty text."
        )

    return value


def _positive_int(
    value: int,
    *,
    field_name: str,
) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(
            f"{field_name} must be a positive integer."
        )

    return value


def _nonnegative_int(
    value: int,
    *,
    field_name: str,
) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(
            f"{field_name} must be a non-negative integer."
        )

    return value


def validate_derived_transcription_record(
    value: DerivedTranscriptionRecord,
) -> None:
    if not isinstance(value, DerivedTranscriptionRecord):
        raise ValueError(
            "value must be a DerivedTranscriptionRecord."
        )

    if (
        value.schema_version
        != DERIVED_TRANSCRIPTION_RECORD_SCHEMA_VERSION
    ):
        raise ValueError(
            "Unsupported derived transcription record schema."
        )

    validate_sha256_id(
        value.record_id,
        field_name="record_id",
    )

    validate_uuid_text(
        value.case_id,
        field_name="case_id",
    )

    validate_uuid_text(
        value.source_document_instance_id,
        field_name="source_document_instance_id",
    )

    validate_sha256_id(
        value.source_snapshot_id,
        field_name="source_snapshot_id",
    )

    _required_text(
        value.original_filename,
        field_name="original_filename",
    )

    validate_raw_sha256(
        value.original_blob_sha256,
        field_name="original_blob_sha256",
    )

    _positive_int(
        value.original_byte_length,
        field_name="original_byte_length",
    )

    _positive_int(
        value.page_number,
        field_name="page_number",
    )

    if value.source_extraction_method not in {
        "pypdf_text",
        "page_ocr",
    }:
        raise ValueError(
            "source_extraction_method is unsupported."
        )

    validate_raw_sha256(
        value.source_page_text_sha256,
        field_name="source_page_text_sha256",
    )

    _nonnegative_int(
        value.source_page_text_byte_length,
        field_name="source_page_text_byte_length",
    )

    if value.profile_id != PHOTO_OCR_PROFILE_ID:
        raise ValueError(
            "profile_id is not the governed photo OCR profile."
        )

    if (
        value.profile_schema_version
        != PHOTO_OCR_PROFILE_SCHEMA_VERSION
    ):
        raise ValueError(
            "profile_schema_version is unsupported."
        )

    if value.image_selection_id != PHOTO_IMAGE_SELECTION_ID:
        raise ValueError(
            "image_selection_id is unsupported."
        )

    _required_text(
        value.embedded_image_name,
        field_name="embedded_image_name",
    )

    validate_raw_sha256(
        value.embedded_image_sha256,
        field_name="embedded_image_sha256",
    )

    _positive_int(
        value.embedded_image_byte_length,
        field_name="embedded_image_byte_length",
    )

    _positive_int(
        value.embedded_image_width,
        field_name="embedded_image_width",
    )

    _positive_int(
        value.embedded_image_height,
        field_name="embedded_image_height",
    )

    if (
        value.preprocessing_steps
        != PHOTO_OCR_PREPROCESSING_STEPS
    ):
        raise ValueError(
            "preprocessing_steps do not match the governed profile."
        )

    if value.ocr_language != PHOTO_OCR_LANGUAGE:
        raise ValueError(
            "ocr_language must be 'eng'."
        )

    if value.ocr_psm != PHOTO_OCR_PSM:
        raise ValueError(
            "ocr_psm must be 6."
        )

    for field_name in (
        "pypdf_package_version",
        "pillow_package_version",
        "pytesseract_package_version",
        "tesseract_command",
        "tesseract_engine_version",
    ):
        _required_text(
            getattr(value, field_name),
            field_name=field_name,
        )

    validate_raw_sha256(
        value.tesseract_executable_sha256,
        field_name="tesseract_executable_sha256",
    )

    validate_raw_sha256(
        value.transcription_sha256,
        field_name="transcription_sha256",
    )

    _positive_int(
        value.transcription_byte_length,
        field_name="transcription_byte_length",
    )

    expected_id = derive_record_id(value)

    if value.record_id != expected_id:
        raise ValueError(
            "record_id does not match the canonical record payload."
        )


__all__ = [
    "validate_derived_transcription_record",
    "validate_raw_sha256",
    "validate_sha256_id",
    "validate_uuid_text",
]
