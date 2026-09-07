from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import inspect

import pytest

import task_work_authority_scope as scope_module

from task_work_authority_scope import (
    TASK_WORK_AUTHORITY_SCOPE_SCHEMA_VERSION,
    TaskWorkAuthorityScopeError,
    build_task_work_authority_scope,
    load_task_work_authority_scope,
    load_task_work_authority_scopes,
    record_task_work_authority_scope,
    resolve_task_work_authority_scope,
)


CASE_ID = "8081166d-9889-40bb-8add-5d0893037ff0"
TASK_ID = "e162d3c5-abe2-4553-b464-15a828798a8e"
PROGRESS_ID = "11111111-1111-4111-8111-111111111111"

ISSUE_ID = "2df52940-c44d-4759-99fe-6a624edc05c0"
ISSUE_DEFINITION_ID = "EK-001"

AUTHORITY_ID = (
    "sha256:"
    + ("a" * 64)
)

SECOND_AUTHORITY_ID = (
    "sha256:"
    + ("b" * 64)
)

RECORDED_AT = "2026-09-07T08:00:00Z"


@dataclass(frozen=True)
class FakeTask:
    case_id: str = CASE_ID
    task_id: str = TASK_ID
    issue_analysis_id: str = ISSUE_ID


@dataclass(frozen=True)
class FakeProgress:
    case_id: str = CASE_ID
    task_id: str = TASK_ID
    progress_id: str = PROGRESS_ID
    recorded_at: str = RECORDED_AT
    question: str = "Was the rehabilitation plan transmitted?"
    answer: str = "The available evidence supports further investigation."


@dataclass(frozen=True)
class FakeReceipt:
    case_id: str
    task_id: str
    progress_id: str
    task_work_recorded_at: str
    question_sha256: str
    answer_sha256: str


@dataclass(frozen=True)
class FakeElement:
    element_id: str
    analysis_status: str = "SUPPORTED_BUT_NOT_ESTABLISHED"
    analysis_confidence: str = "MEDIUM"
    supporting_evidence_keys: tuple[str, ...] = ("e1",)
    adverse_evidence_keys: tuple[str, ...] = ()
    corroborative_evidence_keys: tuple[str, ...] = ()
    conflicting_evidence_keys: tuple[str, ...] = ()
    neutral_evidence_keys: tuple[str, ...] = ()
    evidential_gap_ids: tuple[str, ...] = ()
    unresolved_matters: tuple[str, ...] = ()


@dataclass(frozen=True)
class FakeIssue:
    issue_analysis_id: str
    issue_definition_id: str
    element_records: tuple[FakeElement, ...]


@dataclass(frozen=True)
class FakeIssueMatrix:
    issue_matrix: tuple[FakeIssue, ...]


@dataclass(frozen=True)
class FakeManifest:
    case_id: str
    authority_id: str


@dataclass(frozen=True)
class FakePointer:
    case_id: str
    authority_id: str


@dataclass(frozen=True)
class FakeActivationReceipt:
    case_id: str
    new_authority_id: str


@dataclass(frozen=True)
class FakeAuthority:
    manifest: FakeManifest
    active_pointer: FakePointer
    activation_receipt: FakeActivationReceipt
    case_matrices: FakeIssueMatrix


def _digest(value: str) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def make_receipt(
    progress: FakeProgress | None = None,
    *,
    progress_id: str | None = None,
) -> FakeReceipt:
    progress = (
        progress
        if progress is not None
        else FakeProgress()
    )

    return FakeReceipt(
        case_id=progress.case_id,
        task_id=progress.task_id,
        progress_id=(
            progress_id
            if progress_id is not None
            else progress.progress_id
        ),
        task_work_recorded_at=
            progress.recorded_at,
        question_sha256=
            _digest(progress.question),
        answer_sha256=
            "sha256:"
            + _digest(progress.answer),
    )


