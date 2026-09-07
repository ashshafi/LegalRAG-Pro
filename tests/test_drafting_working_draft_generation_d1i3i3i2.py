from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

import bounded_governed_answer as bounded
import drafting_working_draft_generation as generation

from drafting_evidence_source_adapter import (
    DraftingEvidenceRow,
)
from solicitor_tasks import SolicitorTask
from task_work_authority_scope import (
    TaskWorkAuthorityScope,
    TaskWorkAuthorityScopeError,
)
from task_work_progress import TaskWorkProgress
from task_work_retrieval_receipt import (
    TaskWorkRetrievalReceipt,
)


CASE_ID = "8081166d-9889-40bb-8add-5d0893037ff0"

TASK_ID = "11111111-1111-4111-8111-111111111111"
PROGRESS_ID = "22222222-2222-4222-8222-222222222222"
ISSUE_ID = "33333333-3333-4333-8333-333333333333"

AUTHORITY_ID = "sha256:" + ("a" * 64)
SCOPE_ID = "sha256:" + ("b" * 64)

ELEMENT_ID = "DA-DISABILITY"

KEY = (
    CASE_ID
    + "__Evidence_1_0"
)

OUTSIDE_KEY = (
    CASE_ID
    + "__Outside_1_0"
)

QUESTION = "What does the evidence establish?"
ANSWER = "The task-work answer."


def digest(value: str) -> str:
    return sha256(
        value.encode("utf-8")
    ).hexdigest()


def task():
    return SolicitorTask(
        task_id=TASK_ID,
        case_id=CASE_ID,
        title="Review disability evidence",
        status="IN_PROGRESS",
        priority="HIGH",
        due_date=None,
        assigned_to=None,
        issue_analysis_id=ISSUE_ID,
        issue_name="Disability",
        originating_question=QUESTION,
        origin="MANUAL",
        why_it_matters="Prepare the issue accurately.",
        created_at="2026-09-07T10:00:00Z",
        updated_at="2026-09-07T10:00:00Z",
    )


def progress():
    return TaskWorkProgress(
        schema_version="task-work-progress/1.0",
        progress_id=PROGRESS_ID,
        case_id=CASE_ID,
        task_id=TASK_ID,
        recorded_at="2026-09-07T10:05:00Z",
        question=QUESTION,
        answer=ANSWER,
        outcome="CONTINUE",
    )


def coverage_payload():
    return {
        "search_mode": "document_complete",
        "completion": "complete",
        "scope_document_count": 2,
        "documents_completely_expanded": 2,
        "scope_page_count": 3,
        "pages_inspected": 3,
        "scope_chunk_count": 4,
        "chunks_inspected": 4,
        "case_corpus_complete": False,
        "negative_finding_permitted": True,
        "negative_finding_scope": "searched_scope",
    }


def retrieval_receipt():
    return TaskWorkRetrievalReceipt(
        schema_version=
            "task-work-retrieval-receipt/1.0",
        case_id=CASE_ID,
        task_id=TASK_ID,
        progress_id=PROGRESS_ID,
        task_work_recorded_at=
            "2026-09-07T10:05:00Z",
        receipt_recorded_at=
            "2026-09-07T10:06:00Z",
        retrieval_mode="document_complete",
        question_sha256=digest(QUESTION),
        answer_sha256=digest(ANSWER),
        answer_scope_evidence_keys=(KEY,),
        sources=(),
        semantic_discovery_receipt=None,
        evidence_search_receipt=
            coverage_payload(),
        relied_evidence_keys=(KEY,),
        answer_statement_bindings=(),
        evidence_reference_resolution=None,
    )


