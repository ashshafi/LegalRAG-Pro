from types import SimpleNamespace

import pytest

from drafting_evidence_source_adapter import (
    DraftingEvidenceSourceError,
    generation_evidence_keys,
)


def _element(*keys, element_id="RA-ADJUSTMENT"):
    return SimpleNamespace(
        element_id=element_id,
        supporting_evidence_keys=tuple(keys),
        adverse_evidence_keys=(),
        conflicting_evidence_keys=(),
    )


def _object_receipt(*, answer_scope=(), bindings=()):
    return SimpleNamespace(
        answer_scope_evidence_keys=answer_scope,
        answer_statement_bindings=tuple(bindings),
    )


def test_live_mapping_binding_is_read_from_dict_and_bound_to_selected_element():
    receipt = _object_receipt(
        answer_scope=(),
        bindings=(
            {
                "evidence_keys": ["new-evidence", "shared-evidence"],
                "source_proposition_refs": [
                    {"element_id": "RA-ADJUSTMENT"},
                    {"element_id": "RA-REASONABLENESS"},
                ],
            },
            {
                "evidence_keys": ["other-element-only"],
                "source_proposition_refs": [
                    {"element_id": "RA-TIMING"},
                ],
            },
        ),
    )

    assert generation_evidence_keys(
        retrieval_receipt=receipt,
        element=_element("frozen-old-evidence"),
    ) == ("new-evidence", "shared-evidence")


def test_mapping_binding_without_target_ref_falls_back_to_legacy_element_intersection():
    receipt = _object_receipt(
        answer_scope=(),
        bindings=(
            {
                "evidence_keys": ["e1", "foreign"],
                "source_proposition_refs": [
                    {"element_id": "RA-TIMING"},
                ],
            },
        ),
    )

    assert generation_evidence_keys(
        retrieval_receipt=receipt,
        element=_element("e1", "e2"),
    ) == ("e1",)


def test_explicit_answer_scope_remains_authoritative_over_statement_bindings():
    receipt = _object_receipt(
        answer_scope=("explicit",),
        bindings=(
            {
                "evidence_keys": ["new-evidence"],
                "source_proposition_refs": [
                    {"element_id": "RA-ADJUSTMENT"},
                ],
            },
        ),
    )

    assert generation_evidence_keys(
        retrieval_receipt=receipt,
        element=_element("explicit", "new-evidence"),
    ) == ("explicit",)


def test_empty_scope_and_empty_bindings_still_fail_closed():
    receipt = _object_receipt(answer_scope=(), bindings=())

    with pytest.raises(
        DraftingEvidenceSourceError,
        match="R68 answer scope contains no evidence keys",
    ):
        generation_evidence_keys(
            retrieval_receipt=receipt,
            element=_element("e1"),
        )


def test_object_binding_compatibility_is_preserved():
    binding = SimpleNamespace(
        evidence_keys=("e1",),
        source_proposition_refs=(
            SimpleNamespace(element_id="RA-ADJUSTMENT"),
        ),
    )
    receipt = _object_receipt(
        answer_scope=(),
        bindings=(binding,),
    )

    assert generation_evidence_keys(
        retrieval_receipt=receipt,
        element=_element("old"),
    ) == ("e1",)
