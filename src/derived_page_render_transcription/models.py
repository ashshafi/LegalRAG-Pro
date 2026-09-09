from __future__ import annotations

from dataclasses import dataclass
from typing import Final


DERIVED_PAGE_RENDER_TRANSCRIPTION_RECORD_SCHEMA_VERSION: Final[str] = (
    "derived-page-render-transcription-record/1.0"
)

PAGE_RENDER_OCR_PROFILE_ID: Final[str] = "page-render-ocr/1.0"
PAGE_RENDER_OCR_PROFILE_SCHEMA_VERSION: Final[str] = "1.0"
PAGE_RENDER_ARTIFACT_ROLE: Final[str] = "rendered_pdf_page"

PAGE_RENDER_OCR_DPI: Final[int] = 200
PAGE_RENDER_OCR_LANGUAGE: Final[str] = "eng+urd"
PAGE_RENDER_OCR_PSM: Final[int] = 6

PAGE_RENDER_OCR_PREPROCESSING_STEPS: Final[tuple[str, ...]] = (
    "PIL.Image.convert:RGB",
    "PIL.ImageOps.grayscale",
    "PIL.ImageOps.autocontrast:cutoff=0",
    "PIL.ImageFilter.SHARPEN",
)


@dataclass(frozen=True, slots=True)
class PageRenderTranscriptionRecord:
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

    artifact_role: str
    derived_artifact_sha256: str
    derived_artifact_byte_length: int
    derived_artifact_width: int
    derived_artifact_height: int
    render_dpi: int

    preprocessing_steps: tuple[str, ...]

    ocr_language: str
    ocr_psm: int

    pdf2image_package_version: str
    pillow_package_version: str
    pytesseract_package_version: str

    tesseract_command: str
    tesseract_executable_sha256: str
    tesseract_engine_version: str
    poppler_version: str

    transcription_sha256: str
    transcription_byte_length: int


__all__ = [
    "DERIVED_PAGE_RENDER_TRANSCRIPTION_RECORD_SCHEMA_VERSION",
    "PAGE_RENDER_ARTIFACT_ROLE",
    "PAGE_RENDER_OCR_DPI",
    "PAGE_RENDER_OCR_LANGUAGE",
    "PAGE_RENDER_OCR_PREPROCESSING_STEPS",
    "PAGE_RENDER_OCR_PROFILE_ID",
    "PAGE_RENDER_OCR_PROFILE_SCHEMA_VERSION",
    "PAGE_RENDER_OCR_PSM",
    "PageRenderTranscriptionRecord",
]