def scope():
    return TaskWorkAuthorityScope(
        schema_version=
            "task-work-authority-scope/1.0",
        binding_id=SCOPE_ID,
        case_id=CASE_ID,
        task_id=TASK_ID,
        progress_id=PROGRESS_ID,
        authority_id=AUTHORITY_ID,
        issue_analysis_id=ISSUE_ID,
        issue_definition_id="DISABILITY",
        element_ids=(ELEMENT_ID,),
        reviewer_reference="solicitor@example.test",
        review_note="Explicit scope.",
        recorded_at="2026-09-07T10:07:00Z",
    )


def authority():
    return SimpleNamespace(
        manifest=SimpleNamespace(
            case_id=CASE_ID,
            authority_id=AUTHORITY_ID,
        )
    )


def ledger_element():
    return SimpleNamespace(
        element_id=ELEMENT_ID,
        element_name="Disability",
        legal_question=(
            "Was the claimant disabled within the "
            "meaning of the Equality Act?"
        ),
        analytical_status="partially_supported",
        analytical_confidence="medium",
        supporting_evidence_keys=(KEY,),
        adverse_evidence_keys=(),
        corroborative_evidence_keys=(),
        conflicting_evidence_keys=(),
        neutral_evidence_keys=(),
        evidential_gap_ids=(),
        unresolved_matters=(
            "Statutory definition remains for legal assessment.",
        ),
        provisional_analysis=(
            "The current evidence provides partial factual support "
            "but does not itself finally determine statutory disability."
        ),
        relationships=(),
    )


def row():
    return DraftingEvidenceRow(
        case_id=CASE_ID,
        evidence_key=KEY,
        evidence_binding_id="sha256:" + ("c" * 64),
        source_document_instance_id=
            "44444444-4444-4444-8444-444444444444",
        source_snapshot_id=
            "sha256:" + ("d" * 64),
        document_name="Evidence.pdf",
        page=1,
        chunk_ordinal=0,
        bound_text_role="chunk_text",
        original_blob_sha256="e" * 64,
        page_text_sha256="f" * 64,
        chunk_text_sha256="1" * 64,
        exact_bound_text=(
            "Exact immutable evidence supporting the "
            "limited factual proposition."
        ),
    )


def enriched_results():
    return {
        "ids": [[KEY]],
        "documents": [[
            "Exact immutable evidence supporting the "
            "limited factual proposition."
        ]],
        "metadatas": [[{
            "file": "Evidence.pdf",
            "page": 1,
            "source_document_instance_id":
                "44444444-4444-4444-8444-444444444444",
        }]],
    }


def final_payload(
    *,
    element_id=ELEMENT_ID,
    status="partially_supported",
    confidence="medium",
    cited=None,
):
    if cited is None:
        cited = [KEY]

    return {
        "statements": [{
            "text": (
                "The governed evidence provides partial factual "
                "support relevant to disability, subject to the "
                "existing unresolved statutory assessment."
            ),
            "element_id": element_id,
            "claimed_status": status,
            "claimed_confidence": confidence,
            "cited_evidence_keys": cited,
        }]
    }


class _Responses:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)

        if len(self.calls) == 1:
            return SimpleNamespace(
                output_text=(
                    "FINDING | evidence_key="
                    + KEY
                    + " | file=Evidence.pdf | page=1 | "
                    "classification=supporting | "
                    "finding=limited factual support"
                )
            )

        return SimpleNamespace(
            output_text=json.dumps(
                self.payload
            )
        )


class _Client:
    def __init__(self, payload):
        self.responses = _Responses(
            payload
        )


def arrange(monkeypatch, payload=None):
    if payload is None:
        payload = final_payload()

    element = ledger_element()

    issue = SimpleNamespace(
        issue_analysis_id=ISSUE_ID,
        issue_definition_id="DISABILITY",
        elements=(element,),
    )

    ledger = SimpleNamespace(
        case_id=CASE_ID,
        authority_id=AUTHORITY_ID,
        issues=(issue,),
    )

    monkeypatch.setattr(
        generation,
        "resolve_task_work_authority_scope",
        lambda supplied_scope, *, authority:
            SimpleNamespace(
                scope=supplied_scope,
                issue=issue,
                elements=(element,),
            ),
    )

    monkeypatch.setattr(
        generation,
        "build_matter_analysis_ledger",
        lambda *, authority, events=():
            ledger,
    )

    monkeypatch.setattr(
        generation,
        "reconstruct_bounded_generation_evidence",
        lambda **kwargs: (
            (KEY,),
            (row(),),
            enriched_results(),
        ),
    )

    monkeypatch.setattr(
        bounded,
        "assert_ai_processing_allowed",
        lambda **kwargs: None,
    )

    return _Client(payload)


