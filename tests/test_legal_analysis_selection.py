"""Tests for durable Sprint 2.3 Milestone 2 selection records."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from legal_analysis.enums import Confidence  # noqa: E402
from legal_analysis.registry import DEFAULT_ISSUE_DEFINITION_REGISTRY  # noqa: E402
from legal_analysis.selection import (  # noqa: E402
    ISSUE_SELECTOR_VERSION,
    IssueSelection,
    IssueSelectionAmbiguity,
    IssueSelectionRole,
    SelectedIssue,
    dumps_issue_selection,
    issue_selection_from_dict,
    issue_selection_to_dict,
    loads_issue_selection,
    validate_selection_against_registry,
)


def _selected(issue_id: str, role: IssueSelectionRole) -> SelectedIssue:
    definition = DEFAULT_ISSUE_DEFINITION_REGISTRY.get_definition(issue_id)
    return SelectedIssue(
        issue_definition_id=definition.definition_id,
        issue_definition_version=definition.version,
        issue_name=definition.name,
        selection_role=role,
        selection_rationale="The question matches this controlled issue definition.",
        confidence=Confidence.HIGH,
    )


def test_selected_issue_keeps_exact_definition_version() -> None:
    selected = _selected("EK-001", IssueSelectionRole.PRIMARY)
    assert selected.key == ("EK-001", "1.0")


def test_issue_selection_round_trip_is_identical() -> None:
    value = IssueSelection(
        user_question="What did CACI know about my disability?",
        normalized_question="what did caci know about my disability?",
        primary_issue=_selected("EK-001", IssueSelectionRole.PRIMARY),
        related_issues=(_selected("RA-001", IssueSelectionRole.RELATED),),
        not_selected_issues=(
            _selected("DA-001", IssueSelectionRole.NOT_SELECTED),
            _selected("LIM-001", IssueSelectionRole.NOT_SELECTED),
        ),
        ambiguities=(),
        selection_rationale="The question principally concerns employer knowledge.",
        confidence=Confidence.HIGH,
        selector_version=ISSUE_SELECTOR_VERSION,
        created_at=datetime(2026, 8, 2, 20, 0, tzinfo=timezone.utc),
    )
    restored = loads_issue_selection(dumps_issue_selection(value))
    assert restored == value
    assert issue_selection_from_dict(issue_selection_to_dict(value)) == value


def test_issue_selection_json_is_deterministic() -> None:
    value = IssueSelection(
        user_question="Is the claim out of time?",
        primary_issue=_selected("LIM-001", IssueSelectionRole.PRIMARY),
        not_selected_issues=(
            _selected("DA-001", IssueSelectionRole.NOT_SELECTED),
            _selected("EK-001", IssueSelectionRole.NOT_SELECTED),
            _selected("RA-001", IssueSelectionRole.NOT_SELECTED),
        ),
        selection_rationale="The question concerns limitation.",
        confidence=Confidence.HIGH,
        created_at=datetime(2026, 8, 2, 20, 0, tzinfo=timezone.utc),
    )
    assert dumps_issue_selection(value) == dumps_issue_selection(value)


def test_issue_selection_rejects_empty_question() -> None:
    with pytest.raises(ValueError, match="user_question"):
        IssueSelection(
            user_question="   ",
            primary_issue=None,
            selection_rationale="No issue selected.",
        )


def test_issue_selection_rejects_bad_selector_version() -> None:
    with pytest.raises(ValueError, match="selector_version"):
        IssueSelection(
            user_question="Question",
            primary_issue=None,
            selection_rationale="No issue selected.",
            selector_version="selector-latest",
        )


def test_issue_selection_rejects_primary_with_wrong_role() -> None:
    with pytest.raises(ValueError, match="PRIMARY"):
        IssueSelection(
            user_question="Question",
            primary_issue=_selected("EK-001", IssueSelectionRole.RELATED),
            selection_rationale="Issue routing.",
        )


def test_issue_selection_rejects_issue_in_multiple_roles() -> None:
    with pytest.raises(ValueError, match="multiple selection roles"):
        IssueSelection(
            user_question="Question",
            primary_issue=_selected("EK-001", IssueSelectionRole.PRIMARY),
            related_issues=(_selected("EK-001", IssueSelectionRole.RELATED),),
            selection_rationale="Issue routing.",
        )


def test_ambiguity_requires_candidates() -> None:
    with pytest.raises(ValueError, match="candidate_issue_definition_ids"):
        IssueSelectionAmbiguity(
            description="Ambiguous question",
            candidate_issue_definition_ids=(),
            reason="No legal mechanism identified.",
        )


def test_registry_validation_rejects_unknown_issue() -> None:
    selection = IssueSelection(
        user_question="Question",
        primary_issue=SelectedIssue(
            issue_definition_id="ZZ-999",
            issue_definition_version="1.0",
            issue_name="Invented issue",
            selection_role=IssueSelectionRole.PRIMARY,
            selection_rationale="Invented.",
            confidence=Confidence.HIGH,
        ),
        selection_rationale="Routing.",
    )
    with pytest.raises(KeyError):
        validate_selection_against_registry(
            selection, DEFAULT_ISSUE_DEFINITION_REGISTRY
        )


def test_registry_validation_rejects_wrong_name_for_valid_key() -> None:
    selection = IssueSelection(
        user_question="Question",
        primary_issue=SelectedIssue(
            issue_definition_id="EK-001",
            issue_definition_version="1.0",
            issue_name="Wrong title",
            selection_role=IssueSelectionRole.PRIMARY,
            selection_rationale="Knowledge question.",
            confidence=Confidence.HIGH,
        ),
        selection_rationale="Routing.",
    )
    with pytest.raises(ValueError, match="name mismatch"):
        validate_selection_against_registry(
            selection, DEFAULT_ISSUE_DEFINITION_REGISTRY
        )


def test_ambiguity_registry_validation_rejects_unknown_candidate() -> None:
    selection = IssueSelection(
        user_question="Question",
        primary_issue=None,
        ambiguities=(
            IssueSelectionAmbiguity(
                description="Ambiguous",
                candidate_issue_definition_ids=("RA-001", "ZZ-999"),
                reason="Multiple possibilities.",
            ),
        ),
        selection_rationale="Ambiguous routing.",
    )
    with pytest.raises(ValueError, match="unregistered"):
        validate_selection_against_registry(
            selection, DEFAULT_ISSUE_DEFINITION_REGISTRY
        )
