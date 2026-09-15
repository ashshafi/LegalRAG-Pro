"""Bounded task-scoped agentic investigation for LegalRAG Pro.

GAC1 is subordinate to the existing professional workflow. It builds a bounded
multi-step plan from one existing task, combines already-governed answers, and
records immutable audit receipts plus explicit professional decisions.

It does not create/update/complete tasks, mutate Current Assessment, create or
approve drafts, change court/tribunal reliance, mutate reports, or publish
externally.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import uuid
from typing import Any, Callable, Iterable, Mapping

from case_management.access import MatterAccessContext, require_matter_mutation
from solicitor_tasks import load_tasks

GAC1_SCHEMA_VERSION = "gac1-governed-agentic-investigation/v1"
GAC1_PLAN_SCHEMA_VERSION = "gac1-governed-agentic-plan/v1"
GAC1_EXECUTION_SCHEMA_VERSION = "gac1-governed-agentic-execution/v1"
GAC1_DECISION_SCHEMA_VERSION = "gac1-governed-agentic-decision/v1"

_SAFE_CASE_ID = re.compile(r"^[A-Za-z0-9_.:-]+$")


class GovernedAgenticInvestigationError(RuntimeError):
    """Raised when the bounded GAC1 contract fails closed."""


class GovernedAgenticDecision(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class GovernedAgenticStep:
    step_id: str
    title: str
    question: str


@dataclass(frozen=True)
class GovernedAgenticPlan:
    schema_version: str
    plan_id: str
    case_id: str
    task_id: str
    task_title: str
    objective: str
    steps: tuple[GovernedAgenticStep, ...]


@dataclass(frozen=True)
class GovernedAgenticExecutionReceipt:
    schema_version: str
    receipt_id: str
    execution_id: str
    recorded_at: str
    case_id: str
    task_id: str
    plan_id: str
    step_count: int
    step_records: tuple[dict[str, Any], ...]
    proposed_work_result_sha256: str
    proposed_work_result: str


@dataclass(frozen=True)
class GovernedAgenticProfessionalDecision:
    schema_version: str
    decision_id: str
    recorded_at: str
    case_id: str
    task_id: str
    receipt_id: str
    decision: GovernedAgenticDecision
    reviewer_reference: str
    reviewer_note: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _required(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GovernedAgenticInvestigationError(f"{field_name} is required.")
    return value.strip()


def _case_name(case_id: str) -> str:
    value = _required(case_id, "case_id")
    if not _SAFE_CASE_ID.fullmatch(value) or value in {".", ".."}:
        raise GovernedAgenticInvestigationError("case_id is invalid.")
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _default_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        root = Path(base)
    else:
        root = Path.home() / ".local" / "share"
    return root / "LegalRAG-Pro" / "governed_agentic_investigation" / "v1"


def _root(root: Path | str | None) -> Path:
    return Path(root) if root is not None else _default_root()


def _event_path(case_id: str, *, root: Path | str | None = None) -> Path:
    return _root(root) / _case_name(case_id) / "events.jsonl"


def _decision_path(case_id: str, *, root: Path | str | None = None) -> Path:
    return _root(root) / _case_name(case_id) / "decisions.jsonl"


def _task_exists(
    case_id: str,
    task_id: str,
    *,
    task_loader: Callable[[str], Iterable[Any]],
) -> bool:
    for task in task_loader(case_id):
        if getattr(task, "case_id", None) != case_id:
            raise GovernedAgenticInvestigationError(
                "Task loader returned a cross-matter task."
            )
        if getattr(task, "task_id", None) == task_id:
            return True
    return False


def build_governed_agentic_investigation_plan(task: Any) -> GovernedAgenticPlan:
    """Create one deterministic bounded three-step plan from an existing task."""

    case_id = _required(getattr(task, "case_id", None), "task.case_id")
    task_id = _required(getattr(task, "task_id", None), "task.task_id")
    title = _required(getattr(task, "title", None), "task.title")
    issue = _required(
        getattr(task, "issue_name", None) or "Legal issue",
        "task.issue_name",
    )
    why = _required(
        getattr(task, "why_it_matters", None) or title,
        "task.why_it_matters",
    )
    originating = _required(
        getattr(task, "originating_question", None) or title,
        "task.originating_question",
    )

    objective = (
        f"Investigate the approved task '{title}' for {issue}. "
        f"Work required: {why}"
    )
    common = (
        f"Approved task: {title}\n"
        f"Related issue: {issue}\n"
        f"Why this matters: {why}\n"
        f"Originating investigation: {originating}\n\n"
        "Use only governed matter evidence. Cite material source documents/pages. "
        "Do not change the Current Assessment, task status, professional approval, "
        "court/tribunal reliance state, or any report projection."
    )

    steps = (
        GovernedAgenticStep(
            step_id="supporting-evidence",
            title="Evidence supporting the task proposition",
            question=(
                common
                + "\n\nStep 1: Identify and assess the strongest contemporaneous evidence "
                "that supports resolving this approved task. Distinguish evidence from inference "
                "and identify any material limitations."
            ),
        ),
        GovernedAgenticStep(
            step_id="contrary-evidence",
            title="Contrary or qualifying evidence",
            question=(
                common
                + "\n\nStep 2: Identify and assess the strongest adverse or qualifying evidence "
                "that materially weakens, limits, or creates risk for the proposition being investigated. "
                "Do not omit inconvenient evidence."
            ),
        ),
        GovernedAgenticStep(
            step_id="gaps-next-action",
            title="Remaining gaps and recommended professional next action",
            question=(
                common
                + "\n\nStep 3: Taking the task and governed evidence together, identify what "
                "remains unresolved, what additional evidence (if any) is genuinely required, "
                "and the next professional action. Do not state that the task is complete."
            ),
        ),
    )

    identity_payload = {
        "schema_version": GAC1_PLAN_SCHEMA_VERSION,
        "case_id": case_id,
        "task_id": task_id,
        "task_title": title,
        "objective": objective,
        "steps": [asdict(step) for step in steps],
    }
    plan_id = "sha256:" + _sha(identity_payload)
    return GovernedAgenticPlan(
        schema_version=GAC1_PLAN_SCHEMA_VERSION,
        plan_id=plan_id,
        case_id=case_id,
        task_id=task_id,
        task_title=title,
        objective=objective,
        steps=steps,
    )


def _list_values(result: Mapping[str, Any], key: str) -> list[Any]:
    value = result.get(key)
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _unique_scalar(results: tuple[Mapping[str, Any], ...], key: str) -> Any:
    values = [
        result.get(key)
        for result in results
        if result.get(key) not in (None, "", (), [])
    ]
    canonical = {
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        for value in values
    }
    if len(canonical) > 1:
        raise GovernedAgenticInvestigationError(
            f"Agentic step results disagree on {key}."
        )
    return values[0] if values else None


def _dedupe_dicts(values: Iterable[Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        marker = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        if marker in seen:
            continue
        seen.add(marker)
        output.append(value)
    return output


def _compact_summary_text(value: str, *, limit: int = 420) -> str:
    """Return a deterministic display summary without making another model call."""

    text = " ".join(str(value).strip().split())
    if len(text) <= limit:
        return text
    clipped = text[: max(1, limit - 1)].rstrip()
    boundary = clipped.rfind(" ")
    if boundary >= int(limit * 0.65):
        clipped = clipped[:boundary].rstrip()
    return clipped + "…"


def combine_governed_agentic_step_results(
    *,
    plan: GovernedAgenticPlan,
    step_results: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Combine exactly one governed result per plan step without approving it."""

    results = tuple(step_results)
    if len(results) != len(plan.steps):
        raise GovernedAgenticInvestigationError(
            "Agentic result count does not match the bounded plan."
        )

    answer_parts = [
        "Governed agentic investigation proposal",
        "",
        (
            "This is proposed task work only. It has not changed the Current Assessment, "
            "task status, any WorkingDraft, professional approval, court/tribunal reliance "
            "state, or any report projection."
        ),
    ]
    all_sources: list[Any] = []
    relied_keys: list[str] = []
    scope_keys: list[str] = []
    statement_bindings: list[Any] = []
    search_receipts: list[Any] = []
    reference_resolutions: list[Any] = []
    activation_ids: list[str] = []
    step_summaries: list[dict[str, Any]] = []
    any_new_ai_finding = False

    for step, result in zip(plan.steps, results):
        answer = result.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise GovernedAgenticInvestigationError(
                f"Agentic step {step.step_id} returned no answer."
            )
        answer_parts.extend(["", f"### {step.title}", answer.strip()])
        source_values = _list_values(result, "sources")
        relied_values = [
            value
            for value in _list_values(result, "relied_evidence_keys")
            if isinstance(value, str) and value
        ]
        step_summaries.append(
            {
                "step_id": step.step_id,
                "title": step.title,
                "summary": _compact_summary_text(answer),
                "source_count": len(_dedupe_dicts(source_values)),
                "relied_evidence_count": len(set(relied_values)),
            }
        )
        all_sources.extend(source_values)
        relied_keys.extend(
            value
            for value in _list_values(result, "relied_evidence_keys")
            if isinstance(value, str) and value
        )
        scope_keys.extend(
            value
            for value in _list_values(result, "answer_scope_evidence_keys")
            if isinstance(value, str) and value
        )
        statement_bindings.extend(
            _list_values(result, "answer_statement_bindings")
        )
        if result.get("evidence_search_receipt") is not None:
            search_receipts.append(result.get("evidence_search_receipt"))
        if result.get("evidence_reference_resolution") is not None:
            reference_resolutions.append(result.get("evidence_reference_resolution"))
        activation = result.get("analytical_activation_id")
        if isinstance(activation, str) and activation:
            activation_ids.append(activation)
        any_new_ai_finding = any_new_ai_finding or bool(
            result.get("new_ai_finding")
        )

    answer_parts.extend(
        [
            "",
            "### Professional decision",
            (
                "Accept this proposal only if it is suitable to become recorded task work. "
                "Acceptance does not complete the task and does not approve any draft or case position."
            ),
        ]
    )

    combined: dict[str, Any] = {
        "answer": "\n".join(answer_parts).strip(),
        "sources": _dedupe_dicts(all_sources),
        "relied_evidence_keys": sorted(set(relied_keys)),
        "answer_scope_evidence_keys": sorted(set(scope_keys)),
        "answer_statement_bindings": statement_bindings,
        "evidence_search_receipt": {
            "schema": "gac1-aggregate-evidence-search-receipt/v1",
            "step_receipts": search_receipts,
        },
        "evidence_reference_resolution": {
            "schema": "gac1-aggregate-evidence-reference-resolution/v1",
            "step_resolutions": reference_resolutions,
        },
        "new_ai_finding": any_new_ai_finding,
        "gac1_plan_id": plan.plan_id,
        "gac1_step_count": len(plan.steps),
        "gac1_step_summaries": step_summaries,
        "gac1_proposal": True,
    }

    authority_id = _unique_scalar(results, "analytical_authority_id")
    if authority_id is not None:
        combined["analytical_authority_id"] = authority_id
    authority_mode = _unique_scalar(results, "analytical_authority_mode")
    if authority_mode is not None:
        combined["analytical_authority_mode"] = authority_mode
    if activation_ids:
        combined["gac1_analytical_activation_ids"] = sorted(set(activation_ids))
        if len(set(activation_ids)) == 1:
            combined["analytical_activation_id"] = activation_ids[0]

    return combined


