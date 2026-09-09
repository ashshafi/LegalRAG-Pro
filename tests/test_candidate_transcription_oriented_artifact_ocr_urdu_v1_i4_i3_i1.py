from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

import candidate_transcription.oriented_artifact as artifact


PDF_BYTES = b"%PDF-fake-orientation-artifact-test"


def png_bytes(width: int, height: int, value: int) -> bytes:
    image = Image.new("RGB", (width, height), (value, value + 1, value + 2))
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=9)
    return buffer.getvalue()


STRIP_BYTES = {
    "A": png_bytes(4, 2, 10),
    "B": png_bytes(4, 3, 30),
    "C": png_bytes(4, 1, 50),
}

SPECS = tuple(
    artifact.EmbeddedRasterSpec(
        name=name,
        sha256=hashlib.sha256(STRIP_BYTES[name]).hexdigest(),
        width=4,
        height={"A": 2, "B": 3, "C": 1}[name],
    )
    for name in ("A", "B", "C")
)

ORDER = ("A", "B", "C")


class FakeEmbedded:
    def __init__(self, name: str, data: bytes):
        self.name = name + ".png"
        self.data = data


def install_reader(monkeypatch, *, images, page_count: int = 1):
    class FakeReader:
        def __init__(self, stream):
            assert stream.read() == PDF_BYTES
            self.pages = [
                SimpleNamespace(images=list(images))
                for _ in range(page_count)
            ]

    monkeypatch.setattr(artifact, "PdfReader", FakeReader)


def call_builder(monkeypatch, *, images=None, page_number: int = 1, orientation=None):
    if images is None:
        images = [
            FakeEmbedded("C", STRIP_BYTES["C"]),
            FakeEmbedded("A", STRIP_BYTES["A"]),
            FakeEmbedded("B", STRIP_BYTES["B"]),
        ]

    install_reader(monkeypatch, images=images)

    return artifact.build_orientation_normalized_artifact(
        pdf_bytes=PDF_BYTES,
        page_number=page_number,
        embedded_rasters=SPECS,
        strip_order=ORDER,
        orientation=(
            artifact.ORIENTATION_ROTATE_90_CW
            if orientation is None
            else orientation
        ),
    )


def expected_rotated_png() -> tuple[bytes, str, str]:
    decoded = {}
    for name in ORDER:
        with Image.open(BytesIO(STRIP_BYTES[name])) as image:
            decoded[name] = image.convert("RGB").copy()

    stitched = Image.new("RGB", (4, 6), "white")
    cursor = 0
    for name in ORDER:
        stitched.paste(decoded[name], (0, cursor))
        cursor += decoded[name].height

    rotated = stitched.rotate(-90, expand=True)
    buffer = BytesIO()
    rotated.save(buffer, format="PNG", optimize=False, compress_level=9)

    return (
        buffer.getvalue(),
        hashlib.sha256(stitched.tobytes()).hexdigest(),
        hashlib.sha256(rotated.tobytes()).hexdigest(),
    )


def test_deterministic_reconstruction_and_receipt(monkeypatch):
    first = call_builder(monkeypatch)
    second = call_builder(monkeypatch)
    expected_png, stitched_sha, rotated_sha = expected_rotated_png()

    assert first == second
    assert first.artifact_bytes == expected_png
    assert first.artifact_sha256 == hashlib.sha256(expected_png).hexdigest()
    assert first.artifact_byte_length == len(expected_png)
    assert (first.stitched_width, first.stitched_height) == (4, 6)
    assert (first.artifact_width, first.artifact_height) == (6, 4)
    assert first.stitched_raw_pixel_sha256 == stitched_sha
    assert first.rotated_raw_pixel_sha256 == rotated_sha
    assert first.source_strip_order == ORDER
    assert tuple(spec.name for spec in first.source_strips) == ORDER
    assert first.source_pdf_sha256 == hashlib.sha256(PDF_BYTES).hexdigest()
    assert first.source_pdf_byte_length == len(PDF_BYTES)
    assert first.page_number == 1
    assert first.orientation == "ROTATE_90_CW"
    assert first.media_type == "image/png"
    assert first.artifact_role == "orientation_normalized_embedded_raster/1.0"
    assert first.profile_id == "embedded-raster-stitch-rotate-cw-png/1.0"
    assert first.pillow_version
    assert first.pypdf_version


