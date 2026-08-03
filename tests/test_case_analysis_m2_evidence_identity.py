from __future__ import annotations

from dataclasses import replace

import pytest

from legal_analysis.enums import EvidenceStatus, ProvenanceConfidence

from case_analysis.m2.evidence_identity import assert_compatible_canonical_evidence
from case_analysis_m2_helpers import evidence


def test_compatible_identity_accepts_harmless_non_identity_differences():
    left = evidence(key="shared", summary="First representation")
    right = replace(
        left,
        summary="Second representation",
        provenance_confidence=ProvenanceConfidence.MEDIUM,
    )

    assert_compatible_canonical_evidence("shared", left, right)


def test_one_missing_document_id_is_compatible():
    left = evidence(key="shared", document_id=None)
    right = evidence(key="shared", document_id="doc-1")
    assert_compatible_canonical_evidence("shared", left, right)


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("document_name", "other.pdf"),
        ("page", 2),
        ("citation", "shared.pdf, p.99"),
        ("document_id", "doc-2"),
    ),
)
def test_incompatible_stable_identity_fails_closed(field_name: str, value):
    left = evidence(key="shared")
    right = replace(left, **{field_name: value})

    with pytest.raises(ValueError, match="incompatible stable evidence identity"):
        assert_compatible_canonical_evidence("shared", left, right)


def test_conflicting_global_evidence_semantics_fail_closed():
    left = evidence(key="shared")
    right = replace(left, evidence_status=EvidenceStatus.CLAIMANT_EVIDENCE)

    with pytest.raises(ValueError, match="incompatible global evidence semantics"):
        assert_compatible_canonical_evidence("shared", left, right)
