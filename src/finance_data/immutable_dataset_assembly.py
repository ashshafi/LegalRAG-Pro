"""Deterministic assembly of an immutable Finance dataset from governed source records.

This boundary consumes already-validated domain authorities only.  It performs
no acquisition, inference, persistence, comparable selection, calculation,
projection publication, or runtime/UI activation.
"""

from __future__ import annotations

import json
from typing import Any

from finance_data.immutable_dataset import (
    IMMUTABLE_DATASET_SCHEMA_VERSION,
    ValidatedImmutableDataset,
    derive_immutable_dataset_identity,
    validate_immutable_dataset_document,
)
from finance_data.source_record_authority import (
    FinanceSourceRecordAuthority,
    validate_finance_source_record_authority,
)
from finance_domain.models import (
    Company,
    FinanceWorkspace,
    FinancialObservation,
    FinancialPeriod,
    Security,
)
from finance_domain.serialization import (
    dumps_company,
    dumps_finance_workspace,
    dumps_financial_observation,
    dumps_financial_period,
    dumps_security,
)
from finance_domain.validation import (
    validate_company,
    validate_finance_workspace,
    validate_financial_observation,
    validate_financial_period,
    validate_security,
)


def _required_text(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain leading or trailing whitespace.")
    return value


def _required_tuple(value: tuple[Any, ...], *, field_name: str) -> tuple[Any, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{field_name} must be a tuple.")
    return value


def _canonical_object(payload: str, *, field_name: str) -> dict[str, Any]:
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError(f"{field_name} canonical serialization must be an object.")
    return data


def assemble_immutable_finance_dataset(
    *,
    provider_id: str,
    dataset_id: str,
    dataset_version: str,
    workspace: FinanceWorkspace,
    companies: tuple[Company, ...],
    securities: tuple[Security, ...],
    periods: tuple[FinancialPeriod, ...],
    source_record_authorities: tuple[FinanceSourceRecordAuthority, ...],
) -> ValidatedImmutableDataset:
    """Assemble one validated immutable dataset without creating source facts."""

    provider_id = _required_text(provider_id, field_name="provider_id")
    dataset_id = _required_text(dataset_id, field_name="dataset_id")
    dataset_version = _required_text(dataset_version, field_name="dataset_version")

    companies = _required_tuple(companies, field_name="companies")
    securities = _required_tuple(securities, field_name="securities")
    periods = _required_tuple(periods, field_name="periods")
    source_record_authorities = _required_tuple(
        source_record_authorities,
        field_name="source_record_authorities",
    )
    if not source_record_authorities:
        raise ValueError("source_record_authorities must not be empty.")

    validate_finance_workspace(workspace)
    for company in companies:
        validate_company(company)
    for security in securities:
        validate_security(security)
    for period in periods:
        validate_financial_period(period)

    observations: list[FinancialObservation] = []
    for authority in source_record_authorities:
        validate_finance_source_record_authority(authority)
        if authority.provider_id != provider_id:
            raise ValueError(
                "FinanceSourceRecordAuthority provider_id differs from dataset provider_id."
            )
        for observation in authority.observations:
            validate_financial_observation(observation)
            if observation.provider != provider_id:
                raise ValueError(
                    "FinancialObservation provider differs from dataset provider_id."
                )
            if not observation.source_id.startswith(dataset_id + "/"):
                raise ValueError(
                    "FinancialObservation source_id is outside immutable dataset_id authority."
                )
            observations.append(observation)

    ordered_companies = tuple(sorted(companies, key=lambda item: item.company_id))
    ordered_securities = tuple(sorted(securities, key=lambda item: item.security_id))
    ordered_periods = tuple(
        sorted(periods, key=lambda item: item.financial_period_id)
    )
    ordered_observations = tuple(
        sorted(observations, key=lambda item: item.observation_id)
    )

    document: dict[str, Any] = {
        "schema_version": IMMUTABLE_DATASET_SCHEMA_VERSION,
        "provider_id": provider_id,
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "dataset_identity": "",
        "workspace": _canonical_object(
            dumps_finance_workspace(workspace),
            field_name="workspace",
        ),
        "companies": [
            _canonical_object(dumps_company(company), field_name="company")
            for company in ordered_companies
        ],
        "securities": [
            _canonical_object(dumps_security(security), field_name="security")
            for security in ordered_securities
        ],
        "periods": [
            _canonical_object(dumps_financial_period(period), field_name="period")
            for period in ordered_periods
        ],
        "observations": [
            _canonical_object(
                dumps_financial_observation(observation),
                field_name="observation",
            )
            for observation in ordered_observations
        ],
    }
    document["dataset_identity"] = derive_immutable_dataset_identity(document)

    return validate_immutable_dataset_document(
        document,
        expected_provider_id=provider_id,
        expected_dataset_id=dataset_id,
        expected_dataset_version=dataset_version,
    )


__all__ = ["assemble_immutable_finance_dataset"]