def test_hash_mismatch_is_rejected(monkeypatch):
    bad = bytearray(STRIP_BYTES["B"])
    bad[-1] ^= 1

    images = [
        FakeEmbedded("A", STRIP_BYTES["A"]),
        FakeEmbedded("B", bytes(bad)),
        FakeEmbedded("C", STRIP_BYTES["C"]),
    ]
    install_reader(monkeypatch, images=images)

    with pytest.raises(artifact.OrientedArtifactError, match="SHA-256 differs"):
        artifact.build_orientation_normalized_artifact(
            pdf_bytes=PDF_BYTES,
            page_number=1,
            embedded_rasters=SPECS,
            strip_order=ORDER,
            orientation=artifact.ORIENTATION_ROTATE_90_CW,
        )


def test_dimension_mismatch_is_rejected(monkeypatch):
    wrong_specs = (
        SPECS[0],
        artifact.EmbeddedRasterSpec(
            name="B",
            sha256=SPECS[1].sha256,
            width=4,
            height=99,
        ),
        SPECS[2],
    )

    install_reader(
        monkeypatch,
        images=[
            FakeEmbedded("A", STRIP_BYTES["A"]),
            FakeEmbedded("B", STRIP_BYTES["B"]),
            FakeEmbedded("C", STRIP_BYTES["C"]),
        ],
    )

    with pytest.raises(artifact.OrientedArtifactError, match="dimensions differ"):
        artifact.build_orientation_normalized_artifact(
            pdf_bytes=PDF_BYTES,
            page_number=1,
            embedded_rasters=wrong_specs,
            strip_order=ORDER,
            orientation=artifact.ORIENTATION_ROTATE_90_CW,
        )


def test_missing_expected_strip_is_rejected(monkeypatch):
    install_reader(
        monkeypatch,
        images=[
            FakeEmbedded("A", STRIP_BYTES["A"]),
            FakeEmbedded("C", STRIP_BYTES["C"]),
        ],
    )

    with pytest.raises(artifact.OrientedArtifactError, match="incomplete"):
        artifact.build_orientation_normalized_artifact(
            pdf_bytes=PDF_BYTES,
            page_number=1,
            embedded_rasters=SPECS,
            strip_order=ORDER,
            orientation=artifact.ORIENTATION_ROTATE_90_CW,
        )


def test_duplicate_strip_order_is_rejected_before_pdf_parse(monkeypatch):
    def fail_reader(stream):
        raise AssertionError("PDF reader must not be reached")

    monkeypatch.setattr(artifact, "PdfReader", fail_reader)

    with pytest.raises(artifact.OrientedArtifactError, match="duplicate"):
        artifact.build_orientation_normalized_artifact(
            pdf_bytes=PDF_BYTES,
            page_number=1,
            embedded_rasters=SPECS,
            strip_order=("A", "B", "B"),
            orientation=artifact.ORIENTATION_ROTATE_90_CW,
        )


def test_unsupported_orientation_is_rejected_before_pdf_parse(monkeypatch):
    def fail_reader(stream):
        raise AssertionError("PDF reader must not be reached")

    monkeypatch.setattr(artifact, "PdfReader", fail_reader)

    with pytest.raises(artifact.OrientedArtifactError, match="ROTATE_90_CW"):
        artifact.build_orientation_normalized_artifact(
            pdf_bytes=PDF_BYTES,
            page_number=1,
            embedded_rasters=SPECS,
            strip_order=ORDER,
            orientation="ROTATE_90_CCW",
        )


@pytest.mark.parametrize("page_number", [0, 2])
def test_page_bounds_are_rejected(monkeypatch, page_number):
    install_reader(
        monkeypatch,
        images=[
            FakeEmbedded("A", STRIP_BYTES["A"]),
            FakeEmbedded("B", STRIP_BYTES["B"]),
            FakeEmbedded("C", STRIP_BYTES["C"]),
        ],
    )

    with pytest.raises(artifact.OrientedArtifactError):
        artifact.build_orientation_normalized_artifact(
            pdf_bytes=PDF_BYTES,
            page_number=page_number,
            embedded_rasters=SPECS,
            strip_order=ORDER,
            orientation=artifact.ORIENTATION_ROTATE_90_CW,
        )


def test_receipt_is_frozen(monkeypatch):
    receipt = call_builder(monkeypatch)

    with pytest.raises(FrozenInstanceError):
        receipt.orientation = "ROTATE_90_CCW"


def test_package_has_no_forbidden_boundaries_or_ocr_surface():
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "candidate_transcription"
        / "oriented_artifact.py"
    ).read_text(encoding="utf-8").lower()

    for forbidden in (
        "import openai",
        "from openai",
        "source_evidence",
        "chromadb",
        "streamlit",
        "pytesseract",
        "tesseract",
    ):
        assert forbidden not in source

    assert "candidate_transcriptionstore" not in source
    assert "publish_candidate(" not in source
