"""Transcription-specific professional review chain and projection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from .identity import provisional_review_event
from .models import (
    CandidateTranscriptionRecord,
    TranscriptionReviewDecision,
    TranscriptionReviewEvent,
    TranscriptionReviewProjection,
    TranscriptionReviewState,
)
from .validation import (
    CandidateTranscriptionValidationError,
    validate_candidate_transcription_record,
    validate_transcription_review_event,
)


_DECISION_TO_STATE = {
    TranscriptionReviewDecision.DEFER: TranscriptionReviewState.DEFERRED,
    TranscriptionReviewDecision.APPROVE: TranscriptionReviewState.APPROVED,
    TranscriptionReviewDecision.REJECT: TranscriptionReviewState.REJECTED,
}


def _normalize_utc(value: str) -> str:
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value

    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise CandidateTranscriptionValidationError(
            "reviewed_at_utc must be ISO-8601."
        ) from exc

    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise CandidateTranscriptionValidationError(
            "reviewed_at_utc must carry UTC timezone information."
        )

    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _ordered_review_chain(
    events: Iterable[TranscriptionReviewEvent],
) -> tuple[TranscriptionReviewEvent, ...]:
    values = tuple(events)

    if not values:
        return ()

    for event in values:
        validate_transcription_review_event(event)

    candidate_ids = {event.candidate_record_id for event in values}
    transcription_hashes = {event.transcription_sha256 for event in values}

    if len(candidate_ids) != 1 or len(transcription_hashes) != 1:
        raise CandidateTranscriptionValidationError(
            "review events must bind one candidate and one transcription hash."
        )

    by_id = {event.event_id: event for event in values}
    if len(by_id) != len(values):
        raise CandidateTranscriptionValidationError(
            "duplicate review event_id is not permitted."
        )

    roots = [event for event in values if event.previous_event_id is None]
    if len(roots) != 1:
        raise CandidateTranscriptionValidationError(
            "review history must contain exactly one root event."
        )

    children: dict[str, list[TranscriptionReviewEvent]] = {}
    for event in values:
        if event.previous_event_id is None:
            continue

        if event.previous_event_id not in by_id:
            raise CandidateTranscriptionValidationError(
                "review history references an absent previous_event_id."
            )

        children.setdefault(event.previous_event_id, []).append(event)

    chain = [roots[0]]
    seen = {roots[0].event_id}

    while True:
        next_values = children.get(chain[-1].event_id, [])

        if not next_values:
            break

        if len(next_values) != 1:
            raise CandidateTranscriptionValidationError(
                "review history must not fork."
            )

        next_event = next_values[0]

        if next_event.event_id in seen:
            raise CandidateTranscriptionValidationError(
                "review history must not contain a cycle."
            )

        chain.append(next_event)
        seen.add(next_event.event_id)

    if len(chain) != len(values):
        raise CandidateTranscriptionValidationError(
            "review history is disconnected."
        )

    return tuple(chain)


def project_transcription_review(
    events: Iterable[TranscriptionReviewEvent],
) -> TranscriptionReviewProjection | None:
    chain = _ordered_review_chain(events)

    if not chain:
        return None

    latest = chain[-1]

    return TranscriptionReviewProjection(
        candidate_record_id=latest.candidate_record_id,
        transcription_sha256=latest.transcription_sha256,
        state=_DECISION_TO_STATE[latest.decision],
        latest_event_id=latest.event_id,
        reviewer_reference=latest.reviewer_reference,
        reviewer_note=latest.reviewer_note,
        reviewed_at_utc=latest.reviewed_at_utc,
    )


def make_transcription_review_event(
    *,
    candidate: CandidateTranscriptionRecord,
    decision: TranscriptionReviewDecision,
    reviewer_reference: str,
    reviewer_note: str,
    reviewed_at_utc: str,
    existing_events: Iterable[TranscriptionReviewEvent] = (),
) -> TranscriptionReviewEvent:
    validate_candidate_transcription_record(candidate)

    if not isinstance(decision, TranscriptionReviewDecision):
        raise CandidateTranscriptionValidationError(
            "decision must be TranscriptionReviewDecision."
        )

    existing = tuple(existing_events)
    projection = project_transcription_review(existing)

    if projection is not None:
        if projection.candidate_record_id != candidate.record_id:
            raise CandidateTranscriptionValidationError(
                "existing review history binds a different candidate."
            )

        if projection.transcription_sha256 != candidate.transcription_sha256:
            raise CandidateTranscriptionValidationError(
                "existing review history binds a different transcription."
            )

    event = provisional_review_event(
        candidate_record_id=candidate.record_id,
        transcription_sha256=candidate.transcription_sha256,
        decision=decision,
        reviewer_reference=reviewer_reference,
        reviewer_note=reviewer_note,
        reviewed_at_utc=_normalize_utc(reviewed_at_utc),
        previous_event_id=(
            projection.latest_event_id if projection is not None else None
        ),
    )

    validate_transcription_review_event(event)
    return event
