from __future__ import annotations

import json

import pytest

import governed_analytical_authority.provider as provider_module
from governed_analytical_authority.activation import activate_governed_analytical_authority
from governed_analytical_authority.provider import (
    GovernedAnalyticalAuthorityProviderError,
    load_active_governed_analytical_authority,
)
from governed_analytical_authority.publication import publish_governed_analytical_authority
from test_governed_analytical_authority_models import _bundle, _patch_roots


@pytest.fixture(autouse=True)
def _clear_runtime_authority_cache():
    provider_module._RUNTIME_AUTHORITY_CACHE.clear()
    yield
    provider_module._RUNTIME_AUTHORITY_CACHE.clear()


def _publish(bundle):
    results, matrices, u9b, u9c = bundle
    return publish_governed_analytical_authority(
        structured_legal_analysis_results=results,
        case_matrices=matrices,
        governed_issue_evidence_map=u9b,
        governed_evidential_analysis=u9c,
    )


def test_absent_is_none_even_when_unactivated_authority_is_published(monkeypatch, tmp_path):
    _patch_roots(monkeypatch, tmp_path)
    bundle = _bundle()
    case_id = bundle[1].case_id
    assert load_active_governed_analytical_authority(case_id) is None
    _publish(bundle)
    assert load_active_governed_analytical_authority(case_id) is None


def test_provider_loads_only_exact_active_pointer_and_returns_validated_bundle(monkeypatch, tmp_path):
    _patch_roots(monkeypatch, tmp_path)
    bundle = _bundle()
    manifest = _publish(bundle)
    activate_governed_analytical_authority(case_id=manifest.case_id, authority_id=manifest.authority_id)
    loaded = load_active_governed_analytical_authority(manifest.case_id)
    assert loaded is not None
    assert loaded.manifest == manifest
    assert loaded.structured_legal_analysis_results == bundle[0]


def test_present_but_malformed_active_pointer_fails_closed(monkeypatch, tmp_path):
    root = _patch_roots(monkeypatch, tmp_path)
    bundle = _bundle()
    manifest = _publish(bundle)
    case_root = root / manifest.case_id
    (case_root / "active.json").write_text('{"bad":true}', encoding="utf-8")
    with pytest.raises(GovernedAnalyticalAuthorityProviderError):
        load_active_governed_analytical_authority(manifest.case_id)



def test_exact_unchanged_case_tree_reuses_validated_runtime_authority(monkeypatch, tmp_path):
    _patch_roots(monkeypatch, tmp_path)
    bundle = _bundle()
    manifest = _publish(bundle)
    activate_governed_analytical_authority(
        case_id=manifest.case_id,
        authority_id=manifest.authority_id,
    )

    first = load_active_governed_analytical_authority(manifest.case_id)
    second = load_active_governed_analytical_authority(manifest.case_id)

    assert first is not None
    assert second is first


def test_cached_authority_is_not_reused_after_exact_case_tree_bytes_change(monkeypatch, tmp_path):
    root = _patch_roots(monkeypatch, tmp_path)
    bundle = _bundle()
    manifest = _publish(bundle)
    activate_governed_analytical_authority(
        case_id=manifest.case_id,
        authority_id=manifest.authority_id,
    )
    first = load_active_governed_analytical_authority(manifest.case_id)
    assert first is not None

    object_root = (
        root
        / manifest.case_id
        / "objects"
        / manifest.authority_id.removeprefix("sha256:")
    )
    target = object_root / "structured_legal_analysis_results.json"
    target.write_text(target.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(GovernedAnalyticalAuthorityProviderError):
        load_active_governed_analytical_authority(manifest.case_id)
