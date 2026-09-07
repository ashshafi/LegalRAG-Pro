"""Bounded generation of unpersisted LegalRAG working-draft candidates.

This module joins one existing task-work record, its R68 retrieval receipt,
one explicit professional authority scope, the current governed analytical
authority and one selected scoped element.

Generation is bounded to the intersection of:
    R68 answer_scope_evidence_keys
and:
    the selected governed element's supporting/adverse/corroborative/
    conflicting evidence.

Exact source text is supplied only by the released D1-I3-I3-I1 immutable
source adapter.  This module does not retrieve evidence, persist a draft,
change task state, change analytical authority, release a work product or
activate any UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Callable

from bounded_governed_answer import (
    create_bounded_governed_response,
)
from drafting_evidence_source_adapter import (
    DraftingEvidenceRow,
    DraftingEvidenceSourceError,
    reconstruct_bounded_generation_evidence,
)
from drafting_working_draft import (
    WorkingDraftStatementInput,
)
from matter_analysis_ledger import (
    LedgerElement,
    build_matter_analysis_ledger,
)
from solicitor_tasks import SolicitorTask
from task_work_authority_scope import (
    TaskWorkAuthorityScope,
    TaskWorkAuthorityScopeError,
    resolve_task_work_authority_scope,
)
from task_work_progress import TaskWorkProgress
from task_work_retrieval_receipt import (
    TaskWorkRetrievalReceipt,
)


_MAX_CANDIDATE_STATEMENTS = 8
_MAX_CANDIDATE_STATEMENT_TEXT_LENGTH = 12000

_MAP_MARKER = (
    "LEGALRAG GOVERNED LARGE-MATTER MAP PASS"
)

_REDUCE_MARKER = (
    "LEGALRAG GOVERNED LARGE-MATTER FINAL SYNTHESIS"
)


class DraftingWorkingDraftGenerationError(RuntimeError):
    """A bounded working-draft candidate could not be established."""


@dataclass(frozen=True)
class _Value:
    value: str


@dataclass(frozen=True)
class _DraftingCoverageReceipt:
    search_mode: _Value
    completion: _Value
    scope_document_count: int
    documents_completely_expanded: int
    scope_page_count: int
    pages_inspected: int
    scope_chunk_count: int
    chunks_inspected: int
    case_corpus_complete: bool
    negative_finding_permitted: bool
    negative_finding_scope: _Value


@dataclass(frozen=True)
class _DraftingSearchResult:
    receipt: _DraftingCoverageReceipt


@dataclass(frozen=True)
class _DraftingEvidence:
    search_result: _DraftingSearchResult


@dataclass(frozen=True)
class WorkingDraftGenerationCandidate:
    """One unpersisted bounded generation result."""

    case_id: str
    task_id: str
    progress_id: str
    scope_binding_id: str
    authority_id: str
    issue_analysis_id: str
    issue_definition_id: str
    element_id: str
    evidence_keys: tuple[str, ...]
    statements: tuple[WorkingDraftStatementInput, ...]


def _required_text(
    value: object,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DraftingWorkingDraftGenerationError(
            f"{field_name} is required."
        )

    return value.strip()


def _enum_text(
    value: object,
    field_name: str,
) -> str:
    if hasattr(value, "value"):
        value = getattr(value, "value")

    return _required_text(
        value,
        field_name,
    )


def _sha256_text(
    value: str,
) -> str:
    return sha256(
        value.encode("utf-8")
    ).hexdigest()


def _nonnegative_int(
    value: object,
    field_name: str,
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        raise DraftingWorkingDraftGenerationError(
            f"{field_name} must be a non-negative integer."
        )

    return value


def _required_bool(
    value: object,
    field_name: str,
) -> bool:
    if not isinstance(value, bool):
        raise DraftingWorkingDraftGenerationError(
            f"{field_name} must be Boolean."
        )

    return value


def _authority_identity(
    authority: object,
) -> tuple[str, str]:
    manifest = getattr(
        authority,
        "manifest",
        None,
    )

    if manifest is None:
        raise DraftingWorkingDraftGenerationError(
            "current governed authority has no manifest."
        )

    case_id = _required_text(
        getattr(
            manifest,
            "case_id",
            None,
        ),
        "authority.manifest.case_id",
    )

    authority_id = _required_text(
        getattr(
            manifest,
            "authority_id",
            None,
        ),
        "authority.manifest.authority_id",
    )

    return (
        case_id,
        authority_id,
    )


def _validate_chain(
    *,
    task: SolicitorTask,
    progress: TaskWorkProgress,
    retrieval_receipt: TaskWorkRetrievalReceipt,
    scope: TaskWorkAuthorityScope,
    authority: object,
) -> tuple[str, str]:
    if not isinstance(
        task,
        SolicitorTask,
    ):
        raise DraftingWorkingDraftGenerationError(
            "task must be a SolicitorTask."
        )

    if not isinstance(
        progress,
        TaskWorkProgress,
    ):
        raise DraftingWorkingDraftGenerationError(
            "progress must be a TaskWorkProgress."
        )

    if not isinstance(
        retrieval_receipt,
        TaskWorkRetrievalReceipt,
    ):
        raise DraftingWorkingDraftGenerationError(
            "retrieval_receipt must be a TaskWorkRetrievalReceipt."
        )

    if not isinstance(
        scope,
        TaskWorkAuthorityScope,
    ):
        raise DraftingWorkingDraftGenerationError(
            "scope must be a TaskWorkAuthorityScope."
        )

    case_id = _required_text(
        task.case_id,
        "task.case_id",
    )

    task_id = _required_text(
        task.task_id,
        "task.task_id",
    )

    progress_id = _required_text(
        progress.progress_id,
        "progress.progress_id",
    )

    if progress.case_id != case_id:
        raise DraftingWorkingDraftGenerationError(
            "task-work progress belongs to another case."
        )

    if progress.task_id != task_id:
        raise DraftingWorkingDraftGenerationError(
            "task-work progress belongs to another task."
        )

    if retrieval_receipt.case_id != case_id:
        raise DraftingWorkingDraftGenerationError(
            "R68 retrieval receipt belongs to another case."
        )

    if retrieval_receipt.task_id != task_id:
        raise DraftingWorkingDraftGenerationError(
            "R68 retrieval receipt belongs to another task."
        )

    if retrieval_receipt.progress_id != progress_id:
        raise DraftingWorkingDraftGenerationError(
            "R68 retrieval receipt does not bind this progress record."
        )

    if (
        retrieval_receipt.task_work_recorded_at
        != progress.recorded_at
    ):
        raise DraftingWorkingDraftGenerationError(
            "R68 task-work timestamp does not match progress."
        )

    if (
        retrieval_receipt.question_sha256
        != _sha256_text(
            _required_text(
                progress.question,
                "progress.question",
            )
        )
    ):
        raise DraftingWorkingDraftGenerationError(
            "R68 question hash does not match task-work progress."
        )

    if (
        retrieval_receipt.answer_sha256
        != _sha256_text(
            _required_text(
                progress.answer,
                "progress.answer",
            )
        )
    ):
        raise DraftingWorkingDraftGenerationError(
            "R68 answer hash does not match task-work progress."
        )

    if scope.case_id != case_id:
        raise DraftingWorkingDraftGenerationError(
            "professional authority scope belongs to another case."
        )

    if scope.task_id != task_id:
        raise DraftingWorkingDraftGenerationError(
            "professional authority scope belongs to another task."
        )

    if scope.progress_id != progress_id:
        raise DraftingWorkingDraftGenerationError(
            "professional authority scope does not bind this progress."
        )

    if task.issue_analysis_id != scope.issue_analysis_id:
        raise DraftingWorkingDraftGenerationError(
            "task issue does not match professional authority scope."
        )

    authority_case_id, authority_id = (
        _authority_identity(
            authority
        )
    )

    if authority_case_id != case_id:
        raise DraftingWorkingDraftGenerationError(
            "current governed authority belongs to another case."
        )

    if scope.authority_id != authority_id:
        raise DraftingWorkingDraftGenerationError(
            "professional authority scope is stale."
        )

    try:
        resolve_task_work_authority_scope(
            scope,
            authority=authority,
        )
    except TaskWorkAuthorityScopeError as exc:
        raise DraftingWorkingDraftGenerationError(
            "professional task-work authority scope "
            "does not resolve against current authority."
        ) from exc

    return (
        case_id,
        authority_id,
    )


def _current_ledger_element(
    *,
    authority: object,
    case_id: str,
    authority_id: str,
    scope: TaskWorkAuthorityScope,
    element_id: str,
) -> LedgerElement:
    selected_element_id = _required_text(
        element_id,
        "element_id",
    )

    if selected_element_id not in scope.element_ids:
        raise DraftingWorkingDraftGenerationError(
            "selected element is outside the explicit professional scope."
        )

    ledger = build_matter_analysis_ledger(
        authority=authority,
        events=(),
    )

    if ledger.case_id != case_id:
        raise DraftingWorkingDraftGenerationError(
            "current matter-analysis ledger belongs to another case."
        )

    if ledger.authority_id != authority_id:
        raise DraftingWorkingDraftGenerationError(
            "current matter-analysis ledger authority is stale."
        )

    issues = tuple(
        issue
        for issue in ledger.issues
        if (
            issue.issue_analysis_id
            == scope.issue_analysis_id
            and issue.issue_definition_id
            == scope.issue_definition_id
        )
    )

    if len(issues) != 1:
        raise DraftingWorkingDraftGenerationError(
            "scoped issue is not unique in current matter-analysis ledger."
        )

    elements = tuple(
        element
        for element in issues[0].elements
        if element.element_id
        == selected_element_id
    )

    if len(elements) != 1:
        raise DraftingWorkingDraftGenerationError(
            "selected governed element is not unique in current ledger."
        )

    return elements[0]


def _validate_original_r68_coverage(
    retrieval_receipt: TaskWorkRetrievalReceipt,
) -> dict[str, Any]:
    payload = (
        retrieval_receipt.evidence_search_receipt
    )

    if not isinstance(
        payload,
        dict,
    ):
        raise DraftingWorkingDraftGenerationError(
            "R68 evidence-search receipt is absent or invalid."
        )

    search_mode = _required_text(
        payload.get("search_mode"),
        "R68 evidence_search_receipt.search_mode",
    )

    completion = _required_text(
        payload.get("completion"),
        "R68 evidence_search_receipt.completion",
    )

    negative_scope = _required_text(
        payload.get(
            "negative_finding_scope"
        ),
        "R68 evidence_search_receipt.negative_finding_scope",
    )

    if negative_scope not in {
        "none",
        "searched_scope",
        "case_corpus",
    }:
        raise DraftingWorkingDraftGenerationError(
            "R68 evidence-search receipt has an unsupported "
            "negative-finding scope."
        )

    counts = {
        key: _nonnegative_int(
            payload.get(key),
            "R68 evidence_search_receipt." + key,
        )
        for key in (
            "scope_document_count",
            "documents_completely_expanded",
            "scope_page_count",
            "pages_inspected",
            "scope_chunk_count",
            "chunks_inspected",
        )
    }

    case_corpus_complete = _required_bool(
        payload.get(
            "case_corpus_complete"
        ),
        "R68 evidence_search_receipt.case_corpus_complete",
    )

    negative_permitted = _required_bool(
        payload.get(
            "negative_finding_permitted"
        ),
        "R68 evidence_search_receipt.negative_finding_permitted",
    )

    if (
        counts["documents_completely_expanded"]
        > counts["scope_document_count"]
    ):
        raise DraftingWorkingDraftGenerationError(
            "R68 evidence-search document coverage is inconsistent."
        )

    if (
        counts["pages_inspected"]
        > counts["scope_page_count"]
    ):
        raise DraftingWorkingDraftGenerationError(
            "R68 evidence-search page coverage is inconsistent."
        )

    if (
        counts["chunks_inspected"]
        > counts["scope_chunk_count"]
    ):
        raise DraftingWorkingDraftGenerationError(
            "R68 evidence-search chunk coverage is inconsistent."
        )

    if (
        negative_scope == "case_corpus"
        and not case_corpus_complete
    ):
        raise DraftingWorkingDraftGenerationError(
            "R68 evidence-search receipt permits a case-corpus "
            "negative scope without case-corpus completeness."
        )

    if (
        negative_permitted
        and negative_scope == "none"
    ):
        raise DraftingWorkingDraftGenerationError(
            "R68 evidence-search receipt permits a negative finding "
            "without a negative-finding scope."
        )

    # Preserve these values as provenance only.  They are deliberately not
    # reused as the coverage receipt for the narrower Drafting intersection.
    return {
        "search_mode": search_mode,
        "completion": completion,
        "negative_finding_scope":
            negative_scope,
        "negative_finding_permitted":
            negative_permitted,
        "case_corpus_complete":
            case_corpus_complete,
        **counts,
    }


def _drafting_coverage_evidence(
    *,
    retrieval_receipt: TaskWorkRetrievalReceipt,
    rows: tuple[DraftingEvidenceRow, ...],
) -> _DraftingEvidence:
    _validate_original_r68_coverage(
        retrieval_receipt
    )

    if not rows:
        raise DraftingWorkingDraftGenerationError(
            "Drafting generation contains no immutable evidence rows."
        )

    document_ids = {
        row.source_document_instance_id
        for row in rows
    }

    page_coordinates = {
        (
            row.source_document_instance_id,
            row.page,
        )
        for row in rows
    }

    # The Drafting call has a narrower evidence boundary than the original
    # R68 search.  It therefore must not inherit original whole-search or
    # case-corpus negative-finding authority.
    receipt = _DraftingCoverageReceipt(
        search_mode=_Value(
            "drafting_exact_intersection"
        ),
        completion=_Value(
            "complete"
        ),
        scope_document_count=
            len(document_ids),
        documents_completely_expanded=0,
        scope_page_count=
            len(page_coordinates),
        pages_inspected=0,
        scope_chunk_count=
            len(rows),
        chunks_inspected=
            len(rows),
        case_corpus_complete=False,
        negative_finding_permitted=False,
        negative_finding_scope=
            _Value("none"),
    )

    return _DraftingEvidence(
        search_result=
            _DraftingSearchResult(
                receipt=receipt,
            )
    )


def build_drafting_candidate_output_schema(
    *,
    element: LedgerElement,
    evidence_keys: tuple[str, ...],
) -> dict[str, Any]:
    if not evidence_keys:
        raise DraftingWorkingDraftGenerationError(
            "candidate output schema requires evidence keys."
        )

    if len(
        evidence_keys
    ) != len(
        set(
            evidence_keys
        )
    ):
        raise DraftingWorkingDraftGenerationError(
            "candidate output schema evidence keys are duplicated."
        )

    element_id = _required_text(
        element.element_id,
        "element.element_id",
    )

    current_status = _enum_text(
        element.analytical_status,
        "element.analytical_status",
    )

    current_confidence = _enum_text(
        element.analytical_confidence,
        "element.analytical_confidence",
    )

    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "statements",
        ],
        "properties": {
            "statements": {
                "type": "array",
                "minItems": 1,
                "maxItems":
                    _MAX_CANDIDATE_STATEMENTS,
                "items": {
                    "type": "object",
                    "additionalProperties":
                        False,
                    "required": [
                        "text",
                        "element_id",
                        "claimed_status",
                        "claimed_confidence",
                        "cited_evidence_keys",
                    ],
                    "properties": {
                        "text": {
                            "type": "string",
                        },
                        "element_id": {
                            "type": "string",
                            "const":
                                element_id,
                        },
                        "claimed_status": {
                            "type": "string",
                            "const":
                                current_status,
                        },
                        "claimed_confidence": {
                            "type": "string",
                            "const":
                                current_confidence,
                        },
                        "cited_evidence_keys": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems":
                                len(
                                    evidence_keys
                                ),
                            "items": {
                                "type":
                                    "string",
                                "enum":
                                    list(
                                        evidence_keys
                                    ),
                            },
                        },
                    },
                },
            },
        },
    }


def _format_collection(
    values: object,
) -> str:
    if values is None:
        return "none"

    if isinstance(
        values,
        str,
    ):
        text = values.strip()
        return text or "none"

    try:
        items = tuple(
            str(value).strip()
            for value in values
            if str(value).strip()
        )
    except TypeError:
        text = str(
            values
        ).strip()

        return (
            text
            if text
            else "none"
        )

    if not items:
        return "none"

    return "\n".join(
        f"- {item}"
        for item in items
    )


def build_drafting_prompt_wrapper(
    *,
    case_id: str,
    authority_id: str,
    scope: TaskWorkAuthorityScope,
    element: LedgerElement,
    evidence_keys: tuple[str, ...],
) -> Callable[..., str]:
    selected_element_id = _required_text(
        element.element_id,
        "element.element_id",
    )

    status = _enum_text(
        element.analytical_status,
        "element.analytical_status",
    )

    confidence = _enum_text(
        element.analytical_confidence,
        "element.analytical_confidence",
    )

    element_name = _required_text(
        element.element_name,
        "element.element_name",
    )

    legal_question = _required_text(
        element.legal_question,
        "element.legal_question",
    )

    provisional_analysis = _required_text(
        element.provisional_analysis,
        "element.provisional_analysis",
    )

    safe_keys = tuple(
        sorted(
            evidence_keys
        )
    )

    safe_key_text = "\n".join(
        f"- {key}"
        for key in safe_keys
    )

    unresolved_text = _format_collection(
        element.unresolved_matters
    )

    gap_text = _format_collection(
        element.evidential_gap_ids
    )

    common = f"""
