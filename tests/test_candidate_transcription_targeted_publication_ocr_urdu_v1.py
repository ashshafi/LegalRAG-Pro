from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image
import pytest

from candidate_transcription.crop_lineage import (
    build_candidate_crop_lineage_binding,
)
from candidate_transcription.crop_lineage_store import (
    CandidateCropLineageStoreError,
)
from candidate_transcription.cropped_artifact import build_cropped_artifact
from candidate_transcription.identity import build_candidate_transcription_record
from candidate_transcription.targeted_publication import (
    TARGETED_PUBLICATION_RECEIPT_SCHEMA_VERSION,
    TargetedCandidatePublicationCoordinator,
    TargetedCandidatePublicationError,
    TargetedCandidatePublicationReceiptStore,
    build_targeted_candidate_publication_receipt,
    dumps_targeted_candidate_publication_receipt,
    loads_targeted_candidate_publication_receipt,
    validate_targeted_candidate_publication_receipt,
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


def _unit():
    parent_bytes, parent_sha = _parent()

    crop = build_cropped_artifact(
        parent_artifact_bytes=parent_bytes,
        parent_artifact_sha256=parent_sha,
        parent_artifact_width=12,
        parent_artifact_height=10,
        crop_name="CELL_A",
        bbox=(2, 1, 10, 8),
    )

    text = "candidate targeted publication transcription"

    record = build_candidate_transcription_record(
        case_id="9e10cd5a-00fd-484e-938d-b5c3358c8dae",
        source_document_instance_id="19027781-f4e4-5965-887e-16a44304f507",
        source_snapshot_id="sha256:" + ("1" * 64),
        original_filename="synthetic.pdf",
        original_blob_sha256="2" * 64,
        original_byte_length=123,
        page_number=5,
        source_page_text_sha256="3" * 64,
        source_page_text_byte_length=17,
        derived_artifact_role=crop.artifact_role,
        derived_artifact_sha256=crop.artifact_sha256,
        derived_artifact_byte_length=crop.artifact_byte_length,
        derived_artifact_width=crop.artifact_width,
        derived_artifact_height=crop.artifact_height,
        provider_kind="ai_multimodal",
        provider_reference="openai:gpt-5.6-sol",
        profile_id="candidate-transcription/openai-multimodal/1.0",
        profile_schema_version="1.0",
        transcription_language="urd",
        transcription_text=text,
    )

    binding = build_candidate_crop_lineage_binding(
        candidate_record=record,
        crop_receipt=crop,
    )

    return record, crop, text, binding


def _coordinator(tmp_path: Path) -> TargetedCandidatePublicationCoordinator:
    return TargetedCandidatePublicationCoordinator(
        candidate_store_root=tmp_path / "candidate-root",
        lineage_store_root=tmp_path / "lineage-root",
        receipt_store_root=tmp_path / "receipt-root",
    )


def test_receipt_is_deterministic_frozen_and_complete():
    record, crop, text, binding = _unit()

    first = build_targeted_candidate_publication_receipt(
        candidate_record=record,
        transcription_text=text,
        binding=binding,
    )
    second = build_targeted_candidate_publication_receipt(
        candidate_record=record,
        transcription_text=text,
        binding=binding,
    )

    assert first == second
    assert first.schema_version == TARGETED_PUBLICATION_RECEIPT_SCHEMA_VERSION
    assert first.candidate_record_id == record.record_id
    assert first.transcription_sha256 == record.transcription_sha256
    assert first.derived_artifact_sha256 == record.derived_artifact_sha256
    assert first.binding_id == binding.binding_id
    assert first.parent_artifact_sha256 == binding.parent_artifact_sha256
    assert first.crop_name == binding.crop_name
    assert first.bbox == binding.bbox
    assert first.receipt_id.startswith("sha256:")

    with pytest.raises(FrozenInstanceError):
        first.crop_name = "CELL_B"  # type: ignore[misc]


def test_receipt_serialization_round_trip_is_exact():
    record, _, text, binding = _unit()
    receipt = build_targeted_candidate_publication_receipt(
        candidate_record=record,
        transcription_text=text,
        binding=binding,
    )

    dumped = dumps_targeted_candidate_publication_receipt(receipt)
    loaded = loads_targeted_candidate_publication_receipt(dumped)

    assert loaded == receipt
    assert dumps_targeted_candidate_publication_receipt(loaded) == dumped


def test_receipt_identity_tamper_rejected():
    record, _, text, binding = _unit()
    receipt = build_targeted_candidate_publication_receipt(
        candidate_record=record,
        transcription_text=text,
        binding=binding,
    )
    tampered = replace(receipt, crop_name="CELL_B")

    with pytest.raises(TargetedCandidatePublicationError, match="receipt_id"):
        validate_targeted_candidate_publication_receipt(tampered)


def test_receipt_store_requires_explicit_absolute_root(tmp_path: Path):
    with pytest.raises(TargetedCandidatePublicationError, match="absolute"):
        TargetedCandidatePublicationReceiptStore(Path("."))

    with pytest.raises(TargetedCandidatePublicationError, match="empty"):
        TargetedCandidatePublicationReceiptStore("")


def test_receipt_store_publish_load_and_idempotent_repeat(tmp_path: Path):
    record, _, text, binding = _unit()
    receipt = build_targeted_candidate_publication_receipt(
        candidate_record=record,
        transcription_text=text,
        binding=binding,
    )
    store = TargetedCandidatePublicationReceiptStore(tmp_path / "receipts")

    store.publish_receipt(receipt)
    store.publish_receipt(receipt)

    loaded = store.load_receipt(
        candidate_record_id=receipt.candidate_record_id,
        receipt_id=receipt.receipt_id,
    )
    assert loaded == receipt


def test_receipt_store_rejects_existing_different_bytes(tmp_path: Path):
    record, _, text, binding = _unit()
    receipt = build_targeted_candidate_publication_receipt(
        candidate_record=record,
        transcription_text=text,
        binding=binding,
    )
    store = TargetedCandidatePublicationReceiptStore(tmp_path / "receipts")

    candidate_hex = receipt.candidate_record_id.removeprefix("sha256:")
    receipt_hex = receipt.receipt_id.removeprefix("sha256:")
    path = (
        store.root
        / "targeted_candidate_publication_receipts"
        / candidate_hex
        / f"{receipt_hex}.json"
    )
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(TargetedCandidatePublicationError, match="different bytes"):
        store.publish_receipt(receipt)


def test_coordinator_requires_three_distinct_absolute_roots(tmp_path: Path):
    same = tmp_path / "same"

    with pytest.raises(TargetedCandidatePublicationError, match="distinct"):
        TargetedCandidatePublicationCoordinator(
            candidate_store_root=same,
            lineage_store_root=same,
            receipt_store_root=tmp_path / "receipt",
        )


def test_coordinator_publishes_resolves_and_is_idempotent(tmp_path: Path):
    record, crop, text, binding = _unit()
    coordinator = _coordinator(tmp_path)

    first = coordinator.publish(
        candidate_record=record,
        transcription_text=text,
        crop_receipt=crop,
        binding=binding,
    )
    second = coordinator.publish(
        candidate_record=record,
        transcription_text=text,
        crop_receipt=crop,
        binding=binding,
    )

    assert first == second

    resolved = coordinator.resolve(
        candidate_record_id=first.candidate_record_id,
        receipt_id=first.receipt_id,
        crop_receipt=crop,
    )
    assert resolved == first


def test_failed_lineage_publication_creates_no_completion_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    record, crop, text, binding = _unit()
    coordinator = _coordinator(tmp_path)

    original_publish = coordinator.lineage_store.publish_binding

    def fail_binding(_binding):
        raise CandidateCropLineageStoreError("synthetic lineage failure")

    monkeypatch.setattr(
        coordinator.lineage_store,
        "publish_binding",
        fail_binding,
    )

    with pytest.raises(CandidateCropLineageStoreError, match="synthetic"):
        coordinator.publish(
            candidate_record=record,
            transcription_text=text,
            crop_receipt=crop,
            binding=binding,
        )

    loaded_candidate = coordinator.candidate_store.load_candidate(record.record_id)
    assert loaded_candidate == record
    assert coordinator.candidate_store.read_transcription(loaded_candidate) == text

    expected_receipt = build_targeted_candidate_publication_receipt(
        candidate_record=record,
        transcription_text=text,
        binding=binding,
    )
    with pytest.raises(TargetedCandidatePublicationError, match="does not exist"):
        coordinator.receipt_store.load_receipt(
            candidate_record_id=expected_receipt.candidate_record_id,
            receipt_id=expected_receipt.receipt_id,
        )

    monkeypatch.setattr(
        coordinator.lineage_store,
        "publish_binding",
        original_publish,
    )

    completed = coordinator.publish(
        candidate_record=record,
        transcription_text=text,
        crop_receipt=crop,
        binding=binding,
    )
    assert completed == expected_receipt


def test_preflight_validation_failure_writes_nothing(tmp_path: Path):
    record, crop, text, binding = _unit()
    coordinator = _coordinator(tmp_path)

    with pytest.raises(Exception):
        coordinator.publish(
            candidate_record=record,
            transcription_text="wrong transcription",
            crop_receipt=crop,
            binding=binding,
        )

    assert not (tmp_path / "candidate-root").exists()
    assert not (tmp_path / "lineage-root").exists()
    assert not (tmp_path / "receipt-root").exists()


def test_resolve_fails_when_lineage_object_is_missing(tmp_path: Path):
    record, crop, text, binding = _unit()
    coordinator = _coordinator(tmp_path)

    receipt = coordinator.publish(
        candidate_record=record,
        transcription_text=text,
        crop_receipt=crop,
        binding=binding,
    )

    candidate_hex = binding.candidate_record_id.removeprefix("sha256:")
    binding_hex = binding.binding_id.removeprefix("sha256:")
    lineage_path = (
        tmp_path
        / "lineage-root"
        / "candidate_crop_lineage"
        / candidate_hex
        / f"{binding_hex}.json"
    )
    lineage_path.unlink()

    with pytest.raises(CandidateCropLineageStoreError, match="does not exist"):
        coordinator.resolve(
            candidate_record_id=receipt.candidate_record_id,
            receipt_id=receipt.receipt_id,
            crop_receipt=crop,
        )


def test_foundation_has_no_provider_source_search_ui_or_decision_dependency():
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "src"
        / "candidate_transcription"
        / "targeted_publication.py"
    ).read_text(encoding="utf-8").lower()

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
        "search_activation",
    ):
        assert forbidden not in source
