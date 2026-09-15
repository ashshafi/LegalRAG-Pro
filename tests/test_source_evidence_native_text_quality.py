from __future__ import annotations

import inspect

from source_evidence import capture, extraction
from source_evidence.models import (
    EXTRACTION_PROFILE_ID,
    QUALITY_GATED_EXTRACTION_PROFILE_ID,
    QUALITY_GATED_EXTRACTION_PROFILE_SCHEMA_VERSION,
)
from source_evidence.validation import validate_extraction_profile


def test_outlook_glyph_index_text_falls_below_native_quality_gate() -> None:
    broken = " ".join(f"/{index % 113}" for index in range(1000))
    broken += " \u25a1 \u25a1 \u25a1 \u25a1"
    assert extraction._native_text_is_usable(broken) is False


def test_normal_english_stays_native() -> None:
    text = (
        "Dear Ms England, I write further to the Respondent's disclosure "
        "position and the documents subsequently disclosed by CACI."
    )
    assert extraction._native_text_is_usable(text) is True


def test_unicode_letters_stay_native() -> None:
    assert extraction._native_text_is_usable("یہ ایک قانونی دستاویز ہے") is True


def test_numeric_material_without_pdf_glyph_tokens_stays_native() -> None:
    text = "2026-09-15\n12345.67\n89012.34\n100 200 300"
    assert extraction._native_text_is_usable(text) is True


def test_quality_gate_selects_successor_profile() -> None:
    profile = extraction._build_profile(
        pypdf_version="6.14.2",
        ocr_runtime=None,
        quality_gate_triggered=True,
    )
    assert profile.profile_id == QUALITY_GATED_EXTRACTION_PROFILE_ID
    assert (
        profile.profile_schema_version
        == QUALITY_GATED_EXTRACTION_PROFILE_SCHEMA_VERSION
    )
    validate_extraction_profile(profile, requires_ocr=False)


def test_ordinary_profile_identity_is_unchanged() -> None:
    profile = extraction._build_profile(
        pypdf_version="6.14.2",
        ocr_runtime=None,
    )
    assert profile.profile_id == EXTRACTION_PROFILE_ID


def test_capture_uses_manifest_profile_identity() -> None:
    source = inspect.getsource(capture)
    assert "extraction_profile_id=manifest.extraction_profile.profile_id" in source
    assert "extraction_profile_id=EXTRACTION_PROFILE_ID" not in source
