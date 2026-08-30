"""Governed additive derived-transcription foundation."""

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
    PhotoOcrError,
    PhotoOcrResult,
    transcribe_embedded_photo_page,
)
from .service import (
    DerivedTranscriptionServiceError,
    create_photo_derived_transcription,
)
from .store import (
    DerivedTranscriptionStore,
    DerivedTranscriptionStoreError,
)

__all__ = [
    "DERIVED_TRANSCRIPTION_RECORD_SCHEMA_VERSION",
    "PHOTO_IMAGE_SELECTION_ID",
    "PHOTO_OCR_LANGUAGE",
    "PHOTO_OCR_PREPROCESSING_STEPS",
    "PHOTO_OCR_PROFILE_ID",
    "PHOTO_OCR_PROFILE_SCHEMA_VERSION",
    "PHOTO_OCR_PSM",
    "DerivedTranscriptionRecord",
    "DerivedTranscriptionServiceError",
    "DerivedTranscriptionStore",
    "DerivedTranscriptionStoreError",
    "PhotoOcrError",
    "PhotoOcrResult",
    "create_photo_derived_transcription",
    "transcribe_embedded_photo_page",
]
