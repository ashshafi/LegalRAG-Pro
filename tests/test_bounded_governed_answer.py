from __future__ import annotations

from types import SimpleNamespace

import bounded_governed_answer as bounded


class _Receipt:
    search_mode = SimpleNamespace(value="document_complete")
    completion = SimpleNamespace(value="complete")
    scope_document_count = 2
    documents_completely_expanded = 2
    scope_page_count = 3
    pages_inspected = 3
    scope_chunk_count = 4
    chunks_inspected = 4
    case_corpus_complete = False
    negative_finding_permitted = True
    negative_finding_scope = SimpleNamespace(value="searched_scope")


class _Evidence:
    search_result = SimpleNamespace(receipt=_Receipt())


class _Responses:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        prompt = kwargs["input"]
        if "FINAL SYNTHESIS" in prompt:
            return SimpleNamespace(output_text="Final solicitor-facing answer")
        ordinal = len(self.calls)
        return SimpleNamespace(
            output_text=(
                f"FINDING | evidence_key=e{min(ordinal, 4)} | "
                f"file=batch-{ordinal}.pdf | page={ordinal} | "
                "classification=context | finding=map finding"
            )
        )


class _Client:
    def __init__(self):
        self.responses = _Responses()


def _results():
    text = "X" * 90
    return {
        "ids": [["e1", "e2", "e3", "e4"]],
        "documents": [[text, text, text, text]],
        "metadatas": [[
            {"file": "a.pdf", "page": 1, "u8_evidence_role": "primary_source",
             "source_document_instance_id": "d1", "u8_semantic_discovery_rank": 1},
            {"file": "a.pdf", "page": 2, "u8_evidence_role": "primary_source",
             "source_document_instance_id": "d1", "u8_semantic_discovery_rank": 1},
            {"file": "b.pdf", "page": 2, "u8_evidence_role": "commentary",
             "source_document_instance_id": "d2", "u8_semantic_discovery_rank": 2},
            {"file": "b.pdf", "page": 3, "u8_evidence_role": "primary_source",
             "source_document_instance_id": "d2", "u8_semantic_discovery_rank": 2},
        ]],
    }


def test_trigger_is_deterministic():
    assert not bounded.should_use_bounded_governed_answer(
        "x" * bounded.BOUNDED_ANSWER_TRIGGER_CHARS
    )
    assert bounded.should_use_bounded_governed_answer(
        "x" * (bounded.BOUNDED_ANSWER_TRIGGER_CHARS + 1)
    )


def test_batch_plan_retains_every_evidence_row_once_and_in_order():
    batches = bounded.build_evidence_batches(_results(), target_chars=10_100)
    indexes = tuple(index for batch in batches for index in batch.row_indexes)
    assert indexes == (0, 1, 2, 3)
    combined = "\n".join(batch.text for batch in batches)
    for key in ("e1", "e2", "e3", "e4"):
        assert f"evidence_key: {key}" in combined


def test_bounded_answer_maps_then_reduces_without_dropping_policy_gate(monkeypatch):
    client = _Client()
    authorised = []
    monkeypatch.setattr(
        bounded,
        "assert_ai_processing_allowed",
        lambda **kwargs: authorised.append(kwargs),
    )
    monkeypatch.setattr(bounded, "BOUNDED_BATCH_TARGET_CHARS", 10_100)

    results = _results()
    results["documents"][0] = ["A" * 6_000, "B" * 6_000, "C" * 6_000, "D" * 6_000]

    response = bounded.create_bounded_governed_response(
        client=client,
        model="gpt-5",
        question="What happened?",
        evidence=_Evidence(),
        enriched_results=results,
    )

    assert response.output_text == "Final solicitor-facing answer"
    assert len(client.responses.calls) >= 3
    assert len(authorised) == len(client.responses.calls)
    assert all(call["store"] is False for call in client.responses.calls)
    assert all(len(call["input"]) < 100_000 for call in client.responses.calls)
    assert "Do not generalise it to the entire case corpus" in client.responses.calls[-1]["input"]


def test_analytical_constraint_is_applied_to_every_map_and_reduce(monkeypatch):
    client = _Client()
    monkeypatch.setattr(bounded, "assert_ai_processing_allowed", lambda **kwargs: None)
    results = _results()
    results["documents"][0] = ["A" * 6_000, "B" * 6_000, "C" * 6_000, "D" * 6_000]
    constrained = []

    def constrain_prompt(*, base_prompt, context):
        assert context == "AUTHORITY"
        constrained.append(base_prompt)
        return "CONSTRAINED\n" + base_prompt

    bounded.create_bounded_governed_response(
        client=client,
        model="gpt-5",
        question="Question",
        evidence=_Evidence(),
        enriched_results=results,
        analytical_context="AUTHORITY",
        constrain_prompt=constrain_prompt,
    )

    assert len(constrained) == len(client.responses.calls)
    assert all(call["input"].startswith("CONSTRAINED\n") for call in client.responses.calls)
