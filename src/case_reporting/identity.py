"""Deterministic identities and fingerprints for M5.1 report projection."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final
from uuid import UUID, uuid5

from .models import (
    REPORT_MANIFEST_BUILDER_VERSION,
    REPORT_MANIFEST_SCHEMA_VERSION,
    REPORT_PROJECTION_SCHEMA_VERSION,
    REPORT_PROJECTOR_VERSION,
    CaseReportMetadata,
)

REPORT_PROJECTION_NAMESPACE: Final[UUID] = UUID("47f4d04d-c16a-5c7d-82f8-d5c93c07943c")
REPORT_MANIFEST_NAMESPACE: Final[UUID] = UUID("ab8e99ca-27c3-523f-8817-4592b6e1929e")
REPORT_STATEMENT_NAMESPACE: Final[UUID] = UUID("66d74951-d20c-5d79-aee7-4cebd5884ea1")


def canonical_json_bytes(value: Any) -> bytes:
    """Return canonical UTF-8 JSON bytes for an explicit JSON-compatible value."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def metadata_to_dict(value: CaseReportMetadata) -> dict[str, str | None]:
    return {
        "case_name": value.case_name,
        "case_number": value.case_number,
        "claimant": value.claimant,
        "respondent": value.respondent,
        "case_status": value.case_status,
        "court_or_tribunal": value.court_or_tribunal,
    }


def fingerprint_metadata(value: CaseReportMetadata | None) -> str | None:
    if value is None:
        return None
    return sha256_bytes(canonical_json_bytes(metadata_to_dict(value)))


def derive_report_projection_id(
    *,
    case_id: str,
    source_synthesis_id: str,
    source_foundation_sha256: str,
    source_matrices_sha256: str,
    source_chronology_sha256: str,
    source_synthesis_sha256: str,
    source_metadata_sha256: str | None,
    schema_version: str = REPORT_PROJECTION_SCHEMA_VERSION,
    projector_version: str = REPORT_PROJECTOR_VERSION,
) -> str:
    name = "|".join(
        (
            schema_version,
            projector_version,
            str(UUID(case_id)),
            str(UUID(source_synthesis_id)),
            source_foundation_sha256,
            source_matrices_sha256,
            source_chronology_sha256,
            source_synthesis_sha256,
            source_metadata_sha256 or "",
        )
    )
    return str(uuid5(REPORT_PROJECTION_NAMESPACE, name))


def derive_manifest_id(
    *,
    report_projection_id: str,
    projection_payload_sha256: str,
    manifest_payload_sha256: str,
    schema_version: str = REPORT_MANIFEST_SCHEMA_VERSION,
    builder_version: str = REPORT_MANIFEST_BUILDER_VERSION,
) -> str:
    name = "|".join(
        (
            schema_version,
            builder_version,
            str(UUID(report_projection_id)),
            projection_payload_sha256,
            manifest_payload_sha256,
        )
    )
    return str(uuid5(REPORT_MANIFEST_NAMESPACE, name))


def derive_report_statement_id(
    *,
    issue_analysis_id: str,
    element_id: str,
    category: str,
    text: str,
    evidence_keys: tuple[str, ...],
    citation_ids: tuple[str, ...],
) -> str:
    name = "|".join(
        (
            str(UUID(issue_analysis_id)),
            element_id,
            category,
            text,
            *sorted(evidence_keys),
            "--citations--",
            *sorted(citation_ids),
        )
    )
    return str(uuid5(REPORT_STATEMENT_NAMESPACE, name))


__all__ = [
    "REPORT_MANIFEST_NAMESPACE",
    "REPORT_PROJECTION_NAMESPACE",
    "REPORT_STATEMENT_NAMESPACE",
    "canonical_json_bytes",
    "derive_manifest_id",
    "derive_report_projection_id",
    "derive_report_statement_id",
    "fingerprint_metadata",
    "metadata_to_dict",
    "sha256_bytes",
    "sha256_text",
]
