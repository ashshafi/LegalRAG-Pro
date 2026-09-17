from types import SimpleNamespace

import pytest

from drafting_evidence_source_adapter import (
    DraftingEvidenceSourceError,
    generation_evidence_keys,
)


def _receipt(*, answer_scope=(), bindings=()):
    return SimpleNamespace(
        answer_scope_evidence_keys=answer_scope,
        answer_statement_bindings=tuple(
            SimpleNamespace(evidence_keys=tuple(keys))
            for keys in bindings
        ),
    )


def _element(*keys):
    return SimpleNamespace(
        supporting_evidence_keys=tuple(keys),
        adverse_evidence_keys=(),
        conflicting_evidence_keys=(),
    )


def test_empty_r68_answer_scope_falls_back_to_exact_statement_binding_union():
    receipt = _receipt(
        answer_scope=(),
        bindings=(("e2", "e1"), ("e2",)),
    )
    assert generation_evidence_keys(
        retrieval_receipt=receipt,
        element=_element("e1", "e2", "e3"),
    ) == ("e1", "e2")


def test_explicit_r68_answer_scope_remains_authoritative():
    receipt = _receipt(
        answer_scope=("e1",),
        bindings=(("e2",),),
    )
    assert generation_evidence_keys(
        retrieval_receipt=receipt,
        element=_element("e1", "e2"),
    ) == ("e1",)


def test_statement_binding_fallback_still_intersects_governed_element():
    receipt = _receipt(
        answer_scope=(),
        bindings=(("e1", "foreign"),),
    )
    assert generation_evidence_keys(
        retrieval_receipt=receipt,
        element=_element("e1", "e2"),
    ) == ("e1",)


def test_empty_scope_and_empty_statement_bindings_still_fail_closed():
    receipt = _receipt(answer_scope=(), bindings=())
    with pytest.raises(
        DraftingEvidenceSourceError,
        match="R68 answer scope contains no evidence keys",
    ):
        generation_evidence_keys(
            retrieval_receipt=receipt,
            element=_element("e1"),
        )
