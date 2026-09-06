from pathlib import Path
from types import SimpleNamespace
import bounded_governed_answer as bounded

class _Receipt:
    search_mode = SimpleNamespace(value="document_complete")
    completion = SimpleNamespace(value="complete")
    searched_document_ids = ("doc-1",)
    case_corpus_complete = False
    negative_finding_permitted = True
    negative_finding_scope = SimpleNamespace(value="searched_scope")
    documents_inspected = 1
    pages_inspected = 1
    chunks_inspected = 2
    scope_document_count = 1
    scope_page_count = 1
    scope_chunk_count = 2
    documents_completely_expanded = 1

class _SearchResult:
    receipt = _Receipt()

class _Evidence:
    search_result = _SearchResult()
    search_mode = SimpleNamespace(value="document_complete")

class _Responses:
    def __init__(self):
        self.calls = []
    def create(self, **kwargs):
        self.calls.append(kwargs)
        if "FINAL SYNTHESIS" in kwargs["input"]:
            return SimpleNamespace(output_text="Final new-finding answer")
        return SimpleNamespace(output_text="FINDING | evidence_key=e1 | file=Grounds.pdf | page=4 | classification=respondent_submission | finding=pleaded position")

class _Client:
    def __init__(self):
        self.responses = _Responses()

def _results():
    return {
        "ids": [["e1", "e2"]],
        "documents": [["A" * 6000, "B" * 6000]],
        "metadatas": [[
            {"file": "Grounds.pdf", "page": 4},
            {"file": "Unum.pdf", "page": 2},
        ]],
    }

def _wrapper(*, base_prompt, question):
    return "NEW AI FINDING ? SOURCE COMPARISON\nnot yet part of Current Assessment\n" + question + "\n" + base_prompt

def test_bounded_new_finding_preserves_wrapper_model_and_reasoning(monkeypatch):
    client = _Client()
    monkeypatch.setattr(bounded, "_authorise", lambda model: None)
    response = bounded.create_bounded_governed_response(
        client=client,
        model="gpt-5.6-terra",
        question="Compare paragraphs 27-30.",
        evidence=_Evidence(),
        enriched_results=_results(),
        prompt_wrapper=_wrapper,
        reasoning_effort="none",
    )
    assert response.output_text == "Final new-finding answer"
    assert len(client.responses.calls) >= 2
    assert all(call["model"] == "gpt-5.6-terra" for call in client.responses.calls)
    assert all(call["reasoning"] == {"effort": "none"} for call in client.responses.calls)
    assert all(call["store"] is False for call in client.responses.calls)
    assert all("NEW AI FINDING ? SOURCE COMPARISON" in call["input"] for call in client.responses.calls)

def test_legacy_bounded_calls_do_not_gain_reasoning(monkeypatch):
    client = _Client()
    monkeypatch.setattr(bounded, "_authorise", lambda model: None)
    bounded.create_bounded_governed_response(
        client=client,
        model="gpt-5",
        question="Question",
        evidence=_Evidence(),
        enriched_results=_results(),
    )
    assert all("reasoning" not in call for call in client.responses.calls)

def test_empty_provider_text_reports_provider_status(monkeypatch):
    monkeypatch.setattr(bounded, "_authorise", lambda model: None)
    class EmptyResponses:
        def create(self, **kwargs):
            return SimpleNamespace(output_text="", status="incomplete", incomplete_details=SimpleNamespace(reason="max_output_tokens"))
    client = SimpleNamespace(responses=EmptyResponses())
    try:
        bounded._provider_call(client, model="gpt-5.6-terra", prompt="x", max_output_tokens=10, reasoning_effort="none")
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected RuntimeError")
    assert "status=incomplete" in message
    assert "incomplete_reason=max_output_tokens" in message

def test_legalrag_routes_bounded_new_finding_to_interactive_model_and_wrapper():
    source = Path("src/legalrag.py").read_text(encoding="utf-8-sig")
    assert "model=(INTERACTIVE_CHAT_MODEL if new_ai_finding_mode else CHAT_MODEL)" in source
    assert "prompt_wrapper=(" in source
    assert "wrap_source_comparison_new_ai_finding_prompt" in source
    assert "reasoning_effort=(" in source
    assert "INTERACTIVE_REASONING_EFFORT" in source
