from __future__ import annotations

import pytest

from governed_analytical_authority.identity import (
    derive_governed_analytical_authority_activation_id,
    derive_governed_analytical_authority_id,
    require_canonical_case_id,
)
from governed_analytical_authority.models import GovernedAnalyticalAuthorityActivationAction


def _hash(char: str) -> str:
    return "sha256:" + char * 64


def test_authority_identity_is_deterministic_and_binds_all_four_components():
    kwargs = dict(
        case_id="11111111-1111-4111-8111-111111111111",
        structured_legal_analysis_results_sha256=_hash("1"),
        case_matrices_sha256=_hash("2"),
        governed_issue_evidence_map_sha256=_hash("3"),
        governed_evidential_analysis_sha256=_hash("4"),
    )
    first = derive_governed_analytical_authority_id(**kwargs)
    assert first == derive_governed_analytical_authority_id(**kwargs)
    assert first != derive_governed_analytical_authority_id(
        **{**kwargs, "governed_evidential_analysis_sha256": _hash("5")}
    )


def test_case_identity_requires_exact_canonical_uuid_form():
    canonical = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    assert require_canonical_case_id(canonical) == canonical
    with pytest.raises(ValueError):
        require_canonical_case_id(canonical.upper())
    with pytest.raises(ValueError):
        require_canonical_case_id("../escape")


def test_activation_identity_binds_previous_selection_without_pointer_hash_cycle():
    kwargs = dict(
        case_id="11111111-1111-4111-8111-111111111111",
        action=GovernedAnalyticalAuthorityActivationAction.ACTIVATE,
        previous_activation_id=None,
        previous_authority_id=None,
        new_authority_id=_hash("a"),
        previous_active_pointer_sha256=None,
    )
    first = derive_governed_analytical_authority_activation_id(**kwargs)
    assert first == derive_governed_analytical_authority_activation_id(**kwargs)
    assert first != derive_governed_analytical_authority_activation_id(
        **{**kwargs, "new_authority_id": _hash("b")}
    )
