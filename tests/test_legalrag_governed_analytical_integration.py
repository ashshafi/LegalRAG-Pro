from types import SimpleNamespace

import pytest

import governed_analytical_authority.provider as authority_provider
import governed_answer_authority as answer_authority
from governed_analytical_authority.provider import GovernedAnalyticalAuthorityProviderError
from governed_answer_authority import GovernedAnswerAuthorityError
from governed_answer_authority.models import (
    AnalyticalAuthorityMode,
    AuthorityRoutingResult,
    PropositionReference,
    ValidatedGovernedAnswer,
    AnswerStatementBinding,
)


CASE_ID = "11111111-1111-4111-8111-111111111111"
EVIDENCE_KEY = "e1"


def governed_evidence():
    return SimpleNamespace(
        answer_results={
            "ids": [[EVIDENCE_KEY]],
            "documents": [["Frozen evidence text"]],
            "metadatas": [[{"file": "e.pdf", "page": 1}]],
        },
        search_mode=SimpleNamespace(value="document_complete"),
        semantic_receipt=SimpleNamespace(),
        search_result=SimpleNamespace(receipt=SimpleNamespace()),
    )


class Responses:
    def __init__(self, output_text):
        self.output_text = output_text
        self.calls = []

    def create(self, *, model, input):
        self.calls.append(input)
        return SimpleNamespace(output_text=self.output_text)


def patch_case_u8(monkeypatch, legalrag):
    evidence = governed_evidence()
    monkeypatch.setattr(legalrag, "prepare_governed_answer_evidence", lambda **kwargs: evidence)
    monkeypatch.setattr(legalrag, "enrich_evidence_semantics", lambda value: value)
    monkeypatch.setattr(legalrag, "build_governed_answer_prompt", lambda **kwargs: "U8 PROMPT")
    return evidence


def test_no_case_preserves_legacy_provider_boundary(monkeypatch, legalrag_module):
    legalrag, client = legalrag_module
    monkeypatch.setattr(legalrag, "retrieve", lambda *args, **kwargs: {
        "ids": [[]], "documents": [[]], "metadatas": [[]]
    })
    monkeypatch.setattr(legalrag, "enrich_evidence_semantics", lambda value: value)
    monkeypatch.setattr(legalrag, "build_semantic_context", lambda value: "CTX")
    monkeypatch.setattr(legalrag, "build_semantic_legal_prompt", lambda **kwargs: "LEGACY")
    monkeypatch.setattr(
        authority_provider,
        "load_active_governed_analytical_authority",
        lambda case_id: (_ for _ in ()).throw(AssertionError("provider must not be called")),
    )
    result = legalrag.ask("Question", case_id=None)
    assert result["answer"] == "Governed answer"
    assert "analytical_authority_mode" not in result


def test_absent_authority_uses_existing_u8_prompt(monkeypatch, legalrag_module):
    legalrag, client = legalrag_module
    patch_case_u8(monkeypatch, legalrag)
    monkeypatch.setattr(authority_provider, "load_active_governed_analytical_authority", lambda case_id: None)
    result = legalrag.ask("Question", case_id=CASE_ID)
    assert client.responses.calls == ["U8 PROMPT"]
    assert result["answer"] == "Governed answer"
    assert result["analytical_authority_mode"] == "absent"


def test_unavailable_authority_uses_existing_u8_prompt(monkeypatch, legalrag_module):
    legalrag, client = legalrag_module
    patch_case_u8(monkeypatch, legalrag)
    authority = SimpleNamespace(
        manifest=SimpleNamespace(authority_id="sha256:" + "a" * 64),
        active_pointer=SimpleNamespace(activation_id="sha256:" + "b" * 64),
    )
    monkeypatch.setattr(authority_provider, "load_active_governed_analytical_authority", lambda case_id: authority)
    monkeypatch.setattr(
        answer_authority,
        "route_question_to_active_authority",
        lambda **kwargs: AuthorityRoutingResult(
            mode=AnalyticalAuthorityMode.UNAVAILABLE,
            reason="No unique frozen analysis.",
        ),
    )
    result = legalrag.ask("Question", case_id=CASE_ID)
    assert client.responses.calls == ["U8 PROMPT"]
    assert result["analytical_authority_mode"] == "unavailable"


