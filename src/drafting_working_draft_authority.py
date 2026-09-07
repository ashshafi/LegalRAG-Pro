"""Pure authority evaluation for immutable governed WORKING drafts.

The evaluator does not mutate the draft, analytical authority, Matter Analysis
Ledger, report projection or professional release state. It delegates every
statement-level authority decision to the existing work-product authority
checker.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from drafting_working_draft import (
    WorkingDraft,
    WorkingDraftStatement,
)
from matter_analysis_ledger import (
    build_matter_analysis_ledger,
)
from work_product_authority_checker import (
    WorkProductAuthorityCheck,
    check_work_product_authority,
)


class DraftingWorkingDraftAuthorityError(ValueError):
    """Raised when a working draft cannot be evaluated against current authority."""


@dataclass(frozen=True)
class WorkingDraftStatementAuthorityEvaluation:
    """Existing checker result for one exact immutable draft statement."""

    statement_id: str
    sequence: int
    element_id: str
    check: WorkProductAuthorityCheck


@dataclass(frozen=True)
class WorkingDraftAuthorityEvaluation:
    """Pure collection of statement checks; this is not a release decision."""

    draft_id: str
    case_id: str
    authority_id: str
    issue_analysis_id: str
    statement_evaluations: tuple[
        WorkingDraftStatementAuthorityEvaluation,
        ...,
    ]


def _required_text(
    value: object,
    label: str,
) -> str:
    text = str(value).strip()

    if not text:
        raise DraftingWorkingDraftAuthorityError(
            label + " is required."
        )

    return text


def _tuple_value(
    value: object,
    label: str,
) -> tuple[Any, ...]:
    if value is None:
        return ()

    if isinstance(
        value,
        (
            str,
            bytes,
        ),
    ):
        raise DraftingWorkingDraftAuthorityError(
            label + " must be a collection."
        )

    try:
        return tuple(value)
    except TypeError as exc:
        raise DraftingWorkingDraftAuthorityError(
            label + " must be a collection."
        ) from exc


def _current_authority_identity(
    authority: object,
) -> tuple[str, str]:
    try:
        manifest = authority.manifest
    except AttributeError as exc:
        raise DraftingWorkingDraftAuthorityError(
            "current governed authority does not expose a manifest."
        ) from exc

    case_id = _required_text(
        getattr(
            manifest,
            "case_id",
            "",
        ),
        "authority.manifest.case_id",
    )

    authority_id = _required_text(
        getattr(
            manifest,
            "authority_id",
            "",
        ),
        "authority.manifest.authority_id",
    )

    return (
        case_id,
        authority_id,
    )


def _issue_for_draft(
    *,
    ledger: object,
    draft: WorkingDraft,
) -> object:
    try:
        issues = tuple(
            ledger.issues
        )
    except (
        AttributeError,
        TypeError,
    ) as exc:
        raise DraftingWorkingDraftAuthorityError(
            "Matter Analysis Ledger does not expose governed issues."
        ) from exc

    matches = tuple(
        issue
        for issue in issues
        if _required_text(
            getattr(
                issue,
                "issue_analysis_id",
                "",
            ),
            "ledger issue_analysis_id",
        )
        == draft.issue_analysis_id
    )

    if len(matches) != 1:
        raise DraftingWorkingDraftAuthorityError(
            "working-draft issue is not uniquely present in current authority."
        )

    return matches[0]


def _elements_for_issue(
    issue: object,
) -> dict[str, object]:
    try:
        elements = tuple(
            issue.elements
        )
    except (
        AttributeError,
        TypeError,
    ) as exc:
        raise DraftingWorkingDraftAuthorityError(
            "governed issue does not expose analytical elements."
        ) from exc

    if not elements:
        raise DraftingWorkingDraftAuthorityError(
            "governed issue contains no analytical elements."
        )

    element_by_id: dict[
        str,
        object,
    ] = {}

    for element in elements:
        element_id = _required_text(
            getattr(
                element,
                "element_id",
                "",
            ),
            "ledger element_id",
        )

        if element_id in element_by_id:
            raise DraftingWorkingDraftAuthorityError(
                "governed issue contains duplicate element identities."
            )

        element_by_id[
            element_id
        ] = element

    return element_by_id


def _allowed_evidence_keys(
    element: object,
) -> tuple[str, ...]:
    supporting = _tuple_value(
        getattr(
            element,
            "supporting_evidence_keys",
            (),
        ),
        "supporting_evidence_keys",
    )

    adverse = _tuple_value(
        getattr(
            element,
            "adverse_evidence_keys",
            (),
        ),
        "adverse_evidence_keys",
    )

    corroborative = _tuple_value(
        getattr(
            element,
            "corroborative_evidence_keys",
            (),
        ),
        "corroborative_evidence_keys",
    )

    conflicting = _tuple_value(
        getattr(
            element,
            "conflicting_evidence_keys",
            (),
        ),
        "conflicting_evidence_keys",
    )

    keys = tuple(
        sorted(
            {
                _required_text(
                    key,
                    "allowed evidence key",
                )
                for key in (
                    supporting
                    + adverse
                    + corroborative
                    + conflicting
                )
            }
        )
    )

    return keys


def _evaluate_statement(
    *,
    statement: WorkingDraftStatement,
    element: object,
) -> WorkingDraftStatementAuthorityEvaluation:
    conflicting = _tuple_value(
        getattr(
            element,
            "conflicting_evidence_keys",
            (),
        ),
        "conflicting_evidence_keys",
    )

    unresolved = _tuple_value(
        getattr(
            element,
            "unresolved_matters",
            (),
        ),
        "unresolved_matters",
    )

    gaps = _tuple_value(
        getattr(
            element,
            "evidential_gap_ids",
            (),
        ),
        "evidential_gap_ids",
    )

    check = check_work_product_authority(
        statement=_required_text(
            statement.text,
            "statement text",
        ),
        current_status=_required_text(
            getattr(
                element,
                "analytical_status",
                "",
            ),
            "element analytical_status",
        ),
        current_confidence=_required_text(
            getattr(
                element,
                "analytical_confidence",
                "",
            ),
            "element analytical_confidence",
        ),
        claimed_status=_required_text(
            statement.claimed_status,
            "statement claimed_status",
        ),
        claimed_confidence=_required_text(
            statement.claimed_confidence,
            "statement claimed_confidence",
        ),
        cited_evidence_keys=tuple(
            statement.cited_evidence_keys
        ),
        allowed_evidence_keys=_allowed_evidence_keys(
            element
        ),
        approved_contradiction_count=len(
            conflicting
        ),
        unresolved_matter_count=len(
            unresolved
        ),
        formal_gap_count=len(
            gaps
        ),
    )

    return WorkingDraftStatementAuthorityEvaluation(
        statement_id=_required_text(
            statement.statement_id,
            "statement_id",
        ),
        sequence=statement.sequence,
        element_id=_required_text(
            statement.element_id,
            "statement element_id",
        ),
        check=check,
    )


def evaluate_working_draft_authority(
    *,
    draft: WorkingDraft,
    authority: object,
) -> WorkingDraftAuthorityEvaluation:
    """Evaluate every statement against its exact current governed element."""

    if not isinstance(
        draft,
        WorkingDraft,
    ):
        raise DraftingWorkingDraftAuthorityError(
            "draft must be a WorkingDraft."
        )

    (
        current_case_id,
        current_authority_id,
    ) = _current_authority_identity(
        authority
    )

    if draft.case_id != current_case_id:
        raise DraftingWorkingDraftAuthorityError(
            "working draft belongs to another case."
        )

    if draft.authority_id != current_authority_id:
        raise DraftingWorkingDraftAuthorityError(
            "working draft is bound to a stale governed authority."
        )

    ledger = build_matter_analysis_ledger(
        authority=authority,
        events=(),
    )

    ledger_authority_id = _required_text(
        getattr(
            ledger,
            "authority_id",
            "",
        ),
        "ledger.authority_id",
    )

    if ledger_authority_id != current_authority_id:
        raise DraftingWorkingDraftAuthorityError(
            "Matter Analysis Ledger authority does not match current authority."
        )

    issue = _issue_for_draft(
        ledger=ledger,
        draft=draft,
    )

    element_by_id = _elements_for_issue(
        issue
    )

    if not draft.statements:
        raise DraftingWorkingDraftAuthorityError(
            "working draft contains no statements."
        )

    evaluations: list[
        WorkingDraftStatementAuthorityEvaluation
    ] = []

    for statement in draft.statements:
        if not isinstance(
            statement,
            WorkingDraftStatement,
        ):
            raise DraftingWorkingDraftAuthorityError(
                "working draft contains an invalid statement object."
            )

        element_id = _required_text(
            statement.element_id,
            "statement element_id",
        )

        element = element_by_id.get(
            element_id
        )

        if element is None:
            raise DraftingWorkingDraftAuthorityError(
                "draft statement element is not present in the "
                "draft's current governed issue."
            )

        evaluations.append(
            _evaluate_statement(
                statement=statement,
                element=element,
            )
        )

    return WorkingDraftAuthorityEvaluation(
        draft_id=_required_text(
            draft.draft_id,
            "draft_id",
        ),
        case_id=draft.case_id,
        authority_id=current_authority_id,
        issue_analysis_id=draft.issue_analysis_id,
        statement_evaluations=tuple(
            evaluations
        ),
    )


__all__ = [
    "DraftingWorkingDraftAuthorityError",
    "WorkingDraftStatementAuthorityEvaluation",
    "WorkingDraftAuthorityEvaluation",
    "evaluate_working_draft_authority",
]