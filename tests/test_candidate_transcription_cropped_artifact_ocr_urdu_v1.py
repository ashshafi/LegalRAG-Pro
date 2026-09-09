from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image
import pytest

from candidate_transcription.cropped_artifact import (
    ARTIFACT_ROLE,
    CROPPED_ARTIFACT_SCHEMA_VERSION,
    CroppedArtifactError,
    MEDIA_TYPE,
    PROFILE_ID,
    PROFILE_SCHEMA_VERSION,
    build_cropped_artifact,
)


def _parent() -> tuple[bytes, str]:
    image = Image.new("RGB", (10, 8))
    for y in range(image.height):
        for x in range(image.width):
            image.putpixel(
                (x, y),
                (
                    (x * 17 + y * 3) % 256,
                    (y * 29 + x * 5) % 256,
                    (x * 11 + y * 13) % 256,
                ),
            )

    output = BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    data = output.getvalue()
    return data, hashlib.sha256(data).hexdigest()


def _build(**overrides):
    data, digest = _parent()
    values = {
        "parent_artifact_bytes": data,
        "parent_artifact_sha256": digest,
        "parent_artifact_width": 10,
        "parent_artifact_height": 8,
        "crop_name": "CELL_A",
        "bbox": (2, 1, 8, 6),
    }
    values.update(overrides)
    return build_cropped_artifact(**values)


def test_deterministic_crop_receipt_and_repeat_bytes():
    first = _build()
    second = _build()

    assert first == second
    assert first.schema_version == CROPPED_ARTIFACT_SCHEMA_VERSION
    assert first.artifact_role == ARTIFACT_ROLE
    assert first.profile_id == PROFILE_ID
    assert first.profile_schema_version == PROFILE_SCHEMA_VERSION
    assert first.media_type == MEDIA_TYPE
    assert first.crop_name == "CELL_A"
    assert first.bbox == (2, 1, 8, 6)
    assert (first.artifact_width, first.artifact_height) == (6, 5)
    assert first.artifact_byte_length == len(first.artifact_bytes)
    assert hashlib.sha256(first.artifact_bytes).hexdigest() == first.artifact_sha256
    assert len(first.raw_pixel_sha256) == 64


def test_parent_hash_mismatch_rejected():
    with pytest.raises(CroppedArtifactError, match="SHA-256"):
        _build(parent_artifact_sha256="0" * 64)


def test_parent_dimension_mismatch_rejected():
    with pytest.raises(CroppedArtifactError, match="dimensions"):
        _build(parent_artifact_width=11)


@pytest.mark.parametrize(
    "bbox",
    [
        [2, 1, 8, 6],
        (2, 1, 8),
        (2, 1, True, 6),
    ],
)
def test_bbox_contract_rejects_non_exact_tuple_or_non_integer(bbox):
    with pytest.raises(CroppedArtifactError, match="bbox"):
        _build(bbox=bbox)


@pytest.mark.parametrize(
    "bbox",
    [
        (-1, 1, 8, 6),
        (2, 1, 2, 6),
        (2, 1, 11, 6),
        (2, 1, 8, 9),
    ],
)
def test_bbox_bounds_and_positive_extent_enforced(bbox):
    with pytest.raises(CroppedArtifactError, match="bbox"):
        _build(bbox=bbox)


@pytest.mark.parametrize("crop_name", ["", "cell_a", " CELL_A", "CELL-A"])
def test_crop_name_governance_rejected(crop_name):
    with pytest.raises(CroppedArtifactError, match="crop_name"):
        _build(crop_name=crop_name)


def test_parent_bytes_must_be_exact_nonempty_bytes():
    with pytest.raises(CroppedArtifactError, match="parent_artifact_bytes"):
        _build(parent_artifact_bytes=bytearray(b"x"))

    with pytest.raises(CroppedArtifactError, match="parent_artifact_bytes"):
        _build(parent_artifact_bytes=b"")


def test_parent_sha_must_be_exact_lower_hex():
    with pytest.raises(CroppedArtifactError, match="SHA-256"):
        _build(parent_artifact_sha256="A" * 64)

    with pytest.raises(CroppedArtifactError, match="SHA-256"):
        _build(parent_artifact_sha256="sha256:" + ("0" * 64))


def test_receipt_is_frozen():
    receipt = _build()

    with pytest.raises(FrozenInstanceError):
        receipt.crop_name = "CELL_B"  # type: ignore[misc]


def test_module_has_no_provider_source_store_search_or_ui_dependency():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "candidate_transcription"
        / "cropped_artifact.py"
    )
    source = module_path.read_text(encoding="utf-8").lower()

    for forbidden in (
        "import openai",
        "from openai",
        "source_evidence",
        "chromadb",
        "streamlit",
        "responses.create",
        "tesseract",
        "pytesseract",
    ):
        assert forbidden not in source
