"""Deterministic page extraction from one immutable PDF byte sequence."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import metadata
from io import BytesIO
from pathlib import Path
from typing import Final, Iterator

import pytesseract
from pdf2image import convert_from_bytes
from pypdf import PdfReader

from .models import (
    EXTRACTION_PROFILE_ID,
    EXTRACTION_PROFILE_SCHEMA_VERSION,
    ExtractionMethod,
    ExtractionProfile,
)
from .validation import validate_extraction_profile

_OCR_LANGUAGE: Final[str] = "eng"
_OCR_CONFIG: Final[str] = ""
_OCR_DPI: Final[int] = 200
_TESSERACT_ENV: Final[str] = "LEGALRAG_TESSERACT_CMD"
_POPPLER_ENV: Final[str] = "LEGALRAG_POPPLER_PATH"
_VERSION_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?<!\d)(\d+(?:\.\d+)+)")


class SourceEvidenceExtractionError(RuntimeError):
    """Raised when exact governed PDF page extraction cannot be completed."""


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    """Transient exact page text plus its governed extraction method."""

    page_number: int
    extraction_method: ExtractionMethod
    text: str


@dataclass(frozen=True, slots=True)
class PdfExtractionResult:
    """Transient ordered page extraction plus the exact runtime profile."""

    extraction_profile: ExtractionProfile
    pages: tuple[ExtractedPage, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "pages", tuple(self.pages))


@dataclass(frozen=True, slots=True)
class _OcrRuntime:
    pdf2image_package_version: str
    pytesseract_package_version: str
    tesseract_engine_version: str
    poppler_version: str
    tesseract_cmd: str | None
    poppler_path: str | None


def _package_version(distribution: str) -> str:
    try:
        value = metadata.version(distribution)
    except metadata.PackageNotFoundError as exc:
        raise SourceEvidenceExtractionError(
            f"Required extraction runtime package {distribution!r} is unavailable."
        ) from exc
    if not value:
        raise SourceEvidenceExtractionError(
            f"Required extraction runtime package {distribution!r} has no version."
        )
    return value


@contextmanager
def _configured_tesseract(command: str | None) -> Iterator[None]:
    if command is None:
        yield
        return
    old = pytesseract.pytesseract.tesseract_cmd
    pytesseract.pytesseract.tesseract_cmd = command
    try:
        yield
    finally:
        pytesseract.pytesseract.tesseract_cmd = old


def _normalise_runtime_version(value: object, *, runtime_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise SourceEvidenceExtractionError(
            f"{runtime_name} runtime version could not be established."
        )
    return text


def _poppler_executable(poppler_path: str | None) -> str:
    executable_name = "pdftoppm.exe" if os.name == "nt" else "pdftoppm"
    if poppler_path:
        candidate = Path(poppler_path) / executable_name
        if not candidate.is_file():
            raise SourceEvidenceExtractionError(
                "Configured Poppler pdftoppm executable is unavailable."
            )
        return str(candidate)
    found = shutil.which("pdftoppm")
    if not found:
        raise SourceEvidenceExtractionError(
            "Poppler pdftoppm executable is unavailable for governed OCR."
        )
    return found


def _discover_poppler_version(poppler_path: str | None) -> str:
    executable = _poppler_executable(poppler_path)
    try:
        completed = subprocess.run(
            [executable, "-v"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SourceEvidenceExtractionError(
            "Poppler runtime version could not be established."
        ) from exc
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    match = _VERSION_PATTERN.search(output)
    if match is None:
        raise SourceEvidenceExtractionError(
            "Poppler runtime version could not be established."
        )
    return match.group(1)


def _discover_ocr_runtime() -> _OcrRuntime:
    tesseract_cmd = os.environ.get(_TESSERACT_ENV) or None
    poppler_path = os.environ.get(_POPPLER_ENV) or None
    with _configured_tesseract(tesseract_cmd):
        try:
            tesseract_version = pytesseract.get_tesseract_version()
        except Exception as exc:  # pytesseract raises several platform-specific types
            raise SourceEvidenceExtractionError(
                "Tesseract runtime version could not be established."
            ) from exc
    return _OcrRuntime(
        pdf2image_package_version=_package_version("pdf2image"),
        pytesseract_package_version=_package_version("pytesseract"),
        tesseract_engine_version=_normalise_runtime_version(
            tesseract_version,
            runtime_name="Tesseract",
        ),
        poppler_version=_discover_poppler_version(poppler_path),
        tesseract_cmd=tesseract_cmd,
        poppler_path=poppler_path,
    )


def _ocr_page(pdf_bytes: bytes, page_number: int, runtime: _OcrRuntime) -> str:
    try:
        images = convert_from_bytes(
            pdf_bytes,
            dpi=_OCR_DPI,
            first_page=page_number,
            last_page=page_number,
            poppler_path=runtime.poppler_path,
        )
    except Exception as exc:  # pdf2image wraps Poppler errors in several exception types
        raise SourceEvidenceExtractionError(
            f"Page {page_number} could not be rendered for governed OCR."
        ) from exc
    if len(images) != 1:
        raise SourceEvidenceExtractionError(
            f"Page {page_number} OCR rendering did not return exactly one page image."
        )
    with _configured_tesseract(runtime.tesseract_cmd):
        try:
            text = pytesseract.image_to_string(
                images[0],
                lang=_OCR_LANGUAGE,
                config=_OCR_CONFIG,
            )
        except Exception as exc:
            raise SourceEvidenceExtractionError(
                f"Page {page_number} governed OCR failed."
            ) from exc
    if not isinstance(text, str):
        raise SourceEvidenceExtractionError(
            f"Page {page_number} governed OCR returned invalid text."
        )
    return text


def _build_profile(*, pypdf_version: str, ocr_runtime: _OcrRuntime | None) -> ExtractionProfile:
    profile = ExtractionProfile(
        profile_id=EXTRACTION_PROFILE_ID,
        profile_schema_version=EXTRACTION_PROFILE_SCHEMA_VERSION,
        pypdf_package_version=pypdf_version,
        pdf2image_package_version=(
            ocr_runtime.pdf2image_package_version if ocr_runtime else None
        ),
        pytesseract_package_version=(
            ocr_runtime.pytesseract_package_version if ocr_runtime else None
        ),
        tesseract_engine_version=(
            ocr_runtime.tesseract_engine_version if ocr_runtime else None
        ),
        poppler_version=ocr_runtime.poppler_version if ocr_runtime else None,
        ocr_language=_OCR_LANGUAGE,
        ocr_config=_OCR_CONFIG,
        ocr_dpi=_OCR_DPI,
    )
    validate_extraction_profile(profile, requires_ocr=ocr_runtime is not None)
    return profile


def extract_pdf_pages(pdf_bytes: bytes) -> PdfExtractionResult:
    """Extract every PDF page from one exact immutable byte sequence."""

    if type(pdf_bytes) is not bytes:
        raise TypeError("pdf_bytes must be exact bytes.")
    if not pdf_bytes:
        raise SourceEvidenceExtractionError("PDF source bytes must not be empty.")

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        page_count = len(reader.pages)
    except Exception as exc:
        raise SourceEvidenceExtractionError(
            "PDF source bytes could not be parsed by the governed pypdf runtime."
        ) from exc
    if page_count < 1:
        raise SourceEvidenceExtractionError("PDF source must contain at least one page.")

    pypdf_version = _package_version("pypdf")
    ocr_runtime: _OcrRuntime | None = None
    extracted: list[ExtractedPage] = []

    for page_number, page in enumerate(reader.pages, start=1):
        try:
            pypdf_text = page.extract_text()
        except Exception:
            pypdf_text = None

        if isinstance(pypdf_text, str) and pypdf_text.strip():
            extracted.append(
                ExtractedPage(
                    page_number=page_number,
                    extraction_method=ExtractionMethod.PYPDF_TEXT,
                    text=pypdf_text,
                )
            )
            continue

        if ocr_runtime is None:
            ocr_runtime = _discover_ocr_runtime()
        ocr_text = _ocr_page(pdf_bytes, page_number, ocr_runtime)
        extracted.append(
            ExtractedPage(
                page_number=page_number,
                extraction_method=ExtractionMethod.PAGE_OCR,
                text=ocr_text,
            )
        )

    profile = _build_profile(pypdf_version=pypdf_version, ocr_runtime=ocr_runtime)
    return PdfExtractionResult(extraction_profile=profile, pages=tuple(extracted))


__all__ = [
    "ExtractedPage",
    "PdfExtractionResult",
    "SourceEvidenceExtractionError",
    "extract_pdf_pages",
]