DRAFTING WORKING-CANDIDATE GOVERNANCE

This call may create UNPERSISTED working-draft candidate text only.
It does not change the Current Assessment, task state, analytical authority,
professional scope, evidence, chronology, report or release state.

EXACT GOVERNED COORDINATES
case_id: {case_id}
authority_id: {authority_id}
issue_analysis_id: {scope.issue_analysis_id}
issue_definition_id: {scope.issue_definition_id}
element_id: {selected_element_id}
element_name: {element_name}

LEGAL QUESTION
{legal_question}

CURRENT GOVERNED POSITION
analytical_status: {status}
analytical_confidence: {confidence}

CURRENT PROVISIONAL ANALYSIS
{provisional_analysis}

UNRESOLVED MATTERS
{unresolved_text}

FORMAL EVIDENTIAL GAPS
{gap_text}

ENTIRE PERMITTED DRAFTING EVIDENCE SET FOR THIS CALL
{safe_key_text}

MANDATORY DRAFTING BOUNDARY
- Work on exactly the selected governed element above.
- The supplied evidence rows are the entire permitted Drafting evidence set
  for this call.
- Do not use, cite or infer from any evidence_key outside that set.
- Do not broaden the answer to another element, issue or the whole case.
- Preserve the current analytical status and confidence exactly.
- Do not convert the provisional analysis into a final legal determination.
- Preserve unresolved matters and formal evidential gaps.
- Include material adverse, conflicting or qualifying evidence where supplied.
- The earlier task-work answer is provenance, not independent evidence.
- No negative finding about evidence absence is authorised from this narrowed
  Drafting evidence set.
