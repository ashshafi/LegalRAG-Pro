from __future__ import annotations

import importlib
import sys
import types
from types import SimpleNamespace

import pytest

from evidence_references import (
    CaseEvidenceReferenceResolution,
    EvidenceReference,
    EvidenceReferenceKind,
    EvidenceReferenceResolution,
    EvidenceReferenceResolutionReceipt,
    EvidenceReferenceResolutionStatus,
)
from evidence_search import (
    EvidenceSearchCompletion,
    EvidenceSearchError,
    EvidenceSearchMode,
    NegativeFindingScope,
)


CASE_ID = "11111111-1111-4111-8111-111111111111"
H4_ID = "44444444-4444-4444-8444-444444444444"
H5_ID = "55555555-5555-4555-8555-555555555555"
H6_ID = "66666666-6666-4666-8666-666666666666"



@pytest.fixture
def bridge_module(monkeypatch):
    config = types.ModuleType("config")
    config.openai_client = SimpleNamespace()
    config.collection = SimpleNamespace()
    monkeypatch.setitem(sys.modules, "config", config)
    sys.modules.pop("legalrag", None)
    sys.modules.pop("evidence_reference_bridge.answer", None)
    sys.modules.pop("evidence_reference_bridge", None)
    return importlib.import_module("evidence_reference_bridge.answer")


def _reference(*, evidence_key: str, ref_id_char: str, date_text: str):
    return EvidenceReference(
        reference_id="sha256:" + ref_id_char * 64,
        source_document_instance_id=H5_ID if evidence_key == "scope-key" else H6_ID,
        source_filename="Appendix H5.pdf" if evidence_key == "scope-key" else "Appendix H6.pdf",
        source_evidence_key=evidence_key,
        source_page_number=1,
        source_chunk_ordinal=0,
        source_reference_ordinal=0,
        kind=EvidenceReferenceKind.COMMUNICATION,
        raw_reference_text=f"email from Emma Shakespeare dated {date_text}",
        normalized_target=f"communication:email|person:emma shakespeare|date:{date_text}",
        communication_type="email",
        person_text="Emma Shakespeare",
        date_text=date_text,
        canonical_date="2005-07-06" if date_text.startswith("6") else "2005-07-05",
    )


def _whole_resolution():
    in_scope = EvidenceReferenceResolution(
        reference=_reference(evidence_key="scope-key", ref_id_char="a", date_text="6 July 2005"),
        status=EvidenceReferenceResolutionStatus.POSSIBLE_REFERENCED_BUT_NOT_LOCATED,
        matched_document_ids=(),
        matched_evidence_keys=(),
        basis="No governed communication matched after complete case-corpus inspection.",
    )
    out_scope = EvidenceReferenceResolution(
        reference=_reference(evidence_key="other-key", ref_id_char="b", date_text="5 July 2005"),
        status=EvidenceReferenceResolutionStatus.RESOLVED,
        matched_document_ids=(H4_ID,),
        matched_evidence_keys=("h4-key",),
        basis="One governed target matched.",
    )
    receipt = EvidenceReferenceResolutionReceipt(
        schema_version="1.0",
        case_id=CASE_ID,
        search_mode=EvidenceSearchMode.EXHAUSTIVE_EVIDENCE,
        searched_document_ids=(H4_ID, H5_ID, H6_ID),
        documents_completely_expanded=3,
        pages_inspected=5,
        chunks_inspected=12,
        case_corpus_complete=True,
        possible_not_located_permitted=True,
        reference_count=2,
        resolved_count=1,
        ambiguous_count=0,
        possible_not_located_count=1,
        unresolved_count=0,
    )
    return CaseEvidenceReferenceResolution(
        case_id=CASE_ID,
        resolutions=(in_scope, out_scope),
        receipt=receipt,
    )


def _exhaustive_result():
    return SimpleNamespace(
        case_id=CASE_ID,
        search_mode=EvidenceSearchMode.EXHAUSTIVE_EVIDENCE,
        receipt=SimpleNamespace(
            case_id=CASE_ID,
            completion=EvidenceSearchCompletion.COMPLETE,
            case_corpus_complete=True,
            negative_finding_scope=NegativeFindingScope.CASE_CORPUS,
            negative_finding_permitted=True,
        ),
    )


def _base_result():
    return {
        "answer": "Original governed legal answer",
        "retrieval_mode": EvidenceSearchMode.DOCUMENT_COMPLETE.value,
        "search_results": {
            "ids": [["scope-key"]],
            "documents": [["The email from Emma Shakespeare dated 6 July 2005 is referenced."]],
            "metadatas": [[{"case_id": CASE_ID}]],
        },
        "sources": [],
    }


