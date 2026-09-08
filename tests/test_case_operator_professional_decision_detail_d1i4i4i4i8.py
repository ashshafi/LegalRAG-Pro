from __future__ import annotations

import ast
from pathlib import Path


CASE_OPERATOR = Path(
    "src/ui/case_operator.py"
)


def _function_source(
    name: str,
) -> str:
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
        if isinstance(
            node,
            ast.FunctionDef,
        )
        and node.name == name
    ]

    assert len(matches) == 1

    return (
        ast.get_source_segment(
            source,
            matches[0],
        )
        or ""
    )


def _approved_decision_fragment() -> str:
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


def test_view_professional_decision_displays_exact_stored_review_note():
    fragment = _approved_decision_fragment()

    assert (
        '"review_note"'
        in fragment
    )
    assert (
        "**Professional review note**"
        in fragment
    )
    assert (
        "st.write("
        in fragment
    )
    assert (
        "review_note"
        in fragment
    )


def test_professional_decision_keeps_status_reviewer_date_and_court_scope():
    fragment = _approved_decision_fragment()

    assert (
        "Approved for internal professional reliance"
        in fragment
    )
    assert (
        "Approved by "
        in fragment
    )
    assert (
        "Not approved for court or tribunal reliance"
        in fragment
    )


def test_professional_decision_detail_hides_governance_coordinates():
    fragment = _approved_decision_fragment()

    forbidden = (
        "target_id",
        "event_id",
        "sha256:",
        "projection_payload_sha256",
        "manifest_id",
    )

    for token in forbidden:
        assert token not in fragment


def test_professional_decision_detail_does_not_create_another_decision():
    fragment = _approved_decision_fragment()

    forbidden = (
        "Prepare professional review",
        "Approve for reliance",
        "Reject wording",
        "record_work_product_release(",
        "record_working_draft_professional_release(",
        "Re-review",
        "Create another decision",
    )

    for token in forbidden:
        assert token not in fragment


def test_approved_guard_still_returns_before_unapproved_review_renderer():
    source = _function_source(
        "_render_saved_working_drafts"
    )

    guard_index = source.index(
        "if selected_approved_product is not None:"
    )

    return_index = source.index(
        "            return",
        guard_index,
    )

    review_index = source.rindex(
        "_render_working_draft_professional_review("
    )

    assert guard_index < return_index < review_index


def test_missing_note_is_presented_as_read_only_display_error_not_decision_action():
    fragment = _approved_decision_fragment()

    assert (
        "The stored professional review note could not be displayed."
        in fragment
    )
    assert (
        "st.error("
        in fragment
    )