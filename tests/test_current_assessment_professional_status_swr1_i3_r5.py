from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace as NS

from ui import swd1_issue_workspace as swd1


def _item(
    *,
    authority="authority-current",
    issue="issue-1",
    reviewers=(),
):
    events = tuple(
        NS(reviewer_reference=value)
        for value in reviewers
    )
    return NS(
        run=NS(active_authority_id=authority),
        observation=NS(issue_analysis_id=issue),
        review_events=events,
        review_projection=(NS(state="reviewed") if events else None),
    )


def test_i3_r5_projects_only_exact_active_authority_and_issue():
    result = swd1._swr1_i3_project_issue_ai_review_activity(
        (
            _item(reviewers=("Jane Reviewer",)),
            _item(),
            _item(authority="authority-old", reviewers=("Old Reviewer",)),
            _item(issue="issue-2", reviewers=("Other Issue Reviewer",)),
        ),
        authority_id="authority-current",
        issue_analysis_id="issue-1",
    )

    assert result == {
        "finding_count": 2,
        "reviewed_finding_count": 1,
        "review_event_count": 1,
        "awaiting_review_count": 1,
        "reviewers": ("Jane Reviewer",),
    }


def test_i3_r5_render_never_uses_ai_reviewer_as_professional_adopter(monkeypatch):
    class FakeContainer:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeStreamlit:
        def __init__(self):
            self.subheaders = []
            self.writes = []
            self.captions = []

        def container(self, **kwargs):
            return FakeContainer()

        def subheader(self, value):
            self.subheaders.append(str(value))

        def write(self, value):
            self.writes.append(str(value))

        def caption(self, value):
            self.captions.append(str(value))

    fake = FakeStreamlit()
    monkeypatch.setattr(swd1, "st", fake)
    monkeypatch.setattr(
        swd1,
        "_swr1_i3_load_issue_ai_review_activity",
        lambda **kwargs: {
            "finding_count": 1,
            "reviewed_finding_count": 1,
            "review_event_count": 1,
            "awaiting_review_count": 0,
            "reviewers": ("Jane Reviewer",),
        },
    )

    swd1._swr1_i3_render_issue_professional_status(
        case_id="case-1",
        authority_id="authority-current",
        issue_analysis_id="issue-1",
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
    assert "Jane Reviewer" not in adoption
    assert "Jane Reviewer" not in adopted_at
    assert any(
        value == "Reviewers recorded for AI findings: Jane Reviewer"
        for value in fake.captions
    )


def test_i3_r5_current_swd1_surface_places_professional_status_after_current_position():
    source = Path("src/ui/swd1_issue_workspace.py").read_text(
        encoding="utf-8-sig"
    )
    tree = ast.parse(source)
    show = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "show_swd1_issue_workspace"
    )
    segment = ast.get_source_segment(source, show)
    assert segment is not None

    current = segment.find('st.caption(_solicitor_working_text("CURRENT POSITION"))')
    status = segment.find("_swr1_i3_render_issue_professional_status(")
    question = segment.find('"Question to work on"')

    assert current >= 0
    assert status > current
    assert question > status


def test_i3_r5_loader_is_read_only_only():
    source = Path("src/ui/swd1_issue_workspace.py").read_text(
        encoding="utf-8-sig"
    )
    tree = ast.parse(source)
    loader = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_swr1_i3_load_issue_ai_review_activity"
    )
    segment = ast.get_source_segment(source, loader)
    assert segment is not None
    assert "load_professional_review_inbox" in segment

    for forbidden in (
        "review_agent_observation",
        "publish_professional_review_event",
        "propose_analytical_change_from_professional_review",
        "review_analytical_change",
        "activate_governed_analytical_authority",
        "publish_governed_analytical_authority",
        "create_task",
        "update_task",
    ):
        assert forbidden not in segment


def test_i3_r5_adopter_and_date_are_not_derived_from_other_metadata():
    source = Path("src/ui/swd1_issue_workspace.py").read_text(
        encoding="utf-8-sig"
    )
    tree = ast.parse(source)
    renderer = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_swr1_i3_render_issue_professional_status"
    )
    segment = ast.get_source_segment(source, renderer)
    assert segment is not None

    for forbidden in (
        "reviewer_reference",
        "activation_receipt",
        "active_pointer",
        "reviewed_at_utc",
        "created_at",
        "datetime.now",
        "date.today",
    ):
        assert forbidden not in segment