def generate(monkeypatch, payload=None, **overrides):
    client = arrange(
        monkeypatch,
        payload=payload,
    )

    values = {
        "client": client,
        "model": "gpt-5",
        "task": task(),
        "progress": progress(),
        "retrieval_receipt":
            retrieval_receipt(),
        "scope": scope(),
        "authority": authority(),
        "element_id": ELEMENT_ID,
    }

    values.update(overrides)

    candidate = (
        generation.generate_working_draft_candidate(
            **values
        )
    )

    return (
        client,
        candidate,
    )


def test_generates_unpersisted_bounded_candidate(monkeypatch):
    client, candidate = generate(
        monkeypatch
    )

    assert candidate.case_id == CASE_ID
    assert candidate.task_id == TASK_ID
    assert candidate.progress_id == PROGRESS_ID
    assert candidate.scope_binding_id == SCOPE_ID
    assert candidate.authority_id == AUTHORITY_ID
    assert candidate.issue_analysis_id == ISSUE_ID
    assert candidate.element_id == ELEMENT_ID
    assert candidate.evidence_keys == (KEY,)

    assert len(candidate.statements) == 1

    statement = candidate.statements[0]

    assert statement.element_id == ELEMENT_ID
    assert statement.claimed_status == "partially_supported"
    assert statement.claimed_confidence == "medium"
    assert statement.cited_evidence_keys == (KEY,)

    assert len(client.responses.calls) == 2


def test_prompt_wrapper_reaches_map_and_reduce(monkeypatch):
    client, _candidate = generate(
        monkeypatch
    )

    map_prompt = (
        client.responses.calls[0]["input"]
    )

    reduce_prompt = (
        client.responses.calls[-1]["input"]
    )

    marker = (
        "DRAFTING WORKING-CANDIDATE GOVERNANCE"
    )

    assert marker in map_prompt
    assert marker in reduce_prompt

    assert (
        "DRAFTING MAP-PASS RULES"
        in map_prompt
    )

    assert (
        "DRAFTING FINAL-REDUCE RULES"
        in reduce_prompt
    )

    assert (
        "Do not emit the final Drafting JSON object"
        in map_prompt
    )

    assert (
        "Return only the strict JSON object"
        in reduce_prompt
    )


def test_only_reduce_receives_candidate_schema(monkeypatch):
    client, _candidate = generate(
        monkeypatch
    )

    first = client.responses.calls[0]
    last = client.responses.calls[-1]

    assert "text" not in first
    assert "text" in last

    schema = (
        last["text"]["format"]["schema"]
    )

    statement_schema = (
        schema["properties"]["statements"]["items"]
    )

    assert (
        statement_schema["properties"]["element_id"]["const"]
        == ELEMENT_ID
    )

    assert (
        statement_schema["properties"]["claimed_status"]["const"]
        == "partially_supported"
    )

    assert (
        statement_schema["properties"]["claimed_confidence"]["const"]
        == "medium"
    )

    assert (
        statement_schema["properties"]["cited_evidence_keys"]
        ["items"]["enum"]
        == [KEY]
    )


