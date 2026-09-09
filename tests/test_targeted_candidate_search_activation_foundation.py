from __future__ import annotations

from dataclasses import fields
from enum import Enum
import hashlib
from types import SimpleNamespace

import pytest

from targeted_candidate_search_activation import (
    TARGETED_CANDIDATE_ACTIVATION_CONTRACT_SHA256,
    TARGETED_CANDIDATE_SEARCH_AUTHORITY_KIND,
    TARGETED_CANDIDATE_SEARCH_COLLECTION_NAME,
    TARGETED_CANDIDATE_SEARCH_DISCOVERY_SCOPE,
    TargetedCandidateActivationAuthority,
    TargetedCandidateActivationError,
    TargetedCandidateActivationRow,
    build_targeted_candidate_activation,
    validate_current_review_binding,
    validate_targeted_candidate_activation_row,
)


CANDIDATE_ID = "sha256:" + "1" * 64
SNAPSHOT_ID = "sha256:" + "2" * 64
BINDING_ID = "sha256:" + "3" * 64
RECEIPT_ID = "sha256:" + "4" * 64
REVIEW_EVENT_ID = "sha256:" + "5" * 64
LATER_REVIEW_EVENT_ID = "sha256:" + "6" * 64
ORIGINAL_BLOB_SHA256 = "7" * 64
ARTIFACT_SHA256 = "8" * 64
PARENT_ARTIFACT_SHA256 = "9" * 64
RECORD_SERIALIZATION_SHA256 = "a" * 64
BINDING_SERIALIZATION_SHA256 = "b" * 64
DOCUMENT = "approved targeted candidate text"
TRANSCRIPTION_SHA256 = hashlib.sha256(DOCUMENT.encode("utf-8")).hexdigest()


class ReviewState(str, Enum):
    APPROVED = "APPROVED"
    DEFERRED = "DEFERRED"
    REJECTED = "REJECTED"


def candidate():
    return SimpleNamespace(
        record_id=CANDIDATE_ID,
        case_id="case-1",
        source_document_instance_id="document-1",
        source_snapshot_id=SNAPSHOT_ID,
        page_number=5,
        original_blob_sha256=ORIGINAL_BLOB_SHA256,
        transcription_sha256=TRANSCRIPTION_SHA256,
        transcription_byte_length=len(DOCUMENT.encode("utf-8")),
        derived_artifact_sha256=ARTIFACT_SHA256,
        profile_id="candidate-transcription/openai-multimodal/1.0",
    )


def binding():
    return SimpleNamespace(
        binding_id=BINDING_ID,
        candidate_record_id=CANDIDATE_ID,
        transcription_sha256=TRANSCRIPTION_SHA256,
        derived_artifact_sha256=ARTIFACT_SHA256,
        parent_artifact_sha256=PARENT_ARTIFACT_SHA256,
        crop_name="UPPER_LEFT_CELL_1",
        bbox=(10, 20, 110, 220),
    )


def receipt():
    return SimpleNamespace(
        receipt_id=RECEIPT_ID,
        candidate_record_id=CANDIDATE_ID,
        transcription_sha256=TRANSCRIPTION_SHA256,
        derived_artifact_sha256=ARTIFACT_SHA256,
        binding_id=BINDING_ID,
        parent_artifact_sha256=PARENT_ARTIFACT_SHA256,
        crop_name="UPPER_LEFT_CELL_1",
        bbox=(10, 20, 110, 220),
        candidate_record_serialization_sha256=RECORD_SERIALIZATION_SHA256,
        crop_lineage_binding_serialization_sha256=BINDING_SERIALIZATION_SHA256,
    )


def projection(
    *,
    state=ReviewState.APPROVED,
    event_id=REVIEW_EVENT_ID,
):
    return SimpleNamespace(
        candidate_record_id=CANDIDATE_ID,
        transcription_sha256=TRANSCRIPTION_SHA256,
        state=state,
        latest_event_id=event_id,
    )


def build(*, review_projection=None):
    return build_targeted_candidate_activation(
        candidate=candidate(),
        document=DOCUMENT,
        binding=binding(),
        receipt=receipt(),
        review_projection=review_projection or projection(),
        embedding_model="text-embedding-3-large",
    )


def test_contract_constants_are_exact():
    assert TARGETED_CANDIDATE_ACTIVATION_CONTRACT_SHA256 == (
        "b58841d281f0723df80762c578a133d0ebaf9f180a7822d8a55f23a05c072ed3"
    )
    assert TARGETED_CANDIDATE_SEARCH_COLLECTION_NAME == (
        "targeted_candidate_transcriptions_v1"
    )
    assert TARGETED_CANDIDATE_SEARCH_AUTHORITY_KIND == (
        "targeted_candidate_transcription"
    )
    assert TARGETED_CANDIDATE_SEARCH_DISCOVERY_SCOPE == (
        "targeted_candidate_discovery_only"
    )


def test_authority_fields_match_frozen_p13_contract():
    assert tuple(field.name for field in fields(
        TargetedCandidateActivationAuthority
    )) == (
        "case_id",
        "candidate_record_id",
        "transcription_sha256",
        "transcription_bytes",
        "binding_id",
        "publication_receipt_id",
        "review_event_id",
        "derived_artifact_sha256",
        "embedding_model",
        "collection_name",
    )


