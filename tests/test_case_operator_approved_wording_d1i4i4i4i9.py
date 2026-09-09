from __future__ import annotations

import ast
from pathlib import Path


CASE_OPERATOR = Path("src/ui/case_operator.py")


def _function_source(name: str) -> str:
    source = CASE_OPERATOR.read_text(
        encoding="utf-8-sig"
    )
    tree = ast.parse(
        source,
        filename=str(CASE_OPERATOR),
    )

    matches = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == name
    ]

    assert len(matches) == 1

    return ast.get_source_segment(
        source,
        matches[0],
    ) or ""


def _approved_guard() -> str:
    source = _function_source(
        "_render_saved_working_drafts"
    )

    start = source.index(
        "if selected_approved_product is not None:"
    )

    end = source.index(
        "_clear_drafting_professional_review_state()",
        start,
    )

    return source[start:end]


def test_approved_exact_draft_has_view_approved_wording_surface():
    guard = _approved_guard()

    assert "View approved wording" in guard
    assert '"approved_wording"' in guard
    assert (
        "Exact wording from the professionally approved saved draft."
        in guard
    )


def test_approved_wording_is_rendered_as_plain_solicitor_facing_statements():
    guard = _approved_guard()

    assert "**Statement " in guard
    assert "st.write(" in guard


def test_approved_wording_surface_exposes_no_governance_coordinates():
    guard = _approved_guard()

    forbidden = (
        "target_id",
        "event_id",
        "sha256:",
        "Draft ID:",
        "Draft authority:",
        "Review authority:",
        "Authority check:",
        "Current assessment:",
        "Evidence:",
    )

    for token in forbidden:
        assert token not in guard


def test_approved_wording_surface_has_no_release_or_rereview_action():
    guard = _approved_guard()

    forbidden = (
        "download_button",
        "Download approved",
        "Prepare professional review",
        "Approve for reliance",
        "Reject wording",
        "record_work_product_release(",
        "record_working_draft_professional_release(",
        "Re-review",
    )

    for token in forbidden:
        assert token not in guard


def test_professional_decision_surface_is_preserved_beside_approved_wording():
    guard = _approved_guard()

    assert "View professional decision" in guard
    assert "Professional review note" in guard
    assert "Not approved for court or tribunal reliance" in guard


def test_approved_guard_still_returns_before_unapproved_professional_review():
    source = _function_source(
        "_render_saved_working_drafts"
    )

    guard_index = source.index(
        "if selected_approved_product is not None:"
    )

    wording_index = source.index(
        "View approved wording",
        guard_index,
    )

    return_index = source.index(
        "            return",
        wording_index,
    )

    review_index = source.rindex(
        "_render_working_draft_professional_review("
    )

    assert (
        guard_index
        < wording_index
        < return_index
        < review_index
    )