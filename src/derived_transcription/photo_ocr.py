from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
from importlib.metadata import (
    PackageNotFoundError,
    version,
)
from io import BytesIO
import os
from pathlib import Path
import shutil
from typing import Iterator

from PIL import ImageFilter, ImageOps
import pytesseract
from pypdf import PdfReader

from .models import (
    PHOTO_OCR_LANGUAGE,
    PHOTO_OCR_PSM,
)


_TESSERACT_ENV = "LEGALRAG_TESSERACT_CMD"


class PhotoOcrError(RuntimeError):
    """Raised when governed photo-page OCR cannot complete."""


@dataclass(frozen=True, slots=True)
class PhotoOcrResult:
    embedded_image_name: str
    embedded_image_bytes: bytes
    embedded_image_sha256: str
    embedded_image_width: int
    embedded_image_height: int

    transcription_text: str
    transcription_sha256: str

    pypdf_package_version: str
    pillow_package_version: str
    pytesseract_package_version: str

    tesseract_command: str
    tesseract_executable_sha256: str
    tesseract_engine_version: str


def _package_version(
    package_name: str,
) -> str:
    try:
        value = version(
            package_name
        )
    except PackageNotFoundError as exc:
        raise PhotoOcrError(
            f"Runtime package version is unavailable: {package_name}."
        ) from exc

    if not isinstance(value, str) or not value.strip():
        raise PhotoOcrError(
            f"Runtime package version is invalid: {package_name}."
        )

    return value.strip()


def _tesseract_executable_identity(
    command: str | None,
) -> tuple[str, str]:
    configured = (
        command
        or os.environ.get(_TESSERACT_ENV)
        or pytesseract.pytesseract.tesseract_cmd
    )

    if not isinstance(configured, str) or not configured.strip():
        raise PhotoOcrError(
            "Tesseract command is unavailable."
        )

    raw = configured.strip()

    candidate = Path(raw)

    if candidate.is_file():
        resolved = candidate.resolve()
    else:
        located = shutil.which(raw)

        if located is None:
            raise PhotoOcrError(
                "Tesseract executable could not be resolved."
            )

        resolved = Path(
            located
        ).resolve()

    try:
        executable_bytes = resolved.read_bytes()
    except OSError as exc:
        raise PhotoOcrError(
            "Tesseract executable could not be read for identity verification."
        ) from exc

    digest = hashlib.sha256(
        executable_bytes
    ).hexdigest()

    return str(resolved), digest


@contextmanager
def _configured_tesseract(
    command: str,
) -> Iterator[None]:
    old = pytesseract.pytesseract.tesseract_cmd

    pytesseract.pytesseract.tesseract_cmd = command

    try:
        yield
    finally:
        pytesseract.pytesseract.tesseract_cmd = old


def transcribe_embedded_photo_page(
    pdf_bytes: bytes,
    *,
    page_number: int,
    tesseract_cmd: str | None = None,
) -> PhotoOcrResult:
    """OCR exactly one embedded raster image from one PDF page."""

    if type(pdf_bytes) is not bytes:
        raise TypeError(
            "pdf_bytes must be exact bytes."
        )

    if not pdf_bytes:
        raise PhotoOcrError(
            "PDF source bytes must not be empty."
        )

    if type(page_number) is not int or page_number < 1:
        raise ValueError(
            "page_number must be a positive integer."
        )

    try:
        reader = PdfReader(
            BytesIO(pdf_bytes)
        )
    except Exception as exc:
        raise PhotoOcrError(
            "PDF source bytes could not be parsed."
        ) from exc

    if page_number > len(reader.pages):
        raise PhotoOcrError(
            "Requested source page is absent."
        )

    page = reader.pages[
        page_number - 1
    ]

    try:
        images = tuple(
            page.images
        )
    except Exception as exc:
        raise PhotoOcrError(
            "Embedded PDF page images could not be enumerated."
        ) from exc

    if len(images) != 1:
        raise PhotoOcrError(
            "Governed photo OCR requires exactly one embedded image on the selected page."
        )

    embedded = images[0]

    image_name = getattr(
        embedded,
        "name",
        None,
    )

    if not isinstance(image_name, str) or not image_name.strip():
        raise PhotoOcrError(
            "Embedded image name is unavailable."
        )

    raw_data = getattr(
        embedded,
        "data",
        None,
    )

    if not isinstance(
        raw_data,
        (bytes, bytearray, memoryview),
    ):
        raise PhotoOcrError(
            "Embedded image bytes are unavailable."
        )

    embedded_bytes = bytes(
        raw_data
    )

    if not embedded_bytes:
        raise PhotoOcrError(
            "Embedded image bytes must not be empty."
        )

    try:
        image = embedded.image.convert(
            "RGB"
        )
    except Exception as exc:
        raise PhotoOcrError(
            "Embedded image could not be decoded."
        ) from exc

    width, height = image.size

    if (
        type(width) is not int
        or type(height) is not int
        or width < 1
        or height < 1
    ):
        raise PhotoOcrError(
            "Embedded image dimensions are invalid."
        )

    grayscale = ImageOps.grayscale(
        image
    )

    processed = ImageOps.autocontrast(
        grayscale
    )

    processed = processed.filter(
        ImageFilter.SHARPEN
    )

    resolved_command, executable_sha256 = (
        _tesseract_executable_identity(
            tesseract_cmd
        )
    )

    with _configured_tesseract(
        resolved_command
    ):
        try:
            engine_version = str(
                pytesseract.get_tesseract_version()
            ).strip()
        except Exception as exc:
            raise PhotoOcrError(
                "Tesseract runtime version could not be established."
            ) from exc

        if not engine_version:
            raise PhotoOcrError(
                "Tesseract runtime version is empty."
            )

        try:
            text = pytesseract.image_to_string(
                processed,
                lang=PHOTO_OCR_LANGUAGE,
                config=f"--psm {PHOTO_OCR_PSM}",
            )
        except Exception as exc:
            raise PhotoOcrError(
                "Governed embedded-photo OCR failed."
            ) from exc

    if not isinstance(text, str):
        raise PhotoOcrError(
            "Governed OCR returned invalid text."
        )

    if not text.strip():
        raise PhotoOcrError(
            "Governed embedded-photo OCR returned no usable text."
        )

    transcription_bytes = text.encode(
        "utf-8"
    )

    return PhotoOcrResult(
        embedded_image_name=image_name,
        embedded_image_bytes=embedded_bytes,
        embedded_image_sha256=hashlib.sha256(
            embedded_bytes
        ).hexdigest(),
        embedded_image_width=width,
        embedded_image_height=height,
        transcription_text=text,
        transcription_sha256=hashlib.sha256(
            transcription_bytes
        ).hexdigest(),
        pypdf_package_version=_package_version(
            "pypdf"
        ),
        pillow_package_version=_package_version(
            "Pillow"
        ),
        pytesseract_package_version=_package_version(
            "pytesseract"
        ),
        tesseract_command=resolved_command,
        tesseract_executable_sha256=executable_sha256,
        tesseract_engine_version=engine_version,
    )


__all__ = [
    "PhotoOcrError",
    "PhotoOcrResult",
    "transcribe_embedded_photo_page",
]
