"""Explicit-root immutable stores for candidate transcription objects."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .models import CandidateTranscriptionRecord, TranscriptionReviewEvent
from .serialization import (
    dumps_candidate_record,
    dumps_review_event,
    loads_candidate_record,
    loads_review_event,
)
from .validation import (
    CandidateTranscriptionValidationError,
    validate_candidate_transcription_record,
    validate_transcription_review_event,
)


def _digest_component(value: str) -> str:
    if value.startswith("sha256:"):
        return value.split(":", 1)[1]
    return value


def _publish_immutable(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with path.open("xb") as handle:
            handle.write(payload)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise CandidateTranscriptionValidationError(
                f"immutable object already exists with different bytes: {path}"
            )


class CandidateTranscriptionStore:
    def __init__(self, root: str | Path) -> None:
        if root is None:
            raise CandidateTranscriptionValidationError(
                "candidate transcription store root must be explicit."
            )

        value = str(root).strip()
        if not value:
            raise CandidateTranscriptionValidationError(
                "candidate transcription store root must be explicit."
            )

        self.root = Path(root)

    def _candidate_path(self, record_id: str) -> Path:
        return (
            self.root
            / "candidates"
            / f"{_digest_component(record_id)}.json"
        )

    def _transcription_path(self, transcription_sha256: str) -> Path:
        return (
            self.root
            / "transcriptions"
            / "sha256"
            / f"{transcription_sha256}.txt"
        )

    def publish_candidate(
        self,
        *,
        record: CandidateTranscriptionRecord,
        transcription_text: str,
    ) -> None:
        validate_candidate_transcription_record(record)

        if not isinstance(transcription_text, str):
            raise CandidateTranscriptionValidationError(
                "transcription_text must be str."
            )

        transcription_bytes = transcription_text.encode("utf-8")
        actual_sha = hashlib.sha256(transcription_bytes).hexdigest()

        if actual_sha != record.transcription_sha256:
            raise CandidateTranscriptionValidationError(
                "transcription text SHA-256 does not match record."
            )

        if len(transcription_bytes) != record.transcription_byte_length:
            raise CandidateTranscriptionValidationError(
                "transcription text byte length does not match record."
            )

        _publish_immutable(
            self._transcription_path(record.transcription_sha256),
            transcription_bytes,
        )

        _publish_immutable(
            self._candidate_path(record.record_id),
            dumps_candidate_record(record).encode("utf-8"),
        )

    def load_candidate(self, record_id: str) -> CandidateTranscriptionRecord:
        path = self._candidate_path(record_id)

        if not path.is_file():
            raise CandidateTranscriptionValidationError(
                "candidate transcription record is absent."
            )

        return loads_candidate_record(path.read_text(encoding="utf-8"))

    def read_transcription(
        self,
        record: CandidateTranscriptionRecord,
    ) -> str:
        validate_candidate_transcription_record(record)
        path = self._transcription_path(record.transcription_sha256)

        if not path.is_file():
            raise CandidateTranscriptionValidationError(
                "candidate transcription blob is absent."
            )

        payload = path.read_bytes()

        if hashlib.sha256(payload).hexdigest() != record.transcription_sha256:
            raise CandidateTranscriptionValidationError(
                "candidate transcription blob hash differs from record."
            )

        if len(payload) != record.transcription_byte_length:
            raise CandidateTranscriptionValidationError(
                "candidate transcription blob length differs from record."
            )

        return payload.decode("utf-8")


class TranscriptionReviewEventStore:
    def __init__(self, root: str | Path) -> None:
        if root is None:
            raise CandidateTranscriptionValidationError(
                "transcription review store root must be explicit."
            )

        value = str(root).strip()
        if not value:
            raise CandidateTranscriptionValidationError(
                "transcription review store root must be explicit."
            )

        self.root = Path(root)

    def _events_dir(self, candidate_record_id: str) -> Path:
        return (
            self.root
            / "review_events"
            / _digest_component(candidate_record_id)
        )

    def _event_path(
        self,
        candidate_record_id: str,
        event_id: str,
    ) -> Path:
        return (
            self._events_dir(candidate_record_id)
            / f"{_digest_component(event_id)}.json"
        )

    def publish_event(self, event: TranscriptionReviewEvent) -> None:
        validate_transcription_review_event(event)

        _publish_immutable(
            self._event_path(event.candidate_record_id, event.event_id),
            dumps_review_event(event).encode("utf-8"),
        )

    def load_events(
        self,
        candidate_record_id: str,
    ) -> tuple[TranscriptionReviewEvent, ...]:
        directory = self._events_dir(candidate_record_id)

        if not directory.exists():
            return ()

        events = tuple(
            loads_review_event(path.read_text(encoding="utf-8"))
            for path in sorted(directory.glob("*.json"))
        )

        for event in events:
            if event.candidate_record_id != candidate_record_id:
                raise CandidateTranscriptionValidationError(
                    "review event directory contains a differently bound event."
                )

        return events
