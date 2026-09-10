from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from ui import matter_analysis_ledger as ledger_ui


def _item(
    *,
    authority="authority-current",
    issue="issue-1",
    element="element-1",
    reviewers=(),
):
    events = tuple(
        NS(reviewer_reference=value)
        for value in reviewers
    )
    return NS(
        run=NS(active_authority_id=authority),
        observation=NS(
            issue_analysis_id=issue,
            element_id=element,
        ),
        review_events=events,
        review_projection=(NS(state="reviewed") if events else None),
    )


def test_i3_projects_only_exact_current_authority_issue_and_element():
    items = (
        _item(reviewers=("Jane Solicitor", "Jane Solicitor")),
        _item(),
        _item(authority="authority-old", reviewers=("Old Reviewer",)),
        _item(issue="issue-2", reviewers=("Other Issue Reviewer",)),
        _item(element="element-2", reviewers=("Other Element Reviewer",)),
    )

    result = ledger_ui._swr1_i3_project_ai_review_activity(
        items,
        authority_id="authority-current",
        issue_analysis_id="issue-1",
        element_id="element-1",
    )

    assert result == {
        "finding_count": 2,
        "reviewed_finding_count": 1,
        "review_event_count": 2,
        "awaiting_review_count": 1,
        "reviewers": ("Jane Solicitor",),
    }


def test_i3_unreviewed_means_new_ai_finding_awaiting_review_only():
    result = ledger_ui._swr1_i3_project_ai_review_activity(
        (_item(),),
        authority_id="authority-current",
        issue_analysis_id="issue-1",
        element_id="element-1",
    )
    assert result["finding_count"] == 1
    assert result["reviewed_finding_count"] == 0
    assert result["review_event_count"] == 0
    assert result["awaiting_review_count"] == 1
    assert result["reviewers"] == ()


def test_i3_read_only_loader_fails_closed_without_inventing_state(monkeypatch):
    def fail(*, case_id):
        raise ledger_ui.ProfessionalReviewInboxError("read failure")

    monkeypatch.setattr(
        ledger_ui,
        "load_professional_review_inbox",
        fail,
    )

    assert ledger_ui._swr1_i3_load_ai_review_activity(
        case_id="case-1",
        authority_id="authority-current",
        issue_analysis_id="issue-1",
        element_id="element-1",
    ) is None


def test_i3_render_never_uses_ai_reviewer_as_professional_adopter(monkeypatch):
    class FakeStreamlit:
        def __init__(self):
            self.markdowns = []
            self.writes = []
            self.captions = []

        def markdown(self, value):
            self.markdowns.append(str(value))

        def write(self, value):
            self.writes.append(str(value))

        def caption(self, value):
            self.captions.append(str(value))

    fake = FakeStreamlit()
    monkeypatch.setattr(ledger_ui, "st", fake)
    monkeypatch.setattr(
        ledger_ui,
        "_swr1_i3_load_ai_review_activity",
        lambda **kwargs: {
            "finding_count": 1,
            "reviewed_finding_count": 1,
            "review_event_count": 1,
            "awaiting_review_count": 0,
            "reviewers": ("Jane Solicitor",),
        },
    )

    ledger_ui._swr1_i3_render_professional_status(
        case_id="case-1",
        authority_id="authority-current",
        issue_analysis_id="issue-1",
        element_id="element-1",
    )

    adoption = next(
        value
        for value in fake.writes
        if value.startswith("**Professional adoption:**")
    )
    adopted_at = next(
        value
        for value in fake.writes
        if value.startswith("**Last adopted / activated:**")
    )

    assert adoption.endswith(
        "Not recorded in the current assessment metadata"
    )
    assert adopted_at.endswith(
        "Not recorded in the current assessment metadata"
    )
    assert "Jane Solicitor" not in adoption
    assert "Jane Solicitor" not in adopted_at
    assert any(
        value == "Reviewers recorded for AI findings: Jane Solicitor"
        for value in fake.captions
    )
    assert any(
        "separate from professional adoption" in value
        for value in fake.captions
    )


def test_i3_source_places_status_inside_current_assessment_without_governance_mutation():
    source = Path("src/ui/matter_analysis_ledger.py").read_text(
        encoding="utf-8-sig"
    )
    tree = ast.parse(source)

    assert "### Current assessment" in source
    assert "**Current case assessment:** " in source
    assert "#### Professional status" in source
    assert (
        "**Professional adoption:** "
        in source
    )
    assert (
        "Not recorded in the current assessment metadata"
        in source
    )
    assert "**AI review activity:** " in source
    assert "**New AI findings awaiting review:** " in source
    assert "Reviewers recorded for AI findings: " in source

    load_fn = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_swr1_i3_load_ai_review_activity"
    )
    calls = {
        node.func.id
        for node in ast.walk(load_fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
    }
    assert "load_professional_review_inbox" in calls
    assert "review_agent_observation" not in calls
    assert "publish_professional_review_event" not in calls
    assert "propose_analytical_change_from_professional_review" not in calls
    assert "activate_governed_analytical_authority" not in calls


def test_i3_does_not_extract_adopter_or_date_from_activation_metadata():
    source = Path("src/ui/matter_analysis_ledger.py").read_text(
        encoding="utf-8-sig"
    )
    renderer = ast.get_source_segment(
        source,
        next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_swr1_i3_render_professional_status"
        ),
    )
    assert renderer is not None

    for forbidden in (
        "reviewer_reference",
        "activation_receipt.",
        "active_pointer.",
        "reviewed_at_utc",
        "created_at",
        "datetime.now",
        "date.today",
    ):
        assert forbidden not in renderer
