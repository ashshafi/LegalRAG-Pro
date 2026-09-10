from __future__ import annotations

from types import SimpleNamespace

import pytest

import marriage_document_extraction.service as service
from marriage_document_extraction import (
    MarriageFactExtractionError,
    OpenAIMarriageFactExtractionProvider,
    build_marriage_fact_extraction_output_schema,
    build_marriage_fact_extraction_prompt,
    extract_marriage_document_intelligence,
    extraction_record_receipt,
    validate_extraction_payload,
)
from marriage_document_intelligence import (
    MarriageFactDerivationKind,
    MarriageFactField,
    MarriageTextRepresentationKind,
)


def sha_hex(char: str) -> str:
    return char * 64


def sha_id(char: str) -> str:
    return "sha256:" + sha_hex(char)


class FakeProvider:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def extract(self, *, model: str, transcription_text: str):
        self.calls.append((model, transcription_text))
        return self.payload


def source_values():
    candidate = SimpleNamespace(
        record_id=sha_id("a"),
        source_document_instance_id="doc-1",
        source_snapshot_id="snapshot-1",
        original_filename="nikah-nama.pdf",
        original_blob_sha256=sha_hex("b"),
        page_number=1,
        transcription_sha256=sha_hex("c"),
    )
    binding = SimpleNamespace(
        binding_id=sha_id("d"),
        crop_name="registration-panel",
        bbox=(10, 20, 300, 180),
    )
    receipt = SimpleNamespace(receipt_id=sha_id("e"))
    review_projection = SimpleNamespace(
        latest_event_id=sha_id("f")
    )
    return candidate, binding, receipt, review_projection


def payload():
    return {
        "document_type": "nikah_nama",
        "document_label": "Urdu Nikah Nama registration panel",
        "facts": [
            {
                "field": "bride_name",
                "value": "Example Bride",
                "derivation_kind": "ocr_derived",
                "quality_note": "Clearly represented in the transcription.",
            },
            {
                "field": "registration_number",
                "value": "123/2000",
                "derivation_kind": "ocr_derived",
                "quality_note": "Number is legible in the transcription.",
            },
        ],
        "ai_assisted_english_translation": "AI-assisted translation.",
        "plain_english_explanation": (
            "The passage appears to record marriage registration particulars."
        ),
        "potential_issues": [
            "Check the registration number against the original Union Council record."
        ],
        "next_professional_actions": [
            "Compare the registration particulars with the Union Council record."
        ],
    }


@pytest.fixture(autouse=True)
def governance_gate(monkeypatch):
    calls = []

    def gate(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        service,
        "validate_targeted_candidate_governance_gate",
        gate,
    )
    return calls


def test_mdi1_package_remains_pure_domain_package():
    import marriage_document_intelligence
    root = __import__("pathlib").Path(
        marriage_document_intelligence.__file__
    ).parent
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(root.glob("*.py"))
    ).lower()

    for forbidden in (
        "import openai",
        "from openai",
        "chromadb",
        "streamlit",
        "persistentclient",
        "embeddings.create",
    ):
        assert forbidden not in source


def test_schema_is_strict_and_closed():
    schema = build_marriage_fact_extraction_output_schema()
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    fact = schema["properties"]["facts"]["items"]
    assert fact["additionalProperties"] is False
    assert set(fact["required"]) == set(fact["properties"])


def test_prompt_forbids_guessing_and_legal_conclusions():
    prompt = build_marriage_fact_extraction_prompt("Ø§Ø±Ø¯Ùˆ Ù…ØªÙ†")
    assert "Do not guess missing facts" in prompt
    assert "legally valid" in prompt
    assert "authenticity, fraud or forgery" in prompt
    assert "not a certified translation" in prompt


def test_payload_rejects_unknown_top_level_key():
    value = payload()
    value["unknown"] = "x"
    with pytest.raises(
        MarriageFactExtractionError,
        match="unexpected or missing top-level",
    ):
        validate_extraction_payload(value)


def test_payload_rejects_unknown_fact_field():
    value = payload()
    value["facts"][0]["field"] = "invented_field"
    with pytest.raises(
        MarriageFactExtractionError,
        match="unsupported field",
    ):
        validate_extraction_payload(value)


def test_payload_rejects_duplicate_exact_fact():
    value = payload()
    value["facts"].append(dict(value["facts"][0]))
    with pytest.raises(
        MarriageFactExtractionError,
        match="exact duplicate fact",
    ):
        validate_extraction_payload(value)


