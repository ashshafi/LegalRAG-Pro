from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json

import pytest

from governed_analytical_authority.serialization import (
    dumps_governed_analytical_authority_manifest,
    dumps_structured_legal_analysis_results,
    loads_governed_analytical_authority_manifest,
    loads_structured_legal_analysis_results,
)
from governed_analytical_authority.validation import build_governed_analytical_authority_manifest
from test_governed_analytical_authority_models import FROZEN_M5_SHA256, _bundle


def test_frozen_m5_component_is_lossless_and_matches_governed_h5_sha():
    results, _, _, _ = _bundle()
    payload = dumps_structured_legal_analysis_results(results)
    assert sha256(payload.encode("utf-8")).hexdigest() == FROZEN_M5_SHA256
    restored = loads_structured_legal_analysis_results(payload)
    assert restored == results
    assert dumps_structured_legal_analysis_results(restored) == payload


def test_outer_m5_caller_order_is_canonical_but_inner_state_is_not_reconstructed():
    results, _, _, _ = _bundle()
    assert dumps_structured_legal_analysis_results(tuple(reversed(results))) == dumps_structured_legal_analysis_results(results)
    with pytest.raises(ValueError):
        loads_structured_legal_analysis_results(dumps_structured_legal_analysis_results(results) + "\n")


def test_manifest_serialization_is_strict_canonical_json():
    results, matrices, u9b, u9c = _bundle()
    manifest = build_governed_analytical_authority_manifest(
        structured_legal_analysis_results=results,
        case_matrices=matrices,
        governed_issue_evidence_map=u9b,
        governed_evidential_analysis=u9c,
    )
    payload = dumps_governed_analytical_authority_manifest(manifest)
    assert loads_governed_analytical_authority_manifest(payload) == manifest
    parsed = json.loads(payload)
    parsed["unexpected"] = True
    with pytest.raises(ValueError):
        loads_governed_analytical_authority_manifest(json.dumps(parsed, sort_keys=True, separators=(",", ":")))
