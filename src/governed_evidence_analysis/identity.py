"""Deterministic source fingerprint and semantic identity helpers for U9C-B1."""

from __future__ import annotations

from hashlib import sha256
import json

from governed_issue_evidence.models import GovernedIssueEvidenceMap
from governed_issue_evidence.serialization import dumps_governed_issue_evidence_map
from governed_issue_evidence.validation import validate_governed_issue_evidence_map


_SHA256_PREFIX = "sha256:"


def source_u9b_sha256(source_u9b: GovernedIssueEvidenceMap) -> str:
    """Return a canonical SHA-256 fingerprint of one validated frozen U9B map."""

    validate_governed_issue_evidence_map(source_u9b)
    payload = dumps_governed_issue_evidence_map(source_u9b).encode("utf-8")
    return _SHA256_PREFIX + sha256(payload).hexdigest()


def derive_governed_evidential_analysis_id(
    *,
    schema_version: str,
    identity_version: str,
    case_id: str,
    source_u9b_sha256_value: str,
) -> str:
    """Derive the deterministic U9C semantic identity from its frozen source lineage."""

    if not schema_version.strip():
        raise ValueError("schema_version must be non-empty.")
    if not identity_version.strip():
        raise ValueError("identity_version must be non-empty.")
    if not case_id.strip():
        raise ValueError("case_id must be non-empty.")
    _validate_sha256_id(source_u9b_sha256_value, field_name="source_u9b_sha256")

    payload = {
        "case_id": case_id,
        "identity_version": identity_version,
        "schema_version": schema_version,
        "source_u9b_sha256": source_u9b_sha256_value,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _SHA256_PREFIX + sha256(encoded).hexdigest()


def _validate_sha256_id(value: str, *, field_name: str) -> None:
    if not value.startswith(_SHA256_PREFIX):
        raise ValueError(f"{field_name} must use sha256:<hex> form.")
    digest = value[len(_SHA256_PREFIX) :]
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"{field_name} must contain 64 lowercase hexadecimal characters.")


__all__ = [
    "derive_governed_evidential_analysis_id",
    "source_u9b_sha256",
]
