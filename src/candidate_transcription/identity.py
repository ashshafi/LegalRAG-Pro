"""Deterministic identity for candidate transcription objects."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json

from .models import (
    CANDIDATE_TRANSCRIPTION_SCHEMA_VERSION,
    CandidateTranscriptionRecord,
    TRANSCRIPTION_REVIEW_EVENT_SCHEMA_VERSION,
    TranscriptionReviewDecision,
    TranscriptionReviewEvent,
)


def _canonical_json_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_id(payload: dict[str, object]) -> str:
    return f"sha256:{_sha256_hex(_canonical_json_bytes(payload))}"


def candidate_identity_payload(
    record: CandidateTranscriptionRecord,
) -> dict[str, object]:
    payload = asdict(record)
    payload.pop("record_id", None)
    return payload


def candidate_record_id(record: CandidateTranscriptionRecord) -> str:
    return _sha256_id(candidate_identity_payload(record))


def build_candidate_transcription_record(
    *,
    case_id: str,
    source_document_instance_id: str,
    source_snapshot_id: str,
    original_filename: str,
    original_blob_sha256: str,
    original_byte_length: int,
    page_number: int,
    source_page_text_sha256: str,
    source_page_text_byte_length: int,
    derived_artifact_role: str,
    derived_artifact_sha256: str,
    derived_artifact_byte_length: int,
    derived_artifact_width: int,
    derived_artifact_height: int,
    provider_kind: str,
    provider_reference: str,
    profile_id: str,
    profile_schema_version: str,
    transcription_language: str,
    transcription_text: str,
) -> CandidateTranscriptionRecord:
    if not isinstance(transcription_text, str):
        raise TypeError("transcription_text must be str.")

    transcription_bytes = transcription_text.encode("utf-8")

    provisional = CandidateTranscriptionRecord(
        schema_version=CANDIDATE_TRANSCRIPTION_SCHEMA_VERSION,
        record_id="sha256:" + ("0" * 64),
        case_id=case_id,
        source_document_instance_id=source_document_instance_id,
        source_snapshot_id=source_snapshot_id,
        original_filename=original_filename,
        original_blob_sha256=original_blob_sha256,
        original_byte_length=original_byte_length,
        page_number=page_number,
        source_page_text_sha256=source_page_text_sha256,
        source_page_text_byte_length=source_page_text_byte_length,
        derived_artifact_role=derived_artifact_role,
        derived_artifact_sha256=derived_artifact_sha256,
        derived_artifact_byte_length=derived_artifact_byte_length,
        derived_artifact_width=derived_artifact_width,
        derived_artifact_height=derived_artifact_height,
        provider_kind=provider_kind,
        provider_reference=provider_reference,
        profile_id=profile_id,
        profile_schema_version=profile_schema_version,
        transcription_language=transcription_language,
        transcription_sha256=_sha256_hex(transcription_bytes),
        transcription_byte_length=len(transcription_bytes),
    )

    return CandidateTranscriptionRecord(
        **{
            **asdict(provisional),
            "record_id": candidate_record_id(provisional),
        }
    )


def review_event_identity_payload(
    event: TranscriptionReviewEvent,
) -> dict[str, object]:
    payload = asdict(event)
    payload["decision"] = event.decision.value
    payload.pop("event_id", None)
    return payload


def review_event_id(event: TranscriptionReviewEvent) -> str:
    return _sha256_id(review_event_identity_payload(event))


def provisional_review_event(
    *,
    candidate_record_id: str,
    transcription_sha256: str,
    decision: TranscriptionReviewDecision,
    reviewer_reference: str,
    reviewer_note: str,
    reviewed_at_utc: str,
    previous_event_id: str | None,
) -> TranscriptionReviewEvent:
    provisional = TranscriptionReviewEvent(
        schema_version=TRANSCRIPTION_REVIEW_EVENT_SCHEMA_VERSION,
        event_id="sha256:" + ("0" * 64),
        candidate_record_id=candidate_record_id,
        transcription_sha256=transcription_sha256,
        decision=decision,
        reviewer_reference=reviewer_reference,
        reviewer_note=reviewer_note,
        reviewed_at_utc=reviewed_at_utc,
        previous_event_id=previous_event_id,
    )

    return TranscriptionReviewEvent(
        **{
            **asdict(provisional),
            "decision": decision,
            "event_id": review_event_id(provisional),
        }
    )
