from __future__ import annotations

from dataclasses import replace

import pytest

from governed_analytical_authority.activation import (
    GovernedAnalyticalAuthorityActivationError,
    activate_governed_analytical_authority,
)
from governed_analytical_authority.models import GovernedAnalyticalAuthorityActivationAction
from governed_analytical_authority.provider import load_active_governed_analytical_authority
from governed_analytical_authority.publication import publish_governed_analytical_authority
from test_governed_analytical_authority_models import _bundle, _patch_roots, _u9c_from_u9b


def _publish(results, matrices, u9b, u9c):
    return publish_governed_analytical_authority(
        structured_legal_analysis_results=results,
        case_matrices=matrices,
        governed_issue_evidence_map=u9b,
        governed_evidential_analysis=u9c,
    )


def test_activation_supersession_and_explicit_rollback_preserve_immutable_authorities(monkeypatch, tmp_path):
    _patch_roots(monkeypatch, tmp_path)
    results, matrices, u9b_a, u9c_a = _bundle()
    manifest_a = _publish(results, matrices, u9b_a, u9c_a)
    activate_governed_analytical_authority(case_id=manifest_a.case_id, authority_id=manifest_a.authority_id)

    coverage_b = replace(u9b_a.coverage, query_sha256="sha256:" + "9" * 64)
    u9b_b = replace(u9b_a, coverage=coverage_b)
    u9c_b = _u9c_from_u9b(u9b_b)
    manifest_b = _publish(results, matrices, u9b_b, u9c_b)
    assert manifest_b.authority_id != manifest_a.authority_id
    activate_governed_analytical_authority(case_id=manifest_b.case_id, authority_id=manifest_b.authority_id)
    assert load_active_governed_analytical_authority(manifest_a.case_id).manifest == manifest_b

    activate_governed_analytical_authority(
        case_id=manifest_a.case_id,
        authority_id=manifest_a.authority_id,
        action=GovernedAnalyticalAuthorityActivationAction.ROLLBACK,
    )
    assert load_active_governed_analytical_authority(manifest_a.case_id).manifest == manifest_a


def test_rollback_cannot_select_never_active_authority(monkeypatch, tmp_path):
    _patch_roots(monkeypatch, tmp_path)
    results, matrices, u9b_a, u9c_a = _bundle()
    manifest_a = _publish(results, matrices, u9b_a, u9c_a)
    activate_governed_analytical_authority(case_id=manifest_a.case_id, authority_id=manifest_a.authority_id)
    u9b_b = replace(u9b_a, coverage=replace(u9b_a.coverage, query_sha256="sha256:" + "8" * 64))
    manifest_b = _publish(results, matrices, u9b_b, _u9c_from_u9b(u9b_b))
    with pytest.raises(GovernedAnalyticalAuthorityActivationError):
        activate_governed_analytical_authority(
            case_id=manifest_b.case_id,
            authority_id=manifest_b.authority_id,
            action=GovernedAnalyticalAuthorityActivationAction.ROLLBACK,
        )
