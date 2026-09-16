"""GAC2 governed objective-led multi-step investigation for LegalRAG Pro.

GAC2 is a successor capability built alongside, not on top of, the frozen GAC1
runtime contract. It gives the professional user an explicit investigation
objective and a reviewable five-step plan before any governed evidence calls
are made.

The capability remains subordinate to the existing professional workflow:
- it is bound to one existing approved matter task;
- it does not create/update/complete tasks;
- it does not mutate Current Assessment;
- it does not create, approve or publish drafts;
- it does not change court/tribunal reliance or report projections;
- an investigation result becomes ordinary recorded task work only through the
  existing Case Operator professional acceptance path.
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


GAC2_SCHEMA_VERSION = "gac2-governed-agentic-investigation/v1"
GAC2_PLAN_SCHEMA_VERSION = "gac2-governed-agentic-plan/v1"
GAC2_EXECUTION_SCHEMA_VERSION = "gac2-governed-agentic-execution/v1"
GAC2_DECISION_SCHEMA_VERSION = "gac2-governed-agentic-decision/v1"

_SAFE_CASE_ID = re.compile(r"^[A-Za-z0-9_.:-]+$")
_MAX_OBJECTIVE_CHARS = 2000


class GovernedAgenticInvestigationV2Error(RuntimeError):
    """Raised when the bounded GAC2 contract fails closed."""


class GovernedAgenticDecisionV2(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class GovernedAgenticStepV2:
    step_id: str
    title: str
    question: str


@dataclass(frozen=True)
class GovernedAgenticPlanV2:
    schema_version: str
    plan_id: str
    case_id: str
    task_id: str
    task_title: str
    objective: str
    steps: tuple[GovernedAgenticStepV2, ...]


@dataclass(frozen=True)
class GovernedAgenticExecutionReceiptV2:
    schema_version: str
    receipt_id: str
    execution_id: str
    recorded_at: str
    case_id: str
    task_id: str
    plan_id: str
    objective: str
    step_count: int
    step_records: tuple[dict[str, Any], ...]
    proposed_work_result_sha256: str
    proposed_work_result: str


@dataclass(frozen=True)
class GovernedAgenticProfessionalDecisionV2:
    schema_version: str
    decision_id: str
    recorded_at: str
    case_id: str
    task_id: str
    receipt_id: str
    decision: GovernedAgenticDecisionV2
    reviewer_reference: str
    reviewer_note: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _required(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GovernedAgenticInvestigationV2Error(f"{field_name} is required.")
    return value.strip()


def _bounded_objective(value: Any) -> str:
    objective = _required(value, "objective")
    if len(objective) > _MAX_OBJECTIVE_CHARS:
        raise GovernedAgenticInvestigationV2Error(
            f"objective exceeds {_MAX_OBJECTIVE_CHARS} characters."
        )
    return objective


def _case_name(case_id: str) -> str:
    value = _required(case_id, "case_id")
    if not _SAFE_CASE_ID.fullmatch(value) or value in {".", ".."}:
        raise GovernedAgenticInvestigationV2Error("case_id is invalid.")
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
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "LegalRAG-Pro" / "governed_agentic_investigation" / "v2"


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
            raise GovernedAgenticInvestigationV2Error(
                "Task loader returned a cross-matter task."
            )
        if getattr(task, "task_id", None) == task_id:
            return True
    return False


def build_governed_agentic_investigation_v2_plan(
    task: Any,
    *,
    objective: str,
) -> GovernedAgenticPlanV2:
    """Build a deterministic, reviewable five-step plan for one approved task."""

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
    requested_objective = _bounded_objective(objective)

    common = (
        f"Approved task: {title}\n"
        f"Related issue: {issue}\n"
        f"Why this matters: {why}\n"
        f"Originating investigation: {originating}\n"
        f"Professional investigation objective: {requested_objective}\n\n"
        "Use only governed matter evidence available to LegalRAG. Cite material "
        "source documents/pages and distinguish evidence from inference. Remain "
        "within the approved task and objective. Do not change task status, the "
        "Current Assessment, professional approval, any WorkingDraft, "
        "court/tribunal reliance state, or any report projection."
    )

    steps = (
        GovernedAgenticStepV2(
            step_id="frame-propositions-and-chronology",
            title="Frame the propositions, chronology and actors",
            question=(
                common
                + "\n\nStep 1: Frame the factual propositions that must be tested for "
                "this objective. Identify the material dates, people/organisations and "
                "documentary sequence. Do not decide the issue merely from chronology."
            ),
        ),
        GovernedAgenticStepV2(
            step_id="supporting-evidence",
            title="Strongest supporting evidence",
            question=(
                common
                + "\n\nStep 2: Identify and assess the strongest contemporaneous "
                "evidence supporting the material propositions. State source support, "
                "limitations and any inference explicitly."
            ),
        ),
        GovernedAgenticStepV2(
            step_id="adverse-qualifying-evidence",
            title="Adverse and qualifying evidence",
            question=(
                common
                + "\n\nStep 3: Identify and assess the strongest adverse, inconsistent "
                "or qualifying evidence. Do not omit inconvenient evidence and do not "
                "convert an absence of evidence into proof of the opposite proposition."
            ),
        ),
        GovernedAgenticStepV2(
            step_id="contradictions-connections",
            title="Contradictions and evidential connections",
            question=(
                common
                + "\n\nStep 4: Compare the material accounts and evidence. Identify "
                "genuine contradictions, corroborating connections and unresolved "
                "tensions. Distinguish a documentary contradiction from an allegation "
                "that a person was dishonest."
            ),
        ),
        GovernedAgenticStepV2(
            step_id="gaps-professional-actions",
            title="Evidence gaps and professional next actions",
            question=(
                common
                + "\n\nStep 5: Identify material gaps that remain after the investigation "
                "and propose proportionate professional next actions. Separate actions "
                "that can be taken from the current matter evidence from actions that "
                "require an external document, disclosure, witness input or other "
                "material. Do not state that the approved task is complete."
            ),
        ),
    )

    identity_payload = {
        "schema_version": GAC2_PLAN_SCHEMA_VERSION,
        "case_id": case_id,
        "task_id": task_id,
        "task_title": title,
        "objective": requested_objective,
        "steps": [asdict(step) for step in steps],
    }
    plan_id = "sha256:" + _sha(identity_payload)

    return GovernedAgenticPlanV2(
        schema_version=GAC2_PLAN_SCHEMA_VERSION,
        plan_id=plan_id,
        case_id=case_id,
        task_id=task_id,
        task_title=title,
        objective=requested_objective,
        steps=steps,
    )


def _list_values(result: Mapping[str, Any], key: str) -> list[Any]:
    value = result.get(key)
    return list(value) if isinstance(value, (list, tuple)) else []


def _source_evidence_key(source: Any) -> str | None:
    if not isinstance(source, Mapping):
        return None
    for key in ("evidence_key", "source_evidence_key"):
        value = source.get(key)
        if isinstance(value, str) and value:
            return value
    return None


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
        raise GovernedAgenticInvestigationV2Error(
            f"Agentic step results disagree on {key}."
        )
    return values[0] if values else None


def _compact_summary_text(value: str, *, limit: int = 420) -> str:
    text = " ".join(str(value).strip().split())
    if len(text) <= limit:
        return text
    clipped = text[: max(1, limit - 1)].rstrip()
    boundary = clipped.rfind(" ")
    if boundary >= int(limit * 0.65):
        clipped = clipped[:boundary].rstrip()
    return clipped + "…"


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


def combine_governed_agentic_investigation_v2_results(
    *,
    plan: GovernedAgenticPlanV2,
    step_results: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Combine exactly one governed result per GAC2 step without approving it."""

    results = tuple(step_results)
    if len(results) != len(plan.steps):
        raise GovernedAgenticInvestigationV2Error(
            "Agentic result count does not match the approved GAC2 plan."
        )

    answer_parts = [
        "Governed multi-step investigation proposal",
        "",
        f"Professional objective: {plan.objective}",
        "",
        (
            "This is proposed task work only. It has not changed task status, the "
            "Current Assessment, any WorkingDraft, professional approval, "
            "court/tribunal reliance state, or any report projection."
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
            raise GovernedAgenticInvestigationV2Error(
                f"GAC2 step {step.step_id} returned no answer."
            )
        answer_parts.extend(["", f"### {step.title}", answer.strip()])
        sources = _list_values(result, "sources")
        relied = [
            value
            for value in _list_values(result, "relied_evidence_keys")
            if isinstance(value, str) and value
        ]
        deduped_sources = _dedupe_dicts(sources)
        relied_set = set(relied)
        bound_source_keys = {
            key
            for key in (_source_evidence_key(source) for source in deduped_sources)
            if key is not None and key in relied_set
        }
        relied_sources = [
            dict(source)
            for source in deduped_sources
            if isinstance(source, Mapping)
            and _source_evidence_key(source) in relied_set
        ]
        if relied_set and relied_set.issubset(bound_source_keys):
            reference_binding_status = "bound"
        elif relied_set:
            reference_binding_status = "relied_keys_without_source_metadata"
        elif deduped_sources:
            reference_binding_status = "coverage_only"
        else:
            reference_binding_status = "unbound"
        new_ai_finding = bool(result.get("new_ai_finding"))
        elapsed = result.get("gac2_elapsed_seconds")
        step_summaries.append(
            {
                "step_id": step.step_id,
                "title": step.title,
                "summary": _compact_summary_text(answer),
                "source_count": len(deduped_sources),
                "relied_evidence_count": len(relied_set),
                "relied_source_count": len(relied_sources),
                "new_ai_finding": new_ai_finding,
                "reference_binding_status": reference_binding_status,
                "relied_sources": relied_sources,
                "elapsed_seconds": (
                    float(elapsed) if isinstance(elapsed, (int, float)) else None
                ),
            }
        )
        all_sources.extend(sources)
        relied_keys.extend(relied)
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
            reference_resolutions.append(
                result.get("evidence_reference_resolution")
            )
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
                "Accept this proposal only if it is suitable to become recorded task "
                "work. Acceptance does not complete the task, alter the Current "
                "Assessment, approve a draft, or publish work product."
            ),
        ]
    )

    blocked_reference_steps = [
        item["step_id"]
        for item in step_summaries
        if item.get("reference_binding_status") != "bound"
    ]

    combined: dict[str, Any] = {
        "answer": "\n".join(answer_parts).strip(),
        "sources": _dedupe_dicts(all_sources),
        "relied_evidence_keys": sorted(set(relied_keys)),
        "answer_scope_evidence_keys": sorted(set(scope_keys)),
        "answer_statement_bindings": statement_bindings,
        "evidence_search_receipt": {
            "schema": "gac2-aggregate-evidence-search-receipt/v1",
            "step_receipts": search_receipts,
        },
        "evidence_reference_resolution": {
            "schema": "gac2-aggregate-evidence-reference-resolution/v1",
            "step_resolutions": reference_resolutions,
        },
        "new_ai_finding": any_new_ai_finding,
        "gac2_plan_id": plan.plan_id,
        "gac2_objective": plan.objective,
        "gac2_step_count": len(plan.steps),
        "gac2_step_summaries": step_summaries,
        "gac2_reference_binding_complete": not blocked_reference_steps,
        "gac2_reference_binding_blocked_steps": blocked_reference_steps,
        "gac2_reference_binding_schema": "gac2-reference-binding-audit/v1",
        "gac2_proposal": True,
    }

    authority_id = _unique_scalar(results, "analytical_authority_id")
    if authority_id is not None:
        combined["analytical_authority_id"] = authority_id
    authority_mode = _unique_scalar(results, "analytical_authority_mode")
    if authority_mode is not None:
        combined["analytical_authority_mode"] = authority_mode
    if activation_ids:
        combined["gac2_analytical_activation_ids"] = sorted(set(activation_ids))
        if len(set(activation_ids)) == 1:
            combined["analytical_activation_id"] = activation_ids[0]

    return combined


