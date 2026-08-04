"""Deterministic identity and source-fingerprint helpers for M4.1."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from typing import Final
from uuid import UUID, uuid5

from case_analysis.m2.matrix_serialization import dumps_case_matrices
from case_analysis.m3.chronology_serialization import dumps_case_chronology

from .models import (
    AnalyticalBasis,
    ConflictType,
    FindingScope,
    FindingType,
    GapType,
    PriorityBasis,
    ProvenanceTarget,
    RiskType,
    SynthesisProvenanceRef,
    WHOLE_CASE_SYNTHESIS_SCHEMA_VERSION,
    WHOLE_CASE_SYNTHESISER_VERSION,
    provenance_sort_key,
)

WHOLE_CASE_SYNTHESIS_NAMESPACE: Final[UUID] = UUID("bdf2c0d9-c6d8-57a7-b880-584826c242d6")
WHOLE_CASE_FINDING_NAMESPACE: Final[UUID] = UUID("6dd6dceb-e6f9-5635-8758-4b725a979b9b")
WHOLE_CASE_CONFLICT_NAMESPACE: Final[UUID] = UUID("47ca8119-bba6-50da-9c79-55bbaaf9787d")
WHOLE_CASE_GAP_NAMESPACE: Final[UUID] = UUID("bc3d1dc2-d390-51a3-959a-94228df2c5ba")
WHOLE_CASE_RISK_NAMESPACE: Final[UUID] = UUID("ac99d121-a907-594f-a3f6-3763503d3181")
WHOLE_CASE_QUESTION_NAMESPACE: Final[UUID] = UUID("39bb78b2-0849-5b64-bb8c-96b6eb8c1274")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _uuid(value: str, *, field_name: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"{field_name} must be a valid UUID string.") from exc


def _required(value: str, *, field_name: str) -> str:
    cleaned = str(value).strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty.")
    return cleaned


def _sha256(value: str, *, field_name: str) -> str:
    cleaned = str(value).strip()
    if not _SHA256_RE.fullmatch(cleaned):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest.")
    return cleaned


def _sha256_text(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fingerprint_case_matrices(matrices) -> str:
    """Return the M4 provenance fingerprint of one canonical frozen M2 artifact."""

    return _sha256_text(dumps_case_matrices(matrices))


def fingerprint_case_chronology(chronology) -> str:
    """Return the M4 provenance fingerprint of one canonical frozen M3 artifact."""

    return _sha256_text(dumps_case_chronology(chronology))


def derive_case_synthesis_id(
    *,
    case_id: str,
    foundation_synthesis_id: str,
    source_matrices_sha256: str,
    source_chronology_sha256: str,
    schema_version: str = WHOLE_CASE_SYNTHESIS_SCHEMA_VERSION,
    synthesiser_version: str = WHOLE_CASE_SYNTHESISER_VERSION,
) -> str:
    name = "|".join(
        (
            _required(schema_version, field_name="schema_version"),
            _required(synthesiser_version, field_name="synthesiser_version"),
            _uuid(case_id, field_name="case_id"),
            _uuid(foundation_synthesis_id, field_name="foundation_synthesis_id"),
            _sha256(source_matrices_sha256, field_name="source_matrices_sha256"),
            _sha256(source_chronology_sha256, field_name="source_chronology_sha256"),
        )
    )
    return str(uuid5(WHOLE_CASE_SYNTHESIS_NAMESPACE, name))


def _provenance_tokens(refs: Iterable[SynthesisProvenanceRef | ProvenanceTarget]) -> tuple[str, ...]:
    targets: list[ProvenanceTarget] = []
    for ref in refs:
        targets.append(ref.target if isinstance(ref, SynthesisProvenanceRef) else ref)
    unique = {provenance_sort_key(item) for item in targets}
    return tuple("\x1f".join(parts) for parts in sorted(unique))


def derive_finding_id(
    *,
    synthesis_id: str,
    finding_type: FindingType,
    scope: FindingScope,
    analytical_bases: Iterable[AnalyticalBasis],
    provenance_refs: Iterable[SynthesisProvenanceRef | ProvenanceTarget],
) -> str:
    bases = tuple(sorted({item.value for item in analytical_bases}))
    refs = _provenance_tokens(provenance_refs)
    if not bases or not refs:
        raise ValueError("Finding identity requires analytical bases and provenance.")
    name = "|".join((_uuid(synthesis_id, field_name="synthesis_id"), finding_type.value, scope.value, *bases, *refs))
    return str(uuid5(WHOLE_CASE_FINDING_NAMESPACE, name))


def derive_conflict_id(
    *,
    synthesis_id: str,
    conflict_type: ConflictType,
    scope: FindingScope,
    side_a_refs: Iterable[SynthesisProvenanceRef | ProvenanceTarget],
    side_b_refs: Iterable[SynthesisProvenanceRef | ProvenanceTarget],
) -> str:
    side_a = _provenance_tokens(side_a_refs)
    side_b = _provenance_tokens(side_b_refs)
    if not side_a or not side_b:
        raise ValueError("Conflict identity requires both sides.")
    sides = sorted(("\x1e".join(side_a), "\x1e".join(side_b)))
    name = "|".join((_uuid(synthesis_id, field_name="synthesis_id"), conflict_type.value, scope.value, *sides))
    return str(uuid5(WHOLE_CASE_CONFLICT_NAMESPACE, name))


def derive_gap_id(
    *,
    synthesis_id: str,
    gap_type: GapType,
    scope: FindingScope,
    issue_analysis_id: str,
    element_id: str | None,
    provenance_refs: Iterable[SynthesisProvenanceRef | ProvenanceTarget],
) -> str:
    refs = _provenance_tokens(provenance_refs)
    if not refs:
        raise ValueError("Gap identity requires provenance.")
    name = "|".join(
        (
            _uuid(synthesis_id, field_name="synthesis_id"),
            gap_type.value,
            scope.value,
            _uuid(issue_analysis_id, field_name="issue_analysis_id"),
            str(element_id or ""),
            *refs,
        )
    )
    return str(uuid5(WHOLE_CASE_GAP_NAMESPACE, name))


def derive_risk_id(
    *,
    synthesis_id: str,
    risk_type: RiskType,
    scope: FindingScope,
    basis_finding_ids: Iterable[str] = (),
    conflict_ids: Iterable[str] = (),
    gap_ids: Iterable[str] = (),
    provenance_refs: Iterable[SynthesisProvenanceRef | ProvenanceTarget] = (),
) -> str:
    tokens = [f"finding:{_uuid(item, field_name='finding_id')}" for item in basis_finding_ids]
    tokens.extend(f"conflict:{_uuid(item, field_name='conflict_id')}" for item in conflict_ids)
    tokens.extend(f"gap:{_uuid(item, field_name='gap_id')}" for item in gap_ids)
    tokens.extend(f"provenance:{item}" for item in _provenance_tokens(provenance_refs))
    tokens = sorted(set(tokens))
    if not tokens:
        raise ValueError("Risk identity requires an analytical basis.")
    name = "|".join((_uuid(synthesis_id, field_name="synthesis_id"), risk_type.value, scope.value, *tokens))
    return str(uuid5(WHOLE_CASE_RISK_NAMESPACE, name))


def derive_priority_question_id(
    *,
    synthesis_id: str,
    basis_type: PriorityBasis,
    affected_issue_ids: Iterable[str],
    affected_element_ids: Iterable[str] = (),
    finding_ids: Iterable[str] = (),
    gap_ids: Iterable[str] = (),
    conflict_ids: Iterable[str] = (),
    provenance_refs: Iterable[SynthesisProvenanceRef | ProvenanceTarget] = (),
) -> str:
    issue_ids = sorted({_uuid(item, field_name="affected_issue_id") for item in affected_issue_ids})
    if not issue_ids:
        raise ValueError("Priority-question identity requires affected issues.")
    tokens = [f"issue:{item}" for item in issue_ids]
    tokens.extend(f"element:{_required(item, field_name='affected_element_id')}" for item in affected_element_ids)
    tokens.extend(f"finding:{_uuid(item, field_name='finding_id')}" for item in finding_ids)
    tokens.extend(f"gap:{_uuid(item, field_name='gap_id')}" for item in gap_ids)
    tokens.extend(f"conflict:{_uuid(item, field_name='conflict_id')}" for item in conflict_ids)
    tokens.extend(f"provenance:{item}" for item in _provenance_tokens(provenance_refs))
    name = "|".join(
        (
            _uuid(synthesis_id, field_name="synthesis_id"),
            basis_type.value,
            *sorted(set(tokens)),
        )
    )
    return str(uuid5(WHOLE_CASE_QUESTION_NAMESPACE, name))


__all__ = [
    "WHOLE_CASE_CONFLICT_NAMESPACE",
    "WHOLE_CASE_FINDING_NAMESPACE",
    "WHOLE_CASE_GAP_NAMESPACE",
    "WHOLE_CASE_QUESTION_NAMESPACE",
    "WHOLE_CASE_RISK_NAMESPACE",
    "WHOLE_CASE_SYNTHESIS_NAMESPACE",
    "derive_case_synthesis_id",
    "derive_conflict_id",
    "derive_finding_id",
    "derive_gap_id",
    "derive_priority_question_id",
    "derive_risk_id",
    "fingerprint_case_chronology",
    "fingerprint_case_matrices",
]
