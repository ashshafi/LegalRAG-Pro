from __future__ import annotations

from dataclasses import dataclass
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from ui import case_operator


CASE_ID = "8081166d-9889-40bb-8add-5d0893037ff0"
TASK_ID = "e162d3c5-abe2-4553-b464-15a828798a8e"
ISSUE_ID = "2df52940-c44d-4759-99fe-6a624edc05c0"


@dataclass(frozen=True)
class FakeTask:
    task_id: str = TASK_ID
    issue_analysis_id: str = ISSUE_ID


@dataclass(frozen=True)
class FakeProgress:
    progress_id: str


@dataclass(frozen=True)
class FakeReceipt:
    progress_id: str


@dataclass(frozen=True)
class FakeScope:
    progress_id: str


@dataclass(frozen=True)
class FakeElement:
    element_id: str
    element_name: str
    legal_question: str


@dataclass(frozen=True)
class FakeIssue:
    issue_analysis_id: str
    element_records: tuple[FakeElement, ...]


@dataclass(frozen=True)
class FakeIssueMatrix:
    issue_matrix: tuple[FakeIssue, ...]


@dataclass(frozen=True)
class FakeCaseMatrices:
    issue_matrix: tuple[FakeIssue, ...]


@dataclass(frozen=True)
class FakeAuthority:
    case_matrices: FakeCaseMatrices


def make_authority() -> FakeAuthority:
    return FakeAuthority(
        case_matrices=FakeCaseMatrices(
            issue_matrix=(
                FakeIssue(
                    issue_analysis_id=
                        ISSUE_ID,
                    element_records=(
                        FakeElement(
                            element_id=
                                "EK-INFORMATION",
                            element_name=
                                "Information available to the employer",
                            legal_question=
                                "What information about disability was available?",
                        ),
                        FakeElement(
                            element_id=
                                "EK-RECIPIENT",
                            element_name=
                                "Who received the information",
                            legal_question=
                                "Which CACI personnel received it?",
                        ),
                    ),
                ),
                FakeIssue(
                    issue_analysis_id=
                        "81744366-4784-4e8d-8079-68a79aa174b4",
                    element_records=(
                        FakeElement(
                            element_id=
                                "LIM-ACTS",
                            element_name=
                                "Acts or omissions",
                            legal_question=
                                "Which acts or omissions are relied upon?",
                        ),
                    ),
                ),
            ),
        )
    )


def test_d1i2_unreceipted_progress_is_not_scope_eligible() -> None:
    progress = FakeProgress(
        progress_id=
            "11111111-1111-4111-8111-111111111111"
    )

    rows = (
        case_operator
        ._task_work_scope_capture_rows(
            history=(progress,),
            receipts=(),
            scopes=(),
        )
    )

    assert rows == ()


def test_d1i2_joins_only_exact_receipt_progress_id() -> None:
    first = FakeProgress(
        progress_id=
            "11111111-1111-4111-8111-111111111111"
    )

    second = FakeProgress(
        progress_id=
            "22222222-2222-4222-8222-222222222222"
    )

    receipt = FakeReceipt(
        progress_id=
            second.progress_id
    )

    rows = (
        case_operator
        ._task_work_scope_capture_rows(
            history=(
                first,
                second,
            ),
            receipts=(
                receipt,
            ),
            scopes=(),
        )
    )

    assert rows == (
        (
            second,
            receipt,
            None,
        ),
    )


def test_d1i2_existing_scope_is_read_from_same_progress_join() -> None:
    progress = FakeProgress(
        progress_id=
            "11111111-1111-4111-8111-111111111111"
    )

    receipt = FakeReceipt(
        progress_id=
            progress.progress_id
    )

    scope = FakeScope(
        progress_id=
            progress.progress_id
    )

    rows = (
        case_operator
        ._task_work_scope_capture_rows(
            history=(progress,),
            receipts=(receipt,),
            scopes=(scope,),
        )
    )

    assert rows == (
        (
            progress,
            receipt,
            scope,
        ),
    )