def test_row_fields_match_frozen_p13_contract():
    assert tuple(field.name for field in fields(
        TargetedCandidateActivationRow
    )) == (
        "candidate_record_id",
        "document",
        "case_id",
        "source_document_instance_id",
        "source_snapshot_id",
        "page_number",
        "original_blob_sha256",
        "transcription_sha256",
        "derived_artifact_sha256",
        "profile_id",
        "binding_id",
        "parent_artifact_sha256",
        "crop_name",
        "bbox",
        "publication_receipt_id",
        "review_event_id",
        "authority_kind",
    )


def test_approved_gate_builds_exact_successor_authority_and_row():
    authority, row = build()
    assert authority.candidate_record_id == CANDIDATE_ID
    assert authority.binding_id == BINDING_ID
    assert authority.publication_receipt_id == RECEIPT_ID
    assert authority.review_event_id == REVIEW_EVENT_ID
    assert authority.derived_artifact_sha256 == ARTIFACT_SHA256
    assert row.candidate_record_id == CANDIDATE_ID
    assert row.review_event_id == REVIEW_EVENT_ID
    assert row.authority_kind == TARGETED_CANDIDATE_SEARCH_AUTHORITY_KIND


def test_metadata_is_targeted_and_bbox_is_scalar_serialized():
    _, row = build()
    assert row.metadata() == {
        "case_id": "case-1",
        "source_document_instance_id": "document-1",
        "source_snapshot_id": SNAPSHOT_ID,
        "page_number": 5,
        "original_blob_sha256": ORIGINAL_BLOB_SHA256,
        "transcription_sha256": TRANSCRIPTION_SHA256,
        "derived_artifact_sha256": ARTIFACT_SHA256,
        "profile_id": "candidate-transcription/openai-multimodal/1.0",
        "binding_id": BINDING_ID,
        "parent_artifact_sha256": PARENT_ARTIFACT_SHA256,
        "crop_name": "UPPER_LEFT_CELL_1",
        "bbox": "10,20,110,220",
        "publication_receipt_id": RECEIPT_ID,
        "review_event_id": REVIEW_EVENT_ID,
        "authority_kind": TARGETED_CANDIDATE_SEARCH_AUTHORITY_KIND,
    }


@pytest.mark.parametrize(
    "state",
    (ReviewState.DEFERRED, ReviewState.REJECTED),
)
def test_non_approved_latest_review_fails_before_authority_construction(state):
    with pytest.raises(
        TargetedCandidateActivationError,
        match="not APPROVED",
    ):
        build(review_projection=projection(state=state))


def test_stale_review_event_invalidates_existing_authority_and_row():
    authority, row = build()
    with pytest.raises(
        TargetedCandidateActivationError,
        match="stale",
    ):
        validate_current_review_binding(
            authority=authority,
            row=row,
            review_projection=projection(event_id=LATER_REVIEW_EVENT_ID),
        )


def test_transcription_byte_tamper_fails_closed():
    with pytest.raises(
        TargetedCandidateActivationError,
        match="SHA256 differs",
    ):
        build_targeted_candidate_activation(
            candidate=candidate(),
            document=DOCUMENT.replace("text", "tent"),
            binding=binding(),
            receipt=receipt(),
            review_projection=projection(),
            embedding_model="text-embedding-3-large",
        )


def test_lineage_binding_mismatch_fails_closed():
    wrong = binding()
    wrong.binding_id = "sha256:" + "c" * 64
    with pytest.raises(
        TargetedCandidateActivationError,
        match="lineage binding differs",
    ):
        build_targeted_candidate_activation(
            candidate=candidate(),
            document=DOCUMENT,
            binding=wrong,
            receipt=receipt(),
            review_projection=projection(),
            embedding_model="text-embedding-3-large",
        )


def test_receipt_artifact_mismatch_fails_closed():
    wrong = receipt()
    wrong.derived_artifact_sha256 = "d" * 64
    with pytest.raises(
        TargetedCandidateActivationError,
        match="artifact binding differs",
    ):
        build_targeted_candidate_activation(
            candidate=candidate(),
            document=DOCUMENT,
            binding=binding(),
            receipt=wrong,
            review_projection=projection(),
            embedding_model="text-embedding-3-large",
        )


def test_row_authority_mismatch_fails_closed():
    authority, row = build()
    wrong = TargetedCandidateActivationRow(
        **{
            **row.__dict__,
            "review_event_id": LATER_REVIEW_EVENT_ID,
        }
    )
    with pytest.raises(
        TargetedCandidateActivationError,
        match="review event ID",
    ):
        validate_targeted_candidate_activation_row(
            authority=authority,
            row=wrong,
        )


def test_foundation_has_no_legacy_activation_or_runtime_dependencies():
    import targeted_candidate_search_activation.gate as gate_module
    import targeted_candidate_search_activation.models as models_module
    import targeted_candidate_search_activation.validation as validation_module

    source = "\n".join(
        __import__("inspect").getsource(module)
        for module in (gate_module, models_module, validation_module)
    )
    assert "derived_transcription_search_activation" not in source
    assert "chromadb" not in source.lower()
    assert "openai" not in source.lower()
    assert "embed_document" not in source
    assert "embed_query" not in source
