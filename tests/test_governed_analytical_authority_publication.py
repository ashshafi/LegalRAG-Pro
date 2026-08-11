from __future__ import annotations

from pathlib import Path

import pytest

from governed_analytical_authority.identity import sha256_storage_name
from governed_analytical_authority.publication import (
    GovernedAnalyticalAuthorityPublicationError,
    publish_governed_analytical_authority,
)
from test_governed_analytical_authority_models import _bundle, _patch_roots


def _publish(bundle):
    results, matrices, u9b, u9c = bundle
    return publish_governed_analytical_authority(
        structured_legal_analysis_results=results,
        case_matrices=matrices,
        governed_issue_evidence_map=u9b,
        governed_evidential_analysis=u9c,
    )


def test_publication_is_immutable_idempotent_and_does_not_activate(monkeypatch, tmp_path):
    root = _patch_roots(monkeypatch, tmp_path)
    bundle = _bundle()
    manifest = _publish(bundle)
    assert _publish(bundle) == manifest
    object_root = root / manifest.case_id / "objects" / sha256_storage_name(manifest.authority_id, field_name="authority_id")
    assert {p.name for p in object_root.iterdir()} == {
        "manifest.json", "structured_legal_analysis_results.json", "case_matrices.json",
        "governed_issue_evidence_map.json", "governed_evidential_analysis.json",
    }
    assert not (root / manifest.case_id / "active.json").exists()


def test_existing_authority_bytes_are_never_repaired(monkeypatch, tmp_path):
    root = _patch_roots(monkeypatch, tmp_path)
    bundle = _bundle()
    manifest = _publish(bundle)
    object_root = root / manifest.case_id / "objects" / sha256_storage_name(manifest.authority_id, field_name="authority_id")
    path = object_root / "manifest.json"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(GovernedAnalyticalAuthorityPublicationError):
        _publish(bundle)
    assert path.read_bytes().endswith(b"\n")
