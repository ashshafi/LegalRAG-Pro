from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image
import pytest

from candidate_transcription.crop_lineage import (
    CROP_LINEAGE_SCHEMA_VERSION,
    CandidateCropLineageError,
    build_candidate_crop_lineage_binding,
    dumps_candidate_crop_lineage_binding,
    loads_candidate_crop_lineage_binding,
    validate_candidate_crop_lineage_binding,
    validate_candidate_crop_publication_unit,
)
from candidate_transcription.crop_lineage_store import (
    CandidateCropLineageStore,
    CandidateCropLineageStoreError,
)
from candidate_transcription.cropped_artifact import (
    build_cropped_artifact,
)
from candidate_transcription.identity import (
    build_candidate_transcription_record,
)


def _parent() -> tuple[bytes, str]:
    image = Image.new("RGB", (12, 10))
    for y in range(image.height):
        for x in range(image.width):
            image.putpixel(
                (x, y),
                (
                    (x * 19 + y * 7) % 256,
                    (y * 31 + x * 3) % 256,
                    (x * 13 + y * 11) % 256,
                ),
            )

    output = BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    payload = output.getvalue()
    return payload, hashlib.sha256(payload).hexdigest()


def _crop():
    parent_bytes, parent_sha = _parent()

    return build_cropped_artifact(
        parent_artifact_bytes=parent_bytes,
        parent_artifact_sha256=parent_sha,
        parent_artifact_width=12,
        parent_artifact_height=10,
        crop_name="CELL_A",
        bbox=(2, 1, 10, 8),
    )


def _record_for_crop(crop, text: str, **overrides):
    values = {
        "case_id": "9e10cd5a-00fd-484e-938d-b5c3358c8dae",
        "source_document_instance_id": "19027781-f4e4-5965-887e-16a44304f507",
        "source_snapshot_id": "sha256:" + ("1" * 64),
        "original_filename": "synthetic.pdf",
        "original_blob_sha256": "2" * 64,
        "original_byte_length": 123,
        "page_number": 5,
        "source_page_text_sha256": "3" * 64,
        "source_page_text_byte_length": 17,
        "derived_artifact_role": crop.artifact_role,
        "derived_artifact_sha256": crop.artifact_sha256,
        "derived_artifact_byte_length": crop.artifact_byte_length,
        "derived_artifact_width": crop.artifact_width,
        "derived_artifact_height": crop.artifact_height,
        "provider_kind": "ai_multimodal",
        "provider_reference": "openai:gpt-5.6-sol",
        "profile_id": "candidate-transcription/openai-multimodal/1.0",
        "profile_schema_version": "1.0",
        "transcription_language": "urd",
        "transcription_text": text,
    }
    values.update(overrides)
    return build_candidate_transcription_record(**values)


def _unit():
    crop = _crop()
    text = "candidate crop transcription"
    record = _record_for_crop(crop, text)
    binding = build_candidate_crop_lineage_binding(
        candidate_record=record,
        crop_receipt=crop,
    )
    return record, crop, text, binding


def test_binding_is_deterministic_frozen_and_complete():
    record, crop, text, first = _unit()
    _, _, _, second = _unit()

    assert first == second
    assert first.schema_version == CROP_LINEAGE_SCHEMA_VERSION
    assert first.candidate_record_id == record.record_id
    assert first.transcription_sha256 == record.transcription_sha256
    assert first.derived_artifact_sha256 == crop.artifact_sha256
    assert first.parent_artifact_sha256 == crop.parent_artifact_sha256
    assert first.crop_name == crop.crop_name
    assert first.bbox == crop.bbox
    assert first.raw_pixel_sha256 == crop.raw_pixel_sha256
    assert first.artifact_byte_length == crop.artifact_byte_length
    assert first.artifact_width == crop.artifact_width
    assert first.artifact_height == crop.artifact_height
    assert first.crop_profile_id == crop.profile_id
    assert first.crop_profile_schema_version == crop.profile_schema_version
    assert first.binding_id.startswith("sha256:")

    with pytest.raises(FrozenInstanceError):
        first.crop_name = "CELL_B"  # type: ignore[misc]


def test_serialization_round_trip_is_exact_and_canonical():
    _, _, _, binding = _unit()

    dumped = dumps_candidate_crop_lineage_binding(binding)
    loaded = loads_candidate_crop_lineage_binding(dumped)

    assert loaded == binding
    assert dumps_candidate_crop_lineage_binding(loaded) == dumped


