from types import SimpleNamespace

import pytest

import drafting_working_draft_generation as generation


AGGREGATE_SCHEMA = "gac2-aggregate-evidence-search-receipt/v1"


def _receipt(payload):
    return SimpleNamespace(
        evidence_search_receipt=payload,
    )


def _flat_receipt(*, docs=2):
    return {
        "search_mode": "document_complete",
        "completion": "complete",
        "negative_finding_scope": "searched_scope",
        "negative_finding_permitted": True,
        "case_corpus_complete": False,
        "scope_document_count": docs,
        "documents_completely_expanded": docs,
        "scope_page_count": 10,
        "pages_inspected": 10,
        "scope_chunk_count": 20,
        "chunks_inspected": 20,
    }


def test_legacy_flat_dispatch_preserves_original_return_contract():
    receipt = _receipt(_flat_receipt())

    expected = generation._validate_original_r68_coverage(
        receipt
    )
    actual = generation._validate_drafting_search_coverage(
        receipt
    )

    assert actual == expected


def test_gac2_aggregate_validates_every_step_without_flattening():
    actual = generation._validate_drafting_search_coverage(
        _receipt(
            {
                "schema": AGGREGATE_SCHEMA,
                "step_receipts": [
                    _flat_receipt(docs=2),
                    _flat_receipt(docs=3),
                ],
            }
        )
    )

    assert set(actual) == {
        "schema",
        "step_receipts",
    }
    assert actual["schema"] == AGGREGATE_SCHEMA
    assert len(actual["step_receipts"]) == 2
    assert actual["step_receipts"][0]["scope_document_count"] == 2
    assert actual["step_receipts"][1]["scope_document_count"] == 3


def test_gac2_aggregate_fails_closed_when_later_step_is_invalid():
    broken = _flat_receipt()
    broken.pop("search_mode")

    with pytest.raises(
        generation.DraftingWorkingDraftGenerationError,
        match="step 2 failed validation",
    ):
        generation._validate_drafting_search_coverage(
            _receipt(
                {
                    "schema": AGGREGATE_SCHEMA,
                    "step_receipts": [
                        _flat_receipt(),
                        broken,
                    ],
                }
            )
        )


def test_gac2_aggregate_rejects_empty_steps():
    with pytest.raises(
        generation.DraftingWorkingDraftGenerationError,
        match="has no step receipts",
    ):
        generation._validate_drafting_search_coverage(
            _receipt(
                {
                    "schema": AGGREGATE_SCHEMA,
                    "step_receipts": [],
                }
            )
        )
