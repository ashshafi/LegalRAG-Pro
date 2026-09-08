from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import drafting_approved_work_product as approved


READ_MODEL = Path(
    "src/drafting_approved_work_product.py"
)


def _loader_source() -> str:
    return inspect.getsource(
        approved.load_approved_working_draft_products
    )


def test_approved_product_exposes_professional_review_note():
    fields = tuple(
        field.name
        for field in dataclasses.fields(
            approved.ApprovedWorkingDraftProduct
        )
    )

    assert "review_note" in fields


def test_review_note_is_bound_to_projection_latest_event_and_exact_target():
    source = _loader_source()

    assert (
        "candidate"
        in source
    )
    assert (
        "projection.latest_event_id"
        in source
    )
    assert (
        '"event_id"'
        in source
    )
    assert (
        '"target_id"'
        in source
    )
    assert (
        "len(current_decision_events) != 1"
        in source
    )


def test_review_note_is_required_from_exact_current_decision_event():
    source = _loader_source()

    assert (
        "current_decision_event"
        in source
    )
    assert (
        '"review_note"'
        in source
    )
    assert (
        "review_note=review_note"
        .replace(" ", "")
        in source.replace(" ", "").replace("\n", "")
    )


def test_decision_detail_must_match_projected_reviewer_timestamp_and_reliance_scope():
    source = _loader_source()

    assert (
        "decision_recorded_at != approved_at"
        in source
    )
    assert (
        "decision_reviewer_reference != reviewer_reference"
        in source
    )
    assert (
        "court_or_tribunal_reliance"
        in source
    )


def test_read_model_remains_read_only_and_does_not_create_release_state():
    source = _loader_source()

    forbidden = (
        "record_work_product_release(",
        "publish_artifact(",
        "record_working_draft_professional_release(",
        "open(",
        "write_text(",
        "write_bytes(",
    )

    for token in forbidden:
        assert token not in source


def test_read_model_module_parses_after_i8_extension():
    ast.parse(
        READ_MODEL.read_text(
            encoding="utf-8-sig"
        )
    )