""".strip()

    def wrapper(
        *,
        base_prompt: str,
        question: str,
    ) -> str:
        if not isinstance(
            base_prompt,
            str,
        ) or not base_prompt.strip():
            raise DraftingWorkingDraftGenerationError(
                "bounded base prompt is absent."
            )

        _required_text(
            question,
            "question",
        )

        is_map = (
            _MAP_MARKER
            in base_prompt
        )

        is_reduce = (
            _REDUCE_MARKER
            in base_prompt
        )

        if is_map == is_reduce:
            raise DraftingWorkingDraftGenerationError(
                "bounded Drafting prompt phase is ambiguous or unknown."
            )

        if is_map:
            phase_rules = """
DRAFTING MAP-PASS RULES
- Perform source-bound extraction only.
- Preserve exact evidence keys and source coordinates.
- Do not emit the final Drafting JSON object during this map pass.
- Retain the bounded generator's FINDING format for later synthesis.
""".strip()

        else:
            phase_rules = """
DRAFTING FINAL-REDUCE RULES
- Return only the strict JSON object required by the supplied output schema.
- Every statement must bind exactly to the selected element_id.
- Every statement must repeat the current analytical_status and
  analytical_confidence exactly as claimed_status and claimed_confidence.
- Every cited_evidence_key must be one of the permitted evidence keys above.
- Each statement must cite at least one permitted evidence key.
- Do not add Markdown fences, commentary or fields outside the schema.
""".strip()

        return (
            base_prompt.strip()
            + "\n\n"
            + common
            + "\n\n"
            + phase_rules
        )

    return wrapper


def parse_drafting_candidate_output(
    output_text: object,
    *,
    element: LedgerElement,
    evidence_keys: tuple[str, ...],
) -> tuple[
    WorkingDraftStatementInput,
    ...,
]:
    if not isinstance(
        output_text,
        str,
    ) or not output_text.strip():
        raise DraftingWorkingDraftGenerationError(
            "bounded Drafting provider returned no candidate JSON."
        )

    try:
        payload = json.loads(
            output_text
        )
    except json.JSONDecodeError as exc:
        raise DraftingWorkingDraftGenerationError(
            "bounded Drafting provider returned invalid JSON."
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise DraftingWorkingDraftGenerationError(
            "Drafting candidate JSON must be an object."
        )

    if set(
        payload
    ) != {
        "statements",
    }:
        raise DraftingWorkingDraftGenerationError(
            "Drafting candidate JSON contains unexpected top-level fields."
        )

    raw_statements = payload.get(
        "statements"
    )

    if not isinstance(
        raw_statements,
        list,
    ):
        raise DraftingWorkingDraftGenerationError(
            "Drafting candidate statements must be an array."
        )

    if not (
        1
        <= len(
            raw_statements
        )
        <= _MAX_CANDIDATE_STATEMENTS
    ):
        raise DraftingWorkingDraftGenerationError(
            "Drafting candidate statement count is outside the bounded range."
        )

    expected_element_id = _required_text(
        element.element_id,
        "element.element_id",
    )

    expected_status = _enum_text(
        element.analytical_status,
        "element.analytical_status",
    )

    expected_confidence = _enum_text(
        element.analytical_confidence,
        "element.analytical_confidence",
    )

    permitted_keys = set(
        evidence_keys
    )

    statements = []
    seen_text = set()

    required_fields = {
        "text",
        "element_id",
        "claimed_status",
        "claimed_confidence",
        "cited_evidence_keys",
    }

    for index, raw in enumerate(
        raw_statements,
        start=1,
    ):
        if not isinstance(
            raw,
            dict,
        ):
            raise DraftingWorkingDraftGenerationError(
                f"Drafting candidate statement {index} is not an object."
            )

        if set(
            raw
        ) != required_fields:
            raise DraftingWorkingDraftGenerationError(
                f"Drafting candidate statement {index} "
                "contains unexpected or missing fields."
            )

        text = _required_text(
            raw.get("text"),
            f"statement[{index}].text",
        )

        if len(
            text
        ) > _MAX_CANDIDATE_STATEMENT_TEXT_LENGTH:
            raise DraftingWorkingDraftGenerationError(
                f"Drafting candidate statement {index} "
                "text exceeds the bounded length."
            )

        if text in seen_text:
            raise DraftingWorkingDraftGenerationError(
                "Drafting candidate contains duplicate statement text."
            )

        seen_text.add(
            text
        )

        if (
            raw.get(
                "element_id"
            )
            != expected_element_id
        ):
            raise DraftingWorkingDraftGenerationError(
                f"Drafting candidate statement {index} "
                "binds another governed element."
            )

        if (
            raw.get(
                "claimed_status"
            )
            != expected_status
        ):
            raise DraftingWorkingDraftGenerationError(
                f"Drafting candidate statement {index} "
                "changes the current analytical status."
            )

        if (
            raw.get(
                "claimed_confidence"
            )
            != expected_confidence
        ):
            raise DraftingWorkingDraftGenerationError(
                f"Drafting candidate statement {index} "
                "changes the current analytical confidence."
            )

        cited = raw.get(
            "cited_evidence_keys"
        )

        if not isinstance(
            cited,
            list,
        ) or not cited:
            raise DraftingWorkingDraftGenerationError(
                f"Drafting candidate statement {index} "
                "must cite at least one evidence key."
            )

        if not all(
            isinstance(
                key,
                str,
            )
            and key
            for key in cited
        ):
            raise DraftingWorkingDraftGenerationError(
                f"Drafting candidate statement {index} "
                "contains an invalid evidence key."
            )

        if len(
            cited
        ) != len(
            set(
                cited
            )
        ):
            raise DraftingWorkingDraftGenerationError(
                f"Drafting candidate statement {index} "
                "contains duplicate evidence citations."
            )

        cited_set = set(
            cited
        )

        if not cited_set.issubset(
            permitted_keys
        ):
            raise DraftingWorkingDraftGenerationError(
                f"Drafting candidate statement {index} "
                "cites evidence outside the permitted Drafting set."
            )

        statements.append(
            WorkingDraftStatementInput(
                text=text,
                element_id=
                    expected_element_id,
                claimed_status=
                    expected_status,
                claimed_confidence=
                    expected_confidence,
                cited_evidence_keys=
                    tuple(
                        sorted(
                            cited_set
                        )
                    ),
            )
        )

    return tuple(
        statements
    )


def _generation_question(
    *,
    task: SolicitorTask,
    element: LedgerElement,
) -> str:
    return (
        "Prepare bounded working-draft candidate statement(s) for "
        f"the legal task {task.title!r}, restricted to the governed "
        f"element {element.element_name!r}. Address only this legal "
        f"question: {element.legal_question}"
    )


def generate_working_draft_candidate(
    *,
    client: Any,
    model: str,
    task: SolicitorTask,
    progress: TaskWorkProgress,
    retrieval_receipt: TaskWorkRetrievalReceipt,
    scope: TaskWorkAuthorityScope,
    authority: object,
    element_id: str,
    reasoning_effort: str | None = None,
    store: Any = None,
) -> WorkingDraftGenerationCandidate:
    """Generate one bounded candidate without persisting or approving it."""

    case_id, authority_id = (
        _validate_chain(
            task=task,
            progress=progress,
            retrieval_receipt=
                retrieval_receipt,
            scope=scope,
            authority=authority,
        )
    )

    element = _current_ledger_element(
        authority=authority,
        case_id=case_id,
        authority_id=authority_id,
        scope=scope,
        element_id=element_id,
    )

    try:
        (
            evidence_keys,
            rows,
            enriched_results,
        ) = reconstruct_bounded_generation_evidence(
            case_id=case_id,
            retrieval_receipt=
                retrieval_receipt,
            element=element,
            store=store,
        )
    except DraftingEvidenceSourceError as exc:
        raise DraftingWorkingDraftGenerationError(
            "exact immutable Drafting evidence could not be reconstructed."
        ) from exc

    evidence_keys = tuple(
        sorted(
            evidence_keys
        )
    )

    if not evidence_keys:
        raise DraftingWorkingDraftGenerationError(
            "Drafting evidence intersection is empty."
        )

    if (
        tuple(
            row.evidence_key
            for row in rows
        )
        != evidence_keys
    ):
        raise DraftingWorkingDraftGenerationError(
            "immutable Drafting source rows do not match the permitted evidence set."
        )

    bounded_evidence = (
        _drafting_coverage_evidence(
            retrieval_receipt=
                retrieval_receipt,
            rows=rows,
        )
    )

    question = _generation_question(
        task=task,
        element=element,
    )

    output_schema = (
        build_drafting_candidate_output_schema(
            element=element,
            evidence_keys=
                evidence_keys,
        )
    )

    prompt_wrapper = (
        build_drafting_prompt_wrapper(
            case_id=case_id,
            authority_id=
                authority_id,
            scope=scope,
            element=element,
            evidence_keys=
                evidence_keys,
        )
    )

    try:
        response = (
            create_bounded_governed_response(
                client=client,
                model=_required_text(
                    model,
                    "model",
                ),
                question=question,
                evidence=
                    bounded_evidence,
                enriched_results=
                    enriched_results,
                analytical_context=None,
                constrain_prompt=None,
                prompt_wrapper=
                    prompt_wrapper,
                reasoning_effort=
                    reasoning_effort,
                output_schema=
                    output_schema,
            )
        )
    except Exception as exc:
        if isinstance(
            exc,
            DraftingWorkingDraftGenerationError,
        ):
            raise

        raise DraftingWorkingDraftGenerationError(
            "bounded Drafting provider execution failed."
        ) from exc

    statements = (
        parse_drafting_candidate_output(
            getattr(
                response,
                "output_text",
                None,
            ),
            element=element,
            evidence_keys=
                evidence_keys,
        )
    )

    return WorkingDraftGenerationCandidate(
        case_id=case_id,
        task_id=task.task_id,
        progress_id=
            progress.progress_id,
        scope_binding_id=
            scope.binding_id,
        authority_id=
            authority_id,
        issue_analysis_id=
            scope.issue_analysis_id,
        issue_definition_id=
            scope.issue_definition_id,
        element_id=
            element.element_id,
        evidence_keys=
            evidence_keys,
        statements=
            statements,
    )


__all__ = [
    "DraftingWorkingDraftGenerationError",
    "WorkingDraftGenerationCandidate",
    "build_drafting_candidate_output_schema",
    "build_drafting_prompt_wrapper",
    "parse_drafting_candidate_output",
    "generate_working_draft_candidate",
]