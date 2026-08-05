"""Canonical source-evidence byte identities and deterministic UUID helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final
from uuid import NAMESPACE_URL, UUID, uuid5

SOURCE_DOCUMENT_INSTANCE_NAME_PREFIX: Final[str] = "legalrag-pro/source-document-instance/1.0"


def canonical_json_bytes(value: Any) -> bytes:
    """Return canonical compact UTF-8 JSON bytes with exactly one final LF."""

    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    """Return the lowercase SHA-256 hex digest for exact bytes."""

    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    """Return SHA-256 of exact UTF-8 text bytes without normalization."""

    return sha256_bytes(value.encode("utf-8"))


def canonical_uuid(value: str, *, field_name: str = "uuid") -> str:
    """Require and return the canonical lowercase hyphenated UUID string."""

    try:
        canonical = str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"{field_name} must be a valid UUID string.") from exc
    if str(value) != canonical:
        raise ValueError(f"{field_name} must use canonical UUID text {canonical!r}.")
    return canonical


def validate_sha256_hex(value: str, *, field_name: str = "sha256") -> str:
    """Require a raw lowercase 64-character SHA-256 hex digest."""

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest.")
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest.")
    return value


def validate_sha256_id(value: str, *, field_name: str = "identity") -> str:
    """Require a content-derived ID in the form ``sha256:<hex>``."""

    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise ValueError(f"{field_name} must use 'sha256:<lowercase-hex>' format.")
    validate_sha256_hex(value[7:], field_name=field_name)
    return value


def derive_sha256_id(identity_payload: Any) -> str:
    """Derive ``sha256:<hex>`` over canonical identity-payload bytes."""

    return "sha256:" + sha256_bytes(canonical_json_bytes(identity_payload))


def derive_source_document_instance_id(
    *,
    case_id: str,
    original_filename: str,
    original_blob_sha256: str,
) -> str:
    """Derive the v1 case/name/content document provenance identity."""

    canonical_case_id = canonical_uuid(case_id, field_name="case_id")
    validate_sha256_hex(original_blob_sha256, field_name="original_blob_sha256")
    if not isinstance(original_filename, str) or not original_filename:
        raise ValueError("original_filename must not be empty.")
    name = "\0".join(
        (
            SOURCE_DOCUMENT_INSTANCE_NAME_PREFIX,
            canonical_case_id,
            original_filename,
            original_blob_sha256,
        )
    )
    return str(uuid5(NAMESPACE_URL, name))


__all__ = [
    "SOURCE_DOCUMENT_INSTANCE_NAME_PREFIX",
    "canonical_json_bytes",
    "canonical_uuid",
    "derive_sha256_id",
    "derive_source_document_instance_id",
    "sha256_bytes",
    "sha256_text",
    "validate_sha256_hex",
    "validate_sha256_id",
]