def _compact_sources(result: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    compact = []
    for source in _dedupe_dicts(_list_values(result, "sources")):
        compact.append(
            {
                key: source[key]
                for key in (
                    "file",
                    "page",
                    "evidence_key",
                    "id",
                    "document_id",
                    "document_instance_id",
                    "source_document_instance_id",
                )
                if key in source
            }
        )
    return tuple(compact)



def _profile_field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _profile_sequence_count(value: Any) -> int:
    if isinstance(value, (list, tuple)):
        return len(value)
    return 0


def profile_governed_agentic_step_result(
    *,
    step_id: str,
    title: str,
    elapsed_seconds: float,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """Build deterministic diagnostics from an already-returned governed result.

    This performs no retrieval, no model call and no governed-state mutation.
    """

    sources = _list_values(result, "sources")
    deduped_sources = _dedupe_dicts(sources)

    file_pages: set[tuple[str, str]] = set()
    files: set[str] = set()
    source_evidence_keys: set[str] = set()
    for source in deduped_sources:
        file_name = str(source.get("file") or source.get("document_id") or "").strip()
        page = str(source.get("page") or "").strip()
        if file_name:
            files.add(file_name)
        if file_name or page:
            file_pages.add((file_name, page))
        evidence_key = source.get("evidence_key")
        if isinstance(evidence_key, str) and evidence_key:
            source_evidence_keys.add(evidence_key)

    relied = {
        value
        for value in _list_values(result, "relied_evidence_keys")
        if isinstance(value, str) and value
    }
    answer_scope = {
        value
        for value in _list_values(result, "answer_scope_evidence_keys")
        if isinstance(value, str) and value
    }
    bindings = _list_values(result, "answer_statement_bindings")

    search_receipt = result.get("evidence_search_receipt")
    search_summary = {
        "search_mode": _profile_field(search_receipt, "search_mode"),
        "documents_inspected": _profile_field(search_receipt, "documents_inspected"),
        "pages_inspected": _profile_field(search_receipt, "pages_inspected"),
        "chunks_inspected": _profile_field(search_receipt, "chunks_inspected"),
        "case_corpus_complete": bool(
            _profile_field(search_receipt, "case_corpus_complete", False)
        ),
    }

    resolution = result.get("evidence_reference_resolution")
    findings = (
        resolution.get("findings")
        if isinstance(resolution, Mapping)
        else None
    )
    status_counts: dict[str, int] = {}
    if isinstance(findings, list):
        for finding in findings:
            if not isinstance(finding, Mapping):
                continue
            status = str(
                finding.get("status")
                or finding.get("resolution_status")
                or "unknown"
            )
            status_counts[status] = status_counts.get(status, 0) + 1

    search_results = result.get("search_results")
    search_result_count = 0
    if isinstance(search_results, Mapping):
        ids = search_results.get("ids")
        if (
            isinstance(ids, list)
            and len(ids) == 1
            and isinstance(ids[0], list)
        ):
            search_result_count = len(ids[0])

    answer = result.get("answer")
    answer_text = answer.strip() if isinstance(answer, str) else ""

    try:
        result_json_bytes = len(_canonical_bytes(dict(result)))
    except Exception:
        result_json_bytes = None

    unique_file_page_count = len(file_pages)
    deduped_source_count = len(deduped_sources)
    file_page_expansion_ratio = (
        round(deduped_source_count / unique_file_page_count, 3)
        if unique_file_page_count
        else None
    )

    flags: list[str] = []
    if elapsed_seconds >= 60:
        flags.append("SLOW_STEP_GE_60S")
    if deduped_source_count >= 200:
        flags.append("LARGE_SOURCE_ENVELOPE_GE_200")
    if deduped_source_count >= 100 and not relied:
        flags.append("LARGE_SOURCE_ENVELOPE_WITH_ZERO_RELIED_KEYS")
    if (
        file_page_expansion_ratio is not None
        and file_page_expansion_ratio >= 5
    ):
        flags.append("SOURCE_REFERENCE_EXPANSION_GE_5X")
    if search_result_count >= 200:
        flags.append("LARGE_SEARCH_RESULT_SCOPE_GE_200")

    return {
        "step_id": step_id,
        "title": title,
        "elapsed_seconds": round(float(elapsed_seconds), 3),
        "retrieval_mode": result.get("retrieval_mode"),
        "new_ai_finding": bool(result.get("new_ai_finding")),
        "answer_chars": len(answer_text),
        "answer_words": len(answer_text.split()),
        "raw_source_count": len(sources),
        "deduped_source_count": deduped_source_count,
        "unique_file_count": len(files),
        "unique_file_page_count": unique_file_page_count,
        "file_page_expansion_ratio": file_page_expansion_ratio,
        "source_evidence_key_count": len(source_evidence_keys),
        "relied_evidence_key_count": len(relied),
        "answer_scope_evidence_key_count": len(answer_scope),
        "statement_binding_count": len(bindings),
        "search_result_count": search_result_count,
        "search_receipt": search_summary,
        "reference_resolution_finding_count": (
            len(findings) if isinstance(findings, list) else 0
        ),
        "reference_resolution_status_counts": status_counts,
        "reference_resolution_warning": result.get(
            "evidence_reference_resolution_warning"
        ),
        "result_json_bytes": result_json_bytes,
        "flags": flags,
    }


def build_governed_agentic_performance_profile(
    *,
    step_profiles: Iterable[Mapping[str, Any]],
    phase_seconds: Mapping[str, float],
) -> dict[str, Any]:
    """Aggregate deterministic performance diagnostics without changing legal work."""

    steps = tuple(dict(item) for item in step_profiles)
    elapsed = [
        float(item.get("elapsed_seconds", 0.0))
        for item in steps
    ]
    step_sum = round(sum(elapsed), 3)
    sorted_elapsed = sorted(elapsed)
    median = (
        sorted_elapsed[len(sorted_elapsed) // 2]
        if sorted_elapsed
        else 0.0
    )

    flags: list[str] = []
    slowest = None
    if steps:
        slowest = max(steps, key=lambda item: float(item.get("elapsed_seconds", 0.0)))
        slowest_elapsed = float(slowest.get("elapsed_seconds", 0.0))
        if (
            slowest_elapsed >= 60
            and median > 0
            and slowest_elapsed >= median * 1.75
        ):
            flags.append("STEP_LATENCY_OUTLIER_GE_1_75X_MEDIAN")

    for item in steps:
        for flag in item.get("flags", ()):
            if isinstance(flag, str) and flag not in flags:
                flags.append(flag)

    normalized_phases = {
        str(key): round(float(value), 3)
        for key, value in phase_seconds.items()
        if isinstance(value, (int, float))
    }
    server_total = normalized_phases.get("server_pre_rerun_total", 0.0)
    accounted = round(
        sum(
            value
            for key, value in normalized_phases.items()
            if key not in {"server_pre_rerun_total", "unaccounted_server_seconds"}
        ),
        3,
    )
    unaccounted = round(max(0.0, server_total - accounted), 3)
    normalized_phases["unaccounted_server_seconds"] = unaccounted
    if unaccounted >= 5:
        flags.append("UNACCOUNTED_SERVER_OVERHEAD_GE_5S")

    return {
        "schema": "gac1-performance-profile/v1",
        "step_count": len(steps),
        "step_elapsed_sum_seconds": step_sum,
        "median_step_seconds": round(median, 3),
        "slowest_step_id": (
            str(slowest.get("step_id")) if slowest is not None else None
        ),
        "slowest_step_seconds": (
            round(float(slowest.get("elapsed_seconds", 0.0)), 3)
            if slowest is not None
            else None
        ),
        "steps": list(steps),
        "phase_seconds": normalized_phases,
        "flags": flags,
    }


def append_governed_agentic_investigation_receipt(
    *,
    case_id: str,
    access: MatterAccessContext,
    task_id: str,
    plan: GovernedAgenticPlan,
    step_results: Iterable[Mapping[str, Any]],
    proposed_result: Mapping[str, Any],
    root: Path | str | None = None,
    task_loader: Callable[[str], Iterable[Any]] = load_tasks,
) -> GovernedAgenticExecutionReceipt:
    """Append one immutable audit receipt. This does not create task work."""

    require_matter_mutation(access)
    case = _case_name(case_id)
    task = _required(task_id, "task_id")
    if access.case_id != case:
        raise GovernedAgenticInvestigationError(
            "Matter access does not match agentic investigation case_id."
        )
    if plan.case_id != case or plan.task_id != task:
        raise GovernedAgenticInvestigationError(
            "Agentic plan identity does not match the selected task."
        )
    if not _task_exists(case, task, task_loader=task_loader):
        raise GovernedAgenticInvestigationError(
            "Approved task was not found in this matter."
        )

    results = tuple(step_results)
    if len(results) != len(plan.steps):
        raise GovernedAgenticInvestigationError(
            "Agentic execution result count does not match plan."
        )
    proposed = proposed_result.get("answer")
    if not isinstance(proposed, str) or not proposed.strip():
        raise GovernedAgenticInvestigationError(
            "Agentic proposed work result is empty."
        )

    step_records = []
    for step, result in zip(plan.steps, results):
        answer = result.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise GovernedAgenticInvestigationError(
                f"Agentic step {step.step_id} returned no answer."
            )
        step_records.append(
            {
                "step_id": step.step_id,
                "title": step.title,
                "question_sha256": sha256(
                    step.question.encode("utf-8")
                ).hexdigest(),
                "answer_sha256": sha256(
                    answer.strip().encode("utf-8")
                ).hexdigest(),
                "sources": list(_compact_sources(result)),
                "relied_evidence_keys": sorted(
                    {
                        value
                        for value in _list_values(
                            result, "relied_evidence_keys"
                        )
                        if isinstance(value, str) and value
                    }
                ),
                "analytical_authority_id": result.get("analytical_authority_id"),
                "analytical_activation_id": result.get("analytical_activation_id"),
                "elapsed_seconds": (
                    float(result.get("gac1_elapsed_seconds"))
                    if isinstance(result.get("gac1_elapsed_seconds"), (int, float))
                    else None
                ),
            }
        )

    execution_id = str(uuid.uuid4())
    recorded_at = _now()
    body = {
        "schema_version": GAC1_EXECUTION_SCHEMA_VERSION,
        "execution_id": execution_id,
        "recorded_at": recorded_at,
        "case_id": case,
        "task_id": task,
        "plan_id": plan.plan_id,
        "step_count": len(step_records),
        "step_records": step_records,
        "proposed_work_result_sha256": sha256(
            proposed.strip().encode("utf-8")
        ).hexdigest(),
        "proposed_work_result": proposed.strip(),
    }
    receipt_id = "sha256:" + _sha(body)
    receipt = GovernedAgenticExecutionReceipt(
        schema_version=GAC1_EXECUTION_SCHEMA_VERSION,
        receipt_id=receipt_id,
        execution_id=execution_id,
        recorded_at=recorded_at,
        case_id=case,
        task_id=task,
        plan_id=plan.plan_id,
        step_count=len(step_records),
        step_records=tuple(step_records),
        proposed_work_result_sha256=body["proposed_work_result_sha256"],
        proposed_work_result=proposed.strip(),
    )

    path = _event_path(case, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "schema_version": GAC1_SCHEMA_VERSION,
        "event_type": "execution_receipt",
        "event_id": str(uuid.uuid4()),
        "recorded_at": recorded_at,
        "case_id": case,
        "task_id": task,
        "receipt": asdict(receipt),
    }
    payload = json.dumps(
        event,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(payload + "\n")
        handle.flush()
        os.fsync(handle.fileno())

    return receipt


def load_governed_agentic_investigation_receipts(
    case_id: str,
    task_id: str,
    *,
    root: Path | str | None = None,
) -> tuple[GovernedAgenticExecutionReceipt, ...]:
    case = _case_name(case_id)
    task = _required(task_id, "task_id")
    path = _event_path(case, root=root)
    if not path.exists():
        return ()

    output = []
    seen = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise GovernedAgenticInvestigationError(
                    f"Invalid agentic execution JSON at line {line_number}."
                ) from exc
            if (
                not isinstance(event, dict)
                or event.get("schema_version") != GAC1_SCHEMA_VERSION
                or event.get("event_type") != "execution_receipt"
            ):
                raise GovernedAgenticInvestigationError(
                    f"Invalid agentic execution event at line {line_number}."
                )
            if event.get("case_id") != case:
                raise GovernedAgenticInvestigationError(
                    f"Cross-matter agentic execution event at line {line_number}."
                )
            if event.get("task_id") != task:
                continue
            data = event.get("receipt")
            if not isinstance(data, dict):
                raise GovernedAgenticInvestigationError(
                    f"Agentic receipt missing at line {line_number}."
                )
            receipt = GovernedAgenticExecutionReceipt(
                schema_version=_required(
                    data.get("schema_version"), "receipt.schema_version"
                ),
                receipt_id=_required(data.get("receipt_id"), "receipt.receipt_id"),
                execution_id=_required(
                    data.get("execution_id"), "receipt.execution_id"
                ),
                recorded_at=_required(
                    data.get("recorded_at"), "receipt.recorded_at"
                ),
                case_id=_required(data.get("case_id"), "receipt.case_id"),
                task_id=_required(data.get("task_id"), "receipt.task_id"),
                plan_id=_required(data.get("plan_id"), "receipt.plan_id"),
                step_count=int(data.get("step_count")),
                step_records=tuple(data.get("step_records") or ()),
                proposed_work_result_sha256=_required(
                    data.get("proposed_work_result_sha256"),
                    "receipt.proposed_work_result_sha256",
                ),
                proposed_work_result=_required(
                    data.get("proposed_work_result"),
                    "receipt.proposed_work_result",
                ),
            )
            if receipt.case_id != case or receipt.task_id != task:
                raise GovernedAgenticInvestigationError(
                    f"Agentic receipt identity mismatch at line {line_number}."
                )
            if receipt.receipt_id in seen:
                raise GovernedAgenticInvestigationError(
                    f"Duplicate agentic receipt at line {line_number}."
                )
            seen.add(receipt.receipt_id)
            output.append(receipt)
    return tuple(output)


def _load_professional_decisions(
    case_id: str,
    task_id: str,
    *,
    root: Path | str | None = None,
) -> tuple[GovernedAgenticProfessionalDecision, ...]:
    case = _case_name(case_id)
    task = _required(task_id, "task_id")
    path = _decision_path(case, root=root)
    if not path.exists():
        return ()

    output = []
    seen = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise GovernedAgenticInvestigationError(
                    f"Invalid agentic decision JSON at line {line_number}."
                ) from exc
            if (
                not isinstance(event, dict)
                or event.get("schema_version") != GAC1_SCHEMA_VERSION
                or event.get("event_type") != "professional_decision"
            ):
                raise GovernedAgenticInvestigationError(
                    f"Invalid agentic decision event at line {line_number}."
                )
            if event.get("case_id") != case:
                raise GovernedAgenticInvestigationError(
                    f"Cross-matter agentic decision at line {line_number}."
                )
            if event.get("task_id") != task:
                continue
            data = event.get("decision")
            if not isinstance(data, dict):
                raise GovernedAgenticInvestigationError(
                    f"Agentic decision payload missing at line {line_number}."
                )
            try:
                decision_value = GovernedAgenticDecision(data.get("decision"))
            except ValueError as exc:
                raise GovernedAgenticInvestigationError(
                    f"Unsupported decision at line {line_number}."
                ) from exc
            record = GovernedAgenticProfessionalDecision(
                schema_version=_required(
                    data.get("schema_version"), "decision.schema_version"
                ),
                decision_id=_required(
                    data.get("decision_id"), "decision.decision_id"
                ),
                recorded_at=_required(
                    data.get("recorded_at"), "decision.recorded_at"
                ),
                case_id=_required(data.get("case_id"), "decision.case_id"),
                task_id=_required(data.get("task_id"), "decision.task_id"),
                receipt_id=_required(
                    data.get("receipt_id"), "decision.receipt_id"
                ),
                decision=decision_value,
                reviewer_reference=_required(
                    data.get("reviewer_reference"), "decision.reviewer_reference"
                ),
                reviewer_note=str(data.get("reviewer_note") or "").strip(),
            )
            if record.decision_id in seen:
                raise GovernedAgenticInvestigationError(
                    f"Duplicate agentic decision at line {line_number}."
                )
            seen.add(record.decision_id)
            output.append(record)
    return tuple(output)


def append_governed_agentic_professional_decision(
    *,
    case_id: str,
    access: MatterAccessContext,
    task_id: str,
    receipt_id: str,
    decision: GovernedAgenticDecision | str,
    reviewer_reference: str,
    reviewer_note: str = "",
    root: Path | str | None = None,
) -> GovernedAgenticProfessionalDecision:
    """Record explicit accept/reject of a proposal. No other state is changed."""

    require_matter_mutation(access)
    case = _case_name(case_id)
    task = _required(task_id, "task_id")
    receipt = _required(receipt_id, "receipt_id")
    reviewer = _required(reviewer_reference, "reviewer_reference")
    if access.case_id != case:
        raise GovernedAgenticInvestigationError(
            "Matter access does not match agentic decision case_id."
        )
    try:
        decision_value = GovernedAgenticDecision(decision)
    except ValueError as exc:
        raise GovernedAgenticInvestigationError(
            "Unsupported agentic professional decision."
        ) from exc

    receipts = load_governed_agentic_investigation_receipts(
        case,
        task,
        root=root,
    )
    if receipt not in {item.receipt_id for item in receipts}:
        raise GovernedAgenticInvestigationError(
            "Agentic execution receipt was not found for this task."
        )

    existing = _load_professional_decisions(case, task, root=root)
    for record in existing:
        if (
            record.receipt_id == receipt
            and record.decision is decision_value
            and record.reviewer_reference == reviewer
        ):
            return record

    recorded_at = _now()
    body = {
        "schema_version": GAC1_DECISION_SCHEMA_VERSION,
        "recorded_at": recorded_at,
        "case_id": case,
        "task_id": task,
        "receipt_id": receipt,
        "decision": decision_value.value,
        "reviewer_reference": reviewer,
        "reviewer_note": str(reviewer_note or "").strip(),
    }
    decision_id = "sha256:" + _sha(body)
    record = GovernedAgenticProfessionalDecision(
        schema_version=GAC1_DECISION_SCHEMA_VERSION,
        decision_id=decision_id,
        recorded_at=recorded_at,
        case_id=case,
        task_id=task,
        receipt_id=receipt,
        decision=decision_value,
        reviewer_reference=reviewer,
        reviewer_note=str(reviewer_note or "").strip(),
    )

    path = _decision_path(case, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "schema_version": GAC1_SCHEMA_VERSION,
        "event_type": "professional_decision",
        "event_id": str(uuid.uuid4()),
        "recorded_at": recorded_at,
        "case_id": case,
        "task_id": task,
        "decision": asdict(record),
    }
    event["decision"]["decision"] = decision_value.value
    payload = json.dumps(
        event,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(payload + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return record


__all__ = [
    "GAC1_SCHEMA_VERSION",
    "GovernedAgenticDecision",
    "GovernedAgenticExecutionReceipt",
    "GovernedAgenticInvestigationError",
    "GovernedAgenticPlan",
    "GovernedAgenticProfessionalDecision",
    "GovernedAgenticStep",
    "append_governed_agentic_investigation_receipt",
    "append_governed_agentic_professional_decision",
    "build_governed_agentic_investigation_plan",
    "combine_governed_agentic_step_results",
    "load_governed_agentic_investigation_receipts",
    "profile_governed_agentic_step_result",
    "build_governed_agentic_performance_profile",
]
