"""Immutable governed WORKING drafts derived from scoped Case Operator work.

This module creates no release state. A working draft remains distinct from
the existing report-bound professional work-product release state machine.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable
from uuid import UUID

from task_work_authority_scope import (
    TaskWorkAuthorityScopeError,
    resolve_task_work_authority_scope,
)


WORKING_DRAFT_SCHEMA_VERSION = "drafting-working-draft/1.0"

_DEFAULT_ROOT = (
    Path("solicitor_tasks")
    / "working_drafts"
)

_SHA256_ID_RE = re.compile(
    r"^sha256:[0-9a-f]{64}$"
)

_SHA256_HEX_RE = re.compile(
    r"^[0-9a-f]{64}$"
)


class DraftingWorkingDraftError(ValueError):
    """Raised when governed working-draft integrity cannot be established."""


@dataclass(frozen=True)
class WorkingDraftStatementInput:
    """One proposed statement before deterministic working-draft identity."""

    text: str
    element_id: str
    claimed_status: str
    claimed_confidence: str
    cited_evidence_keys: tuple[str, ...]


@dataclass(frozen=True)
class WorkingDraftStatement:
    """One immutable statement bound to exactly one governed element."""

    statement_id: str
    sequence: int
    text: str
    element_id: str
    claimed_status: str
    claimed_confidence: str
    cited_evidence_keys: tuple[str, ...]


@dataclass(frozen=True)
class WorkingDraft:
    """One immutable WORKING draft. This object is never a release decision."""

    schema_version: str
    draft_id: str
    case_id: str
    task_id: str
    progress_id: str
    task_work_recorded_at: str
    task_work_question_sha256: str
    task_work_answer_sha256: str
    scope_binding_id: str
    authority_id: str
    issue_analysis_id: str
    issue_definition_id: str
    title: str
    purpose: str
    statements: tuple[WorkingDraftStatement, ...]
    creator_reference: str
    recorded_at: str


def _required(
    value: object,
    label: str,
) -> str:
    text = str(value).strip()

    if not text:
        raise DraftingWorkingDraftError(
            label + " is required."
        )

    return text


def _canonical_uuid(
    value: object,
    label: str,
) -> str:
    text = _required(
        value,
        label,
    )

    try:
        parsed = UUID(text)
    except ValueError as exc:
        raise DraftingWorkingDraftError(
            label + " must be a UUID."
        ) from exc

    canonical = str(parsed)

    if text.lower() != canonical:
        raise DraftingWorkingDraftError(
            label + " must use canonical UUID form."
        )

    return canonical


def _sha256_id(
    value: object,
    label: str,
) -> str:
    text = _required(
        value,
        label,
    ).lower()

    if not _SHA256_ID_RE.fullmatch(text):
        raise DraftingWorkingDraftError(
            label + " must be a sha256: identifier."
        )

    return text


def _sha256_hex_value(
    value: object,
    label: str,
) -> str:
    text = _required(
        value,
        label,
    ).lower()

    if text.startswith("sha256:"):
        text = text[7:]

    if not _SHA256_HEX_RE.fullmatch(text):
        raise DraftingWorkingDraftError(
            label + " must contain one SHA256 digest."
        )

    return text


def _text_sha256(
    value: str,
) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def _canonical_timestamp(
    value: object,
    label: str,
) -> str:
    text = _required(
        value,
        label,
    )

    candidate = (
        text[:-1] + "+00:00"
        if text.endswith("Z")
        else text
    )

    try:
        parsed = datetime.fromisoformat(
            candidate
        )
    except ValueError as exc:
        raise DraftingWorkingDraftError(
            label + " must be an ISO-8601 timestamp."
        ) from exc

    if parsed.tzinfo is None:
        raise DraftingWorkingDraftError(
            label + " must include a timezone."
        )

    return text


def _now_utc() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(
            timespec="microseconds"
        )
        .replace(
            "+00:00",
            "Z",
        )
    )


def _canonical_evidence_keys(
    values: Iterable[object],
) -> tuple[str, ...]:
    keys = tuple(
        _required(
            value,
            "cited evidence key",
        )
        for value in values
    )

    if len(keys) != len(set(keys)):
        raise DraftingWorkingDraftError(
            "cited evidence keys must be unique."
        )

    return tuple(
        sorted(keys)
    )


def _canonical_json(
    value: object,
) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _derive_sha256_id(
    payload: object,
) -> str:
    digest = hashlib.sha256(
        _canonical_json(
            payload
        ).encode("utf-8")
    ).hexdigest()

    return "sha256:" + digest


def _identity_value(
    value: object,
    attribute: str,
    label: str,
) -> str:
    try:
        raw = getattr(
            value,
            attribute,
        )
    except AttributeError as exc:
        raise DraftingWorkingDraftError(
            label + " does not expose " + attribute + "."
        ) from exc

    return _required(
        raw,
        label + "." + attribute,
    )


def _validate_source_chain(
    *,
    task: object,
    progress: object,
    retrieval_receipt: object,
    scope: object,
    authority: object,
) -> tuple[
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    str,
]:
    case_id = _canonical_uuid(
        _identity_value(
            task,
            "case_id",
            "task",
        ),
        "case_id",
    )

    task_id = _canonical_uuid(
        _identity_value(
            task,
            "task_id",
            "task",
        ),
        "task_id",
    )

    progress_case_id = _canonical_uuid(
        _identity_value(
            progress,
            "case_id",
            "progress",
        ),
        "progress.case_id",
    )

    progress_task_id = _canonical_uuid(
        _identity_value(
            progress,
            "task_id",
            "progress",
        ),
        "progress.task_id",
    )

    progress_id = _canonical_uuid(
        _identity_value(
            progress,
            "progress_id",
            "progress",
        ),
        "progress_id",
    )

    if progress_case_id != case_id:
        raise DraftingWorkingDraftError(
            "task-work progress belongs to another case."
        )

    if progress_task_id != task_id:
        raise DraftingWorkingDraftError(
            "task-work progress belongs to another task."
        )

    receipt_case_id = _canonical_uuid(
        _identity_value(
            retrieval_receipt,
            "case_id",
            "retrieval receipt",
        ),
        "retrieval_receipt.case_id",
    )

    receipt_task_id = _canonical_uuid(
        _identity_value(
            retrieval_receipt,
            "task_id",
            "retrieval receipt",
        ),
        "retrieval_receipt.task_id",
    )

    receipt_progress_id = _canonical_uuid(
        _identity_value(
            retrieval_receipt,
            "progress_id",
            "retrieval receipt",
        ),
        "retrieval_receipt.progress_id",
    )

    if (
        receipt_case_id != case_id
        or receipt_task_id != task_id
        or receipt_progress_id != progress_id
    ):
        raise DraftingWorkingDraftError(
            "R68 retrieval receipt does not match the task-work record."
        )

    scope_case_id = _canonical_uuid(
        _identity_value(
            scope,
            "case_id",
            "authority scope",
        ),
        "scope.case_id",
    )

    scope_task_id = _canonical_uuid(
        _identity_value(
            scope,
            "task_id",
            "authority scope",
        ),
        "scope.task_id",
    )

    scope_progress_id = _canonical_uuid(
        _identity_value(
            scope,
            "progress_id",
            "authority scope",
        ),
        "scope.progress_id",
    )

    if (
        scope_case_id != case_id
        or scope_task_id != task_id
        or scope_progress_id != progress_id
    ):
        raise DraftingWorkingDraftError(
            "D1-I1 authority scope does not match the task-work record."
        )

    task_issue_id = _canonical_uuid(
        _identity_value(
            task,
            "issue_analysis_id",
            "task",
        ),
        "task.issue_analysis_id",
    )

    scope_issue_id = _canonical_uuid(
        _identity_value(
            scope,
            "issue_analysis_id",
            "authority scope",
        ),
        "scope.issue_analysis_id",
    )

    if task_issue_id != scope_issue_id:
        raise DraftingWorkingDraftError(
            "task issue does not match the D1-I1 authority scope."
        )

    scope_binding_id = _sha256_id(
        _identity_value(
            scope,
            "binding_id",
            "authority scope",
        ),
        "scope.binding_id",
    )

    authority_id = _sha256_id(
        _identity_value(
            scope,
            "authority_id",
            "authority scope",
        ),
        "scope.authority_id",
    )

    try:
        manifest = authority.manifest
    except AttributeError as exc:
        raise DraftingWorkingDraftError(
            "current authority does not expose a manifest."
        ) from exc

    current_case_id = _canonical_uuid(
        getattr(
            manifest,
            "case_id",
            "",
        ),
        "authority.manifest.case_id",
    )

    current_authority_id = _sha256_id(
        getattr(
            manifest,
            "authority_id",
            "",
        ),
        "authority.manifest.authority_id",
    )

    if current_case_id != case_id:
        raise DraftingWorkingDraftError(
            "current governed authority belongs to another case."
        )

    if current_authority_id != authority_id:
        raise DraftingWorkingDraftError(
            "working draft cannot use a stale D1-I1 authority scope."
        )

    progress_recorded_at = _canonical_timestamp(
        _identity_value(
            progress,
            "recorded_at",
            "progress",
        ),
        "progress.recorded_at",
    )

    receipt_recorded_at = _canonical_timestamp(
        _identity_value(
            retrieval_receipt,
            "task_work_recorded_at",
            "retrieval receipt",
        ),
        "retrieval_receipt.task_work_recorded_at",
    )

    if progress_recorded_at != receipt_recorded_at:
        raise DraftingWorkingDraftError(
            "R68 receipt timestamp does not match task-work progress."
        )

    question = _required(
        _identity_value(
            progress,
            "question",
            "progress",
        ),
        "progress.question",
    )

    answer = _required(
        _identity_value(
            progress,
            "answer",
            "progress",
        ),
        "progress.answer",
    )

    question_sha256 = _text_sha256(
        question
    )

    answer_sha256 = _text_sha256(
        answer
    )

    receipt_question_sha256 = _sha256_hex_value(
        _identity_value(
            retrieval_receipt,
            "question_sha256",
            "retrieval receipt",
        ),
        "retrieval_receipt.question_sha256",
    )

    receipt_answer_sha256 = _sha256_hex_value(
        _identity_value(
            retrieval_receipt,
            "answer_sha256",
            "retrieval receipt",
        ),
        "retrieval_receipt.answer_sha256",
    )

    if receipt_question_sha256 != question_sha256:
        raise DraftingWorkingDraftError(
            "R68 question hash does not match task-work progress."
        )

    if receipt_answer_sha256 != answer_sha256:
        raise DraftingWorkingDraftError(
            "R68 answer hash does not match task-work progress."
        )

    try:
        resolve_task_work_authority_scope(
            scope,
            authority=authority,
        )
    except TaskWorkAuthorityScopeError as exc:
        raise DraftingWorkingDraftError(
            "D1-I1 authority scope is not current: "
            + str(exc)
        ) from exc

    issue_definition_id = _required(
        _identity_value(
            scope,
            "issue_definition_id",
            "authority scope",
        ),
        "scope.issue_definition_id",
    )

    return (
        case_id,
        task_id,
        progress_id,
        progress_recorded_at,
        question_sha256,
        answer_sha256,
        scope_binding_id,
        issue_definition_id,
    )


def build_working_draft(
    *,
    task: object,
    progress: object,
    retrieval_receipt: object,
    scope: object,
    authority: object,
    title: str,
    purpose: str,
    statements: Iterable[WorkingDraftStatementInput],
    creator_reference: str,
    recorded_at: str | None = None,
) -> WorkingDraft:
    """Build one immutable WORKING draft from an exact governed source chain."""

    (
        case_id,
        task_id,
        progress_id,
        task_work_recorded_at,
        question_sha256,
        answer_sha256,
        scope_binding_id,
        issue_definition_id,
    ) = _validate_source_chain(
        task=task,
        progress=progress,
        retrieval_receipt=retrieval_receipt,
        scope=scope,
        authority=authority,
    )

    authority_id = _sha256_id(
        getattr(
            scope,
            "authority_id",
            "",
        ),
        "scope.authority_id",
    )

    issue_analysis_id = _canonical_uuid(
        getattr(
            scope,
            "issue_analysis_id",
            "",
        ),
        "scope.issue_analysis_id",
    )

    scoped_element_ids = tuple(
        _required(
            value,
            "scope.element_id",
        )
        for value in getattr(
            scope,
            "element_ids",
            (),
        )
    )

    if not scoped_element_ids:
        raise DraftingWorkingDraftError(
            "D1-I1 authority scope contains no governed elements."
        )

    if len(scoped_element_ids) != len(set(scoped_element_ids)):
        raise DraftingWorkingDraftError(
            "D1-I1 authority scope contains duplicate elements."
        )

    title_value = _required(
        title,
        "title",
    )

    purpose_value = _required(
        purpose,
        "purpose",
    )

    creator_value = _required(
        creator_reference,
        "creator_reference",
    )

    supplied_statements = tuple(
        statements
    )

    if not supplied_statements:
        raise DraftingWorkingDraftError(
            "a working draft must contain at least one statement."
        )

    persisted_statements: list[
        WorkingDraftStatement
    ] = []

    for sequence, supplied in enumerate(
        supplied_statements,
        start=1,
    ):
        if not isinstance(
            supplied,
            WorkingDraftStatementInput,
        ):
            raise DraftingWorkingDraftError(
                "statements must be WorkingDraftStatementInput values."
            )

        text = _required(
            supplied.text,
            "statement text",
        )

        element_id = _required(
            supplied.element_id,
            "statement element_id",
        )

        if element_id not in scoped_element_ids:
            raise DraftingWorkingDraftError(
                "draft statement element is outside the explicit D1-I1 scope."
            )

        claimed_status = _required(
            supplied.claimed_status,
            "statement claimed_status",
        )

        claimed_confidence = _required(
            supplied.claimed_confidence,
            "statement claimed_confidence",
        )

        cited_evidence_keys = (
            _canonical_evidence_keys(
                supplied.cited_evidence_keys
            )
        )

        statement_identity_payload = {
            "sequence": sequence,
            "text": text,
            "element_id": element_id,
            "claimed_status": claimed_status,
            "claimed_confidence": claimed_confidence,
            "cited_evidence_keys": list(
                cited_evidence_keys
            ),
        }

        persisted_statements.append(
            WorkingDraftStatement(
                statement_id=_derive_sha256_id(
                    statement_identity_payload
                ),
                sequence=sequence,
                text=text,
                element_id=element_id,
                claimed_status=claimed_status,
                claimed_confidence=claimed_confidence,
                cited_evidence_keys=cited_evidence_keys,
            )
        )

    statement_ids = tuple(
        item.statement_id
        for item in persisted_statements
    )

    if len(statement_ids) != len(set(statement_ids)):
        raise DraftingWorkingDraftError(
            "working draft contains duplicate statement identities."
        )

    draft_identity_payload = {
        "schema_version": WORKING_DRAFT_SCHEMA_VERSION,
        "case_id": case_id,
        "task_id": task_id,
        "progress_id": progress_id,
        "task_work_recorded_at": task_work_recorded_at,
        "task_work_question_sha256": question_sha256,
        "task_work_answer_sha256": answer_sha256,
        "scope_binding_id": scope_binding_id,
        "authority_id": authority_id,
        "issue_analysis_id": issue_analysis_id,
        "issue_definition_id": issue_definition_id,
        "title": title_value,
        "purpose": purpose_value,
        "statements": [
            asdict(item)
            for item in persisted_statements
        ],
        "creator_reference": creator_value,
    }

    draft_id = _derive_sha256_id(
        draft_identity_payload
    )

    recorded_at_value = (
        _canonical_timestamp(
            recorded_at,
            "recorded_at",
        )
        if recorded_at is not None
        else _now_utc()
    )

    return WorkingDraft(
        schema_version=WORKING_DRAFT_SCHEMA_VERSION,
        draft_id=draft_id,
        case_id=case_id,
        task_id=task_id,
        progress_id=progress_id,
        task_work_recorded_at=task_work_recorded_at,
        task_work_question_sha256=question_sha256,
        task_work_answer_sha256=answer_sha256,
        scope_binding_id=scope_binding_id,
        authority_id=authority_id,
        issue_analysis_id=issue_analysis_id,
        issue_definition_id=issue_definition_id,
        title=title_value,
        purpose=purpose_value,
        statements=tuple(
            persisted_statements
        ),
        creator_reference=creator_value,
        recorded_at=recorded_at_value,
    )


def working_draft_path(
    case_id: str,
    task_id: str,
    *,
    root: str | Path | None = None,
) -> Path:
    canonical_case_id = _canonical_uuid(
        case_id,
        "case_id",
    )

    canonical_task_id = _canonical_uuid(
        task_id,
        "task_id",
    )

    base = (
        Path(root)
        if root is not None
        else _DEFAULT_ROOT
    )

    return (
        base
        / canonical_case_id
        / (
            canonical_task_id
            + ".jsonl"
        )
    )


def _statement_from_dict(
    value: object,
) -> WorkingDraftStatement:
    if not isinstance(value, dict):
        raise DraftingWorkingDraftError(
            "persisted draft statement is not an object."
        )

    try:
        statement = WorkingDraftStatement(
            statement_id=_sha256_id(
                value["statement_id"],
                "statement_id",
            ),
            sequence=int(
                value["sequence"]
            ),
            text=_required(
                value["text"],
                "statement.text",
            ),
            element_id=_required(
                value["element_id"],
                "statement.element_id",
            ),
            claimed_status=_required(
                value["claimed_status"],
                "statement.claimed_status",
            ),
            claimed_confidence=_required(
                value["claimed_confidence"],
                "statement.claimed_confidence",
            ),
            cited_evidence_keys=_canonical_evidence_keys(
                value[
                    "cited_evidence_keys"
                ]
            ),
        )
    except (
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise DraftingWorkingDraftError(
            "persisted working-draft statement is invalid."
        ) from exc

    if statement.sequence < 1:
        raise DraftingWorkingDraftError(
            "persisted statement sequence must be positive."
        )

    payload = {
        "sequence": statement.sequence,
        "text": statement.text,
        "element_id": statement.element_id,
        "claimed_status": statement.claimed_status,
        "claimed_confidence": statement.claimed_confidence,
        "cited_evidence_keys": list(
            statement.cited_evidence_keys
        ),
    }

    if _derive_sha256_id(payload) != statement.statement_id:
        raise DraftingWorkingDraftError(
            "persisted statement identity does not match its content."
        )

    return statement


def _draft_from_dict(
    value: object,
) -> WorkingDraft:
    if not isinstance(value, dict):
        raise DraftingWorkingDraftError(
            "persisted working draft is not an object."
        )

    try:
        schema_version = _required(
            value["schema_version"],
            "schema_version",
        )

        if schema_version != WORKING_DRAFT_SCHEMA_VERSION:
            raise DraftingWorkingDraftError(
                "unsupported working-draft schema version."
            )

        statements = tuple(
            _statement_from_dict(
                item
            )
            for item in value[
                "statements"
            ]
        )

        if not statements:
            raise DraftingWorkingDraftError(
                "persisted working draft has no statements."
            )

        expected_sequences = tuple(
            range(
                1,
                len(statements) + 1,
            )
        )

        actual_sequences = tuple(
            statement.sequence
            for statement in statements
        )

        if actual_sequences != expected_sequences:
            raise DraftingWorkingDraftError(
                "persisted statement sequence is not canonical."
            )

        draft = WorkingDraft(
            schema_version=schema_version,
            draft_id=_sha256_id(
                value["draft_id"],
                "draft_id",
            ),
            case_id=_canonical_uuid(
                value["case_id"],
                "case_id",
            ),
            task_id=_canonical_uuid(
                value["task_id"],
                "task_id",
            ),
            progress_id=_canonical_uuid(
                value["progress_id"],
                "progress_id",
            ),
            task_work_recorded_at=_canonical_timestamp(
                value[
                    "task_work_recorded_at"
                ],
                "task_work_recorded_at",
            ),
            task_work_question_sha256=_sha256_hex_value(
                value[
                    "task_work_question_sha256"
                ],
                "task_work_question_sha256",
            ),
            task_work_answer_sha256=_sha256_hex_value(
                value[
                    "task_work_answer_sha256"
                ],
                "task_work_answer_sha256",
            ),
            scope_binding_id=_sha256_id(
                value[
                    "scope_binding_id"
                ],
                "scope_binding_id",
            ),
            authority_id=_sha256_id(
                value["authority_id"],
                "authority_id",
            ),
            issue_analysis_id=_canonical_uuid(
                value[
                    "issue_analysis_id"
                ],
                "issue_analysis_id",
            ),
            issue_definition_id=_required(
                value[
                    "issue_definition_id"
                ],
                "issue_definition_id",
            ),
            title=_required(
                value["title"],
                "title",
            ),
            purpose=_required(
                value["purpose"],
                "purpose",
            ),
            statements=statements,
            creator_reference=_required(
                value[
                    "creator_reference"
                ],
                "creator_reference",
            ),
            recorded_at=_canonical_timestamp(
                value["recorded_at"],
                "recorded_at",
            ),
        )
    except (
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise DraftingWorkingDraftError(
            "persisted working draft is invalid."
        ) from exc

    identity_payload = {
        "schema_version": draft.schema_version,
        "case_id": draft.case_id,
        "task_id": draft.task_id,
        "progress_id": draft.progress_id,
        "task_work_recorded_at": draft.task_work_recorded_at,
        "task_work_question_sha256": draft.task_work_question_sha256,
        "task_work_answer_sha256": draft.task_work_answer_sha256,
        "scope_binding_id": draft.scope_binding_id,
        "authority_id": draft.authority_id,
        "issue_analysis_id": draft.issue_analysis_id,
        "issue_definition_id": draft.issue_definition_id,
        "title": draft.title,
        "purpose": draft.purpose,
        "statements": [
            asdict(statement)
            for statement in draft.statements
        ],
        "creator_reference": draft.creator_reference,
    }

    if _derive_sha256_id(identity_payload) != draft.draft_id:
        raise DraftingWorkingDraftError(
            "persisted working-draft identity does not match its content."
        )

    return draft


def load_working_drafts(
    case_id: str,
    task_id: str,
    *,
    root: str | Path | None = None,
) -> tuple[WorkingDraft, ...]:
    path = working_draft_path(
        case_id,
        task_id,
        root=root,
    )

    if not path.exists():
        return ()

    drafts: list[
        WorkingDraft
    ] = []

    seen_ids: set[
        str
    ] = set()

    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        for line_number, line in enumerate(
            handle,
            start=1,
        ):
            if not line.strip():
                raise DraftingWorkingDraftError(
                    "working-draft history contains an empty line."
                )

            try:
                payload = json.loads(
                    line
                )
            except json.JSONDecodeError as exc:
                raise DraftingWorkingDraftError(
                    "working-draft history contains invalid JSON "
                    + "at line "
                    + str(line_number)
                    + "."
                ) from exc

            draft = _draft_from_dict(
                payload
            )

            if (
                draft.case_id != case_id
                or draft.task_id != task_id
            ):
                raise DraftingWorkingDraftError(
                    "working-draft history contains a foreign record."
                )

            if draft.draft_id in seen_ids:
                raise DraftingWorkingDraftError(
                    "working-draft history contains a duplicate draft_id."
                )

            seen_ids.add(
                draft.draft_id
            )

            drafts.append(
                draft
            )

    return tuple(
        drafts
    )


def load_working_draft(
    case_id: str,
    task_id: str,
    draft_id: str,
    *,
    root: str | Path | None = None,
) -> WorkingDraft | None:
    target_id = _sha256_id(
        draft_id,
        "draft_id",
    )

    matches = tuple(
        draft
        for draft in load_working_drafts(
            case_id,
            task_id,
            root=root,
        )
        if draft.draft_id
        == target_id
    )

    if len(matches) > 1:
        raise DraftingWorkingDraftError(
            "working-draft history contains duplicate draft identity."
        )

    return (
        matches[0]
        if matches
        else None
    )


def record_working_draft(
    *,
    task: object,
    progress: object,
    retrieval_receipt: object,
    scope: object,
    authority: object,
    title: str,
    purpose: str,
    statements: Iterable[WorkingDraftStatementInput],
    creator_reference: str,
    recorded_at: str | None = None,
    root: str | Path | None = None,
) -> WorkingDraft:
    """Append one exact immutable WORKING draft after full source validation."""

    draft = build_working_draft(
        task=task,
        progress=progress,
        retrieval_receipt=retrieval_receipt,
        scope=scope,
        authority=authority,
        title=title,
        purpose=purpose,
        statements=statements,
        creator_reference=creator_reference,
        recorded_at=recorded_at,
    )

    existing = load_working_drafts(
        draft.case_id,
        draft.task_id,
        root=root,
    )

    if any(
        item.draft_id
        == draft.draft_id
        for item in existing
    ):
        raise DraftingWorkingDraftError(
            "this exact working draft is already recorded."
        )

    path = working_draft_path(
        draft.case_id,
        draft.task_id,
        root=root,
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = asdict(
        draft
    )

    with path.open(
        "a",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        handle.write(
            _canonical_json(
                payload
            )
        )

        handle.write(
            "\n"
        )

        handle.flush()

    return draft


__all__ = [
    "WORKING_DRAFT_SCHEMA_VERSION",
    "DraftingWorkingDraftError",
    "WorkingDraftStatementInput",
    "WorkingDraftStatement",
    "WorkingDraft",
    "build_working_draft",
    "working_draft_path",
    "load_working_drafts",
    "load_working_draft",
    "record_working_draft",
]