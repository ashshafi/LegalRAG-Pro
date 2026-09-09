"""Validation for immutable candidate transcription and review records."""

from __future__ import annotations

from datetime import datetime, timezone
import re

from .identity import candidate_record_id, review_event_id
from .models import (
    CANDIDATE_TRANSCRIPTION_SCHEMA_VERSION,
    CandidateTranscriptionRecord,
    TRANSCRIPTION_REVIEW_EVENT_SCHEMA_VERSION,
    TranscriptionReviewDecision,
    TranscriptionReviewEvent,
)


_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_SHA256_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_ALLOWED_PROVIDER_KINDS = frozenset({"ai_multimodal", "human"})


class CandidateTranscriptionValidationError(ValueError):
    pass


def _fail(message: str) -> None:
    raise CandidateTranscriptionValidationError(message)


def _required_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{name} must be non-empty text.")
    return value


def _positive_int(name: str, value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        _fail(f"{name} must be a positive integer.")
    return value


def _nonnegative_int(name: str, value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _fail(f"{name} must be a non-negative integer.")
    return value


def _sha_hex(name: str, value: object) -> str:
    value = _required_text(name, value)
    if _SHA256_HEX.fullmatch(value) is None:
        _fail(f"{name} must be a lowercase SHA-256 hex digest.")
    return value


def _sha_id(name: str, value: object) -> str:
    value = _required_text(name, value)
    if _SHA256_ID.fullmatch(value) is None:
        _fail(f"{name} must be a sha256:<hex> identifier.")
    return value


def _validate_utc(value: object) -> str:
    value = _required_text("reviewed_at_utc", value)
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise CandidateTranscriptionValidationError(
            "reviewed_at_utc must be ISO-8601."
        ) from exc

    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _fail("reviewed_at_utc must carry UTC timezone information.")
    return value


def validate_candidate_transcription_record(
    record: CandidateTranscriptionRecord,
) -> None:
    if not isinstance(record, CandidateTranscriptionRecord):
        _fail("record must be CandidateTranscriptionRecord.")

    if record.schema_version != CANDIDATE_TRANSCRIPTION_SCHEMA_VERSION:
        _fail("candidate transcription schema_version is unsupported.")

    _sha_id("record_id", record.record_id)
    _required_text("case_id", record.case_id)
    _required_text(
        "source_document_instance_id",
        record.source_document_instance_id,
    )
    _sha_id("source_snapshot_id", record.source_snapshot_id)
    _required_text("original_filename", record.original_filename)
    _sha_hex("original_blob_sha256", record.original_blob_sha256)
    _positive_int("original_byte_length", record.original_byte_length)
    _positive_int("page_number", record.page_number)
    _sha_hex("source_page_text_sha256", record.source_page_text_sha256)
    _nonnegative_int(
        "source_page_text_byte_length",
        record.source_page_text_byte_length,
    )
    _required_text("derived_artifact_role", record.derived_artifact_role)
    _sha_hex("derived_artifact_sha256", record.derived_artifact_sha256)
    _positive_int(
        "derived_artifact_byte_length",
        record.derived_artifact_byte_length,
    )
    _positive_int("derived_artifact_width", record.derived_artifact_width)
    _positive_int("derived_artifact_height", record.derived_artifact_height)
    _required_text("provider_kind", record.provider_kind)

    if record.provider_kind not in _ALLOWED_PROVIDER_KINDS:
        _fail(
            "provider_kind must be one of: "
            + ", ".join(sorted(_ALLOWED_PROVIDER_KINDS))
        )

    _required_text("provider_reference", record.provider_reference)
    _required_text("profile_id", record.profile_id)
    _required_text("profile_schema_version", record.profile_schema_version)
    _required_text("transcription_language", record.transcription_language)
    _sha_hex("transcription_sha256", record.transcription_sha256)
    _positive_int(
        "transcription_byte_length",
        record.transcription_byte_length,
    )

    if candidate_record_id(record) != record.record_id:
        _fail("record_id does not match the deterministic candidate identity.")


def validate_transcription_review_event(
    event: TranscriptionReviewEvent,
) -> None:
    if not isinstance(event, TranscriptionReviewEvent):
        _fail("event must be TranscriptionReviewEvent.")

    if event.schema_version != TRANSCRIPTION_REVIEW_EVENT_SCHEMA_VERSION:
        _fail("transcription review schema_version is unsupported.")

    _sha_id("event_id", event.event_id)
    _sha_id("candidate_record_id", event.candidate_record_id)
    _sha_hex("transcription_sha256", event.transcription_sha256)

    if not isinstance(event.decision, TranscriptionReviewDecision):
        _fail("decision must be TranscriptionReviewDecision.")

    _required_text("reviewer_reference", event.reviewer_reference)

    if not isinstance(event.reviewer_note, str):
        _fail("reviewer_note must be str.")

    _validate_utc(event.reviewed_at_utc)

    if event.previous_event_id is not None:
        _sha_id("previous_event_id", event.previous_event_id)

    if review_event_id(event) != event.event_id:
        _fail("event_id does not match the deterministic review-event identity.")
