from __future__ import annotations

from dataclasses import fields, replace
import inspect
from pathlib import Path

import pytest

from candidate_transcription.identity import build_candidate_transcription_record
from candidate_transcription.models import (
    CandidateTranscriptionRecord,
    TranscriptionReviewDecision,
    TranscriptionReviewState,
)
from candidate_transcription.review import (
    make_transcription_review_event,
    project_transcription_review,
)
from candidate_transcription.serialization import (
    dumps_candidate_record,
    dumps_review_event,
    loads_candidate_record,
    loads_review_event,
)
from candidate_transcription.store import (
    CandidateTranscriptionStore,
    TranscriptionReviewEventStore,
)
from candidate_transcription.validation import (
    CandidateTranscriptionValidationError,
    validate_candidate_transcription_record,
)


def make_candidate(
    *,
    text: str = "اصل اردو متن\n",
    provider_kind: str = "ai_multimodal",
    provider_reference: str = "openai:test-model",
    artifact_sha: str = "4" * 64,
):
    return build_candidate_transcription_record(
        case_id="case-1",
        source_document_instance_id="document-1",
        source_snapshot_id="sha256:" + ("1" * 64),
        original_filename="certificate.pdf",
        original_blob_sha256="2" * 64,
        original_byte_length=1000,
        page_number=5,
        source_page_text_sha256="3" * 64,
        source_page_text_byte_length=237,
        derived_artifact_role="orientation-normalised-page-raster",
        derived_artifact_sha256=artifact_sha,
        derived_artifact_byte_length=2000,
        derived_artifact_width=2009,
        derived_artifact_height=1500,
        provider_kind=provider_kind,
        provider_reference=provider_reference,
        profile_id="candidate-transcription/test",
        profile_schema_version="1.0",
        transcription_language="urd",
        transcription_text=text,
    )


def test_candidate_identity_is_deterministic_and_content_bound():
    a = make_candidate()
    b = make_candidate()
    assert a == b
    assert a.record_id.startswith("sha256:")

    assert make_candidate(text="مختلف متن\n").record_id != a.record_id
    assert make_candidate(provider_reference="human:reviewer").record_id != a.record_id
    assert make_candidate(artifact_sha="5" * 64).record_id != a.record_id


def test_candidate_record_contains_no_review_or_reliance_state():
    names = {field.name for field in fields(CandidateTranscriptionRecord)}
    assert "reviewer_reference" not in names
    assert "reviewer_note" not in names
    assert "decision" not in names
    assert "approved" not in names
    assert "rejected" not in names
    assert "court_or_tribunal_reliance" not in names


def test_candidate_serialization_round_trip_is_canonical():
    record = make_candidate()
    payload = dumps_candidate_record(record)
    assert loads_candidate_record(payload) == record
    assert dumps_candidate_record(loads_candidate_record(payload)) == payload


def test_candidate_validation_rejects_identity_tamper():
    record = make_candidate()
    tampered = replace(record, provider_reference="openai:other-model")

    with pytest.raises(CandidateTranscriptionValidationError):
        validate_candidate_transcription_record(tampered)


def test_candidate_store_has_explicit_root_and_is_immutable(tmp_path: Path):
    signature = inspect.signature(CandidateTranscriptionStore)
    assert signature.parameters["root"].default is inspect._empty

    record = make_candidate()
    text = "اصل اردو متن\n"
    store = CandidateTranscriptionStore(tmp_path / "candidate-store")

    store.publish_candidate(record=record, transcription_text=text)
    store.publish_candidate(record=record, transcription_text=text)

    assert store.load_candidate(record.record_id) == record
    assert store.read_transcription(record) == text

    with pytest.raises(CandidateTranscriptionValidationError):
        store.publish_candidate(
            record=record,
            transcription_text="different text\n",
        )


def test_review_chain_is_transcription_specific_and_projected():
    candidate = make_candidate()

    first = make_transcription_review_event(
        candidate=candidate,
        decision=TranscriptionReviewDecision.DEFER,
        reviewer_reference="reviewer-1",
        reviewer_note="Needs source-image comparison.",
        reviewed_at_utc="2026-09-09T10:00:00Z",
    )

    second = make_transcription_review_event(
        candidate=candidate,
        decision=TranscriptionReviewDecision.APPROVE,
        reviewer_reference="reviewer-1",
        reviewer_note="Compared against the exact source image.",
        reviewed_at_utc="2026-09-09T10:05:00+00:00",
        existing_events=(first,),
    )

    assert second.previous_event_id == first.event_id
    assert second.candidate_record_id == candidate.record_id
    assert second.transcription_sha256 == candidate.transcription_sha256

    projection = project_transcription_review((second, first))
    assert projection is not None
    assert projection.state is TranscriptionReviewState.APPROVED
    assert projection.candidate_record_id == candidate.record_id
    assert projection.transcription_sha256 == candidate.transcription_sha256
    assert projection.latest_event_id == second.event_id


def test_review_serialization_round_trip_and_store(tmp_path: Path):
    candidate = make_candidate(provider_kind="human", provider_reference="human:operator")

    event = make_transcription_review_event(
        candidate=candidate,
        decision=TranscriptionReviewDecision.REJECT,
        reviewer_reference="reviewer-2",
        reviewer_note="Text does not faithfully match the source.",
        reviewed_at_utc="2026-09-09T11:00:00Z",
    )

    payload = dumps_review_event(event)
    assert loads_review_event(payload) == event

    store = TranscriptionReviewEventStore(tmp_path / "review-store")
    store.publish_event(event)
    store.publish_event(event)

    loaded = store.load_events(candidate.record_id)
    assert loaded == (event,)


def test_review_projection_rejects_forks():
    candidate = make_candidate()

    root = make_transcription_review_event(
        candidate=candidate,
        decision=TranscriptionReviewDecision.DEFER,
        reviewer_reference="reviewer",
        reviewer_note="defer",
        reviewed_at_utc="2026-09-09T09:00:00Z",
    )

    approve = make_transcription_review_event(
        candidate=candidate,
        decision=TranscriptionReviewDecision.APPROVE,
        reviewer_reference="reviewer",
        reviewer_note="approve",
        reviewed_at_utc="2026-09-09T09:01:00Z",
        existing_events=(root,),
    )

    reject = make_transcription_review_event(
        candidate=candidate,
        decision=TranscriptionReviewDecision.REJECT,
        reviewer_reference="reviewer",
        reviewer_note="reject",
        reviewed_at_utc="2026-09-09T09:02:00Z",
        existing_events=(root,),
    )

    with pytest.raises(CandidateTranscriptionValidationError):
        project_transcription_review((root, approve, reject))


def test_foundation_has_no_openai_chroma_streamlit_or_source_evidence_dependency():
    package_root = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "candidate_transcription"
    )

    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(package_root.glob("*.py"))
    ).lower()

    assert "import openai" not in combined
    assert "from openai" not in combined
    assert "chromadb" not in combined
    assert "streamlit" not in combined
    assert "source_evidence" not in combined


def test_foundation_has_no_search_activation_surface():
    package_root = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "candidate_transcription"
    )

    names = {path.name for path in package_root.glob("*.py")}
    assert "activation.py" not in names
    assert "search.py" not in names