def make_authority(
    authority_id: str = AUTHORITY_ID,
) -> FakeAuthority:
    issue = FakeIssue(
        issue_analysis_id=ISSUE_ID,
        issue_definition_id=
            ISSUE_DEFINITION_ID,
        element_records=(
            FakeElement(
                element_id="EK-INFORMATION",
            ),
            FakeElement(
                element_id="EK-RECIPIENT",
            ),
            FakeElement(
                element_id="EK-DIRECT-KNOWLEDGE",
            ),
        ),
    )

    return FakeAuthority(
        manifest=FakeManifest(
            case_id=CASE_ID,
            authority_id=authority_id,
        ),
        active_pointer=FakePointer(
            case_id=CASE_ID,
            authority_id=authority_id,
        ),
        activation_receipt=
            FakeActivationReceipt(
                case_id=CASE_ID,
                new_authority_id=
                    authority_id,
            ),
        case_matrices=FakeIssueMatrix(
            issue_matrix=(issue,),
        ),
    )


def test_d1i1_records_exact_progress_authority_and_multi_element_scope(
    tmp_path: Path,
) -> None:
    task = FakeTask()
    progress = FakeProgress()
    receipt = make_receipt(
        progress
    )
    authority = make_authority()

    scope = record_task_work_authority_scope(
        task=task,
        progress=progress,
        retrieval_receipt=receipt,
        authority=authority,
        element_ids=(
            "EK-RECIPIENT",
            "EK-INFORMATION",
        ),
        reviewer_reference=
            "solicitor:test",
        review_note=
            "Explicit professional scope selection.",
        recorded_at=
            "2026-09-07T08:10:00Z",
        root=tmp_path,
    )

    assert (
        scope.schema_version
        == TASK_WORK_AUTHORITY_SCOPE_SCHEMA_VERSION
    )

    assert scope.case_id == CASE_ID
    assert scope.task_id == TASK_ID
    assert scope.progress_id == PROGRESS_ID
    assert scope.authority_id == AUTHORITY_ID
    assert scope.issue_analysis_id == ISSUE_ID

    assert (
        scope.issue_definition_id
        == ISSUE_DEFINITION_ID
    )

    assert scope.element_ids == (
        "EK-INFORMATION",
        "EK-RECIPIENT",
    )

    assert scope.binding_id.startswith(
        "sha256:"
    )

    loaded = load_task_work_authority_scopes(
        CASE_ID,
        TASK_ID,
        root=tmp_path,
    )

    assert loaded == (scope,)

    exact = load_task_work_authority_scope(
        CASE_ID,
        TASK_ID,
        PROGRESS_ID,
        root=tmp_path,
    )

    assert exact == scope

    resolution = (
        resolve_task_work_authority_scope(
            scope,
            authority=authority,
        )
    )

    assert tuple(
        element.element_id
        for element in resolution.elements
    ) == (
        "EK-INFORMATION",
        "EK-RECIPIENT",
    )


def test_d1i1_requires_one_or_more_explicit_elements() -> None:
    progress = FakeProgress()

    with pytest.raises(
        TaskWorkAuthorityScopeError,
        match="at least one",
    ):
        build_task_work_authority_scope(
            task=FakeTask(),
            progress=progress,
            retrieval_receipt=
                make_receipt(progress),
            authority=make_authority(),
            element_ids=(),
            reviewer_reference=
                "solicitor:test",
        )


def test_d1i1_never_infers_element_from_task_issue() -> None:
    signature = inspect.signature(
        build_task_work_authority_scope
    )

    parameter = signature.parameters[
        "element_ids"
    ]

    assert (
        parameter.default
        is inspect.Parameter.empty
    )

    progress = FakeProgress()

    with pytest.raises(
        TaskWorkAuthorityScopeError,
        match="at least one",
    ):
        build_task_work_authority_scope(
            task=FakeTask(),
            progress=progress,
            retrieval_receipt=
                make_receipt(progress),
            authority=make_authority(),
            element_ids=(),
            reviewer_reference=
                "solicitor:test",
        )


def test_d1i1_rejects_element_outside_bound_issue() -> None:
    progress = FakeProgress()

    with pytest.raises(
        TaskWorkAuthorityScopeError,
        match="absent from current authority",
    ):
        build_task_work_authority_scope(
            task=FakeTask(),
            progress=progress,
            retrieval_receipt=
                make_receipt(progress),
            authority=make_authority(),
            element_ids=(
                "LIM-ACTS",
            ),
            reviewer_reference=
                "solicitor:test",
        )


