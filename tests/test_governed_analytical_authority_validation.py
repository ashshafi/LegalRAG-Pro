from __future__ import annotations

from dataclasses import replace

import pytest

from governed_analytical_authority.validation import (
    GovernedAnalyticalAuthorityValidationError,
    build_governed_analytical_authority_manifest,
    validate_governed_analytical_authority_components,
    validate_governed_analytical_authority_manifest,
)
from test_governed_analytical_authority_models import _bundle


def test_complete_four_component_bundle_cross_validates_without_rebuilding_authority():
    results, matrices, u9b, u9c = _bundle()
    source_ids = validate_governed_analytical_authority_components(
        structured_legal_analysis_results=results,
        case_matrices=matrices,
        governed_issue_evidence_map=u9b,
        governed_evidential_analysis=u9c,
    )
    assert source_ids == tuple(sorted(matrices.source_analysis_ids))


def test_u9c_u9b_lineage_tamper_fails_closed():
    results, matrices, u9b, u9c = _bundle()
    tampered = replace(u9c, source_u9b_sha256="sha256:" + "0" * 64)
    with pytest.raises(GovernedAnalyticalAuthorityValidationError):
        validate_governed_analytical_authority_components(
            structured_legal_analysis_results=results,
            case_matrices=matrices,
            governed_issue_evidence_map=u9b,
            governed_evidential_analysis=tampered,
        )


def test_manifest_component_hash_tamper_fails_closed():
    results, matrices, u9b, u9c = _bundle()
    manifest = build_governed_analytical_authority_manifest(
        structured_legal_analysis_results=results,
        case_matrices=matrices,
        governed_issue_evidence_map=u9b,
        governed_evidential_analysis=u9c,
    )
    tampered = replace(manifest, case_matrices_sha256="sha256:" + "0" * 64)
    with pytest.raises(GovernedAnalyticalAuthorityValidationError):
        validate_governed_analytical_authority_manifest(
            tampered,
            structured_legal_analysis_results=results,
            case_matrices=matrices,
            governed_issue_evidence_map=u9b,
            governed_evidential_analysis=u9c,
        )