def append_governed_agentic_investigation_v2_receipt(
    *,
    case_id: str,
    access: MatterAccessContext,
    task_id: str,
    plan: GovernedAgenticPlanV2,
    step_results: Iterable[Mapping[str, Any]],
    proposed_result: Mapping[str, Any],
    root: Path | str | None = None,
    task_loader: Callable[[str], Iterable[Any]] = load_tasks,
) -> GovernedAgenticExecutionReceiptV2:
    """Append one immutable GAC2 execution receipt; create no task work."""

    require_matter_mutation(access)
    case = _case_name(case_id)
    task = _required(task_id, "task_id")

    if access.case_id != case:
        raise GovernedAgenticInvestigationV2Error(
            "Matter access does not match GAC2 case_id."
        )
    if plan.case_id != case or plan.task_id != task:
        raise GovernedAgenticInvestigationV2Error(
            "GAC2 plan identity does not match the selected task."
        )
    if not _task_exists(case, task, task_loader=task_loader):
        raise GovernedAgenticInvestigationV2Error(
            "Approved task was not found in this matter."
        )

    results = tuple(step_results)
    if len(results) != len(plan.steps):
        raise GovernedAgenticInvestigationV2Error(
            "GAC2 execution result count does not match plan."
        )

    proposed = proposed_result.get("answer")
    if not isinstance(proposed, str) or not proposed.strip():
        raise GovernedAgenticInvestigationV2Error(
            "GAC2 proposed work result is empty."
        )

    step_records = []
    for step, result in zip(plan.steps, results):
        answer = result.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise GovernedAgenticInvestigationV2Error(
                f"GAC2 step {step.step_id} returned no answer."
            )
        elapsed = result.get("gac2_elapsed_seconds")
        step_records.append(
            {
                "step_id": step.step_id,
                "title": step.title,
                "question_sha256": sha256(step.question.encode("utf-8")).hexdigest(),
                "answer_sha256": sha256(answer.strip().encode("utf-8")).hexdigest(),
                "sources": list(_compact_sources(result)),
                "relied_evidence_keys": sorted(
                    {
                        value
                        for value in _list_values(result, "relied_evidence_keys")
                        if isinstance(value, str) and value
                    }
                ),
                "analytical_authority_id": result.get("analytical_authority_id"),
                "analytical_activation_id": result.get("analytical_activation_id"),
                "elapsed_seconds": (
                    float(elapsed) if isinstance(elapsed, (int, float)) else None
                ),
            }
        )

    execution_id = str(uuid.uuid4())
    recorded_at = _now()
    body = {
        "schema_version": GAC2_EXECUTION_SCHEMA_VERSION,
        "execution_id": execution_id,
        "recorded_at": recorded_at,
        "case_id": case,
        "task_id": task,
        "plan_id": plan.plan_id,
        "objective": plan.objective,
        "step_count": len(step_records),
        "step_records": step_records,
        "proposed_work_result_sha256": sha256(
            proposed.strip().encode("utf-8")
        ).hexdigest(),
        "proposed_work_result": proposed.strip(),
    }
    receipt_id = "sha256:" + _sha(body)
    receipt = GovernedAgenticExecutionReceiptV2(
        schema_version=GAC2_EXECUTION_SCHEMA_VERSION,
        receipt_id=receipt_id,
        execution_id=execution_id,
        recorded_at=recorded_at,
        case_id=case,
        task_id=task,
        plan_id=plan.plan_id,
        objective=plan.objective,
        step_count=len(step_records),
        step_records=tuple(step_records),
        proposed_work_result_sha256=body["proposed_work_result_sha256"],
        proposed_work_result=proposed.strip(),
    )

    path = _event_path(case, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "schema_version": GAC2_SCHEMA_VERSION,
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


def load_governed_agentic_investigation_v2_receipts(
    case_id: str,
    task_id: str,
    *,
    root: Path | str | None = None,
) -> tuple[GovernedAgenticExecutionReceiptV2, ...]:
    case = _case_name(case_id)
    task = _required(task_id, "task_id")
    path = _event_path(case, root=root)
    if not path.exists():
        return ()

    output = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise GovernedAgenticInvestigationV2Error(
                    f"Invalid GAC2 execution JSON at line {line_number}."
                ) from exc
            if (
                not isinstance(event, dict)
                or event.get("schema_version") != GAC2_SCHEMA_VERSION
                or event.get("event_type") != "execution_receipt"
            ):
                raise GovernedAgenticInvestigationV2Error(
                    f"Invalid GAC2 execution event at line {line_number}."
                )
            if event.get("case_id") != case:
                raise GovernedAgenticInvestigationV2Error(
                    f"Cross-matter GAC2 execution event at line {line_number}."
                )
            if event.get("task_id") != task:
                continue
            data = event.get("receipt")
            if not isinstance(data, dict):
                raise GovernedAgenticInvestigationV2Error(
                    f"GAC2 receipt missing at line {line_number}."
                )
            receipt = GovernedAgenticExecutionReceiptV2(
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
                objective=_required(data.get("objective"), "receipt.objective"),
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
                raise GovernedAgenticInvestigationV2Error(
                    f"GAC2 receipt identity mismatch at line {line_number}."
                )
            if receipt.receipt_id in seen:
                raise GovernedAgenticInvestigationV2Error(
                    f"Duplicate GAC2 receipt at line {line_number}."
                )
            seen.add(receipt.receipt_id)
            output.append(receipt)
    return tuple(output)


def _load_professional_decisions(
    case_id: str,
    task_id: str,
    *,
    root: Path | str | None = None,
) -> tuple[GovernedAgenticProfessionalDecisionV2, ...]:
    case = _case_name(case_id)
    task = _required(task_id, "task_id")
    path = _decision_path(case, root=root)
    if not path.exists():
        return ()

    output = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise GovernedAgenticInvestigationV2Error(
                    f"Invalid GAC2 decision JSON at line {line_number}."
                ) from exc
            if (
                not isinstance(event, dict)
                or event.get("schema_version") != GAC2_SCHEMA_VERSION
                or event.get("event_type") != "professional_decision"
            ):
                raise GovernedAgenticInvestigationV2Error(
                    f"Invalid GAC2 decision event at line {line_number}."
                )
            if event.get("case_id") != case:
                raise GovernedAgenticInvestigationV2Error(
                    f"Cross-matter GAC2 decision at line {line_number}."
                )
            if event.get("task_id") != task:
                continue
            data = event.get("decision")
            if not isinstance(data, dict):
                raise GovernedAgenticInvestigationV2Error(
                    f"GAC2 decision payload missing at line {line_number}."
                )
            try:
                decision_value = GovernedAgenticDecisionV2(data.get("decision"))
            except ValueError as exc:
                raise GovernedAgenticInvestigationV2Error(
                    f"Unsupported GAC2 decision at line {line_number}."
                ) from exc
            record = GovernedAgenticProfessionalDecisionV2(
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
                raise GovernedAgenticInvestigationV2Error(
                    f"Duplicate GAC2 decision at line {line_number}."
                )
            seen.add(record.decision_id)
            output.append(record)
    return tuple(output)


def append_governed_agentic_investigation_v2_professional_decision(
    *,
    case_id: str,
    access: MatterAccessContext,
    task_id: str,
    receipt_id: str,
    decision: GovernedAgenticDecisionV2 | str,
    reviewer_reference: str,
    reviewer_note: str = "",
    root: Path | str | None = None,
) -> GovernedAgenticProfessionalDecisionV2:
    """Record explicit GAC2 accept/reject without changing any other state."""

    require_matter_mutation(access)
    case = _case_name(case_id)
    task = _required(task_id, "task_id")
    receipt = _required(receipt_id, "receipt_id")
    reviewer = _required(reviewer_reference, "reviewer_reference")

    if access.case_id != case:
        raise GovernedAgenticInvestigationV2Error(
            "Matter access does not match GAC2 decision case_id."
        )
    try:
        decision_value = GovernedAgenticDecisionV2(decision)
    except ValueError as exc:
        raise GovernedAgenticInvestigationV2Error(
            "Unsupported GAC2 professional decision."
        ) from exc

    receipts = load_governed_agentic_investigation_v2_receipts(
        case,
        task,
        root=root,
    )
    if receipt not in {item.receipt_id for item in receipts}:
        raise GovernedAgenticInvestigationV2Error(
            "GAC2 execution receipt was not found for this task."
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
        "schema_version": GAC2_DECISION_SCHEMA_VERSION,
        "recorded_at": recorded_at,
        "case_id": case,
        "task_id": task,
        "receipt_id": receipt,
        "decision": decision_value.value,
        "reviewer_reference": reviewer,
        "reviewer_note": str(reviewer_note or "").strip(),
    }
    decision_id = "sha256:" + _sha(body)
    record = GovernedAgenticProfessionalDecisionV2(
        schema_version=GAC2_DECISION_SCHEMA_VERSION,
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
        "schema_version": GAC2_SCHEMA_VERSION,
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
    "GAC2_SCHEMA_VERSION",
    "GovernedAgenticDecisionV2",
    "GovernedAgenticExecutionReceiptV2",
    "GovernedAgenticInvestigationV2Error",
    "GovernedAgenticPlanV2",
    "GovernedAgenticProfessionalDecisionV2",
    "GovernedAgenticStepV2",
    "append_governed_agentic_investigation_v2_professional_decision",
    "append_governed_agentic_investigation_v2_receipt",
    "build_governed_agentic_investigation_v2_plan",
    "combine_governed_agentic_investigation_v2_results",
    "load_governed_agentic_investigation_v2_receipts",
]
