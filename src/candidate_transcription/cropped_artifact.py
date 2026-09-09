"""Deterministic provider-neutral crops of a governed parent image artifact.

This module creates one immutable in-memory crop receipt from exact caller-supplied
parent artifact bytes and an exact bounding box.  It does not perform provider
calls, persistence, search activation, OCR, or source-document access.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib import metadata
from io import BytesIO
import re

from PIL import Image


CROPPED_ARTIFACT_SCHEMA_VERSION = "cropped-artifact-receipt/1.0"
ARTIFACT_ROLE = "targeted_cropped_artifact/1.0"
PROFILE_ID = "orientation-parent-bbox-crop-png/1.0"
PROFILE_SCHEMA_VERSION = "1.0"
MEDIA_TYPE = "image/png"
PNG_COMPRESS_LEVEL = 9

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CROP_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


class CroppedArtifactError(RuntimeError):
    """Raised when deterministic cropped-artifact construction cannot be proven."""


@dataclass(frozen=True)
class CroppedArtifactReceipt:
    schema_version: str
    artifact_role: str
    profile_id: str
    profile_schema_version: str
    media_type: str
    parent_artifact_sha256: str
    parent_artifact_byte_length: int
    parent_artifact_width: int
    parent_artifact_height: int
    crop_name: str
    bbox: tuple[int, int, int, int]
    raw_pixel_sha256: str
    artifact_bytes: bytes
    artifact_sha256: str
    artifact_byte_length: int
    artifact_width: int
    artifact_height: int
    pillow_version: str


def _fail(message: str) -> None:
    raise CroppedArtifactError(message)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _fail(f"{field_name} must be a positive integer.")
    return value


def _parent_sha256(value: object) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail("parent_artifact_sha256 must be exact lower-case SHA-256 hex.")
    return value


def _crop_name(value: object) -> str:
    if not isinstance(value, str) or _CROP_NAME_RE.fullmatch(value) is None:
        _fail("crop_name must match the governed upper-case identifier profile.")
    return value


def _bbox(
    value: object,
    *,
    parent_width: int,
    parent_height: int,
) -> tuple[int, int, int, int]:
    if type(value) is not tuple or len(value) != 4:
        _fail("bbox must be an exact four-integer tuple.")

    if any(isinstance(item, bool) or not isinstance(item, int) for item in value):
        _fail("bbox must contain exact integers.")

    left, top, right, bottom = value

    if left < 0 or top < 0:
        _fail("bbox origin must be non-negative.")
    if right <= left or bottom <= top:
        _fail("bbox must have positive width and height.")
    if right > parent_width or bottom > parent_height:
        _fail("bbox exceeds parent artifact bounds.")

    return left, top, right, bottom


def _encode_png_twice(image: Image.Image) -> bytes:
    def encode() -> bytes:
        output = BytesIO()
        image.save(
            output,
            format="PNG",
            optimize=False,
            compress_level=PNG_COMPRESS_LEVEL,
        )
        return output.getvalue()

    first = encode()
    second = encode()

    if first != second:
        _fail("Deterministic PNG repeat encoding differed.")

    return first


def build_cropped_artifact(
    *,
    parent_artifact_bytes: bytes,
    parent_artifact_sha256: str,
    parent_artifact_width: int,
    parent_artifact_height: int,
    crop_name: str,
    bbox: tuple[int, int, int, int],
) -> CroppedArtifactReceipt:
    """Build one exact deterministic crop from one exact parent image artifact."""

    if type(parent_artifact_bytes) is not bytes or not parent_artifact_bytes:
        _fail("parent_artifact_bytes must be non-empty exact bytes.")

    expected_parent_sha256 = _parent_sha256(parent_artifact_sha256)
    width = _positive_int(parent_artifact_width, field_name="parent_artifact_width")
    height = _positive_int(parent_artifact_height, field_name="parent_artifact_height")
    governed_crop_name = _crop_name(crop_name)
    governed_bbox = _bbox(
        bbox,
        parent_width=width,
        parent_height=height,
    )

    actual_parent_sha256 = _sha256_bytes(parent_artifact_bytes)
    if actual_parent_sha256 != expected_parent_sha256:
        _fail("Parent artifact SHA-256 verification failed.")

    try:
        with Image.open(BytesIO(parent_artifact_bytes)) as opened:
            opened.load()

            if opened.size != (width, height):
                _fail("Parent artifact dimensions do not match caller binding.")

            parent = opened.convert("RGB")
    except CroppedArtifactError:
        raise
    except Exception as exc:
        raise CroppedArtifactError(
            "Parent artifact could not be decoded as an image."
        ) from exc

    crop = parent.crop(governed_bbox)

    expected_crop_size = (
        governed_bbox[2] - governed_bbox[0],
        governed_bbox[3] - governed_bbox[1],
    )
    if crop.size != expected_crop_size:
        _fail("Cropped artifact dimensions differ from exact bbox geometry.")

    normalized = crop.convert("RGB")
    raw_pixel_sha256 = _sha256_bytes(normalized.tobytes())
    artifact_bytes = _encode_png_twice(normalized)
    artifact_sha256 = _sha256_bytes(artifact_bytes)

    return CroppedArtifactReceipt(
        schema_version=CROPPED_ARTIFACT_SCHEMA_VERSION,
        artifact_role=ARTIFACT_ROLE,
        profile_id=PROFILE_ID,
        profile_schema_version=PROFILE_SCHEMA_VERSION,
        media_type=MEDIA_TYPE,
        parent_artifact_sha256=expected_parent_sha256,
        parent_artifact_byte_length=len(parent_artifact_bytes),
        parent_artifact_width=width,
        parent_artifact_height=height,
        crop_name=governed_crop_name,
        bbox=governed_bbox,
        raw_pixel_sha256=raw_pixel_sha256,
        artifact_bytes=artifact_bytes,
        artifact_sha256=artifact_sha256,
        artifact_byte_length=len(artifact_bytes),
        artifact_width=expected_crop_size[0],
        artifact_height=expected_crop_size[1],
        pillow_version=metadata.version("Pillow"),
    )


__all__ = [
    "ARTIFACT_ROLE",
    "CROPPED_ARTIFACT_SCHEMA_VERSION",
    "CroppedArtifactError",
    "CroppedArtifactReceipt",
    "MEDIA_TYPE",
    "PNG_COMPRESS_LEVEL",
    "PROFILE_ID",
    "PROFILE_SCHEMA_VERSION",
    "build_cropped_artifact",
]
