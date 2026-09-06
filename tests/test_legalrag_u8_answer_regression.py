from __future__ import annotations

import importlib
import sys
import types
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from evidence_answer import GovernedAnswerEvidenceError
from evidence_search import EvidenceSearchMode


CASE_ID = "11111111-1111-4111-8111-111111111111"
DOC_ID = "55555555-5555-4555-8555-555555555555"
EVIDENCE_KEY = "evidence-5555-1-0"


class _Responses:
    def __init__(self):
        self.calls = []

    def create(self, *, model, input, store):
        assert store is False
        self.calls.append({"model": model, "input": input, "store": store})
        return SimpleNamespace(output_text="Governed answer")


class _Client:
    def __init__(self):
        self.responses = _Responses()


@pytest.fixture
def legalrag_module(monkeypatch):
    client = _Client()
    config = types.ModuleType("config")
    config.openai_client = client
    config.collection = SimpleNamespace()
    monkeypatch.setitem(sys.modules, "config", config)
    sys.modules.pop("legalrag", None)
    sys.modules.pop("retriever", None)
    sys.modules.pop("query_expander", None)
    module = importlib.import_module("legalrag")
    return module, client


def _answer_results():
    return {
        "ids": [[EVIDENCE_KEY]],
        "documents": [["From: HR Director\nWe will discuss the phased return."]],
        "metadatas": [[{
            "case_id": CASE_ID,
            "file": "Appendix H5.pdf",
            "page": 1,
            "chunk": 0,
            "evidence_source_type": "employer_record",
            "evidence_source_label": "Employer evidence",
            "evidence_classification_method": "automatic",
            "chunk_source_type": "employer_record",
            "chunk_source_label": "Employer evidence",
            "chunk_provenance_method": "chunk-leading-sender",
            "primary_source_tier": 4,
            "primary_source_label": "Primary/direct record",
            "u8_evidence_role": "primary_source",
            "u8_evidence_role_rule": "primary-direct-record",
            "u8_evidence_role_basis": "direct employer correspondence",
            "u8_semantic_discovery_rank": 3,
            "u8_governed_search_mode": "document_complete",
            "source_document_instance_id": DOC_ID,
        }]],
    }


def _governed_stub():
    receipt = SimpleNamespace()
    search_result = SimpleNamespace(receipt=receipt)
    return SimpleNamespace(
        answer_results=_answer_results(),
        search_mode=EvidenceSearchMode.DOCUMENT_COMPLETE,
        semantic_receipt=SimpleNamespace(),
        search_result=search_result,
        case_id=CASE_ID,
        question="Did CACI fail to make reasonable adjustments?",
    )


def test_case_scoped_answer_uses_governed_u8_evidence_and_not_legacy_retrieve(
    legalrag_module,
    monkeypatch,
):
    legalrag, client = legalrag_module
    governed = _governed_stub()
    monkeypatch.setattr(legalrag, "prepare_governed_answer_evidence", lambda **kwargs: governed)
    monkeypatch.setattr(
        legalrag,
        "build_governed_answer_prompt",
        lambda **kwargs: "U8 governed prompt with complete primary evidence",
    )
    monkeypatch.setattr(
        legalrag,
        "retrieve",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy retrieve called")),
    )

    result = legalrag.ask(
        "Did CACI fail to make reasonable adjustments?",
        ["Appendix H5.pdf"],
        case_id=CASE_ID,
    )

    assert result["answer"] == "Governed answer"
    assert result["retrieval_mode"] == "document_complete"
    assert len(client.responses.calls) == 1
    assert client.responses.calls[0]["input"] == "U8 governed prompt with complete primary evidence"
    assert client.responses.calls[0]["store"] is False
    assert result["sources"][0]["evidence_role"] == "primary_source"
    assert result["sources"][0]["source_document_instance_id"] == DOC_ID
    assert result["sources"][0]["evidence_key"] == EVIDENCE_KEY


def test_governed_failure_returns_safe_non_negative_answer_without_calling_model(
    legalrag_module,
    monkeypatch,
):
    legalrag, client = legalrag_module

    def fail(**kwargs):
        raise GovernedAnswerEvidenceError("partial semantic search cannot establish absence")

    monkeypatch.setattr(legalrag, "prepare_governed_answer_evidence", fail)

    result = legalrag.ask("Is there no evidence?", case_id=CASE_ID)

    assert "could not establish a complete governed evidence set" in result["answer"]
    assert "No corpus-level negative finding has been made" in result["answer"]
    assert result["sources"] == []
    assert result["retrieval_mode"] == "governed_failed_closed"
    assert client.responses.calls == []


def test_global_legacy_answer_path_remains_unchanged_when_case_id_is_absent(
    legalrag_module,
    monkeypatch,
):
    legalrag, client = legalrag_module
    calls = []
    legacy_results = {
        "ids": [["legacy-1"]],
        "documents": [["Legacy evidence text"]],
        "metadatas": [[{"file": "legacy.pdf", "page": 1}]],
    }

    def legacy(question, selected_documents, n_results, *, case_id):
        calls.append((question, selected_documents, n_results, case_id))
        return legacy_results

    monkeypatch.setattr(legalrag, "retrieve", legacy)
    monkeypatch.setattr(
        legalrag,
        "prepare_governed_answer_evidence",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("governed path called")),
    )

    result = legalrag.ask("Legacy question", ["legacy.pdf"])

    assert calls == [("Legacy question", ["legacy.pdf"], 10, None)]
    assert result["answer"] == "Governed answer"
    assert "retrieval_mode" not in result
    assert result["sources"][0]["file"] == "legacy.pdf"
    assert len(client.responses.calls) == 1


def test_case_scoped_sources_preserve_complete_u8_role_and_discovery_audit_fields(
    legalrag_module,
    monkeypatch,
):
    legalrag, _ = legalrag_module
    governed = _governed_stub()
    monkeypatch.setattr(legalrag, "prepare_governed_answer_evidence", lambda **kwargs: governed)
    monkeypatch.setattr(legalrag, "build_governed_answer_prompt", lambda **kwargs: "prompt")

    result = legalrag.ask("Question", case_id=CASE_ID)
    source = result["sources"][0]

    assert source["evidence_role"] == "primary_source"
    assert source["evidence_role_rule"] == "primary-direct-record"
    assert source["evidence_role_basis"] == "direct employer correspondence"
    assert source["semantic_discovery_rank"] == 3
    assert source["governed_search_mode"] == "document_complete"
