"""Canonical serialization and identity helpers for frozen Finance F2 datasets."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Final

from finance_domain import derive_finance_id
from finance_domain.identity import canonical_json_bytes

FROZEN_DATASET_SCHEMA_VERSION: Final[str] = "finance-frozen-dataset/1.0"


class _RejectedJsonNumber(ValueError):
    pass


def _reject_float(value: str) -> None:
    raise _RejectedJsonNumber(f"JSON numeric literal {value!r} is not permitted in a frozen finance dataset.")


def _reject_constant(value: str) -> None:
    raise _RejectedJsonNumber(f"JSON constant {value!r} is not permitted in a frozen finance dataset.")


def loads_dataset_document(payload: str) -> dict[str, Any]:
    """Load a frozen dataset without accepting duplicate keys or JSON floats.

    Governed financial values are serialized as canonical Decimal strings by
    F1. Raw JSON numeric literals are therefore unnecessary and are rejected.
    """

    if not isinstance(payload, str):
        raise ValueError("Frozen finance dataset payload must be text.")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON object key {key!r} is not allowed.")
            result[key] = value
        return result

    try:
        data = json.loads(
            payload,
            object_pairs_hook=reject_duplicates,
            parse_int=_reject_float,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid frozen finance dataset JSON.") from exc
    except _RejectedJsonNumber as exc:
        raise ValueError(str(exc)) from exc

    if not isinstance(data, dict):
        raise ValueError("Frozen finance dataset root must be a JSON object.")
    return data


def dataset_identity_payload_to_dict(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Frozen finance dataset must be a dictionary.")
    if "dataset_identity" not in value:
        raise ValueError("Frozen finance dataset is missing dataset_identity.")
    payload = deepcopy(value)
    payload.pop("dataset_identity")
    return payload


def derive_dataset_identity(value: dict[str, Any]) -> str:
    """Derive content identity over canonical dataset semantics, excluding itself."""

    return derive_finance_id(dataset_identity_payload_to_dict(value))


def dumps_dataset_document(value: dict[str, Any]) -> str:
    """Return canonical JSON text for the complete frozen dataset document."""

    if not isinstance(value, dict):
        raise ValueError("Frozen finance dataset must be a dictionary.")
    return canonical_json_bytes(value).decode("utf-8")


__all__ = [
    "FROZEN_DATASET_SCHEMA_VERSION",
    "dataset_identity_payload_to_dict",
    "derive_dataset_identity",
    "dumps_dataset_document",
    "loads_dataset_document",
]
