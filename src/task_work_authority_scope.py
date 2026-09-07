"""Explicit professional authority scope for one persisted task-work result.

This module does not create, replace or amend analytical authority.

One authority-scope record binds:
- one existing SolicitorTask,
- one exact TaskWorkProgress result,
- its matching retrieval receipt,
- one currently active governed analytical authority,
- one governed issue,
- and one-or-more explicitly selected governed elements.

Element scope is never inferred from task prose, issue title, evidence overlap,
or retrieval results.

The persisted sidecar is independent of:
- solicitor-task schema,
- task-work-progress schema,
- retrieval-receipt schema,
- report projection,
- work-product release,
- and Drafting UI state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID
import hashlib
import json
import os
import re


TASK_WORK_AUTHORITY_SCOPE_SCHEMA_VERSION = (
    "task-work-authority-scope/1.0"
)

_DEFAULT_ROOT = (
    Path("solicitor_tasks")
    / "task_work_authority_scope"
)

_SHA256_ID = re.compile(
    r"^sha256:[0-9a-f]{64}$"
)


class TaskWorkAuthorityScopeError(RuntimeError):
    """Raised when task-work authority scope is invalid or stale."""


@dataclass(frozen=True)
class TaskWorkAuthorityScope:
    schema_version: str
    binding_id: str
    case_id: str
    task_id: str
    progress_id: str
    authority_id: str
    issue_analysis_id: str
    issue_definition_id: str
    element_ids: tuple[str, ...]
    reviewer_reference: str
    review_note: str
    recorded_at: str


@dataclass(frozen=True)
class TaskWorkAuthorityScopeResolution:
    scope: TaskWorkAuthorityScope
    issue: Any
    elements: tuple[Any, ...]


def _required(
    value: object,
    field_name: str,
) -> str:
    if not isinstance(value, str):
        raise TaskWorkAuthorityScopeError(
            field_name + " must be text."
        )

    result = value.strip()

    if not result:
        raise TaskWorkAuthorityScopeError(
            field_name + " must not be empty."
        )

    return result


def _optional_text(
    value: object,
    field_name: str,
) -> str:
    if value is None:
        return ""

    if not isinstance(value, str):
        raise TaskWorkAuthorityScopeError(
            field_name + " must be text."
        )

    return value.strip()


def _uuid(
    value: object,
    field_name: str,
) -> str:
    text = _required(
        value,
        field_name,
    )

    try:
        canonical = str(
            UUID(text)
        )
    except (ValueError, TypeError, AttributeError) as exc:
        raise TaskWorkAuthorityScopeError(
            field_name + " must be a UUID."
        ) from exc

    if canonical != text.lower():
        raise TaskWorkAuthorityScopeError(
            field_name + " must be canonical."
        )

    return canonical


def _sha256_id(
    value: object,
    field_name: str,
) -> str:
    text = _required(
        value,
        field_name,
    ).lower()

    if not _SHA256_ID.fullmatch(text):
        raise TaskWorkAuthorityScopeError(
            field_name
            + " must be a sha256: identity."
        )

    return text


def _timestamp(
    value: object,
    field_name: str,
) -> str:
    text = _required(
        value,
        field_name,
    )

    candidate = text

    if candidate.endswith("Z"):
        candidate = (
            candidate[:-1]
            + "+00:00"
        )

    try:
        parsed = datetime.fromisoformat(
            candidate
        )
    except ValueError as exc:
        raise TaskWorkAuthorityScopeError(
            field_name
            + " must be an ISO-8601 timestamp."
        ) from exc

    if parsed.tzinfo is None:
        raise TaskWorkAuthorityScopeError(
            field_name
            + " must be timezone-aware."
        )

    return (
        parsed
        .astimezone(timezone.utc)
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )


def _canonical_bytes(
    value: object,
) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _text_sha256(
    value: object,
    field_name: str,
) -> str:
    text = _required(
        value,
        field_name,
    )

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def _receipt_hash_matches(
    value: object,
    expected_hex: str,
    field_name: str,
) -> None:
    actual = _required(
        value,
        field_name,
    ).lower()

    permitted = {
        expected_hex,
        "sha256:" + expected_hex,
    }

    if actual not in permitted:
        raise TaskWorkAuthorityScopeError(
            field_name
            + " does not match the persisted task-work content."
        )


def _authority_identity(
    authority: object,
) -> tuple[str, str]:
    try:
        manifest = getattr(
            authority,
            "manifest",
        )

        active_pointer = getattr(
            authority,
            "active_pointer",
        )

        activation_receipt = getattr(
            authority,
            "activation_receipt",
        )

        case_id = _uuid(
            getattr(
                manifest,
                "case_id",
            ),
            "authority.manifest.case_id",
        )

        manifest_authority_id = _sha256_id(
            getattr(
                manifest,
                "authority_id",
            ),
            "authority.manifest.authority_id",
        )

        pointer_case_id = _uuid(
            getattr(
                active_pointer,
                "case_id",
            ),
            "authority.active_pointer.case_id",
        )

        pointer_authority_id = _sha256_id(
            getattr(
                active_pointer,
                "authority_id",
            ),
            "authority.active_pointer.authority_id",
        )

        receipt_case_id = _uuid(
            getattr(
                activation_receipt,
                "case_id",
            ),
            "authority.activation_receipt.case_id",
        )

        receipt_authority_id = _sha256_id(
            getattr(
                activation_receipt,
                "new_authority_id",
            ),
            "authority.activation_receipt.new_authority_id",
        )

    except AttributeError as exc:
        raise TaskWorkAuthorityScopeError(
            "authority does not expose the required governed identity."
        ) from exc

    if not (
        case_id
        == pointer_case_id
        == receipt_case_id
    ):
        raise TaskWorkAuthorityScopeError(
            "governed authority case identity is inconsistent."
        )

    if not (
        manifest_authority_id
        == pointer_authority_id
        == receipt_authority_id
    ):
        raise TaskWorkAuthorityScopeError(
            "governed authority identity is inconsistent."
        )

    return (
        case_id,
        manifest_authority_id,
    )


def _issue_and_elements(
    authority: object,
    *,
    issue_analysis_id: str,
    issue_definition_id: str,
    element_ids: tuple[str, ...],
) -> tuple[Any, tuple[Any, ...]]:
    try:
        issue_matrix = tuple(
            getattr(
                getattr(
                    authority,
                    "case_matrices",
                ),
                "issue_matrix",
            )
        )
    except (AttributeError, TypeError) as exc:
        raise TaskWorkAuthorityScopeError(
            "authority does not expose the governed issue matrix."
        ) from exc

    matches = tuple(
        issue
        for issue in issue_matrix
        if _required(
            getattr(
                issue,
                "issue_analysis_id",
                "",
            ),
            "issue.issue_analysis_id",
        )
        == issue_analysis_id
    )

    if len(matches) != 1:
        raise TaskWorkAuthorityScopeError(
            "bound issue is not uniquely present in current authority."
        )

    issue = matches[0]

    current_definition_id = _required(
        getattr(
            issue,
            "issue_definition_id",
            "",
        ),
        "issue.issue_definition_id",
    )

    if current_definition_id != issue_definition_id:
        raise TaskWorkAuthorityScopeError(
            "bound issue definition is stale or inconsistent."
        )

    try:
        records = tuple(
            getattr(
                issue,
                "element_records",
            )
        )
    except (AttributeError, TypeError) as exc:
        raise TaskWorkAuthorityScopeError(
            "governed issue does not expose element records."
        ) from exc

    by_id: dict[str, Any] = {}

    for record in records:
        element_id = _required(
            getattr(
                record,
                "element_id",
                "",
            ),
            "element.element_id",
        )

        if element_id in by_id:
            raise TaskWorkAuthorityScopeError(
                "current authority contains duplicate element IDs."
            )

        by_id[element_id] = record

    missing = tuple(
        element_id
        for element_id in element_ids
        if element_id not in by_id
    )

    if missing:
        raise TaskWorkAuthorityScopeError(
            "bound governed element is absent from current authority: "
            + ", ".join(missing)
        )

    resolved = tuple(
        by_id[element_id]
        for element_id in element_ids
    )

    return (
        issue,
        resolved,
    )


def _canonical_element_ids(
    values: Iterable[object],
) -> tuple[str, ...]:
    if isinstance(
        values,
        (str, bytes),
    ):
        raise TaskWorkAuthorityScopeError(
            "element_ids must be an iterable of element IDs."
        )

    result = tuple(
        _required(
            value,
            "element_id",
        )
        for value in values
    )

    if not result:
        raise TaskWorkAuthorityScopeError(
            "element_ids must contain at least one governed element."
        )

    if len(result) != len(set(result)):
        raise TaskWorkAuthorityScopeError(
            "element_ids must not contain duplicates."
        )

    return tuple(
        sorted(result)
    )


def _scope_payload(
    scope: TaskWorkAuthorityScope,
    *,
    include_binding_id: bool,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version":
            scope.schema_version,
        "case_id":
            scope.case_id,
        "task_id":
            scope.task_id,
        "progress_id":
            scope.progress_id,
        "authority_id":
            scope.authority_id,
        "issue_analysis_id":
            scope.issue_analysis_id,
        "issue_definition_id":
            scope.issue_definition_id,
        "element_ids":
            list(scope.element_ids),
        "reviewer_reference":
            scope.reviewer_reference,
        "review_note":
            scope.review_note,
        "recorded_at":
            scope.recorded_at,
    }

    if include_binding_id:
        payload["binding_id"] = (
            scope.binding_id
        )

    return payload


def _binding_id(
    scope: TaskWorkAuthorityScope,
) -> str:
    digest = hashlib.sha256(
        _canonical_bytes(
            _scope_payload(
                scope,
                include_binding_id=False,
            )
        )
    ).hexdigest()

    return "sha256:" + digest


def validate_task_work_authority_scope(
    scope: TaskWorkAuthorityScope,
) -> TaskWorkAuthorityScope:
    if not isinstance(
        scope,
        TaskWorkAuthorityScope,
    ):
        raise TaskWorkAuthorityScopeError(
            "scope must be a TaskWorkAuthorityScope."
        )

    if (
        scope.schema_version
        != TASK_WORK_AUTHORITY_SCOPE_SCHEMA_VERSION
    ):
        raise TaskWorkAuthorityScopeError(
            "unsupported task-work authority-scope schema."
        )

    _uuid(
        scope.case_id,
        "case_id",
    )

    _uuid(
        scope.task_id,
        "task_id",
    )

    _uuid(
        scope.progress_id,
        "progress_id",
    )

    _sha256_id(
        scope.authority_id,
        "authority_id",
    )

    _uuid(
        scope.issue_analysis_id,
        "issue_analysis_id",
    )

    _required(
        scope.issue_definition_id,
        "issue_definition_id",
    )

    canonical_elements = (
        _canonical_element_ids(
            scope.element_ids
        )
    )

    if canonical_elements != scope.element_ids:
        raise TaskWorkAuthorityScopeError(
            "element_ids are not in canonical order."
        )

    _required(
        scope.reviewer_reference,
        "reviewer_reference",
    )

    _optional_text(
        scope.review_note,
        "review_note",
    )

    _timestamp(
        scope.recorded_at,
        "recorded_at",
    )

    actual_binding_id = _sha256_id(
        scope.binding_id,
        "binding_id",
    )

    expected_binding_id = _binding_id(
        scope
    )

    if actual_binding_id != expected_binding_id:
        raise TaskWorkAuthorityScopeError(
            "binding_id does not match canonical scope payload."
        )

    return scope


def build_task_work_authority_scope(
    *,
    task: object,
    progress: object,
    retrieval_receipt: object,
    authority: object,
    element_ids: Iterable[object],
    reviewer_reference: str,
    review_note: str = "",
    recorded_at: str | None = None,
) -> TaskWorkAuthorityScope:
    task_case_id = _uuid(
        getattr(
            task,
            "case_id",
            "",
        ),
        "task.case_id",
    )

    task_id = _uuid(
        getattr(
            task,
            "task_id",
            "",
        ),
        "task.task_id",
    )

    issue_analysis_id = _uuid(
        getattr(
            task,
            "issue_analysis_id",
            "",
        ),
        "task.issue_analysis_id",
    )

    progress_case_id = _uuid(
        getattr(
            progress,
            "case_id",
            "",
        ),
        "progress.case_id",
    )

    progress_task_id = _uuid(
        getattr(
            progress,
            "task_id",
            "",
        ),
        "progress.task_id",
    )

    progress_id = _uuid(
        getattr(
            progress,
            "progress_id",
            "",
        ),
        "progress.progress_id",
    )

    if progress_case_id != task_case_id:
        raise TaskWorkAuthorityScopeError(
            "task-work case does not match task."
        )

    if progress_task_id != task_id:
        raise TaskWorkAuthorityScopeError(
            "task-work task_id does not match task."
        )

    receipt_case_id = _uuid(
        getattr(
            retrieval_receipt,
            "case_id",
            "",
        ),
        "retrieval_receipt.case_id",
    )

    receipt_task_id = _uuid(
        getattr(
            retrieval_receipt,
            "task_id",
            "",
        ),
        "retrieval_receipt.task_id",
    )

    receipt_progress_id = _uuid(
        getattr(
            retrieval_receipt,
            "progress_id",
            "",
        ),
        "retrieval_receipt.progress_id",
    )

    if receipt_case_id != task_case_id:
        raise TaskWorkAuthorityScopeError(
            "retrieval receipt case does not match task."
        )

    if receipt_task_id != task_id:
        raise TaskWorkAuthorityScopeError(
            "retrieval receipt task_id does not match task."
        )

    if receipt_progress_id != progress_id:
        raise TaskWorkAuthorityScopeError(
            "retrieval receipt progress_id does not match task-work."
        )

    progress_recorded_at = _timestamp(
        getattr(
            progress,
            "recorded_at",
            "",
        ),
        "progress.recorded_at",
    )

    receipt_task_work_recorded_at = _timestamp(
        getattr(
            retrieval_receipt,
            "task_work_recorded_at",
            "",
        ),
        "retrieval_receipt.task_work_recorded_at",
    )

    if (
        progress_recorded_at
        != receipt_task_work_recorded_at
    ):
        raise TaskWorkAuthorityScopeError(
            "retrieval receipt timestamp does not match task-work."
        )

    question_hash = _text_sha256(
        getattr(
            progress,
            "question",
            "",
        ),
        "progress.question",
    )

    answer_hash = _text_sha256(
        getattr(
            progress,
            "answer",
            "",
        ),
        "progress.answer",
    )

    _receipt_hash_matches(
        getattr(
            retrieval_receipt,
            "question_sha256",
            "",
        ),
        question_hash,
        "retrieval_receipt.question_sha256",
    )

    _receipt_hash_matches(
        getattr(
            retrieval_receipt,
            "answer_sha256",
            "",
        ),
        answer_hash,
        "retrieval_receipt.answer_sha256",
    )

    authority_case_id, authority_id = (
        _authority_identity(
            authority
        )
    )

    if authority_case_id != task_case_id:
        raise TaskWorkAuthorityScopeError(
            "governed authority case does not match task."
        )

    canonical_element_ids = (
        _canonical_element_ids(
            element_ids
        )
    )

    try:
        issue_matrix = tuple(
            authority.case_matrices.issue_matrix
        )
    except (AttributeError, TypeError) as exc:
        raise TaskWorkAuthorityScopeError(
            "authority does not expose the governed issue matrix."
        ) from exc

    task_issue_matches = tuple(
        issue
        for issue in issue_matrix
        if str(
            getattr(
                issue,
                "issue_analysis_id",
                "",
            )
        ).strip()
        == issue_analysis_id
    )

    if len(task_issue_matches) != 1:
        raise TaskWorkAuthorityScopeError(
            "task issue is not uniquely present in current authority."
        )

    task_issue = task_issue_matches[0]

    issue_definition_id = _required(
        getattr(
            task_issue,
            "issue_definition_id",
            "",
        ),
        "issue.issue_definition_id",
    )

    _issue_and_elements(
        authority,
        issue_analysis_id=
            issue_analysis_id,
        issue_definition_id=
            issue_definition_id,
        element_ids=
            canonical_element_ids,
    )

    reviewer = _required(
        reviewer_reference,
        "reviewer_reference",
    )

    note = _optional_text(
        review_note,
        "review_note",
    )

    timestamp = _timestamp(
        recorded_at
        if recorded_at is not None
        else _utc_now(),
        "recorded_at",
    )

    provisional = TaskWorkAuthorityScope(
        schema_version=
            TASK_WORK_AUTHORITY_SCOPE_SCHEMA_VERSION,
        binding_id=
            "sha256:" + ("0" * 64),
        case_id=
            task_case_id,
        task_id=
            task_id,
        progress_id=
            progress_id,
        authority_id=
            authority_id,
        issue_analysis_id=
            issue_analysis_id,
        issue_definition_id=
            issue_definition_id,
        element_ids=
            canonical_element_ids,
        reviewer_reference=
            reviewer,
        review_note=
            note,
        recorded_at=
            timestamp,
    )

    scope = TaskWorkAuthorityScope(
        schema_version=
            provisional.schema_version,
        binding_id=
            _binding_id(
                provisional
            ),
        case_id=
            provisional.case_id,
        task_id=
            provisional.task_id,
        progress_id=
            provisional.progress_id,
        authority_id=
            provisional.authority_id,
        issue_analysis_id=
            provisional.issue_analysis_id,
        issue_definition_id=
            provisional.issue_definition_id,
        element_ids=
            provisional.element_ids,
        reviewer_reference=
            provisional.reviewer_reference,
        review_note=
            provisional.review_note,
        recorded_at=
            provisional.recorded_at,
    )

    return validate_task_work_authority_scope(
        scope
    )


def _root_path(
    root: str | Path | None,
) -> Path:
    if root is None:
        return _DEFAULT_ROOT

    return Path(root)


def task_work_authority_scope_path(
    case_id: str,
    task_id: str,
    *,
    root: str | Path | None = None,
) -> Path:
    canonical_case_id = _uuid(
        case_id,
        "case_id",
    )

    canonical_task_id = _uuid(
        task_id,
        "task_id",
    )

    return (
        _root_path(root)
        / canonical_case_id
        / (
            canonical_task_id
            + ".jsonl"
        )
    )


def _deserialize_scope(
    value: object,
) -> TaskWorkAuthorityScope:
    if not isinstance(
        value,
        dict,
    ):
        raise TaskWorkAuthorityScopeError(
            "persisted task-work authority scope must be an object."
        )

    required = {
        "schema_version",
        "binding_id",
        "case_id",
        "task_id",
        "progress_id",
        "authority_id",
        "issue_analysis_id",
        "issue_definition_id",
        "element_ids",
        "reviewer_reference",
        "review_note",
        "recorded_at",
    }

    if set(value) != required:
        raise TaskWorkAuthorityScopeError(
            "persisted task-work authority scope fields are not exact."
        )

    element_values = value[
        "element_ids"
    ]

    if not isinstance(
        element_values,
        list,
    ):
        raise TaskWorkAuthorityScopeError(
            "persisted element_ids must be a list."
        )

    scope = TaskWorkAuthorityScope(
        schema_version=
            value["schema_version"],
        binding_id=
            value["binding_id"],
        case_id=
            value["case_id"],
        task_id=
            value["task_id"],
        progress_id=
            value["progress_id"],
        authority_id=
            value["authority_id"],
        issue_analysis_id=
            value["issue_analysis_id"],
        issue_definition_id=
            value["issue_definition_id"],
        element_ids=
            tuple(element_values),
        reviewer_reference=
            value["reviewer_reference"],
        review_note=
            value["review_note"],
        recorded_at=
            value["recorded_at"],
    )

    return validate_task_work_authority_scope(
        scope
    )


def load_task_work_authority_scopes(
    case_id: str,
    task_id: str,
    *,
    root: str | Path | None = None,
) -> tuple[TaskWorkAuthorityScope, ...]:
    path = task_work_authority_scope_path(
        case_id,
        task_id,
        root=root,
    )

    if not path.exists():
        return ()

    if not path.is_file():
        raise TaskWorkAuthorityScopeError(
            "task-work authority-scope path is not a file."
        )

    result: list[
        TaskWorkAuthorityScope
    ] = []

    seen_binding_ids: set[str] = set()
    seen_progress_ids: set[str] = set()

    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        for line_number, raw_line in enumerate(
            handle,
            start=1,
        ):
            line = raw_line.strip()

            if not line:
                raise TaskWorkAuthorityScopeError(
                    "blank authority-scope record at line "
                    + str(line_number)
                    + "."
                )

            try:
                value = json.loads(
                    line
                )
            except json.JSONDecodeError as exc:
                raise TaskWorkAuthorityScopeError(
                    "invalid authority-scope JSON at line "
                    + str(line_number)
                    + "."
                ) from exc

            scope = _deserialize_scope(
                value
            )

            if scope.case_id != _uuid(
                case_id,
                "case_id",
            ):
                raise TaskWorkAuthorityScopeError(
                    "persisted scope case_id does not match path."
                )

            if scope.task_id != _uuid(
                task_id,
                "task_id",
            ):
                raise TaskWorkAuthorityScopeError(
                    "persisted scope task_id does not match path."
                )

            if scope.binding_id in seen_binding_ids:
                raise TaskWorkAuthorityScopeError(
                    "duplicate persisted binding_id."
                )

            if scope.progress_id in seen_progress_ids:
                raise TaskWorkAuthorityScopeError(
                    "more than one authority scope exists for one progress_id."
                )

            seen_binding_ids.add(
                scope.binding_id
            )

            seen_progress_ids.add(
                scope.progress_id
            )

            result.append(
                scope
            )

    return tuple(result)


def load_task_work_authority_scope(
    case_id: str,
    task_id: str,
    progress_id: str,
    *,
    root: str | Path | None = None,
) -> TaskWorkAuthorityScope | None:
    canonical_progress_id = _uuid(
        progress_id,
        "progress_id",
    )

    matches = tuple(
        scope
        for scope
        in load_task_work_authority_scopes(
            case_id,
            task_id,
            root=root,
        )
        if scope.progress_id
        == canonical_progress_id
    )

    if not matches:
        return None

    if len(matches) != 1:
        raise TaskWorkAuthorityScopeError(
            "authority scope is not unique for progress_id."
        )

    return matches[0]


def append_task_work_authority_scope(
    scope: TaskWorkAuthorityScope,
    *,
    root: str | Path | None = None,
) -> TaskWorkAuthorityScope:
    scope = validate_task_work_authority_scope(
        scope
    )

    existing = load_task_work_authority_scopes(
        scope.case_id,
        scope.task_id,
        root=root,
    )

    if any(
        item.progress_id
        == scope.progress_id
        for item in existing
    ):
        raise TaskWorkAuthorityScopeError(
            "authority scope already exists for this progress_id."
        )

    path = task_work_authority_scope_path(
        scope.case_id,
        scope.task_id,
        root=root,
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = _scope_payload(
        scope,
        include_binding_id=True,
    )

    encoded = (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )

    with path.open(
        "a",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        handle.write(
            encoded
        )

        handle.flush()
        os.fsync(
            handle.fileno()
        )

    return scope


def record_task_work_authority_scope(
    *,
    task: object,
    progress: object,
    retrieval_receipt: object,
    authority: object,
    element_ids: Iterable[object],
    reviewer_reference: str,
    review_note: str = "",
    recorded_at: str | None = None,
    root: str | Path | None = None,
) -> TaskWorkAuthorityScope:
    scope = build_task_work_authority_scope(
        task=task,
        progress=progress,
        retrieval_receipt=
            retrieval_receipt,
        authority=authority,
        element_ids=element_ids,
        reviewer_reference=
            reviewer_reference,
        review_note=review_note,
        recorded_at=recorded_at,
    )

    return append_task_work_authority_scope(
        scope,
        root=root,
    )


def resolve_task_work_authority_scope(
    scope: TaskWorkAuthorityScope,
    *,
    authority: object,
) -> TaskWorkAuthorityScopeResolution:
    scope = validate_task_work_authority_scope(
        scope
    )

    authority_case_id, current_authority_id = (
        _authority_identity(
            authority
        )
    )

    if authority_case_id != scope.case_id:
        raise TaskWorkAuthorityScopeError(
            "bound authority scope belongs to another case."
        )

    if current_authority_id != scope.authority_id:
        raise TaskWorkAuthorityScopeError(
            "bound task-work authority scope is stale: "
            "the governed analytical authority has changed."
        )

    issue, elements = _issue_and_elements(
        authority,
        issue_analysis_id=
            scope.issue_analysis_id,
        issue_definition_id=
            scope.issue_definition_id,
        element_ids=
            scope.element_ids,
    )

    return TaskWorkAuthorityScopeResolution(
        scope=scope,
        issue=issue,
        elements=elements,
    )


__all__ = [
    "TASK_WORK_AUTHORITY_SCOPE_SCHEMA_VERSION",
    "TaskWorkAuthorityScope",
    "TaskWorkAuthorityScopeError",
    "TaskWorkAuthorityScopeResolution",
    "append_task_work_authority_scope",
    "build_task_work_authority_scope",
    "load_task_work_authority_scope",
    "load_task_work_authority_scopes",
    "record_task_work_authority_scope",
    "resolve_task_work_authority_scope",
    "task_work_authority_scope_path",
    "validate_task_work_authority_scope",
]