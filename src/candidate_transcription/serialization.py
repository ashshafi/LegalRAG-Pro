"""Canonical serialization for candidate transcription objects."""

from __future__ import annotations

from dataclasses import asdict
import json
from typing import Mapping

from .models import (
    CandidateTranscriptionRecord,
    TranscriptionReviewDecision,
    TranscriptionReviewEvent,
)
from .validation import (
    CandidateTranscriptionValidationError,
    validate_candidate_transcription_record,
    validate_transcription_review_event,
)


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def candidate_record_to_dict(
    record: CandidateTranscriptionRecord,
) -> dict[str, object]:
    validate_candidate_transcription_record(record)
    return asdict(record)


def dumps_candidate_record(record: CandidateTranscriptionRecord) -> str:
    return _canonical_json(candidate_record_to_dict(record))


def candidate_record_from_dict(
    payload: Mapping[str, object],
) -> CandidateTranscriptionRecord:
    expected = set(CandidateTranscriptionRecord.__dataclass_fields__)
    actual = set(payload)

    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise CandidateTranscriptionValidationError(
            f"candidate record keys differ; missing={missing}, extra={extra}"
        )

    record = CandidateTranscriptionRecord(**dict(payload))
    validate_candidate_transcription_record(record)
    return record


def loads_candidate_record(value: str) -> CandidateTranscriptionRecord:
    payload = json.loads(value)

    if not isinstance(payload, dict):
        raise CandidateTranscriptionValidationError(
            "candidate record JSON must decode to an object."
        )

    return candidate_record_from_dict(payload)


def review_event_to_dict(
    event: TranscriptionReviewEvent,
) -> dict[str, object]:
    validate_transcription_review_event(event)
    payload = asdict(event)
    payload["decision"] = event.decision.value
    return payload


def dumps_review_event(event: TranscriptionReviewEvent) -> str:
    return _canonical_json(review_event_to_dict(event))


def review_event_from_dict(
    payload: Mapping[str, object],
) -> TranscriptionReviewEvent:
    expected = set(TranscriptionReviewEvent.__dataclass_fields__)
    actual = set(payload)

    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise CandidateTranscriptionValidationError(
            f"review event keys differ; missing={missing}, extra={extra}"
        )

    values = dict(payload)

    try:
        values["decision"] = TranscriptionReviewDecision(values["decision"])
    except (TypeError, ValueError) as exc:
        raise CandidateTranscriptionValidationError(
            "review decision is unsupported."
        ) from exc

    event = TranscriptionReviewEvent(**values)
    validate_transcription_review_event(event)
    return event


def loads_review_event(value: str) -> TranscriptionReviewEvent:
    payload = json.loads(value)

    if not isinstance(payload, dict):
        raise CandidateTranscriptionValidationError(
            "review event JSON must decode to an object."
        )

    return review_event_from_dict(payload)