def test_payload_rejects_conclusive_language_in_explanation():
    value = payload()
    value["plain_english_explanation"] = "The marriage is valid."
    with pytest.raises(
        MarriageFactExtractionError,
        match="prohibited conclusive legal statement",
    ):
        validate_extraction_payload(value)


def test_service_attaches_application_supplied_provenance(governance_gate):
    candidate, binding, receipt, projection = source_values()
    provider = FakeProvider(payload())

    record = extract_marriage_document_intelligence(
        candidate=candidate,
        transcription_text="approved transcription",
        binding=binding,
        receipt=receipt,
        review_projection=projection,
        provider=provider,
        model="test-model",
    )

    assert len(governance_gate) == 1
    assert provider.calls == [
        ("test-model", "approved transcription")
    ]

    fact = record.facts[0]
    assert fact.field is MarriageFactField.BRIDE_NAME
    assert fact.provenance.candidate_record_id == candidate.record_id
    assert fact.provenance.transcription_sha256 == candidate.transcription_sha256
    assert fact.provenance.review_event_id == projection.latest_event_id
    assert fact.provenance.binding_id == binding.binding_id
    assert fact.provenance.publication_receipt_id == receipt.receipt_id
    assert fact.provenance.crop_name == binding.crop_name
    assert fact.provenance.bbox.left == 10
    assert fact.provenance.bbox.bottom == 180


def test_ai_text_is_labelled_but_never_certified():
    candidate, binding, receipt, projection = source_values()
    record = extract_marriage_document_intelligence(
        candidate=candidate,
        transcription_text="approved transcription",
        binding=binding,
        receipt=receipt,
        review_projection=projection,
        provider=FakeProvider(payload()),
        model="test-model",
    )

    assert tuple(
        item.kind for item in record.text_representations
    ) == (
        MarriageTextRepresentationKind.AI_ASSISTED_ENGLISH_TRANSLATION,
        MarriageTextRepresentationKind.PLAIN_ENGLISH_EXPLANATION,
    )
    assert all(item.produced_by_legalrag for item in record.text_representations)
    assert record.text_representations[0].provenance.derivation_kind is (
        MarriageFactDerivationKind.AI_TRANSLATED
    )


def test_zero_facts_is_allowed_when_source_is_unclear():
    value = payload()
    value["facts"] = []
    candidate, binding, receipt, projection = source_values()

    record = extract_marriage_document_intelligence(
        candidate=candidate,
        transcription_text="unclear transcription",
        binding=binding,
        receipt=receipt,
        review_projection=projection,
        provider=FakeProvider(value),
        model="test-model",
    )
    assert record.facts == ()


def test_receipt_is_deterministic():
    candidate, binding, receipt, projection = source_values()
    record = extract_marriage_document_intelligence(
        candidate=candidate,
        transcription_text="approved transcription",
        binding=binding,
        receipt=receipt,
        review_projection=projection,
        provider=FakeProvider(payload()),
        model="test-model",
    )

    one = extraction_record_receipt(record)
    two = extraction_record_receipt(record)
    assert one == two
    assert len(one["sha256"]) == 64
    assert one["utf8_bytes"] > 0


def test_openai_adapter_uses_one_strict_responses_call():
    calls = []

    class Responses:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                output_text=__import__("json").dumps(payload())
            )

    provider = OpenAIMarriageFactExtractionProvider(
        client=SimpleNamespace(responses=Responses())
    )
    result = provider.extract(
        model="test-model",
        transcription_text="approved transcription",
    )

    assert result["document_type"] == "nikah_nama"
    assert len(calls) == 1
    call = calls[0]
    assert call["model"] == "test-model"
    assert call["store"] is False
    fmt = call["text"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["name"] == "marriage_document_fact_extraction"
    assert fmt["strict"] is True


def test_openai_adapter_rejects_non_json_output():
    class Responses:
        def create(self, **kwargs):
            return SimpleNamespace(output_text="not-json")

    provider = OpenAIMarriageFactExtractionProvider(
        client=SimpleNamespace(responses=Responses())
    )

    with pytest.raises(
        MarriageFactExtractionError,
        match="invalid JSON",
    ):
        provider.extract(
            model="test-model",
            transcription_text="approved transcription",
        )


@pytest.fixture(autouse=True)
def _allow_openai_provider_policy_for_unit_tests(monkeypatch):
    import marriage_document_extraction.openai_provider as provider_module

    monkeypatch.setattr(
        provider_module,
        "assert_ai_processing_allowed",
        lambda **kwargs: object(),
    )
