"""Immutable models for provider-neutral candidate transcriptions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


CANDIDATE_TRANSCRIPTION_SCHEMA_VERSION = "candidate-transcription-record/1.0"
TRANSCRIPTION_REVIEW_EVENT_SCHEMA_VERSION = "transcription-review-event/1.0"


@dataclass(frozen=True)
class CandidateTranscriptionRecord:
    schema_version: str
    record_id: str
    case_id: str
    source_document_instance_id: str
    source_snapshot_id: str
    original_filename: str
    original_blob_sha256: str
    original_byte_length: int
    page_number: int
    source_page_text_sha256: str
    source_page_text_byte_length: int
    derived_artifact_role: str
    derived_artifact_sha256: str
    derived_artifact_byte_length: int
    derived_artifact_width: int
    derived_artifact_height: int
    provider_kind: str
    provider_reference: str
    profile_id: str
    profile_schema_version: str
    transcription_language: str
    transcription_sha256: str
    transcription_byte_length: int


class TranscriptionReviewDecision(str, Enum):
    DEFER = "DEFER"
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class TranscriptionReviewState(str, Enum):
    DEFERRED = "DEFERRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class TranscriptionReviewEvent:
    schema_version: str
    event_id: str
    candidate_record_id: str
    transcription_sha256: str
    decision: TranscriptionReviewDecision
    reviewer_reference: str
    reviewer_note: str
    reviewed_at_utc: str
    previous_event_id: str | None


@dataclass(frozen=True)
class TranscriptionReviewProjection:
    candidate_record_id: str
    transcription_sha256: str
    state: TranscriptionReviewState
    latest_event_id: str
    reviewer_reference: str
    reviewer_note: str
    reviewed_at_utc: str
