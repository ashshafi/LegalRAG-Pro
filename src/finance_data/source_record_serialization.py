"""Canonical serialization for immutable Finance source-record authority."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from finance_domain.identity import canonical_json_bytes
from finance_domain.serialization import loads_financial_observation

from .source_record_authority import (
    FINANCE_SOURCE_RECORD_AUTHORITY_SCHEMA_VERSION,
    FinanceSourceRecordAuthority,
    finance_source_record_authority_to_dict,
    validate_finance_source_record_authority,
)


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON value is forbidden: {value}")


def _required_text(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain leading or trailing whitespace.")
    return value


def _datetime(value: Any, *, field_name: str, optional: bool = False) -> datetime | None:
    if value is None and optional:
        return None
    text = _required_text(value, field_name=field_name)
    if not text.endswith("Z"):
        raise ValueError(f"{field_name} must use canonical UTC Z form.")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a valid datetime.") from exc
    return parsed


def dumps_finance_source_record_authority(
    value: FinanceSourceRecordAuthority,
) -> str:
    validate_finance_source_record_authority(value)
    return canonical_json_bytes(
        finance_source_record_authority_to_dict(value)
    ).decode("utf-8")


def loads_finance_source_record_authority(
    payload: str,
) -> FinanceSourceRecordAuthority:
    if not isinstance(payload, str):
        raise ValueError("payload must be text.")

    try:
        data = json.loads(
            payload,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("Invalid Finance source-record authority JSON.") from exc

    if not isinstance(data, dict):
        raise ValueError("Finance source-record authority payload must be a JSON object.")

    expected_keys = {
        "schema_version",
        "provider_id",
        "source_id",
        "source_version",
        "publication_at",
        "retrieved_at",
        "observations",
        "source_record_authority_id",
    }
    if set(data) != expected_keys:
        raise ValueError("Finance source-record authority keys are not exact.")

    schema_version = _required_text(data["schema_version"], field_name="schema_version")
    if schema_version != FINANCE_SOURCE_RECORD_AUTHORITY_SCHEMA_VERSION:
        raise ValueError("Unsupported Finance source-record authority schema_version.")

    raw_observations = data["observations"]
    if not isinstance(raw_observations, list):
        raise ValueError("observations must be a JSON array.")

    observations = tuple(
        loads_financial_observation(
            canonical_json_bytes(item).decode("utf-8")
        )
        for item in raw_observations
    )

    value = FinanceSourceRecordAuthority(
        schema_version=schema_version,
        provider_id=_required_text(data["provider_id"], field_name="provider_id"),
        source_id=_required_text(data["source_id"], field_name="source_id"),
        source_version=_required_text(data["source_version"], field_name="source_version"),
        publication_at=_datetime(
            data["publication_at"],
            field_name="publication_at",
            optional=True,
        ),
        retrieved_at=_datetime(data["retrieved_at"], field_name="retrieved_at"),
        observations=observations,
        source_record_authority_id=_required_text(
            data["source_record_authority_id"],
            field_name="source_record_authority_id",
        ),
    )
    validate_finance_source_record_authority(value)

    canonical = dumps_finance_source_record_authority(value)
    if payload != canonical:
        raise ValueError(
            "Finance source-record authority JSON is not in exact canonical form."
        )
    return value


__all__ = [
    "dumps_finance_source_record_authority",
    "loads_finance_source_record_authority",
]
