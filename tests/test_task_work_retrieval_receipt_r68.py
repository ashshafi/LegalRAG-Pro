from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from task_work_retrieval_receipt import (
    TASK_WORK_RETRIEVAL_RECEIPT_SCHEMA_VERSION,
    append_task_work_retrieval_receipt,
    load_task_work_retrieval_receipts,
)


@dataclass(frozen=True)
class FakeReceipt:
    case_id: str
    search_mode: str
    completion: str


def _result():
    return {
        "retrieval_mode": "exhaustive_evidence",
        "sources": [
            {"file": "ET1 Form 07.11.2025.pdf", "page": 1, "evidence_key": "e-et1-p1"},
            {"file": "ACAS Early Conciliation Certificate.pdf", "page": 1},
        ],
        "search_results": {
            "ids": [["e-et1-p1", "e-acas-p1"]],
            "documents": [["DO NOT PERSIST RAW ET1 TEXT", "DO NOT PERSIST RAW ACAS TEXT"]],
            "metadatas": [[{"page": 1}, {"page": 1}]],
        },
        "semantic_discovery_receipt": FakeReceipt("case-1", "semantic_discovery", "complete"),
        "evidence_search_receipt": FakeReceipt("case-1", "exhaustive_evidence", "complete"),
        "relied_evidence_keys": ["e-et1-p1"],
        "answer_statement_bindings": [{"statement_id": "s1", "evidence_keys": ["e-et1-p1"]}],
        "evidence_reference_resolution": {
            "receipt": {"searched_document_ids": ["doc-et1", "doc-acas"]}
        },
    }


def test_r68_appends_compact_receipt_linked_to_progress_id(tmp_path: Path):
    question = "What is the ET1 presentation date?"
    answer = "The ET1 says 07/11/2025."
    receipt = append_task_work_retrieval_receipt(
        case_id="case-1",
        task_id="task-1",
        progress_id="progress-1",
        task_work_recorded_at="2026-09-07T00:00:00Z",
        question=question,
        answer=answer,
        result=_result(),
        root=tmp_path,
    )
    assert receipt.schema_version == TASK_WORK_RETRIEVAL_RECEIPT_SCHEMA_VERSION
    assert receipt.progress_id == "progress-1"
    assert receipt.answer_scope_evidence_keys == ("e-et1-p1", "e-acas-p1")
    assert receipt.sources[0]["file"] == "ET1 Form 07.11.2025.pdf"
    assert receipt.sources[0]["page"] == 1
    assert receipt.relied_evidence_keys == ("e-et1-p1",)
    assert receipt.question_sha256 == hashlib.sha256(question.encode()).hexdigest()
    assert receipt.answer_sha256 == hashlib.sha256(answer.encode()).hexdigest()
    loaded = load_task_work_retrieval_receipts("case-1", "task-1", root=tmp_path)
    assert loaded == (receipt,)


def test_r68_sidecar_does_not_persist_raw_search_documents(tmp_path: Path):
    append_task_work_retrieval_receipt(
        case_id="case-1",
        task_id="task-1",
        progress_id="progress-1",
        task_work_recorded_at="2026-09-07T00:00:00Z",
        question="question",
        answer="answer",
        result=_result(),
        root=tmp_path,
    )
    path = tmp_path / "case-1" / "work_retrieval_receipts.jsonl"
    raw = path.read_text(encoding="utf-8")
    assert "DO NOT PERSIST RAW ET1 TEXT" not in raw
    assert "DO NOT PERSIST RAW ACAS TEXT" not in raw
    assert json.loads(raw)["progress_id"] == "progress-1"


def test_r68_case_operator_persists_receipt_after_task_work_record():
    source = Path("src/ui/case_operator.py").read_text(encoding="utf-8-sig")
    assert "progress = append_task_work_progress(" in source
    assert "append_task_work_retrieval_receipt(" in source
    assert "progress_id=progress.progress_id" in source
    assert "task_work_recorded_at=progress.recorded_at" in source
    assert "result=result" in source


def test_r68_preserves_task_work_progress_schema_v1():
    source = Path("src/task_work_progress.py").read_text(encoding="utf-8-sig")
    assert 'TASK_WORK_PROGRESS_SCHEMA_VERSION = "task-work-progress/1.0"' in source
    assert "retrieval_receipt" not in source


def test_r68_receipt_module_has_no_task_or_authority_mutator():
    source = Path("src/task_work_retrieval_receipt.py").read_text(encoding="utf-8-sig")
    for marker in (
        "_update_task_status",
        "append_task_event",
        "publish_authority",
        "activate_authority",
        "chromadb",
        "OpenAI(",
    ):
        assert marker not in source