def test_applied_authority_returns_only_validated_rendered_answer(monkeypatch, legalrag_module):
    legalrag, client = legalrag_module
    patch_case_u8(monkeypatch, legalrag)
    authority = SimpleNamespace(
        manifest=SimpleNamespace(authority_id="sha256:" + "a" * 64),
        active_pointer=SimpleNamespace(activation_id="sha256:" + "b" * 64),
    )
    route = AuthorityRoutingResult(
        mode=AnalyticalAuthorityMode.APPLIED,
        reason="exact",
        issue_analysis_id="a1",
        issue_definition_id="RA-001",
        issue_definition_version="1.0",
        issue_name="Reasonable adjustments",
        selector_version="selector/1.0",
    )
    context = SimpleNamespace()
    binding = AnswerStatementBinding(
        statement_id="S1",
        statement_text="The record supports the point but does not establish it.",
        source_proposition_refs=(PropositionReference("a1", "E1", 0),),
        evidence_keys=(EVIDENCE_KEY,),
        source_status="supported_but_not_established",
    )
    validated = ValidatedGovernedAnswer(
        answer="[supported_but_not_established] Frozen proposition.",
        bindings=(binding,),
        relied_evidence_keys=(EVIDENCE_KEY,),
    )
    monkeypatch.setattr(authority_provider, "load_active_governed_analytical_authority", lambda case_id: authority)
    monkeypatch.setattr(answer_authority, "route_question_to_active_authority", lambda **kwargs: route)
    monkeypatch.setattr(answer_authority, "build_runtime_authority_context", lambda **kwargs: context)
    monkeypatch.setattr(answer_authority, "build_constrained_governed_answer_prompt", lambda **kwargs: "CONSTRAINED")
    monkeypatch.setattr(answer_authority, "validate_answer_statement_bindings", lambda **kwargs: validated)

    result = legalrag.ask("Question", case_id=CASE_ID)
    assert client.responses.calls == ["CONSTRAINED"]
    assert result["answer"] == validated.answer
    assert result["analytical_authority_mode"] == "applied"
    assert result["relied_evidence_keys"] == [EVIDENCE_KEY]
    assert result["search_results"]["ids"] == [[EVIDENCE_KEY]]


def test_invalid_provider_fails_closed_before_openai(monkeypatch, legalrag_module):
    legalrag, client = legalrag_module
    patch_case_u8(monkeypatch, legalrag)
    error = GovernedAnalyticalAuthorityProviderError("tampered")
    monkeypatch.setattr(
        authority_provider,
        "load_active_governed_analytical_authority",
        lambda case_id: (_ for _ in ()).throw(error),
    )
    result = legalrag.ask("Question", case_id=CASE_ID)
    assert client.responses.calls == []
    assert result["retrieval_mode"] == "document_complete"
    assert result["analytical_authority_mode"] == "invalid_authority"


def test_invalid_binding_fails_closed_and_never_returns_raw_output(monkeypatch, legalrag_module):
    legalrag, client = legalrag_module
    patch_case_u8(monkeypatch, legalrag)
    authority = SimpleNamespace(
        manifest=SimpleNamespace(authority_id="sha256:" + "a" * 64),
        active_pointer=SimpleNamespace(activation_id="sha256:" + "b" * 64),
    )
    monkeypatch.setattr(authority_provider, "load_active_governed_analytical_authority", lambda case_id: authority)
    monkeypatch.setattr(
        answer_authority,
        "route_question_to_active_authority",
        lambda **kwargs: AuthorityRoutingResult(
            mode=AnalyticalAuthorityMode.APPLIED,
            reason="exact",
            issue_analysis_id="a1",
            issue_definition_id="RA-001",
            issue_definition_version="1.0",
            issue_name="Reasonable adjustments",
            selector_version="selector/1.0",
        ),
    )
    monkeypatch.setattr(answer_authority, "build_runtime_authority_context", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(answer_authority, "build_constrained_governed_answer_prompt", lambda **kwargs: "CONSTRAINED")
    monkeypatch.setattr(
        answer_authority,
        "validate_answer_statement_bindings",
        lambda **kwargs: (_ for _ in ()).throw(GovernedAnswerAuthorityError("invalid")),
    )
    result = legalrag.ask("Question", case_id=CASE_ID)
    assert client.responses.calls == ["CONSTRAINED"]
    assert result["answer"] != "Governed answer"
    assert result["retrieval_mode"] == "document_complete"
    assert result["analytical_authority_mode"] == "invalid_analytical_output"


@pytest.fixture
def legalrag_module(monkeypatch):
    import importlib
    import sys
    import types

    client = SimpleNamespace(responses=Responses("Governed answer"))
    config = types.ModuleType("config")
    config.openai_client = client
    config.collection = SimpleNamespace()
    monkeypatch.setitem(sys.modules, "config", config)
    sys.modules.pop("legalrag", None)
    sys.modules.pop("retriever", None)
    module = importlib.import_module("legalrag")
    return module, client