def test_d1i2_rejects_duplicate_receipts_for_progress() -> None:
    progress = FakeProgress(
        progress_id=
            "11111111-1111-4111-8111-111111111111"
    )

    receipt = FakeReceipt(
        progress_id=
            progress.progress_id
    )

    with pytest.raises(
        case_operator.TaskWorkAuthorityScopeError,
        match="more than one retrieval receipt",
    ):
        case_operator._task_work_scope_capture_rows(
            history=(progress,),
            receipts=(
                receipt,
                receipt,
            ),
            scopes=(),
        )


def test_d1i2_rejects_orphan_receipt() -> None:
    with pytest.raises(
        case_operator.TaskWorkAuthorityScopeError,
        match="no matching persisted task-work",
    ):
        case_operator._task_work_scope_capture_rows(
            history=(),
            receipts=(
                FakeReceipt(
                    progress_id=
                        "11111111-1111-4111-8111-111111111111"
                ),
            ),
            scopes=(),
        )


def test_d1i2_scope_options_come_only_from_task_exact_issue() -> None:
    issue, elements = (
        case_operator
        ._task_work_scope_issue_elements(
            authority=
                make_authority(),
            task=
                FakeTask(),
        )
    )

    assert (
        issue.issue_analysis_id
        == ISSUE_ID
    )

    assert tuple(
        element.element_id
        for element in elements
    ) == (
        "EK-INFORMATION",
        "EK-RECIPIENT",
    )

    assert "LIM-ACTS" not in {
        element.element_id
        for element in elements
    }


def test_d1i2_reviewer_reference_uses_canonical_email(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        case_operator,
        "current_user_identity",
        lambda: SimpleNamespace(
            user_id=
                "39a7aa9d-3cba-5441-a0c7-58f9315cff42",
            email=
                "reviewer@example.test",
        ),
    )

    assert (
        case_operator
        ._current_scope_reviewer_reference()
        == "reviewer@example.test"
    )


def test_d1i2_no_receipt_means_no_authority_or_scope_load(
    monkeypatch,
) -> None:
    progress = FakeProgress(
        progress_id=
            "11111111-1111-4111-8111-111111111111"
    )

    monkeypatch.setattr(
        case_operator,
        "load_task_work_retrieval_receipts",
        lambda case_id, task_id: (),
    )

    def forbidden(*args, **kwargs):
        pytest.fail(
            "unreceipted work must not load scope or authority"
        )

    monkeypatch.setattr(
        case_operator,
        "load_task_work_authority_scopes",
        forbidden,
    )

    monkeypatch.setattr(
        case_operator,
        "load_active_governed_analytical_authority",
        forbidden,
    )

    case_operator._render_task_work_scope_capture(
        case_id=CASE_ID,
        task=FakeTask(),
        history=(progress,),
    )


def test_d1i2_does_not_modify_provider_persistence_path() -> None:
    source = inspect.getsource(
        case_operator._persist_task_work_result
    )

    assert (
        "record_task_work_authority_scope"
        not in source
    )

    assert (
        "load_task_work_authority_scopes"
        not in source
    )

    assert (
        "Set work scope"
        not in source
    )


def test_d1i2_scope_render_is_after_persisted_history() -> None:
    source = inspect.getsource(
        case_operator
        ._render_approved_task_execution
    )

    history_index = source.index(
        "_render_task_work_history(history=history)"
    )

    scope_index = source.index(
        "_render_task_work_scope_capture("
    )

    substantive_index = source.index(
        "substantive_history = "
        "_substantive_task_work_history(history)"
    )

    assert (
        history_index
        < scope_index
        < substantive_index
    )


def test_d1i2_source_has_no_automatic_scope_recording() -> None:
    source = Path(
        case_operator.__file__
    ).read_text(
        encoding="utf-8"
    )

    persist_source = inspect.getsource(
        case_operator._persist_task_work_result
    )

    assert (
        "record_task_work_authority_scope"
        in source
    )

    assert (
        "record_task_work_authority_scope"
        not in persist_source
    )

    helper_source = inspect.getsource(
        case_operator
        ._render_task_work_scope_capture
    )

    assert (
        'st.form_submit_button(\n'
        '                    "Set work scope"'
        in helper_source
    )

    assert (
        "selected_element_ids"
        in helper_source
    )

    assert (
        "current_user_identity"
        in helper_source
    )

    assert (
        ".email"
        not in helper_source
    )

    assert (
        'getattr(\n'
        '                    identity,\n'
        '                    "email",'
        in helper_source
    )