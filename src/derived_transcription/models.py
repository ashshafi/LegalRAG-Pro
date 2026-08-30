from __future__ import annotations

from dataclasses import dataclass
from typing import Final


DERIVED_TRANSCRIPTION_RECORD_SCHEMA_VERSION: Final[str] = (
    "derived-transcription-record/1.0"
)

PHOTO_OCR_PROFILE_ID: Final[str] = "photo-embedded-image-ocr/1.0"
PHOTO_OCR_PROFILE_SCHEMA_VERSION: Final[str] = "1.0"

PHOTO_IMAGE_SELECTION_ID: Final[str] = (
    "pypdf-page-single-embedded-image/1.0"
)

PHOTO_OCR_LANGUAGE: Final[str] = "eng"
PHOTO_OCR_PSM: Final[int] = 6

PHOTO_OCR_PREPROCESSING_STEPS: Final[tuple[str, ...]] = (
    "PIL.Image.convert:RGB",
    "PIL.ImageOps.grayscale",
    "PIL.ImageOps.autocontrast:cutoff=0",
    "PIL.ImageFilter.SHARPEN",
)


@dataclass(frozen=True, slots=True)
class DerivedTranscriptionRecord:
    schema_version: str
    record_id: str

    case_id: str
    source_document_instance_id: str
    source_snapshot_id: str

    original_filename: str
    original_blob_sha256: str
    original_byte_length: int

    page_number: int
    source_extraction_method: str
    source_page_text_sha256: str
    source_page_text_byte_length: int

    profile_id: str
    profile_schema_version: str
    image_selection_id: str

    embedded_image_name: str
    embedded_image_sha256: str
    embedded_image_byte_length: int
    embedded_image_width: int
    embedded_image_height: int

    preprocessing_steps: tuple[str, ...]

    ocr_language: str
    ocr_psm: int

    pypdf_package_version: str
    pillow_package_version: str
    pytesseract_package_version: str

    tesseract_command: str
    tesseract_executable_sha256: str
    tesseract_engine_version: str

    transcription_sha256: str
    transcription_byte_length: int


__all__ = [
    "DERIVED_TRANSCRIPTION_RECORD_SCHEMA_VERSION",
    "PHOTO_IMAGE_SELECTION_ID",
    "PHOTO_OCR_LANGUAGE",
    "PHOTO_OCR_PREPROCESSING_STEPS",
    "PHOTO_OCR_PROFILE_ID",
    "PHOTO_OCR_PROFILE_SCHEMA_VERSION",
    "PHOTO_OCR_PSM",
    "DerivedTranscriptionRecord",
]