def test_narrowed_drafting_coverage_forbids_negative_findings(
    monkeypatch,
):
    client, _candidate = generate(
        monkeypatch
    )

    assert len(client.responses.calls) == 2

    map_prompt = client.responses.calls[0]["input"]
    reduce_prompt = client.responses.calls[-1]["input"]

    for prompt in (
        map_prompt,
        reduce_prompt,
    ):
        assert (
            "case_corpus_complete: False"
            in prompt
        )

        assert (
            "negative_finding_permitted: False"
            in prompt
        )

        assert (
            "negative_finding_scope: none"
            in prompt
        )

        assert (
            "No negative finding about evidence absence is authorised"
            in prompt
        )

    assert (
        "Do not make any negative finding about evidence being absent; "
        "other batches exist."
        in map_prompt
    )

    assert (
        "Do not state or imply that evidence is absent."
        in reduce_prompt
    )


def test_progress_question_hash_mismatch_fails_before_provider(
    monkeypatch,
):
    client = arrange(
        monkeypatch
    )

    receipt = retrieval_receipt()

    object.__setattr__(
        receipt,
        "question_sha256",
        "0" * 64,
    )

    with pytest.raises(
        generation.DraftingWorkingDraftGenerationError,
        match="question hash",
    ):
        generation.generate_working_draft_candidate(
            client=client,
            model="gpt-5",
            task=task(),
            progress=progress(),
            retrieval_receipt=receipt,
            scope=scope(),
            authority=authority(),
            element_id=ELEMENT_ID,
        )

    assert client.responses.calls == []


def test_progress_answer_hash_mismatch_fails_before_provider(
    monkeypatch,
):
    client = arrange(
        monkeypatch
    )

    receipt = retrieval_receipt()

    object.__setattr__(
        receipt,
        "answer_sha256",
        "0" * 64,
    )

    with pytest.raises(
        generation.DraftingWorkingDraftGenerationError,
        match="answer hash",
    ):
        generation.generate_working_draft_candidate(
            client=client,
            model="gpt-5",
            task=task(),
            progress=progress(),
            retrieval_receipt=receipt,
            scope=scope(),
            authority=authority(),
            element_id=ELEMENT_ID,
        )

    assert client.responses.calls == []


def test_stale_scope_fails_before_source_or_provider(
    monkeypatch,
):
    client = arrange(
        monkeypatch
    )

    monkeypatch.setattr(
        generation,
        "resolve_task_work_authority_scope",
        lambda *args, **kwargs: (
            _raise_scope_error()
        ),
    )

    with pytest.raises(
        generation.DraftingWorkingDraftGenerationError,
        match="does not resolve",
    ):
        generation.generate_working_draft_candidate(
            client=client,
            model="gpt-5",
            task=task(),
            progress=progress(),
            retrieval_receipt=
                retrieval_receipt(),
            scope=scope(),
            authority=authority(),
            element_id=ELEMENT_ID,
        )

    assert client.responses.calls == []


def _raise_scope_error():
    raise TaskWorkAuthorityScopeError(
        "stale"
    )


def test_element_outside_professional_scope_fails(
    monkeypatch,
):
    client = arrange(
        monkeypatch
    )

    with pytest.raises(
        generation.DraftingWorkingDraftGenerationError,
        match="outside the explicit professional scope",
    ):
        generation.generate_working_draft_candidate(
            client=client,
            model="gpt-5",
            task=task(),
            progress=progress(),
            retrieval_receipt=
                retrieval_receipt(),
            scope=scope(),
            authority=authority(),
            element_id="OTHER-ELEMENT",
        )

    assert client.responses.calls == []


def test_invalid_r68_coverage_fails_closed(
    monkeypatch,
):
    client = arrange(
        monkeypatch
    )

    receipt = retrieval_receipt()

    object.__setattr__(
        receipt,
        "evidence_search_receipt",
        None,
    )

    with pytest.raises(
        generation.DraftingWorkingDraftGenerationError,
        match="evidence-search receipt",
    ):
        generation.generate_working_draft_candidate(
            client=client,
            model="gpt-5",
            task=task(),
            progress=progress(),
            retrieval_receipt=receipt,
            scope=scope(),
            authority=authority(),
            element_id=ELEMENT_ID,
        )

    assert client.responses.calls == []


