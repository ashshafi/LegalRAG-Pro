"""Provider-neutral candidate transcription and professional review foundation."""

from .identity import (
    build_candidate_transcription_record,
    candidate_identity_payload,
    review_event_identity_payload,
)
from .models import (
    CandidateTranscriptionRecord,
    TranscriptionReviewDecision,
    TranscriptionReviewEvent,
    TranscriptionReviewProjection,
    TranscriptionReviewState,
)
from .review import make_transcription_review_event, project_transcription_review
from .store import CandidateTranscriptionStore, TranscriptionReviewEventStore
from .validation import (
    CandidateTranscriptionValidationError,
    validate_candidate_transcription_record,
    validate_transcription_review_event,
)

__all__ = [
    "CandidateTranscriptionRecord",
    "CandidateTranscriptionStore",
    "CandidateTranscriptionValidationError",
    "TranscriptionReviewDecision",
    "TranscriptionReviewEvent",
    "TranscriptionReviewEventStore",
    "TranscriptionReviewProjection",
    "TranscriptionReviewState",
    "build_candidate_transcription_record",
    "candidate_identity_payload",
    "make_transcription_review_event",
    "project_transcription_review",
    "review_event_identity_payload",
    "validate_candidate_transcription_record",
    "validate_transcription_review_event",
]
