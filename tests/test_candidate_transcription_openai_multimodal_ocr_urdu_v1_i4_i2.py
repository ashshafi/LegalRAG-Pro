from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

import candidate_transcription.openai_multimodal as multimodal
from ai_provider_policy import (
    AIDataClassification,
    AIProcessingAuthorization,
    AIProcessingPurpose,
    AIProviderPolicyError,
)


IMAGE_BYTES = b"exact-derived-image-bytes"
IMAGE_SHA = hashlib.sha256(IMAGE_BYTES).hexdigest()


def authorization(model: str = "gpt-test") -> AIProcessingAuthorization:
    return AIProcessingAuthorization(
        policy_sha256="sha256:" + ("1" * 64),
        profile_reference="policy:test",
        external_evidence_reference="evidence:test",
        provider="openai",
        purpose=AIProcessingPurpose.CANDIDATE_TRANSCRIPTION,
        data_classification=AIDataClassification.PRIVILEGED,
        model=model,
        retention_profile="test-retention",
    )


class FakeResponses:
    def __init__(self, *, events: list[str], output_text: object = "candidate text"):
        self.events = events
        self.output_text = output_text
        self.calls: list[dict[str, object]] = []
        self.error: Exception | None = None

    def create(self, **kwargs):
        self.events.append("create")
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(output_text=self.output_text)


class FakeClient:
    def __init__(self, responses: FakeResponses):
        self.responses = responses


def call_adapter(*, client, model: str = "gpt-test"):
    return multimodal.transcribe_candidate_image(
        client=client,
        model=model,
        image_bytes=IMAGE_BYTES,
        media_type="image/png",
        derived_artifact_sha256=IMAGE_SHA,
        derived_artifact_width=2009,
        derived_artifact_height=1500,
    )


def test_candidate_transcription_processing_purpose_is_explicit():
    assert (
        AIProcessingPurpose.CANDIDATE_TRANSCRIPTION.value
        == "candidate_transcription"
    )


def test_policy_gate_precedes_exact_multimodal_request(monkeypatch):
    events: list[str] = []
    responses = FakeResponses(events=events, output_text="exact candidate\n")
    client = FakeClient(responses)

    def fake_policy(**kwargs):
        events.append("policy")
        assert kwargs == {
            "provider": "openai",
            "purpose": AIProcessingPurpose.CANDIDATE_TRANSCRIPTION,
            "data_classification": AIDataClassification.PRIVILEGED,
            "model": "gpt-test",
        }
        return authorization()

    monkeypatch.setattr(multimodal, "assert_ai_processing_allowed", fake_policy)

    receipt = call_adapter(client=client)

    assert events == ["policy", "create"]
    assert len(responses.calls) == 1

    request = responses.calls[0]
    assert request["model"] == "gpt-test"
    assert request["store"] is False

    messages = request["input"]
    assert isinstance(messages, list)
    assert len(messages) == 2

    system_message = messages[0]
    user_message = messages[1]

    assert system_message["role"] == "system"
    assert system_message["content"][0]["type"] == "input_text"

    assert user_message["role"] == "user"
    user_content = user_message["content"]
    assert [item["type"] for item in user_content] == [
        "input_text",
        "input_image",
    ]

    expected_url = (
        "data:image/png;base64,"
        + base64.b64encode(IMAGE_BYTES).decode("ascii")
    )
    assert user_content[1]["image_url"] == expected_url
    assert user_content[1]["detail"] == "high"

    instruction = user_content[0]["text"]
    assert IMAGE_SHA in instruction
    assert "2009x1500" in instruction
    assert "image/png" in instruction

    assert receipt.transcription_text == "exact candidate\n"
    assert receipt.provider == "openai"
    assert receipt.model == "gpt-test"
    assert receipt.provider_reference == "openai:gpt-test"
    assert receipt.provider_kind == "ai_multimodal"
    assert receipt.derived_artifact_sha256 == IMAGE_SHA
    assert receipt.derived_artifact_byte_length == len(IMAGE_BYTES)
    assert receipt.derived_artifact_width == 2009
    assert receipt.derived_artifact_height == 1500
    assert receipt.media_type == "image/png"
    assert receipt.policy_sha256 == "sha256:" + ("1" * 64)
    assert receipt.policy_profile_reference == "policy:test"
    assert receipt.policy_external_evidence_reference == "evidence:test"
    assert receipt.policy_retention_profile == "test-retention"


