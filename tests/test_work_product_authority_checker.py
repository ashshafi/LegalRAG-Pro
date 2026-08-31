from pathlib import Path

import pytest

from work_product_authority_checker import (
    WorkProductAuthorityCheckerError,
    WorkProductAuthorityResult,
    check_work_product_authority,
)


def _check(
    **overrides,
):

    values = {
        "statement":
            "The issue remains disputed.",

        "current_status":
            "disputed",

        "current_confidence":
            "medium",

        "claimed_status":
            "disputed",

        "claimed_confidence":
            "medium",

        "cited_evidence_keys":
            (
                "e1",
            ),

        "allowed_evidence_keys":
            (
                "e1",
                "e2",
            ),

        "approved_contradiction_count":
            0,

        "unresolved_matter_count":
            0,

        "formal_gap_count":
            0,
    }

    values.update(
        overrides
    )

    return check_work_product_authority(
        **values
    )


def test_exact_structured_alignment_passes():

    result = _check()

    assert (
        result.result
        is WorkProductAuthorityResult.ALIGNED
    )


def test_higher_claimed_confidence_is_not_authorized():

    result = _check(
        claimed_confidence=
            "high",
    )

    assert (
        result.result
        is WorkProductAuthorityResult.NOT_AUTHORIZED
    )

    assert any(
        "exceeds"
        in reason
        for reason
        in result.reasons
    )


def test_different_claimed_status_is_not_authorized():

    result = _check(
        claimed_status=
            "well_supported",
    )

    assert (
        result.result
        is WorkProductAuthorityResult.NOT_AUTHORIZED
    )


def test_foreign_evidence_is_not_authorized():

    result = _check(
        cited_evidence_keys=
            (
                "foreign",
            ),
    )

    assert (
        result.result
        is WorkProductAuthorityResult.NOT_AUTHORIZED
    )


def test_no_declared_evidence_basis_is_caution():

    result = _check(
        cited_evidence_keys=(),
    )

    assert (
        result.result
        is WorkProductAuthorityResult.CAUTION
    )


def test_material_uncertainty_produces_caution():

    result = _check(
        approved_contradiction_count=
            1,

        unresolved_matter_count=
            2,
    )

    assert (
        result.result
        is WorkProductAuthorityResult.CAUTION
    )

    assert any(
        "approved contradiction"
        in reason
        for reason
        in result.reasons
    )


def test_lower_confidence_is_conservative_not_overclaiming():

    result = _check(
        claimed_confidence=
            "low",
    )

    assert (
        result.result
        is WorkProductAuthorityResult.ALIGNED
    )


def test_blank_statement_fails_closed():

    with pytest.raises(
        WorkProductAuthorityCheckerError,
        match=
            "statement must not be blank",
    ):

        _check(
            statement=
                "   ",
        )


def test_checker_is_pure_and_contains_no_ai_or_persistence():

    source = Path(
        "src/work_product_authority_checker.py"
    ).read_text(
        encoding="utf-8"
    ).lower()

    for forbidden in (
        "openai",
        "chromadb",
        "jsonl",
        "write_text(",
        "open(",
        "publish_governed_analytical_authority",
        "activate_governed_analytical_authority",
    ):

        assert forbidden not in source
