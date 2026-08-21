"""Immutable source-record authority for already-normalised Finance observations.

This module is deliberately additive.  It does not acquire data, bind document
provenance, select comparables, write persistence, publish projections, or
activate runtime/UI state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from finance_domain.identity import derive_finance_id, validate_sha256_id
from finance_domain.models import FinancialObservation
from finance_domain.serialization import financial_observation_to_dict
from finance_domain.validation import validate_financial_observation


FINANCE_SOURCE_RECORD_AUTHORITY_SCHEMA_VERSION = "finance-source-record-authority/1.0"


def _required_text(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain leading or trailing whitespace.")
    return value


def _utc_datetime(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError(f"{field_name} must be timezone-aware UTC.")
    return value


def _optional_utc_datetime(value: datetime | None, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    return _utc_datetime(value, field_name=field_name)


def _datetime_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    value = _utc_datetime(value, field_name="datetime")
    return value.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class FinanceSourceRecordAuthority:
    schema_version: str
    provider_id: str
    source_id: str
    source_version: str
    publication_at: datetime | None
    retrieved_at: datetime
    observations: tuple[FinancialObservation, ...]
    source_record_authority_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "observations", tuple(self.observations))


def finance_source_record_authority_identity_payload_to_dict(
    value: FinanceSourceRecordAuthority,
) -> dict[str, object]:
    return {
        "schema_version": value.schema_version,
        "provider_id": value.provider_id,
        "source_id": value.source_id,
        "source_version": value.source_version,
        "publication_at": _datetime_text(value.publication_at),
        "retrieved_at": _datetime_text(value.retrieved_at),
        "observations": [
            financial_observation_to_dict(observation)
            for observation in value.observations
        ],
    }


def finance_source_record_authority_to_dict(
    value: FinanceSourceRecordAuthority,
) -> dict[str, object]:
    payload = finance_source_record_authority_identity_payload_to_dict(value)
    return {
        **payload,
        "source_record_authority_id": value.source_record_authority_id,
    }


def derive_finance_source_record_authority_id(
    value: FinanceSourceRecordAuthority,
) -> str:
    return derive_finance_id(
        finance_source_record_authority_identity_payload_to_dict(value)
    )


def validate_finance_source_record_authority(
    value: FinanceSourceRecordAuthority,
) -> None:
    if not isinstance(value, FinanceSourceRecordAuthority):
        raise ValueError("value must be FinanceSourceRecordAuthority.")
    if value.schema_version != FINANCE_SOURCE_RECORD_AUTHORITY_SCHEMA_VERSION:
        raise ValueError("Unsupported Finance source-record authority schema_version.")

    provider_id = _required_text(value.provider_id, field_name="provider_id")
    source_id = _required_text(value.source_id, field_name="source_id")
    source_version = _required_text(value.source_version, field_name="source_version")
    publication_at = _optional_utc_datetime(
        value.publication_at,
        field_name="publication_at",
    )
    retrieved_at = _utc_datetime(value.retrieved_at, field_name="retrieved_at")

    if not value.observations:
        raise ValueError("observations must not be empty.")

    observation_ids: list[str] = []
    for observation in value.observations:
        validate_financial_observation(observation)
        if observation.provider != provider_id:
            raise ValueError(
                "FinancialObservation provider differs from source-record authority."
            )
        if not (
            observation.source_id == source_id
            or observation.source_id.startswith(source_id + "/")
        ):
            raise ValueError(
                "FinancialObservation source_id is outside source-record authority."
            )
        if observation.source_version != source_version:
            raise ValueError(
                "FinancialObservation source_version differs from source-record authority."
            )
        if publication_at is not None and observation.publication_at != publication_at:
            raise ValueError(
                "FinancialObservation publication_at differs from source-record authority."
            )
        if retrieved_at < observation.observed_at:
            raise ValueError(
                "source-record retrieved_at must not precede observation observed_at."
            )
        if observation.publication_at is not None and retrieved_at < observation.publication_at:
            raise ValueError(
                "source-record retrieved_at must not precede observation publication_at."
            )
        observation_ids.append(observation.observation_id)

    if len(set(observation_ids)) != len(observation_ids):
        raise ValueError("observations must be unique by observation_id.")
    if observation_ids != sorted(observation_ids):
        raise ValueError("observations must use canonical observation_id sorted order.")

    validate_sha256_id(
        value.source_record_authority_id,
        field_name="source_record_authority_id",
    )
    expected = derive_finance_source_record_authority_id(value)
    if value.source_record_authority_id != expected:
        raise ValueError(
            "source_record_authority_id does not match its canonical identity payload."
        )


def build_finance_source_record_authority(
    *,
    provider_id: str,
    source_id: str,
    source_version: str,
    publication_at: datetime | None,
    retrieved_at: datetime,
    observations: tuple[FinancialObservation, ...],
) -> FinanceSourceRecordAuthority:
    provisional = FinanceSourceRecordAuthority(
        schema_version=FINANCE_SOURCE_RECORD_AUTHORITY_SCHEMA_VERSION,
        provider_id=provider_id,
        source_id=source_id,
        source_version=source_version,
        publication_at=publication_at,
        retrieved_at=retrieved_at,
        observations=tuple(observations),
        source_record_authority_id="",
    )
    final = FinanceSourceRecordAuthority(
        schema_version=provisional.schema_version,
        provider_id=provisional.provider_id,
        source_id=provisional.source_id,
        source_version=provisional.source_version,
        publication_at=provisional.publication_at,
        retrieved_at=provisional.retrieved_at,
        observations=provisional.observations,
        source_record_authority_id=derive_finance_source_record_authority_id(provisional),
    )
    validate_finance_source_record_authority(final)
    return final


__all__ = [
    "FINANCE_SOURCE_RECORD_AUTHORITY_SCHEMA_VERSION",
    "FinanceSourceRecordAuthority",
    "build_finance_source_record_authority",
    "derive_finance_source_record_authority_id",
    "finance_source_record_authority_identity_payload_to_dict",
    "finance_source_record_authority_to_dict",
    "validate_finance_source_record_authority",
]
