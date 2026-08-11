"""Content-derived identities for governed analytical authority infrastructure."""

from __future__ import annotations

from hashlib import sha256
import json
from uuid import UUID

from .models import (
    GOVERNED_ANALYTICAL_AUTHORITY_ACTIVATION_SCHEMA_VERSION,
    GOVERNED_ANALYTICAL_AUTHORITY_IDENTITY_VERSION,
    GOVERNED_ANALYTICAL_AUTHORITY_MANIFEST_SCHEMA_VERSION,
    GovernedAnalyticalAuthorityActivationAction,
)


_SHA256_PREFIX = "sha256:"


def canonical_sha256(payload: str | bytes) -> str:
    """Return ``sha256:<lowercase-hex>`` over exact UTF-8/text or supplied bytes."""

    data = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
    return _SHA256_PREFIX + sha256(data).hexdigest()


def require_canonical_case_id(case_id: str) -> str:
    """Require a lowercase hyphenated canonical UUID string without normalising it."""

    if not isinstance(case_id, str):
        raise ValueError("case_id must be a canonical UUID string.")
    try:
        canonical = str(UUID(case_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("case_id must be a canonical UUID string.") from exc
    if case_id != canonical:
        raise ValueError("case_id must use lowercase hyphenated canonical UUID form.")
    return case_id


def require_sha256_id(value: str, *, field_name: str) -> str:
    """Require exact ``sha256:<64 lowercase hex>`` form."""

    if not isinstance(value, str) or not value.startswith(_SHA256_PREFIX):
        raise ValueError(f"{field_name} must use sha256:<hex> form.")
    digest = value[len(_SHA256_PREFIX) :]
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError(
            f"{field_name} must contain exactly 64 lowercase hexadecimal characters."
        )
    return value


def sha256_storage_name(value: str, *, field_name: str) -> str:
    """Return the filesystem-safe 64-hex digest for a governed SHA-256 identity."""

    return require_sha256_id(value, field_name=field_name)[len(_SHA256_PREFIX) :]


def derive_governed_analytical_authority_id(
    *,
    case_id: str,
    structured_legal_analysis_results_sha256: str,
    case_matrices_sha256: str,
    governed_issue_evidence_map_sha256: str,
    governed_evidential_analysis_sha256: str,
    schema_version: str = GOVERNED_ANALYTICAL_AUTHORITY_MANIFEST_SCHEMA_VERSION,
    identity_version: str = GOVERNED_ANALYTICAL_AUTHORITY_IDENTITY_VERSION,
) -> str:
    """Derive the exact four-component B4 authority identity."""

    require_canonical_case_id(case_id)
    for field_name, value in (
        ("structured_legal_analysis_results_sha256", structured_legal_analysis_results_sha256),
        ("case_matrices_sha256", case_matrices_sha256),
        ("governed_issue_evidence_map_sha256", governed_issue_evidence_map_sha256),
        ("governed_evidential_analysis_sha256", governed_evidential_analysis_sha256),
    ):
        require_sha256_id(value, field_name=field_name)
    if schema_version != GOVERNED_ANALYTICAL_AUTHORITY_MANIFEST_SCHEMA_VERSION:
        raise ValueError("Unsupported governed analytical-authority manifest schema.")
    if identity_version != GOVERNED_ANALYTICAL_AUTHORITY_IDENTITY_VERSION:
        raise ValueError("Unsupported governed analytical-authority identity version.")

    payload = {
        "case_id": case_id,
        "case_matrices_sha256": case_matrices_sha256,
        "governed_evidential_analysis_sha256": governed_evidential_analysis_sha256,
        "governed_issue_evidence_map_sha256": governed_issue_evidence_map_sha256,
        "identity_version": identity_version,
        "schema_version": schema_version,
        "structured_legal_analysis_results_sha256": (
            structured_legal_analysis_results_sha256
        ),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _SHA256_PREFIX + sha256(encoded).hexdigest()


def derive_governed_analytical_authority_activation_id(
    *,
    case_id: str,
    action: GovernedAnalyticalAuthorityActivationAction,
    previous_activation_id: str | None,
    previous_authority_id: str | None,
    new_authority_id: str,
    previous_active_pointer_sha256: str | None,
    schema_version: str = GOVERNED_ANALYTICAL_AUTHORITY_ACTIVATION_SCHEMA_VERSION,
) -> str:
    """Derive one lifecycle identity without creating circular pointer hashing."""

    require_canonical_case_id(case_id)
    if schema_version != GOVERNED_ANALYTICAL_AUTHORITY_ACTIVATION_SCHEMA_VERSION:
        raise ValueError("Unsupported governed authority activation schema.")
    if not isinstance(action, GovernedAnalyticalAuthorityActivationAction):
        raise ValueError("action must be a GovernedAnalyticalAuthorityActivationAction.")
    require_sha256_id(new_authority_id, field_name="new_authority_id")
    if previous_activation_id is not None:
        require_sha256_id(previous_activation_id, field_name="previous_activation_id")
    if previous_authority_id is not None:
        require_sha256_id(previous_authority_id, field_name="previous_authority_id")
    if previous_active_pointer_sha256 is not None:
        require_sha256_id(
            previous_active_pointer_sha256,
            field_name="previous_active_pointer_sha256",
        )

    payload = {
        "action": action.value,
        "case_id": case_id,
        "new_authority_id": new_authority_id,
        "previous_activation_id": previous_activation_id,
        "previous_active_pointer_sha256": previous_active_pointer_sha256,
        "previous_authority_id": previous_authority_id,
        "schema_version": schema_version,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _SHA256_PREFIX + sha256(encoded).hexdigest()


__all__ = [
    "canonical_sha256",
    "derive_governed_analytical_authority_activation_id",
    "derive_governed_analytical_authority_id",
    "require_canonical_case_id",
    "require_sha256_id",
    "sha256_storage_name",
]