def test_artifact_hash_mismatch_fails_before_policy_or_api(monkeypatch):
    events: list[str] = []
    responses = FakeResponses(events=events)
    client = FakeClient(responses)

    monkeypatch.setattr(
        multimodal,
        "assert_ai_processing_allowed",
        lambda **kwargs: events.append("policy"),
    )

    with pytest.raises(
        multimodal.OpenAIMultimodalTranscriptionError,
        match="do not match",
    ):
        multimodal.transcribe_candidate_image(
            client=client,
            model="gpt-test",
            image_bytes=IMAGE_BYTES,
            media_type="image/png",
            derived_artifact_sha256="0" * 64,
            derived_artifact_width=2009,
            derived_artifact_height=1500,
        )

    assert events == []
    assert responses.calls == []


def test_policy_denial_fails_closed_before_api_call(monkeypatch):
    events: list[str] = []
    responses = FakeResponses(events=events)
    client = FakeClient(responses)

    def deny(**kwargs):
        events.append("policy")
        raise AIProviderPolicyError("denied")

    monkeypatch.setattr(multimodal, "assert_ai_processing_allowed", deny)

    with pytest.raises(
        multimodal.OpenAIMultimodalTranscriptionError,
        match="denied",
    ):
        call_adapter(client=client)

    assert events == ["policy"]
    assert responses.calls == []


def test_api_error_is_wrapped_after_policy_gate(monkeypatch):
    events: list[str] = []
    responses = FakeResponses(events=events)
    responses.error = RuntimeError("transport failure")
    client = FakeClient(responses)

    monkeypatch.setattr(
        multimodal,
        "assert_ai_processing_allowed",
        lambda **kwargs: (
            events.append("policy"),
            authorization(),
        )[1],
    )

    with pytest.raises(
        multimodal.OpenAIMultimodalTranscriptionError,
        match="call failed",
    ):
        call_adapter(client=client)

    assert events == ["policy", "create"]


@pytest.mark.parametrize("output_text", [None, "", "   "])
def test_empty_output_text_is_rejected(monkeypatch, output_text):
    events: list[str] = []
    responses = FakeResponses(events=events, output_text=output_text)
    client = FakeClient(responses)

    monkeypatch.setattr(
        multimodal,
        "assert_ai_processing_allowed",
        lambda **kwargs: authorization(),
    )

    with pytest.raises(
        multimodal.OpenAIMultimodalTranscriptionError,
        match="non-empty output_text",
    ):
        call_adapter(client=client)


@pytest.mark.parametrize(
    ("media_type", "width", "height"),
    [
        ("application/pdf", 2009, 1500),
        ("image/png", 0, 1500),
        ("image/png", 2009, 0),
    ],
)
def test_invalid_artifact_metadata_is_rejected_before_policy(
    monkeypatch,
    media_type,
    width,
    height,
):
    calls = []
    monkeypatch.setattr(
        multimodal,
        "assert_ai_processing_allowed",
        lambda **kwargs: calls.append(kwargs),
    )

    with pytest.raises(multimodal.OpenAIMultimodalTranscriptionError):
        multimodal.transcribe_candidate_image(
            client=FakeClient(FakeResponses(events=[])),
            model="gpt-test",
            image_bytes=IMAGE_BYTES,
            media_type=media_type,
            derived_artifact_sha256=IMAGE_SHA,
            derived_artifact_width=width,
            derived_artifact_height=height,
        )

    assert calls == []


def test_adapter_has_no_forbidden_foundation_dependencies_or_publication_surface():
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "candidate_transcription"
        / "openai_multimodal.py"
    ).read_text(encoding="utf-8").lower()

    assert "import openai" not in source
    assert "from openai" not in source
    assert "source_evidence" not in source
    assert "chromadb" not in source
    assert "streamlit" not in source
    assert "candidate_transcriptionstore" not in source
    assert "publish_candidate(" not in source
    assert "transcriptionreview" not in source
