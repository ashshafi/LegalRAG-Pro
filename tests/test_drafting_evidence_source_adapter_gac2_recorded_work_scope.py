from types import SimpleNamespace

import pytest

from drafting_evidence_source_adapter import (
    DraftingEvidenceSourceError,
    _generation_evidence_keys_for_recorded_work,
    generation_evidence_keys,
)


AGGREGATE_SCHEMA = "gac2-aggregate-evidence-search-receipt/v1"


def _element(*keys):
    return SimpleNamespace(
        element_id="RA-ADJUSTMENT",
        supporting_evidence_keys=tuple(keys),
        adverse_evidence_keys=(),
        conflicting_evidence_keys=(),
    )


def _receipt(
    *,
    schema=None,
    answer_scope=(),
    relied=(),
    sources=(),
    bindings=(),
):
    return SimpleNamespace(
        answer_scope_evidence_keys=tuple(answer_scope),
        relied_evidence_keys=tuple(relied),
        sources=tuple(sources),
        answer_statement_bindings=tuple(bindings),
        evidence_search_receipt=(
            {"schema": schema, "step_receipts": [{}]}
            if schema is not None
            else None
        ),
    )


def _source(key):
    return {"evidence_key": key}


def test_gac2_empty_explicit_scope_uses_recorded_work_relied_evidence():
    receipt = _receipt(
        schema=AGGREGATE_SCHEMA,
        relied=("vacancy-2", "vacancy-1"),
        sources=(_source("vacancy-1"), _source("vacancy-2")),
        bindings=(
            {
                "evidence_keys": ["old-current-assessment"],
                "source_proposition_refs": [
                    {"element_id": "RA-ADJUSTMENT"},
                ],
            },
        ),
    )

    assert _generation_evidence_keys_for_recorded_work(
        retrieval_receipt=receipt,
        element=_element("old-current-assessment"),
    ) == ("vacancy-1", "vacancy-2")


def test_gac2_relied_scope_must_exist_in_receipt_sources():
    receipt = _receipt(
        schema=AGGREGATE_SCHEMA,
        relied=("vacancy-1", "missing"),
        sources=(_source("vacancy-1"),),
    )

    with pytest.raises(
        DraftingEvidenceSourceError,
        match="not fully represented",
    ):
        _generation_evidence_keys_for_recorded_work(
            retrieval_receipt=receipt,
            element=_element("old"),
        )


def test_gac2_duplicate_relied_keys_fail_closed():
    receipt = _receipt(
        schema=AGGREGATE_SCHEMA,
        relied=("e1", "e1"),
        sources=(_source("e1"),),
    )

    with pytest.raises(
        DraftingEvidenceSourceError,
        match="duplicate relied evidence keys",
    ):
        _generation_evidence_keys_for_recorded_work(
            retrieval_receipt=receipt,
            element=_element("old"),
        )


def test_explicit_answer_scope_remains_legacy_authoritative_path():
    receipt = _receipt(
        schema=AGGREGATE_SCHEMA,
        answer_scope=("explicit",),
        relied=("vacancy",),
        sources=(_source("vacancy"),),
    )

    expected = generation_evidence_keys(
        retrieval_receipt=receipt,
        element=_element("explicit", "vacancy"),
    )
    actual = _generation_evidence_keys_for_recorded_work(
        retrieval_receipt=receipt,
        element=_element("explicit", "vacancy"),
    )

    assert actual == expected == ("explicit",)


def test_non_gac2_behavior_delegates_to_legacy_r9_scope():
    receipt = _receipt(
        bindings=(
            {
                "evidence_keys": ["bound"],
                "source_proposition_refs": [
                    {"element_id": "RA-ADJUSTMENT"},
                ],
            },
        ),
    )

    expected = generation_evidence_keys(
        retrieval_receipt=receipt,
        element=_element("old"),
    )
    actual = _generation_evidence_keys_for_recorded_work(
        retrieval_receipt=receipt,
        element=_element("old"),
    )

    assert actual == expected
