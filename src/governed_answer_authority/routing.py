"""Selector-only routing into an already-active frozen analytical authority."""

from __future__ import annotations

from typing import Any

from legal_analysis.selector import DeterministicIssueSelector

from .models import AnalyticalAuthorityMode, AuthorityRoutingResult


def route_question_to_active_authority(
    *,
    question: str,
    case_id: str,
    authority: Any,
    selector: DeterministicIssueSelector | None = None,
) -> AuthorityRoutingResult:
    """Route a current question to exactly one pre-existing frozen analysis.

    This function performs issue selection only. It never retrieves evidence, maps,
    assesses, renders, rebuilds matrices, constructs U9B/U9C-B1, or mutates authority.
    """

    service = selector or DeterministicIssueSelector()
    selection = service.select(question, case_id=case_id)

    if selection.primary_issue is None:
        return AuthorityRoutingResult(
            mode=AnalyticalAuthorityMode.UNAVAILABLE,
            reason="No registered primary issue could be selected for the current question.",
            selector_version=selection.selector_version,
        )
    if selection.ambiguities:
        return AuthorityRoutingResult(
            mode=AnalyticalAuthorityMode.UNAVAILABLE,
            reason="The current question is analytically ambiguous under the controlled selector.",
            selector_version=selection.selector_version,
        )

    primary = selection.primary_issue
    matches = tuple(
        result
        for result in authority.structured_legal_analysis_results
        if result.issue_definition_id == primary.issue_definition_id
        and result.issue_definition_version == primary.issue_definition_version
    )

    if not matches:
        return AuthorityRoutingResult(
            mode=AnalyticalAuthorityMode.UNAVAILABLE,
            reason="The active authority contains no exact frozen analysis for the selected issue.",
            issue_definition_id=primary.issue_definition_id,
            issue_definition_version=primary.issue_definition_version,
            issue_name=primary.issue_name,
            selector_version=selection.selector_version,
        )
    if len(matches) != 1:
        return AuthorityRoutingResult(
            mode=AnalyticalAuthorityMode.UNAVAILABLE,
            reason="The active authority contains multiple compatible frozen analyses; no heuristic choice is permitted.",
            issue_definition_id=primary.issue_definition_id,
            issue_definition_version=primary.issue_definition_version,
            issue_name=primary.issue_name,
            selector_version=selection.selector_version,
        )

    selected = matches[0]
    if selected.case_id != case_id:
        raise ValueError("Selected frozen analysis belongs to a different case.")
    if selected.issue_analysis_id not in authority.manifest.source_analysis_ids:
        raise ValueError("Selected frozen analysis is not bound by the active authority manifest.")

    return AuthorityRoutingResult(
        mode=AnalyticalAuthorityMode.APPLIED,
        reason="Exactly one existing frozen analysis matched the controlled primary issue.",
        issue_analysis_id=selected.issue_analysis_id,
        issue_definition_id=selected.issue_definition_id,
        issue_definition_version=selected.issue_definition_version,
        issue_name=primary.issue_name,
        selector_version=selection.selector_version,
    )


__all__ = ["route_question_to_active_authority"]
