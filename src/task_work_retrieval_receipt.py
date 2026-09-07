"""Append-only diagnostic provenance for Case Operator task-work runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any


TASK_WORK_RETRIEVAL_RECEIPT_SCHEMA_VERSION = "task-work-retrieval-receipt/1.0"
_RECEIPT_EVENT_TYPE = "TASK_WORK_RETRIEVAL_RECEIPT_RECORDED"


class TaskWorkRetrievalReceiptError(RuntimeError):
    """Raised when a diagnostic retrieval receipt is invalid."""


@dataclass(frozen=True)
class TaskWorkRetrievalReceipt:
    schema_version: str
    case_id: str
    task_id: str
    progress_id: str
    task_work_recorded_at: str
    receipt_recorded_at: str
    retrieval_mode: str | None
    question_sha256: str
    answer_sha256: str
    answer_scope_evidence_keys: tuple[str, ...]
    sources: tuple[dict[str, Any], ...]
    semantic_discovery_receipt: Any
    evidence_search_receipt: Any
    relied_evidence_keys: tuple[str, ...]
    answer_statement_bindings: tuple[Any, ...]
    evidence_reference_resolution: Any


def _required(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TaskWorkRetrievalReceiptError(f"{field_name} is required.")
    return value.strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "__dict__"):
        return _json_safe(vars(value))
    return str(value)


def _case_name(case_id: object) -> str:
    value = _required(case_id, "case_id")
    if "/" in value or "\\" in value or value in {".", ".."}:
        raise TaskWorkRetrievalReceiptError("Invalid case_id.")
    return value


def task_work_retrieval_receipt_path(case_id: str, *, root=None) -> Path:
    base = Path(root) if root is not None else Path("solicitor_tasks")
    return base / _case_name(case_id) / "work_retrieval_receipts.jsonl"


def _answer_scope_evidence_keys(result: dict[str, Any]) -> tuple[str, ...]:
    search_results = result.get("search_results")
    if not isinstance(search_results, dict):
        return ()
    rows = search_results.get("ids")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], list):
        return ()
    return tuple(v for v in rows[0] if isinstance(v, str) and v)


def _compact_sources(result: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    raw = result.get("sources")
    if not isinstance(raw, list):
        return ()
    compact = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        entry = {}
        for key in (
            "file", "page", "evidence_key", "id", "document_id",
            "document_instance_id", "source_document_instance_id"
        ):
            if item.get(key) is not None:
                entry[key] = _json_safe(item.get(key))
        if entry:
            compact.append(entry)
    return tuple(compact)


def build_task_work_retrieval_receipt(
    *,
    case_id: str,
    task_id: str,
    progress_id: str,
    task_work_recorded_at: str,
    question: str,
    answer: str,
    result: dict[str, Any],
) -> TaskWorkRetrievalReceipt:
    if not isinstance(result, dict):
        raise TaskWorkRetrievalReceiptError("result must be a dictionary.")

    relied = result.get("relied_evidence_keys")
    if not isinstance(relied, list):
        relied = []
    bindings = result.get("answer_statement_bindings")
    if not isinstance(bindings, list):
        bindings = []
    retrieval_mode = result.get("retrieval_mode")
    if retrieval_mode is not None and not isinstance(retrieval_mode, str):
        retrieval_mode = str(retrieval_mode)

    return TaskWorkRetrievalReceipt(
        schema_version=TASK_WORK_RETRIEVAL_RECEIPT_SCHEMA_VERSION,
        case_id=_case_name(case_id),
        task_id=_required(task_id, "task_id"),
        progress_id=_required(progress_id, "progress_id"),
        task_work_recorded_at=_required(task_work_recorded_at, "task_work_recorded_at"),
        receipt_recorded_at=_now(),
        retrieval_mode=retrieval_mode,
        question_sha256=_sha256_text(_required(question, "question")),
        answer_sha256=_sha256_text(_required(answer, "answer")),
        answer_scope_evidence_keys=_answer_scope_evidence_keys(result),
        sources=_compact_sources(result),
        semantic_discovery_receipt=_json_safe(result.get("semantic_discovery_receipt")),
        evidence_search_receipt=_json_safe(result.get("evidence_search_receipt")),
        relied_evidence_keys=tuple(v for v in relied if isinstance(v, str) and v),
        answer_statement_bindings=tuple(_json_safe(v) for v in bindings),
        evidence_reference_resolution=_json_safe(result.get("evidence_reference_resolution")),
    )


def append_task_work_retrieval_receipt(
    *,
    case_id: str,
    task_id: str,
    progress_id: str,
    task_work_recorded_at: str,
    question: str,
    answer: str,
    result: dict[str, Any],
    root=None,
) -> TaskWorkRetrievalReceipt:
    receipt = build_task_work_retrieval_receipt(
        case_id=case_id,
        task_id=task_id,
        progress_id=progress_id,
        task_work_recorded_at=task_work_recorded_at,
        question=question,
        answer=answer,
        result=result,
    )
    path = task_work_retrieval_receipt_path(receipt.case_id, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "schema_version": TASK_WORK_RETRIEVAL_RECEIPT_SCHEMA_VERSION,
        "event_type": _RECEIPT_EVENT_TYPE,
        "case_id": receipt.case_id,
        "task_id": receipt.task_id,
        "progress_id": receipt.progress_id,
        "receipt": _json_safe(asdict(receipt)),
    }
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
    return receipt


def load_task_work_retrieval_receipts(
    case_id: str,
    task_id: str,
    *,
    root=None,
) -> tuple[TaskWorkRetrievalReceipt, ...]:
    normalized_case_id = _case_name(case_id)
    normalized_task_id = _required(task_id, "task_id")
    path = task_work_retrieval_receipt_path(normalized_case_id, root=root)
    if not path.exists():
        return ()

    records = []
    seen_progress_ids = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise TaskWorkRetrievalReceiptError(
                    f"Invalid retrieval-receipt JSON at line {line_number}."
                ) from exc

            if not isinstance(event, dict):
                raise TaskWorkRetrievalReceiptError(
                    f"Invalid retrieval-receipt event at line {line_number}."
                )
            if event.get("schema_version") != TASK_WORK_RETRIEVAL_RECEIPT_SCHEMA_VERSION:
                raise TaskWorkRetrievalReceiptError(
                    f"Unsupported retrieval-receipt schema at line {line_number}."
                )
            if event.get("event_type") != _RECEIPT_EVENT_TYPE:
                raise TaskWorkRetrievalReceiptError(
                    f"Unsupported retrieval-receipt event type at line {line_number}."
                )

            payload = event.get("receipt")
            if not isinstance(payload, dict):
                raise TaskWorkRetrievalReceiptError(
                    f"Invalid retrieval-receipt payload at line {line_number}."
                )

            record = TaskWorkRetrievalReceipt(
                schema_version=_required(payload.get("schema_version"), "schema_version"),
                case_id=_case_name(payload.get("case_id")),
                task_id=_required(payload.get("task_id"), "task_id"),
                progress_id=_required(payload.get("progress_id"), "progress_id"),
                task_work_recorded_at=_required(
                    payload.get("task_work_recorded_at"), "task_work_recorded_at"
                ),
                receipt_recorded_at=_required(
                    payload.get("receipt_recorded_at"), "receipt_recorded_at"
                ),
                retrieval_mode=payload.get("retrieval_mode"),
                question_sha256=_required(payload.get("question_sha256"), "question_sha256"),
                answer_sha256=_required(payload.get("answer_sha256"), "answer_sha256"),
                answer_scope_evidence_keys=tuple(
                    v for v in payload.get("answer_scope_evidence_keys", [])
                    if isinstance(v, str) and v
                ),
                sources=tuple(
                    v for v in payload.get("sources", [])
                    if isinstance(v, dict)
                ),
                semantic_discovery_receipt=payload.get("semantic_discovery_receipt"),
                evidence_search_receipt=payload.get("evidence_search_receipt"),
                relied_evidence_keys=tuple(
                    v for v in payload.get("relied_evidence_keys", [])
                    if isinstance(v, str) and v
                ),
                answer_statement_bindings=tuple(
                    payload.get("answer_statement_bindings", [])
                    if isinstance(payload.get("answer_statement_bindings", []), list)
                    else []
                ),
                evidence_reference_resolution=payload.get("evidence_reference_resolution"),
            )

            if record.schema_version != TASK_WORK_RETRIEVAL_RECEIPT_SCHEMA_VERSION:
                raise TaskWorkRetrievalReceiptError(
                    f"Receipt schema mismatch at line {line_number}."
                )
            if event.get("case_id") != record.case_id or event.get("task_id") != record.task_id:
                raise TaskWorkRetrievalReceiptError(
                    f"Retrieval-receipt identity mismatch at line {line_number}."
                )
            if event.get("progress_id") != record.progress_id:
                raise TaskWorkRetrievalReceiptError(
                    f"Retrieval-receipt progress identity mismatch at line {line_number}."
                )
            if record.progress_id in seen_progress_ids:
                raise TaskWorkRetrievalReceiptError(
                    f"Duplicate retrieval receipt for progress_id at line {line_number}."
                )
            seen_progress_ids.add(record.progress_id)
            if record.task_id == normalized_task_id:
                records.append(record)

    return tuple(records)


__all__ = [
    "TASK_WORK_RETRIEVAL_RECEIPT_SCHEMA_VERSION",
    "TaskWorkRetrievalReceipt",
    "TaskWorkRetrievalReceiptError",
    "append_task_work_retrieval_receipt",
    "build_task_work_retrieval_receipt",
    "load_task_work_retrieval_receipts",
    "task_work_retrieval_receipt_path",
]