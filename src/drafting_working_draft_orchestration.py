"""Two-step orchestration for governed LegalRAG WORKING drafts.

Preparation is pure:
    generated candidate
    -> exact source/scope/current-authority bridge validation
    -> build_working_draft
    -> per-statement authority evaluation
    -> PreparedWorkingDraft

Recording is separate and explicit:
    PreparedWorkingDraft
    -> fresh source-chain build
    -> fresh current-authority evaluation
    -> record_working_draft

Authority evaluation is not release approval and no aggregate release state
is created here.  A recorded object remains a WORKING draft.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from drafting_evidence_source_adapter import (
    DraftingEvidenceSourceError,
    generation_evidence_keys,
)
from drafting_working_draft import (
    DraftingWorkingDraftError,
    WorkingDraft,
    WorkingDraftStatementInput,
    build_working_draft,
    record_working_draft,
)
from drafting_working_draft_authority import (
    DraftingWorkingDraftAuthorityError,
    WorkingDraftAuthorityEvaluation,
    evaluate_working_draft_authority,
)
from drafting_working_draft_generation import (
    WorkingDraftGenerationCandidate,
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


class DraftingWorkingDraftOrchestrationError(RuntimeError):
    """The generated-candidate to WORKING-draft bridge failed closed."""


@dataclass(frozen=True)
class PreparedWorkingDraft:
    """Pure, unrecorded draft plus its per-statement authority evaluation."""

    candidate: WorkingDraftGenerationCandidate
    draft: WorkingDraft
    authority_evaluation: WorkingDraftAuthorityEvaluation


@dataclass(frozen=True)
class RecordedWorkingDraft:
    """Explicitly persisted WORKING draft plus fresh authority evaluation."""

    draft: WorkingDraft
    authority_evaluation: WorkingDraftAuthorityEvaluation


def _required(
    value: object,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DraftingWorkingDraftOrchestrationError(
            f"{field_name} is required."
        )

    return value.strip()


def _authority_identity(
    authority: object,
) -> tuple[str, str]:
    manifest = getattr(
        authority,
        "manifest",
        None,
    )

    if manifest is None:
        raise DraftingWorkingDraftOrchestrationError(
            "current governed authority has no manifest."
        )

    return (
        _required(
            getattr(
                manifest,
                "case_id",
                None,
            ),
            "authority.manifest.case_id",
        ),
        _required(
            getattr(
                manifest,
                "authority_id",
                None,
            ),
            "authority.manifest.authority_id",
        ),
    )


def _validate_candidate_bridge(
    *,
    candidate: WorkingDraftGenerationCandidate,
    task: SolicitorTask,
    progress: TaskWorkProgress,
    retrieval_receipt: TaskWorkRetrievalReceipt,
    scope: TaskWorkAuthorityScope,
    authority: object,
) -> object:
    if not isinstance(
        candidate,
        WorkingDraftGenerationCandidate,
    ):
        raise DraftingWorkingDraftOrchestrationError(
            "candidate must be a WorkingDraftGenerationCandidate."
        )

    if not isinstance(
        task,
        SolicitorTask,
    ):
        raise DraftingWorkingDraftOrchestrationError(
            "task must be a SolicitorTask."
        )

    if not isinstance(
        progress,
        TaskWorkProgress,
    ):
        raise DraftingWorkingDraftOrchestrationError(
            "progress must be a TaskWorkProgress."
        )

    if not isinstance(
        retrieval_receipt,
        TaskWorkRetrievalReceipt,
    ):
        raise DraftingWorkingDraftOrchestrationError(
            "retrieval_receipt must be a TaskWorkRetrievalReceipt."
        )

    if not isinstance(
        scope,
        TaskWorkAuthorityScope,
    ):
        raise DraftingWorkingDraftOrchestrationError(
            "scope must be a TaskWorkAuthorityScope."
        )

    case_id = _required(
        task.case_id,
        "task.case_id",
    )

    task_id = _required(
        task.task_id,
        "task.task_id",
    )

    progress_id = _required(
        progress.progress_id,
        "progress.progress_id",
    )

    if candidate.case_id != case_id:
        raise DraftingWorkingDraftOrchestrationError(
            "generation candidate belongs to another case."
        )

    if candidate.task_id != task_id:
        raise DraftingWorkingDraftOrchestrationError(
            "generation candidate belongs to another task."
        )

    if candidate.progress_id != progress_id:
        raise DraftingWorkingDraftOrchestrationError(
            "generation candidate belongs to another task-work progress record."
        )

    if progress.case_id != case_id:
        raise DraftingWorkingDraftOrchestrationError(
            "task-work progress belongs to another case."
        )

    if progress.task_id != task_id:
        raise DraftingWorkingDraftOrchestrationError(
            "task-work progress belongs to another task."
        )

    if retrieval_receipt.case_id != case_id:
        raise DraftingWorkingDraftOrchestrationError(
            "R68 receipt belongs to another case."
        )

    if retrieval_receipt.task_id != task_id:
        raise DraftingWorkingDraftOrchestrationError(
            "R68 receipt belongs to another task."
        )

    if retrieval_receipt.progress_id != progress_id:
        raise DraftingWorkingDraftOrchestrationError(
            "R68 receipt belongs to another task-work progress record."
        )

    if scope.case_id != case_id:
        raise DraftingWorkingDraftOrchestrationError(
            "professional scope belongs to another case."
        )

    if scope.task_id != task_id:
        raise DraftingWorkingDraftOrchestrationError(
            "professional scope belongs to another task."
        )

    if scope.progress_id != progress_id:
        raise DraftingWorkingDraftOrchestrationError(
            "professional scope belongs to another task-work progress record."
        )

    if candidate.scope_binding_id != scope.binding_id:
        raise DraftingWorkingDraftOrchestrationError(
            "generation candidate does not bind the supplied professional scope."
        )

    if candidate.issue_analysis_id != scope.issue_analysis_id:
        raise DraftingWorkingDraftOrchestrationError(
            "generation candidate issue does not match professional scope."
        )

    if candidate.issue_definition_id != scope.issue_definition_id:
        raise DraftingWorkingDraftOrchestrationError(
            "generation candidate issue definition does not match professional scope."
        )

    if task.issue_analysis_id != scope.issue_analysis_id:
        raise DraftingWorkingDraftOrchestrationError(
            "task issue does not match professional scope."
        )

    authority_case_id, authority_id = (
        _authority_identity(
            authority
        )
    )

    if authority_case_id != case_id:
        raise DraftingWorkingDraftOrchestrationError(
            "current governed authority belongs to another case."
        )

    if scope.authority_id != authority_id:
        raise DraftingWorkingDraftOrchestrationError(
            "professional scope is stale against current authority."
        )

    if candidate.authority_id != authority_id:
        raise DraftingWorkingDraftOrchestrationError(
            "generation candidate is stale against current authority."
        )

    try:
        resolution = (
            resolve_task_work_authority_scope(
                scope,
                authority=authority,
            )
        )
    except TaskWorkAuthorityScopeError as exc:
        raise DraftingWorkingDraftOrchestrationError(
            "professional scope does not resolve against current authority."
        ) from exc

    selected = tuple(
        element
        for element in resolution.elements
        if getattr(
            element,
            "element_id",
            None,
        )
        == candidate.element_id
    )

    if len(selected) != 1:
        raise DraftingWorkingDraftOrchestrationError(
            "generation candidate element is not uniquely present "
            "in the resolved professional scope."
        )

    element = selected[0]

    try:
        expected_evidence_keys = (
            generation_evidence_keys(
                retrieval_receipt=
                    retrieval_receipt,
                element=element,
            )
        )
    except DraftingEvidenceSourceError as exc:
        raise DraftingWorkingDraftOrchestrationError(
            "generation evidence boundary cannot be reconstructed."
        ) from exc

    if (
        tuple(candidate.evidence_keys)
        != tuple(expected_evidence_keys)
    ):
        raise DraftingWorkingDraftOrchestrationError(
            "generation candidate evidence boundary does not match "
            "the current R68-by-element safe set."
        )

    if not candidate.statements:
        raise DraftingWorkingDraftOrchestrationError(
            "generation candidate contains no statements."
        )

    permitted_keys = set(
        expected_evidence_keys
    )

    for index, statement in enumerate(
        candidate.statements,
        start=1,
    ):
        if not isinstance(
            statement,
            WorkingDraftStatementInput,
        ):
            raise DraftingWorkingDraftOrchestrationError(
                f"candidate statement {index} has an invalid type."
            )

        if statement.element_id != candidate.element_id:
            raise DraftingWorkingDraftOrchestrationError(
                f"candidate statement {index} binds another governed element."
            )

        cited = tuple(
            statement.cited_evidence_keys
        )

        if not cited:
            raise DraftingWorkingDraftOrchestrationError(
                f"candidate statement {index} contains no evidence citation."
            )

        if len(cited) != len(set(cited)):
            raise DraftingWorkingDraftOrchestrationError(
                f"candidate statement {index} contains duplicate evidence citations."
            )

        if not set(cited).issubset(
            permitted_keys
        ):
            raise DraftingWorkingDraftOrchestrationError(
                f"candidate statement {index} cites evidence outside "
                "the current safe set."
            )

    return element


def _validate_built_draft(
    *,
    candidate: WorkingDraftGenerationCandidate,
    draft: object,
) -> None:
    exact_fields = (
        (
            "case_id",
            candidate.case_id,
        ),
        (
            "task_id",
            candidate.task_id,
        ),
        (
            "progress_id",
            candidate.progress_id,
        ),
        (
            "scope_binding_id",
            candidate.scope_binding_id,
        ),
        (
            "authority_id",
            candidate.authority_id,
        ),
        (
            "issue_analysis_id",
            candidate.issue_analysis_id,
        ),
        (
            "issue_definition_id",
            candidate.issue_definition_id,
        ),
    )

    for field_name, expected in exact_fields:
        actual = getattr(
            draft,
            field_name,
            None,
        )

        if actual != expected:
            raise DraftingWorkingDraftOrchestrationError(
                "built working draft does not preserve candidate "
                + field_name
                + "."
            )

    draft_statements = tuple(
        getattr(
            draft,
            "statements",
            (),
        )
    )

    if len(draft_statements) != len(candidate.statements):
        raise DraftingWorkingDraftOrchestrationError(
            "built working draft statement count differs from candidate."
        )

    for generated, built in zip(
        candidate.statements,
        draft_statements,
        strict=True,
    ):
        if built.text != generated.text:
            raise DraftingWorkingDraftOrchestrationError(
                "built working draft changed generated statement text."
            )

        if built.element_id != generated.element_id:
            raise DraftingWorkingDraftOrchestrationError(
                "built working draft changed generated statement element."
            )

        if built.claimed_status != generated.claimed_status:
            raise DraftingWorkingDraftOrchestrationError(
                "built working draft changed generated claimed status."
            )

        if built.claimed_confidence != generated.claimed_confidence:
            raise DraftingWorkingDraftOrchestrationError(
                "built working draft changed generated claimed confidence."
            )

        if tuple(
            built.cited_evidence_keys
        ) != tuple(
            sorted(
                generated.cited_evidence_keys
            )
        ):
            raise DraftingWorkingDraftOrchestrationError(
                "built working draft changed generated evidence citations."
            )


def _validate_evaluation(
    *,
    draft: object,
    evaluation: object,
) -> None:
    if (
        getattr(
            evaluation,
            "draft_id",
            None,
        )
        != getattr(
            draft,
            "draft_id",
            None,
        )
    ):
        raise DraftingWorkingDraftOrchestrationError(
            "authority evaluation does not bind the exact working draft."
        )

    for field_name in (
        "case_id",
        "authority_id",
        "issue_analysis_id",
    ):
        if (
            getattr(
                evaluation,
                field_name,
                None,
            )
            != getattr(
                draft,
                field_name,
                None,
            )
        ):
            raise DraftingWorkingDraftOrchestrationError(
                "authority evaluation does not preserve draft "
                + field_name
                + "."
            )

    statement_evaluations = tuple(
        getattr(
            evaluation,
            "statement_evaluations",
            (),
        )
    )

    draft_statements = tuple(
        getattr(
            draft,
            "statements",
            (),
        )
    )

    if len(statement_evaluations) != len(draft_statements):
        raise DraftingWorkingDraftOrchestrationError(
            "authority evaluation does not cover every draft statement."
        )


def prepare_generated_working_draft(
    *,
    candidate: WorkingDraftGenerationCandidate,
    task: SolicitorTask,
    progress: TaskWorkProgress,
    retrieval_receipt: TaskWorkRetrievalReceipt,
    scope: TaskWorkAuthorityScope,
    authority: object,
    title: str,
    purpose: str,
    creator_reference: str,
) -> PreparedWorkingDraft:
    """Pure preparation gate; never writes a working draft."""

    _validate_candidate_bridge(
        candidate=candidate,
        task=task,
        progress=progress,
        retrieval_receipt=
            retrieval_receipt,
        scope=scope,
        authority=authority,
    )

    try:
        draft = build_working_draft(
            task=task,
            progress=progress,
            retrieval_receipt=
                retrieval_receipt,
            scope=scope,
            authority=authority,
            title=title,
            purpose=purpose,
            statements=
                candidate.statements,
            creator_reference=
                creator_reference,
        )
    except DraftingWorkingDraftError as exc:
        raise DraftingWorkingDraftOrchestrationError(
            "generated candidate could not be built as a WORKING draft."
        ) from exc

    _validate_built_draft(
        candidate=candidate,
        draft=draft,
    )

    try:
        evaluation = (
            evaluate_working_draft_authority(
                draft=draft,
                authority=authority,
            )
        )
    except DraftingWorkingDraftAuthorityError as exc:
        raise DraftingWorkingDraftOrchestrationError(
            "WORKING draft authority evaluation failed."
        ) from exc

    _validate_evaluation(
        draft=draft,
        evaluation=evaluation,
    )

    return PreparedWorkingDraft(
        candidate=candidate,
        draft=draft,
        authority_evaluation=
            evaluation,
    )


def record_prepared_working_draft(
    *,
    prepared: PreparedWorkingDraft,
    task: SolicitorTask,
    progress: TaskWorkProgress,
    retrieval_receipt: TaskWorkRetrievalReceipt,
    scope: TaskWorkAuthorityScope,
    authority: object,
    root: Any = None,
) -> RecordedWorkingDraft:
    """Explicitly persist one prepared WORKING draft after fresh validation.

    This function does not approve the draft for reliance.  Per-statement
    ALIGNED / CAUTION / NOT_AUTHORIZED results remain authority-check results,
    not an aggregate release decision.
    """

    if not isinstance(
        prepared,
        PreparedWorkingDraft,
    ):
        raise DraftingWorkingDraftOrchestrationError(
            "prepared must be a PreparedWorkingDraft."
        )

    candidate = prepared.candidate

    _validate_candidate_bridge(
        candidate=candidate,
        task=task,
        progress=progress,
        retrieval_receipt=
            retrieval_receipt,
        scope=scope,
        authority=authority,
    )

    # Rebuild immediately before persistence so the full released source-chain
    # validation is repeated against the current supplied authority.
    try:
        fresh_draft = build_working_draft(
            task=task,
            progress=progress,
            retrieval_receipt=
                retrieval_receipt,
            scope=scope,
            authority=authority,
            title=prepared.draft.title,
            purpose=prepared.draft.purpose,
            statements=
                candidate.statements,
            creator_reference=
                prepared.draft.creator_reference,
        )
    except DraftingWorkingDraftError as exc:
        raise DraftingWorkingDraftOrchestrationError(
            "prepared WORKING draft no longer satisfies its source chain."
        ) from exc

    _validate_built_draft(
        candidate=candidate,
        draft=fresh_draft,
    )

    if (
        fresh_draft.draft_id
        != prepared.draft.draft_id
    ):
        raise DraftingWorkingDraftOrchestrationError(
            "fresh WORKING draft identity differs from the prepared draft."
        )

    # Fresh authority evaluation occurs immediately before the append.
    try:
        fresh_evaluation = (
            evaluate_working_draft_authority(
                draft=fresh_draft,
                authority=authority,
            )
        )
    except DraftingWorkingDraftAuthorityError as exc:
        raise DraftingWorkingDraftOrchestrationError(
            "prepared WORKING draft no longer passes current authority evaluation."
        ) from exc

    _validate_evaluation(
        draft=fresh_draft,
        evaluation=fresh_evaluation,
    )

    # No aggregate authority result is manufactured or used as release state.
    # Invocation of this function is the explicit WORKING-draft save action.
    try:
        recorded = record_working_draft(
            task=task,
            progress=progress,
            retrieval_receipt=
                retrieval_receipt,
            scope=scope,
            authority=authority,
            title=fresh_draft.title,
            purpose=fresh_draft.purpose,
            statements=
                candidate.statements,
            creator_reference=
                fresh_draft.creator_reference,
            recorded_at=
                fresh_draft.recorded_at,
            root=root,
        )
    except DraftingWorkingDraftError as exc:
        raise DraftingWorkingDraftOrchestrationError(
            "explicit WORKING-draft persistence failed."
        ) from exc

    _validate_built_draft(
        candidate=candidate,
        draft=recorded,
    )

    if recorded.draft_id != fresh_draft.draft_id:
        raise DraftingWorkingDraftOrchestrationError(
            "recorded WORKING draft identity differs from validated draft."
        )

    if recorded.recorded_at != fresh_draft.recorded_at:
        raise DraftingWorkingDraftOrchestrationError(
            "recorded WORKING draft timestamp differs from validated append."
        )

    return RecordedWorkingDraft(
        draft=recorded,
        authority_evaluation=
            fresh_evaluation,
    )


__all__ = [
    "DraftingWorkingDraftOrchestrationError",
    "PreparedWorkingDraft",
    "RecordedWorkingDraft",
    "prepare_generated_working_draft",
    "record_prepared_working_draft",
]