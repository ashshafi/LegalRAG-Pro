from pathlib import Path
import ast


CASE_OPERATOR = Path(
    "src/ui/case_operator.py"
)


def _source() -> str:
    return CASE_OPERATOR.read_text(
        encoding="utf-8-sig"
    )


def _function_source(
    name: str,
) -> str:
    source = _source()
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


def test_approved_selected_draft_uses_existing_persistent_read_model():
    source = _function_source(
        "_render_saved_working_drafts"
    )

    assert (
        "approved_by_draft_id.get("
        in source
    )
    assert (
        "selected_approved_product"
        in source
    )


def test_approved_selected_draft_exposes_view_professional_decision():
    source = _function_source(
        "_render_saved_working_drafts"
    )

    assert (
        '"View professional decision"'
        in source
    )
    assert (
        "Approved for internal professional reliance"
        in source
    )
    assert (
        "Not approved for court or tribunal reliance"
        in source
    )


def test_approved_selected_draft_returns_before_professional_review_entry():
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


def test_unapproved_selected_draft_still_enters_existing_professional_review():
    source = _function_source(
        "_render_saved_working_drafts"
    )

    assert (
        "_render_working_draft_professional_review("
        in source
    )


def test_approved_guard_does_not_write_release_or_working_draft_state():
    source = _function_source(
        "_render_saved_working_drafts"
    )

    forbidden = (
        "record_work_product_release(",
        "record_working_draft_professional_release(",
        "record_prepared_working_draft(",
        "publish_artifact(",
        "update_task(",
    )

    for token in forbidden:
        assert token not in source


def test_approved_guard_explains_that_normal_workflow_does_not_create_second_decision():
    source = _function_source(
        "_render_saved_working_drafts"
    )

    assert (
        "The normal solicitor workflow does not create a second decision."
        in source
    )


def test_professional_review_renderer_is_preserved_for_unapproved_drafts():
    source = _function_source(
        "_render_working_draft_professional_review"
    )

    assert (
        '"Prepare professional review"'
        in source
    )
    assert (
        '"Approve for reliance"'
        in source
    )
    assert (
        '"Reject wording"'
        in source
    )


def test_i7_does_not_add_deliberate_rereview_action():
    source = _function_source(
        "_render_saved_working_drafts"
    )

    forbidden_visible = (
        "Re-review",
        "Create another decision",
        "Override professional decision",
        "Change professional decision",
    )

    for text in forbidden_visible:
        assert text not in source