def test_candidate_artifact_sha_mismatch_rejected():
    crop = _crop()
    record = _record_for_crop(
        crop,
        "candidate crop transcription",
        derived_artifact_sha256="0" * 64,
    )

    with pytest.raises(CandidateCropLineageError, match="SHA-256"):
        build_candidate_crop_lineage_binding(
            candidate_record=record,
            crop_receipt=crop,
        )


def test_candidate_artifact_geometry_mismatch_rejected():
    crop = _crop()
    record = _record_for_crop(
        crop,
        "candidate crop transcription",
        derived_artifact_width=crop.artifact_width + 1,
    )

    with pytest.raises(CandidateCropLineageError, match="width"):
        build_candidate_crop_lineage_binding(
            candidate_record=record,
            crop_receipt=crop,
        )


def test_full_page_candidate_role_cannot_receive_crop_binding():
    crop = _crop()
    record = _record_for_crop(
        crop,
        "candidate crop transcription",
        derived_artifact_role="orientation_normalized_artifact/1.0",
    )

    with pytest.raises(CandidateCropLineageError, match="role"):
        build_candidate_crop_lineage_binding(
            candidate_record=record,
            crop_receipt=crop,
        )


def test_binding_identity_tamper_rejected():
    _, _, _, binding = _unit()
    tampered = replace(binding, crop_name="CELL_B")

    with pytest.raises(CandidateCropLineageError, match="binding_id"):
        validate_candidate_crop_lineage_binding(tampered)


def test_publication_unit_validates_candidate_text_crop_and_binding():
    record, crop, text, binding = _unit()

    validate_candidate_crop_publication_unit(
        candidate_record=record,
        transcription_text=text,
        crop_receipt=crop,
        binding=binding,
    )


def test_publication_unit_rejects_wrong_transcription_text():
    record, crop, _, binding = _unit()

    with pytest.raises(CandidateCropLineageError, match="Transcription text SHA-256"):
        validate_candidate_crop_publication_unit(
            candidate_record=record,
            transcription_text="different text",
            crop_receipt=crop,
            binding=binding,
        )


def test_store_publish_load_list_and_idempotent_repeat(tmp_path: Path):
    _, _, _, binding = _unit()
    store = CandidateCropLineageStore(tmp_path / "lineage-root")

    store.publish_binding(binding)
    store.publish_binding(binding)

    assert store.load_binding(
        candidate_record_id=binding.candidate_record_id,
        binding_id=binding.binding_id,
    ) == binding

    assert store.list_candidate_bindings(binding.candidate_record_id) == (binding,)


def test_store_requires_explicit_non_current_root():
    with pytest.raises(CandidateCropLineageStoreError, match="explicit"):
        CandidateCropLineageStore(Path("."))

    with pytest.raises(CandidateCropLineageStoreError, match="empty"):
        CandidateCropLineageStore("")


def test_store_detects_existing_different_bytes(tmp_path: Path):
    _, _, _, binding = _unit()
    store = CandidateCropLineageStore(tmp_path / "lineage-root")

    candidate_hex = binding.candidate_record_id.removeprefix("sha256:")
    binding_hex = binding.binding_id.removeprefix("sha256:")
    path = (
        store.root
        / "candidate_crop_lineage"
        / candidate_hex
        / f"{binding_hex}.json"
    )
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(CandidateCropLineageStoreError, match="different bytes"):
        store.publish_binding(binding)


def test_store_rejects_corrupt_binding(tmp_path: Path):
    _, _, _, binding = _unit()
    store = CandidateCropLineageStore(tmp_path / "lineage-root")
    store.publish_binding(binding)

    candidate_hex = binding.candidate_record_id.removeprefix("sha256:")
    binding_hex = binding.binding_id.removeprefix("sha256:")
    path = (
        store.root
        / "candidate_crop_lineage"
        / candidate_hex
        / f"{binding_hex}.json"
    )
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(CandidateCropLineageStoreError, match="invalid"):
        store.load_binding(
            candidate_record_id=binding.candidate_record_id,
            binding_id=binding.binding_id,
        )


def test_foundation_has_no_provider_source_search_ui_or_review_dependency():
    root = Path(__file__).resolve().parents[1]

    for relative in (
        "src/candidate_transcription/crop_lineage.py",
        "src/candidate_transcription/crop_lineage_store.py",
    ):
        source = (root / relative).read_text(encoding="utf-8").lower()

        for forbidden in (
            "import openai",
            "from openai",
            "source_evidence",
            "chromadb",
            "streamlit",
            "responses.create",
            "pytesseract",
            "tesseract",
            "transcriptionreview",
            "review_event",
        ):
            assert forbidden not in source
