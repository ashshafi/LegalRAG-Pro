"""Behavioural routing tests for Sprint 2.3 Milestone 2."""

from __future__ import annotations

import sys
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from legal_analysis.enums import Confidence  # noqa: E402
from legal_analysis.selection import IssueSelectionRole  # noqa: E402
from legal_analysis.selector import DeterministicIssueSelector  # noqa: E402


SELECTOR = DeterministicIssueSelector()


def _related_ids(result) -> tuple[str, ...]:
    return tuple(item.issue_definition_id for item in result.related_issues)


def _not_selected_ids(result) -> tuple[str, ...]:
    return tuple(item.issue_definition_id for item in result.not_selected_issues)


def test_acceptance_query_1_knowledge_primary_adjustments_related() -> None:
    result = SELECTOR.select("What evidence shows CACI knew about my disability?")
    assert result.primary_issue is not None
    assert result.primary_issue.issue_definition_id == "EK-001"
    assert result.primary_issue.issue_definition_version == "1.0"
    assert _related_ids(result) == ("RA-001",)
    assert result.primary_issue.selection_role is IssueSelectionRole.PRIMARY
    assert result.confidence is Confidence.HIGH


def test_acceptance_query_2_limitation_primary_only() -> None:
    result = SELECTOR.select("Is my claim out of time if the failures continued?")
    assert result.primary_issue is not None
    assert result.primary_issue.issue_definition_id == "LIM-001"
    assert _related_ids(result) == ()
    assert "continu" in result.primary_issue.selection_rationale.lower() or "limitation" in result.primary_issue.selection_rationale.lower()


def test_acceptance_query_3_work_from_home_routes_to_adjustments() -> None:
    result = SELECTOR.select(
        "Should CACI have allowed me to work from home because of my disability?"
    )
    assert result.primary_issue is not None
    assert result.primary_issue.issue_definition_id == "RA-001"
    assert _related_ids(result) == ("EK-001",)


def test_acceptance_query_4_discrimination_arising_primary() -> None:
    result = SELECTOR.select(
        "Was I treated unfavourably because of something arising from my disability?"
    )
    assert result.primary_issue is not None
    assert result.primary_issue.issue_definition_id == "DA-001"
    assert "EK-001" in _related_ids(result)


def test_acceptance_query_5_adjustments_primary_limitation_related() -> None:
    result = SELECTOR.select(
        "Did CACI fail to make reasonable adjustments and is that claim still in time because the failure continued?"
    )
    assert result.primary_issue is not None
    assert result.primary_issue.issue_definition_id == "RA-001"
    assert "LIM-001" in _related_ids(result)
    assert "EK-001" in _related_ids(result)


def test_acceptance_query_6_contract_is_unsupported() -> None:
    result = SELECTOR.select("Did CACI breach my employment contract?")
    assert result.primary_issue is None
    assert result.related_issues == ()
    assert not result.ambiguities
    assert "not represented" in result.selection_rationale.lower()
    assert set(_not_selected_ids(result)) == {"RA-001", "DA-001", "EK-001", "LIM-001"}


def test_acceptance_query_7_broad_discrimination_is_ambiguous() -> None:
    result = SELECTOR.select("Was what happened to me discriminatory?")
    assert result.primary_issue is None
    assert result.confidence is Confidence.LOW
    assert len(result.ambiguities) == 1
    assert result.ambiguities[0].candidate_issue_definition_ids == (
        "RA-001",
        "DA-001",
    )
    assert set(_not_selected_ids(result)) == {"EK-001", "LIM-001"}


def test_focus_sensitive_knowledge_question_beats_adjustment_context() -> None:
    result = SELECTOR.select("Did CACI know that I wanted a reasonable adjustment?")
    assert result.primary_issue is not None
    assert result.primary_issue.issue_definition_id == "EK-001"
    assert _related_ids(result)[0] == "RA-001"


def test_equivalent_knowledge_paraphrase_routes_identically() -> None:
    first = SELECTOR.select("What did CACI know about my disability?")
    second = SELECTOR.select("Was the company aware that I was disabled?")
    assert first.primary_issue is not None and second.primary_issue is not None
    assert first.primary_issue.key == second.primary_issue.key == ("EK-001", "1.0")


def test_repeated_identical_question_is_substantively_deterministic() -> None:
    question = "Should CACI have allowed me to work from home because of my disability?"
    first = SELECTOR.select(question)
    second = SELECTOR.select(question)
    assert first.primary_issue == second.primary_issue
    assert first.related_issues == second.related_issues
    assert first.not_selected_issues == second.not_selected_issues
    assert first.ambiguities == second.ambiguities
    assert first.selection_rationale == second.selection_rationale
    assert first.confidence == second.confidence


def test_limitation_with_explicit_adjustment_context_keeps_limitation_primary_when_focus_is_time() -> None:
    result = SELECTOR.select(
        "Is my reasonable adjustments claim out of time because the failure continued?"
    )
    assert result.primary_issue is not None
    assert result.primary_issue.issue_definition_id == "LIM-001"
    assert "RA-001" in _related_ids(result)


def test_discrimination_arising_with_limitation_adds_limitation_related() -> None:
    result = SELECTOR.select(
        "Was I treated unfavourably because of disability-related absence, and is that claim out of time?"
    )
    assert result.primary_issue is not None
    assert result.primary_issue.issue_definition_id == "DA-001"
    assert "LIM-001" in _related_ids(result)


def test_unfair_dismissal_is_not_invented() -> None:
    result = SELECTOR.select("Was I unfairly dismissed?")
    assert result.primary_issue is None
    assert "dismissal issue" in result.selection_rationale.lower()


def test_unknown_general_question_does_not_force_nearest_issue() -> None:
    result = SELECTOR.select("What should I do next?")
    assert result.primary_issue is None
    assert result.confidence is Confidence.LOW
    assert "selected reliably" in result.selection_rationale.lower()


def test_selection_rationale_is_about_routing_not_merits() -> None:
    result = SELECTOR.select("What evidence shows CACI knew about my disability?")
    text = " ".join(
        [result.selection_rationale]
        + [item.selection_rationale for item in result.all_selected_issues()]
    ).lower()
    assert "strong claim" not in text
    assert "probably knew" not in text
    assert "proves" not in text
    assert "likely to win" not in text