def test_answer_bridge_filters_whole_case_reference_findings_to_answer_scope(monkeypatch, bridge_module):
    bridge = bridge_module
    monkeypatch.setattr(bridge, "resolve_evidence_references", lambda result: _whole_resolution())
    calls = []

    def search_service(**kwargs):
        calls.append(kwargs)
        return _exhaustive_result()

    result = bridge.ask_with_reference_findings(
        "What evidence supports the return-to-work issue?",
        case_id=CASE_ID,
        answer_service=lambda *args, **kwargs: _base_result(),
        search_service=search_service,
    )

    assert result["answer"] == "Original governed legal answer"
    assert calls[0]["mode"] is EvidenceSearchMode.EXHAUSTIVE_EVIDENCE
    assert calls[0]["candidate_document_ids"] == ()
    payload = result["evidence_reference_resolution"]
    assert payload["receipt"]["case_corpus_complete"] is True
    assert payload["receipt"]["documents_completely_expanded"] == 3
    assert payload["receipt"]["reference_count"] == 1
    assert len(payload["findings"]) == 1
    assert payload["findings"][0]["source_evidence_key"] == "scope-key"
    assert payload["findings"][0]["status"] == "POSSIBLE_REFERENCED_BUT_NOT_LOCATED"
    assert result["evidence_reference_resolution_warning"] is None


def test_answer_bridge_preserves_resolved_target_outside_original_answer_scope(monkeypatch, bridge_module):
    bridge = bridge_module
    whole = _whole_resolution()
    # Switch the in-scope item to a resolved target in H4.
    item = EvidenceReferenceResolution(
        reference=whole.resolutions[0].reference,
        status=EvidenceReferenceResolutionStatus.RESOLVED,
        matched_document_ids=(H4_ID,),
        matched_evidence_keys=("h4-key",),
        basis="One governed target matched after complete case-corpus inspection.",
    )
    receipt = EvidenceReferenceResolutionReceipt(
        schema_version="1.0",
        case_id=CASE_ID,
        search_mode=EvidenceSearchMode.EXHAUSTIVE_EVIDENCE,
        searched_document_ids=(H4_ID, H5_ID, H6_ID),
        documents_completely_expanded=3,
        pages_inspected=5,
        chunks_inspected=12,
        case_corpus_complete=True,
        possible_not_located_permitted=True,
        reference_count=1,
        resolved_count=1,
        ambiguous_count=0,
        possible_not_located_count=0,
        unresolved_count=0,
    )
    monkeypatch.setattr(
        bridge,
        "resolve_evidence_references",
        lambda result: CaseEvidenceReferenceResolution(
            case_id=CASE_ID,
            resolutions=(item,),
            receipt=receipt,
        ),
    )

    result = bridge.ask_with_reference_findings(
        "Question",
        case_id=CASE_ID,
        answer_service=lambda *args, **kwargs: _base_result(),
        search_service=lambda **kwargs: _exhaustive_result(),
    )

    finding = result["evidence_reference_resolution"]["findings"][0]
    assert finding["status"] == "RESOLVED"
    assert finding["matched_document_ids"] == [H4_ID]
    assert finding["matched_evidence_keys"] == ["h4-key"]


def test_answer_bridge_failure_preserves_legal_answer_and_blocks_missing_reference_claim(monkeypatch, bridge_module):
    bridge = bridge_module
    def fail(**kwargs):
        raise EvidenceSearchError("controlled")

    result = bridge.ask_with_reference_findings(
        "Question",
        case_id=CASE_ID,
        answer_service=lambda *args, **kwargs: _base_result(),
        search_service=fail,
    )

    assert result["answer"] == "Original governed legal answer"
    assert result["evidence_reference_resolution"] is None
    assert "No missing-reference finding has been made" in result[
        "evidence_reference_resolution_warning"
    ]


def test_global_legacy_answer_does_not_run_reference_search(bridge_module):
    bridge = bridge_module
    calls = []
    base = {"answer": "Legacy", "sources": [], "search_results": {}}

    result = bridge.ask_with_reference_findings(
        "Legacy question",
        case_id=None,
        answer_service=lambda *args, **kwargs: base,
        search_service=lambda **kwargs: calls.append(kwargs),
    )

    assert result is base
    assert calls == []


def test_failed_closed_governed_answer_does_not_run_reference_search(bridge_module):
    bridge = bridge_module
    calls = []
    base = {
        "answer": "Governed failure",
        "retrieval_mode": "governed_failed_closed",
        "search_results": {"ids": [[]]},
    }

    result = bridge.ask_with_reference_findings(
        "Question",
        case_id=CASE_ID,
        answer_service=lambda *args, **kwargs: base,
        search_service=lambda **kwargs: calls.append(kwargs),
    )

    assert result is base
    assert calls == []