def test_invalid_json_fails_closed(monkeypatch):
    client = arrange(
        monkeypatch
    )

    original_create = (
        client.responses.create
    )

    def invalid_final(**kwargs):
        client.responses.calls.append(
            kwargs
        )

        if len(client.responses.calls) == 1:
            return SimpleNamespace(
                output_text=(
                    "FINDING | evidence_key="
                    + KEY
                    + " | file=Evidence.pdf | page=1 | "
                    "classification=supporting | finding=x"
                )
            )

        return SimpleNamespace(
            output_text="not-json"
        )

    client.responses.create = invalid_final

    with pytest.raises(
        generation.DraftingWorkingDraftGenerationError,
        match="invalid JSON",
    ):
        generation.generate_working_draft_candidate(
            client=client,
            model="gpt-5",
            task=task(),
            progress=progress(),
            retrieval_receipt=
                retrieval_receipt(),
            scope=scope(),
            authority=authority(),
            element_id=ELEMENT_ID,
        )


def test_wrong_element_from_provider_fails_closed(
    monkeypatch,
):
    with pytest.raises(
        generation.DraftingWorkingDraftGenerationError,
        match="another governed element",
    ):
        generate(
            monkeypatch,
            payload=final_payload(
                element_id="OTHER-ELEMENT",
            ),
        )


def test_changed_status_from_provider_fails_closed(
    monkeypatch,
):
    with pytest.raises(
        generation.DraftingWorkingDraftGenerationError,
        match="changes the current analytical status",
    ):
        generate(
            monkeypatch,
            payload=final_payload(
                status="well_supported",
            ),
        )


def test_changed_confidence_from_provider_fails_closed(
    monkeypatch,
):
    with pytest.raises(
        generation.DraftingWorkingDraftGenerationError,
        match="changes the current analytical confidence",
    ):
        generate(
            monkeypatch,
            payload=final_payload(
                confidence="high",
            ),
        )


def test_out_of_scope_evidence_citation_fails_closed(
    monkeypatch,
):
    with pytest.raises(
        generation.DraftingWorkingDraftGenerationError,
        match="outside the permitted Drafting set",
    ):
        generate(
            monkeypatch,
            payload=final_payload(
                cited=[
                    OUTSIDE_KEY,
                ],
            ),
        )


def test_duplicate_evidence_citation_fails_closed(
    monkeypatch,
):
    with pytest.raises(
        generation.DraftingWorkingDraftGenerationError,
        match="duplicate evidence citations",
    ):
        generate(
            monkeypatch,
            payload=final_payload(
                cited=[
                    KEY,
                    KEY,
                ],
            ),
        )


def test_wrapper_unknown_phase_fails_closed():
    wrapper = (
        generation.build_drafting_prompt_wrapper(
            case_id=CASE_ID,
            authority_id=AUTHORITY_ID,
            scope=scope(),
            element=ledger_element(),
            evidence_keys=(KEY,),
        )
    )

    with pytest.raises(
        generation.DraftingWorkingDraftGenerationError,
        match="phase",
    ):
        wrapper(
            base_prompt="UNKNOWN PROVIDER PHASE",
            question="Question",
        )


def test_module_has_no_persistence_ui_or_retrieval_dependency():
    source = Path(
        generation.__file__
    ).read_text(
        encoding="utf-8"
    ).lower()

    forbidden = (
        "streamlit",
        "chromadb",
        "record_working_draft",
        "append_task_work_progress",
        "record_task_work_authority_scope",
        "append_task_work_retrieval_receipt",
        "update_task(",
        "work_product_release",
        "search_case_evidence",
        "similarity_search",
        "report_projection_provider",
        "responses.create",
        "chat.completions",
        "import openai",
        "from openai",
    )

    assert not any(
        token in source
        for token in forbidden
    )