def test_d1i1_requires_matching_r68_progress_receipt() -> None:
    progress = FakeProgress()

    wrong_progress_id = (
        "22222222-2222-4222-8222-222222222222"
    )

    with pytest.raises(
        TaskWorkAuthorityScopeError,
        match="progress_id",
    ):
        build_task_work_authority_scope(
            task=FakeTask(),
            progress=progress,
            retrieval_receipt=
                make_receipt(
                    progress,
                    progress_id=
                        wrong_progress_id,
                ),
            authority=make_authority(),
            element_ids=(
                "EK-INFORMATION",
            ),
            reviewer_reference=
                "solicitor:test",
        )


def test_d1i1_requires_receipt_hash_binding_to_exact_task_work() -> None:
    progress = FakeProgress()

    receipt = FakeReceipt(
        case_id=CASE_ID,
        task_id=TASK_ID,
        progress_id=PROGRESS_ID,
        task_work_recorded_at=
            RECORDED_AT,
        question_sha256=
            "0" * 64,
        answer_sha256=
            _digest(progress.answer),
    )

    with pytest.raises(
        TaskWorkAuthorityScopeError,
        match="question_sha256",
    ):
        build_task_work_authority_scope(
            task=FakeTask(),
            progress=progress,
            retrieval_receipt=receipt,
            authority=make_authority(),
            element_ids=(
                "EK-INFORMATION",
            ),
            reviewer_reference=
                "solicitor:test",
        )


def test_d1i1_fails_closed_if_bound_authority_is_no_longer_current(
    tmp_path: Path,
) -> None:
    progress = FakeProgress()

    scope = record_task_work_authority_scope(
        task=FakeTask(),
        progress=progress,
        retrieval_receipt=
            make_receipt(progress),
        authority=make_authority(),
        element_ids=(
            "EK-INFORMATION",
        ),
        reviewer_reference=
            "solicitor:test",
        root=tmp_path,
    )

    with pytest.raises(
        TaskWorkAuthorityScopeError,
        match="stale",
    ):
        resolve_task_work_authority_scope(
            scope,
            authority=make_authority(
                SECOND_AUTHORITY_ID
            ),
        )


def test_d1i1_rejects_internally_inconsistent_current_authority() -> None:
    authority = make_authority()

    inconsistent = FakeAuthority(
        manifest=authority.manifest,
        active_pointer=FakePointer(
            case_id=CASE_ID,
            authority_id=
                SECOND_AUTHORITY_ID,
        ),
        activation_receipt=
            authority.activation_receipt,
        case_matrices=
            authority.case_matrices,
    )

    progress = FakeProgress()

    with pytest.raises(
        TaskWorkAuthorityScopeError,
        match="identity is inconsistent",
    ):
        build_task_work_authority_scope(
            task=FakeTask(),
            progress=progress,
            retrieval_receipt=
                make_receipt(progress),
            authority=inconsistent,
            element_ids=(
                "EK-INFORMATION",
            ),
            reviewer_reference=
                "solicitor:test",
        )


def test_d1i1_allows_only_one_binding_per_progress_id(
    tmp_path: Path,
) -> None:
    progress = FakeProgress()

    kwargs = dict(
        task=FakeTask(),
        progress=progress,
        retrieval_receipt=
            make_receipt(progress),
        authority=make_authority(),
        element_ids=(
            "EK-INFORMATION",
        ),
        reviewer_reference=
            "solicitor:test",
        root=tmp_path,
    )

    first = (
        record_task_work_authority_scope(
            **kwargs
        )
    )

    assert first.progress_id == PROGRESS_ID

    with pytest.raises(
        TaskWorkAuthorityScopeError,
        match="already exists",
    ):
        record_task_work_authority_scope(
            **kwargs
        )


def test_d1i1_does_not_mutate_existing_task_or_receipt_schemas() -> None:
    source = Path(
        scope_module.__file__
    ).read_text(
        encoding="utf-8"
    )

    assert "solicitor_tasks import" not in source
    assert "task_work_progress import" not in source
    assert "task_work_retrieval_receipt import" not in source

    assert "openai" not in source.lower()
    assert "chromadb" not in source.lower()
    assert "streamlit" not in source.lower()
    assert "requests" not in source.lower()


def test_d1i1_default_runtime_root_stays_under_existing_ignored_task_root() -> None:
    path = (
        scope_module
        .task_work_authority_scope_path(
            CASE_ID,
            TASK_ID,
        )
    )

    assert path.parts[0] == "solicitor_tasks"
    assert (
        "task_work_authority_scope"
        in path.parts
    )