"""Stable evidence-identity rules for Sprint 2.4 Milestone 2.

The compatibility contract deliberately reproduces the final accepted M5
traceability rule without importing M5's private helper.
"""

from __future__ import annotations

from legal_analysis.models import EvidenceReference


def assert_compatible_evidence_identity(
    evidence_key: str,
    existing: EvidenceReference,
    candidate: EvidenceReference,
) -> None:
    """Fail closed when one stable key resolves to incompatible evidence identity."""

    conflicts: list[str] = []
    if existing.chunk_id != candidate.chunk_id:
        conflicts.append("chunk_id")
    if existing.document_name != candidate.document_name:
        conflicts.append("document_name")
    if existing.page != candidate.page:
        conflicts.append("page")
    if existing.citation != candidate.citation:
        conflicts.append("citation")
    if (
        existing.document_id
        and candidate.document_id
        and existing.document_id != candidate.document_id
    ):
        conflicts.append("document_id")

    if conflicts:
        raise ValueError(
            f"Evidence key {evidence_key!r} resolves to incompatible stable evidence identity "
            f"({', '.join(conflicts)})."
        )


def assert_compatible_global_evidence_semantics(
    evidence_key: str,
    existing: EvidenceReference,
    candidate: EvidenceReference,
) -> None:
    """Reject contradictory durable source semantics for one canonical evidence item.

    Summary wording and provenance confidence are intentionally not compared;
    they are permitted to vary by the accepted M5 compatibility contract.
    """

    conflicts: list[str] = []
    for field_name in (
        "source_type",
        "evidence_status",
        "provenance_type",
        "provenance_basis",
    ):
        if getattr(existing, field_name) != getattr(candidate, field_name):
            conflicts.append(field_name)
    if conflicts:
        raise ValueError(
            f"Evidence key {evidence_key!r} resolves to incompatible global evidence semantics "
            f"({', '.join(conflicts)})."
        )


def assert_compatible_canonical_evidence(
    evidence_key: str,
    existing: EvidenceReference,
    candidate: EvidenceReference,
) -> None:
    """Validate both stable identity and case-wide global evidence semantics."""

    assert_compatible_evidence_identity(evidence_key, existing, candidate)
    assert_compatible_global_evidence_semantics(evidence_key, existing, candidate)


__all__ = [
    "assert_compatible_canonical_evidence",
    "assert_compatible_evidence_identity",
    "assert_compatible_global_evidence_semantics",
]
