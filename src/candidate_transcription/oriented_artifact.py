"""Deterministic orientation-normalized image artifacts for candidate transcription."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import BytesIO
import importlib.metadata
import re

from PIL import Image
from pypdf import PdfReader


RECEIPT_SCHEMA_VERSION = "orientation-normalized-artifact-receipt/1.0"
ARTIFACT_ROLE = "orientation_normalized_embedded_raster/1.0"
PROFILE_ID = "embedded-raster-stitch-rotate-cw-png/1.0"
PROFILE_SCHEMA_VERSION = "1.0"
ORIENTATION_ROTATE_90_CW = "ROTATE_90_CW"
MEDIA_TYPE = "image/png"
PNG_COMPRESS_LEVEL = 9

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


class OrientedArtifactError(RuntimeError):
    """Raised when deterministic orientation-artifact construction fails."""


@dataclass(frozen=True)
class EmbeddedRasterSpec:
    name: str
    sha256: str
    width: int
    height: int


@dataclass(frozen=True)
class OrientedArtifactReceipt:
    schema_version: str
    artifact_role: str
    profile_id: str
    profile_schema_version: str
    orientation: str
    media_type: str
    page_number: int
    source_pdf_sha256: str
    source_pdf_byte_length: int
    source_strip_order: tuple[str, ...]
    source_strips: tuple[EmbeddedRasterSpec, ...]
    stitched_width: int
    stitched_height: int
    stitched_raw_pixel_sha256: str
    rotated_raw_pixel_sha256: str
    artifact_bytes: bytes
    artifact_sha256: str
    artifact_byte_length: int
    artifact_width: int
    artifact_height: int
    pillow_version: str
    pypdf_version: str


def _fail(message: str) -> None:
    raise OrientedArtifactError(message)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _positive_int(name: str, value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        _fail(f"{name} must be a positive integer.")
    return value


def _validate_specs(
    *,
    embedded_rasters: tuple[EmbeddedRasterSpec, ...],
    strip_order: tuple[str, ...],
) -> tuple[dict[str, EmbeddedRasterSpec], tuple[str, ...]]:
    if not isinstance(embedded_rasters, tuple) or not embedded_rasters:
        _fail("embedded_rasters must be a non-empty tuple.")

    if not isinstance(strip_order, tuple) or not strip_order:
        _fail("strip_order must be a non-empty tuple.")

    specs: dict[str, EmbeddedRasterSpec] = {}

    for spec in embedded_rasters:
        if not isinstance(spec, EmbeddedRasterSpec):
            _fail("embedded_rasters must contain EmbeddedRasterSpec values.")
        if not isinstance(spec.name, str) or not spec.name.strip():
            _fail("embedded raster name must be non-empty text.")
        if spec.name != spec.name.strip():
            _fail("embedded raster name must not contain surrounding whitespace.")
        if _SHA256_HEX.fullmatch(spec.sha256) is None:
            _fail("embedded raster SHA-256 must be lowercase hexadecimal.")
        _positive_int("embedded raster width", spec.width)
        _positive_int("embedded raster height", spec.height)

        if spec.name in specs:
            _fail(f"duplicate embedded raster specification: {spec.name}")
        specs[spec.name] = spec

    if any(not isinstance(name, str) or not name for name in strip_order):
        _fail("strip_order must contain non-empty names.")

    if len(set(strip_order)) != len(strip_order):
        _fail("strip_order contains duplicate names.")

    if set(strip_order) != set(specs):
        _fail("strip_order must match the embedded raster specification set exactly.")

    widths = {spec.width for spec in specs.values()}
    if len(widths) != 1:
        _fail("all embedded raster strips must have one exact width.")

    return specs, strip_order


def _encode_png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(
        buffer,
        format="PNG",
        optimize=False,
        compress_level=PNG_COMPRESS_LEVEL,
    )
    return buffer.getvalue()


def build_orientation_normalized_artifact(
    *,
    pdf_bytes: bytes,
    page_number: int,
    embedded_rasters: tuple[EmbeddedRasterSpec, ...],
    strip_order: tuple[str, ...],
    orientation: str,
) -> OrientedArtifactReceipt:
    """Build one deterministic in-memory orientation-normalized PNG artifact."""

    if not isinstance(pdf_bytes, bytes) or not pdf_bytes:
        _fail("pdf_bytes must be non-empty bytes.")

    _positive_int("page_number", page_number)

    if orientation != ORIENTATION_ROTATE_90_CW:
        _fail("orientation must be ROTATE_90_CW for this profile.")

    specs, order = _validate_specs(
        embedded_rasters=embedded_rasters,
        strip_order=strip_order,
    )

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
    except Exception as exc:
        raise OrientedArtifactError("PDF parsing failed.") from exc

    if page_number > len(reader.pages):
        _fail("page_number is outside the supplied PDF.")

    page = reader.pages[page_number - 1]
    decoded: dict[str, Image.Image] = {}

    for embedded in page.images:
        raw_name = getattr(embedded, "name", None)
        data = getattr(embedded, "data", None)

        if not isinstance(raw_name, str) or not isinstance(data, bytes):
            continue

        name = raw_name.rsplit(".", 1)[0]
        if name not in specs:
            continue

        if name in decoded:
            _fail(f"duplicate expected embedded raster found in PDF: {name}")

        spec = specs[name]
        if _sha256(data) != spec.sha256:
            _fail(f"embedded raster SHA-256 differs for {name}.")

        try:
            with Image.open(BytesIO(data)) as image:
                rgb = image.convert("RGB").copy()
        except Exception as exc:
            raise OrientedArtifactError(
                f"embedded raster decoding failed for {name}."
            ) from exc

        if rgb.size != (spec.width, spec.height):
            _fail(f"embedded raster dimensions differ for {name}.")

        decoded[name] = rgb

    if set(decoded) != set(specs):
        missing = tuple(name for name in order if name not in decoded)
        _fail(f"expected embedded raster set is incomplete: {missing}")

    stitched_width = specs[order[0]].width
    stitched_height = sum(specs[name].height for name in order)

    stitched = Image.new("RGB", (stitched_width, stitched_height), "white")
    cursor = 0
    for name in order:
        stitched.paste(decoded[name], (0, cursor))
        cursor += decoded[name].height

    stitched_raw_pixel_sha256 = _sha256(stitched.tobytes())

    rotated = stitched.rotate(-90, expand=True)
    rotated_raw_pixel_sha256 = _sha256(rotated.tobytes())

    png_first = _encode_png(rotated)
    png_second = _encode_png(rotated)

    if png_first != png_second:
        _fail("repeated PNG encoding was not byte-deterministic.")

    artifact_sha256 = _sha256(png_first)

    return OrientedArtifactReceipt(
        schema_version=RECEIPT_SCHEMA_VERSION,
        artifact_role=ARTIFACT_ROLE,
        profile_id=PROFILE_ID,
        profile_schema_version=PROFILE_SCHEMA_VERSION,
        orientation=ORIENTATION_ROTATE_90_CW,
        media_type=MEDIA_TYPE,
        page_number=page_number,
        source_pdf_sha256=_sha256(pdf_bytes),
        source_pdf_byte_length=len(pdf_bytes),
        source_strip_order=order,
        source_strips=tuple(specs[name] for name in order),
        stitched_width=stitched.width,
        stitched_height=stitched.height,
        stitched_raw_pixel_sha256=stitched_raw_pixel_sha256,
        rotated_raw_pixel_sha256=rotated_raw_pixel_sha256,
        artifact_bytes=png_first,
        artifact_sha256=artifact_sha256,
        artifact_byte_length=len(png_first),
        artifact_width=rotated.width,
        artifact_height=rotated.height,
        pillow_version=importlib.metadata.version("Pillow"),
        pypdf_version=importlib.metadata.version("pypdf"),
    )
