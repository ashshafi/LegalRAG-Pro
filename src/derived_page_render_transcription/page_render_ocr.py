from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
from importlib.metadata import PackageNotFoundError, version
from io import BytesIO
from pathlib import Path
import re
import shutil
import subprocess

from PIL import Image, ImageFilter, ImageOps
from pdf2image import convert_from_bytes
import pytesseract

from .models import (
    PAGE_RENDER_OCR_DPI,
    PAGE_RENDER_OCR_LANGUAGE,
    PAGE_RENDER_OCR_PREPROCESSING_STEPS,
    PAGE_RENDER_OCR_PSM,
)


class PageRenderOcrError(RuntimeError):
    """Raised when governed whole-page OCR cannot complete."""


@dataclass(frozen=True, slots=True)
class _OcrRuntime:
    pdf2image_package_version: str
    pillow_package_version: str
    pytesseract_package_version: str
    tesseract_command: str
    tesseract_executable_sha256: str
    tesseract_engine_version: str
    poppler_version: str
    installed_languages: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PageRenderOcrResult:
    derived_artifact_bytes: bytes
    derived_artifact_sha256: str
    derived_artifact_width: int
    derived_artifact_height: int

    transcription_text: str
    transcription_sha256: str

    pdf2image_package_version: str
    pillow_package_version: str
    pytesseract_package_version: str

    tesseract_command: str
    tesseract_executable_sha256: str
    tesseract_engine_version: str
    poppler_version: str


def _package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError as exc:
        raise PageRenderOcrError(f"Required package {name!r} is not installed.") from exc


def _resolve_executable(explicit: str | None, fallback_name: str) -> str:
    candidate = explicit or shutil.which(fallback_name)
    if not candidate:
        raise PageRenderOcrError(f"Required executable {fallback_name!r} is unavailable.")
    path = Path(candidate).expanduser().resolve(strict=False)
    if not path.is_file():
        raise PageRenderOcrError(f"Required executable {fallback_name!r} is invalid.")
    return str(path)


def _run_text(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PageRenderOcrError(
            f"Runtime command failed: {Path(command[0]).name}."
        ) from exc
    return completed.stdout


def _discover_runtime(
    *,
    tesseract_cmd: str | None,
    pdfinfo_cmd: str | None,
) -> _OcrRuntime:
    tesseract = _resolve_executable(tesseract_cmd, "tesseract")
    pdfinfo = _resolve_executable(pdfinfo_cmd, "pdfinfo")

    try:
        tesseract_bytes = Path(tesseract).read_bytes()
    except OSError as exc:
        raise PageRenderOcrError("Tesseract executable bytes could not be read.") from exc

    tesseract_version_output = _run_text([tesseract, "--version"])
    first_tesseract_line = tesseract_version_output.splitlines()[0].strip()
    match = re.search(r"tesseract\s+v?([^\s]+)", first_tesseract_line, flags=re.I)
    if match is None:
        raise PageRenderOcrError("Tesseract runtime version could not be parsed.")

    language_output = _run_text([tesseract, "--list-langs"])
    languages = tuple(
        sorted(
            line.strip()
            for line in language_output.splitlines()
            if line.strip() and not line.lower().startswith("list of available languages")
        )
    )

    required = tuple(PAGE_RENDER_OCR_LANGUAGE.split("+"))
    missing = tuple(lang for lang in required if lang not in languages)
    if missing:
        raise PageRenderOcrError(
            "Required OCR language data is unavailable: " + ", ".join(missing)
        )

    poppler_output = _run_text([pdfinfo, "-v"])
    first_poppler_line = poppler_output.splitlines()[0].strip()
    poppler_match = re.search(r"version\s+([^\s]+)", first_poppler_line, flags=re.I)
    if poppler_match is None:
        raise PageRenderOcrError("Poppler runtime version could not be parsed.")

    return _OcrRuntime(
        pdf2image_package_version=_package_version("pdf2image"),
        pillow_package_version=_package_version("Pillow"),
        pytesseract_package_version=_package_version("pytesseract"),
        tesseract_command=tesseract,
        tesseract_executable_sha256=hashlib.sha256(tesseract_bytes).hexdigest(),
        tesseract_engine_version=match.group(1),
        poppler_version=poppler_match.group(1),
        installed_languages=languages,
    )


@contextmanager
def _configured_tesseract(command: str):
    old = pytesseract.pytesseract.tesseract_cmd
    pytesseract.pytesseract.tesseract_cmd = command
    try:
        yield
    finally:
        pytesseract.pytesseract.tesseract_cmd = old


def _png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=9)
    return buffer.getvalue()


def transcribe_rendered_pdf_page(
    pdf_bytes: bytes,
    *,
    page_number: int,
    tesseract_cmd: str | None = None,
    pdfinfo_cmd: str | None = None,
) -> PageRenderOcrResult:
    if type(pdf_bytes) is not bytes or not pdf_bytes:
        raise ValueError("pdf_bytes must be non-empty exact bytes.")
    if type(page_number) is not int or page_number < 1:
        raise ValueError("page_number must be a positive integer.")

    runtime = _discover_runtime(
        tesseract_cmd=tesseract_cmd,
        pdfinfo_cmd=pdfinfo_cmd,
    )

    try:
        pages = convert_from_bytes(
            pdf_bytes,
            dpi=PAGE_RENDER_OCR_DPI,
            first_page=page_number,
            last_page=page_number,
        )
    except Exception as exc:
        raise PageRenderOcrError("Selected PDF page could not be rendered.") from exc

    if len(pages) != 1:
        raise PageRenderOcrError("Selected PDF page did not render to exactly one raster.")

    rendered = pages[0].convert("RGB")
    artifact_bytes = _png_bytes(rendered)
    artifact_sha = hashlib.sha256(artifact_bytes).hexdigest()

    ocr_image = rendered.convert("RGB")
    ocr_image = ImageOps.grayscale(ocr_image)
    ocr_image = ImageOps.autocontrast(ocr_image, cutoff=0)
    ocr_image = ocr_image.filter(ImageFilter.SHARPEN)

    try:
        with _configured_tesseract(runtime.tesseract_command):
            text = pytesseract.image_to_string(
                ocr_image,
                lang=PAGE_RENDER_OCR_LANGUAGE,
                config=f"--psm {PAGE_RENDER_OCR_PSM}",
            )
    except Exception as exc:
        raise PageRenderOcrError("Tesseract page-render OCR failed.") from exc

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise PageRenderOcrError("Page-render OCR returned no usable text.")

    transcription = normalized + "\n"
    transcription_bytes = transcription.encode("utf-8")

    return PageRenderOcrResult(
        derived_artifact_bytes=artifact_bytes,
        derived_artifact_sha256=artifact_sha,
        derived_artifact_width=rendered.width,
        derived_artifact_height=rendered.height,
        transcription_text=transcription,
        transcription_sha256=hashlib.sha256(transcription_bytes).hexdigest(),
        pdf2image_package_version=runtime.pdf2image_package_version,
        pillow_package_version=runtime.pillow_package_version,
        pytesseract_package_version=runtime.pytesseract_package_version,
        tesseract_command=runtime.tesseract_command,
        tesseract_executable_sha256=runtime.tesseract_executable_sha256,
        tesseract_engine_version=runtime.tesseract_engine_version,
        poppler_version=runtime.poppler_version,
    )


__all__ = [
    "PageRenderOcrError",
    "PageRenderOcrResult",
    "transcribe_rendered_pdf_page",
]
