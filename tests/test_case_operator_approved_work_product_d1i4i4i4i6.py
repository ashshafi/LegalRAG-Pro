from pathlib import Path
import ast


CASE_OPERATOR = Path(
    "src/ui/case_operator.py"
)


def _source() -> str:
    return CASE_OPERATOR.read_text(
        encoding="utf-8-sig"
    )


def _function_source(name: str) -> str:
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


def test_case_operator_loads_read_only_approved_products_persistently():
    source = _function_source(
        "_render_saved_working_drafts"
    )

    assert (
        "load_approved_working_draft_products("
        in source
    )
    assert (
        "approved_by_draft_id"
        in source
    )


def test_saved_draft_cards_show_solicitor_facing_approved_status():
    source = _function_source(
        "_render_saved_working_drafts"
    )

    assert (
        "Approved for internal professional reliance"
        in source
    )
    assert (
        "Not approved for court or tribunal reliance"
        in source
    )
    assert (
        "Approved by "
        in source
    )


def test_unapproved_saved_drafts_keep_working_material_status():
    source = _function_source(
        "_render_saved_working_drafts"
    )

    assert (
        "Working material only - not approval for reliance."
        in source
    )


def test_approved_surface_does_not_display_internal_identifiers():
    source = _function_source(
        "_render_saved_working_drafts"
    )

    forbidden_visible_fragments = (
        "BINDING ID",
        "ARTIFACT SHA",
        "TARGET ID",
        "projection_payload_sha256",
    )

    for fragment in forbidden_visible_fragments:
        assert fragment not in source


def test_case_operator_approved_surface_is_read_only():
    source = _function_source(
        "_render_saved_working_drafts"
    )

    forbidden = (
        "record_work_product_release(",
        "publish_artifact(",
        "record_prepared_working_draft(",
        "update_task(",
    )

    for token in forbidden:
        assert token not in source


def test_reports_and_sidebar_are_not_imported_by_approved_read_model():
    source = Path(
        "src/drafting_approved_work_product.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert "ui.reports" not in source
    assert "ui.sidebar" not in source