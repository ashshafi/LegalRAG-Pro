"""Deterministic identities for the Finance MVP domain."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from source_evidence.identity import (
    canonical_json_bytes,
    canonical_uuid,
    derive_sha256_id,
    validate_sha256_id,
)


def canonical_decimal_text(value: Decimal) -> str:
    """Return one exponent-free canonical decimal representation.

    Binary floating-point values are intentionally unsupported by the domain
    model. Numerically equivalent Decimal values receive the same text.
    """

    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("value must be a finite Decimal.")
    if value.is_zero():
        return "0"
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def derive_finance_id(identity_payload: Any) -> str:
    """Return a content-derived finance identity over canonical JSON bytes."""

    return derive_sha256_id(identity_payload)


__all__ = [
    "canonical_decimal_text",
    "canonical_json_bytes",
    "canonical_uuid",
    "derive_finance_id",
    "validate_sha256_id",
]
