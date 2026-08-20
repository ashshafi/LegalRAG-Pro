"""Fail-closed validation for frozen Finance F2 observation datasets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from finance_domain import (
    Company,
    FinanceWorkspace,
    FinancialObservation,
    FinancialPeriod,
    Security,
    dumps_company,
    dumps_finance_workspace,
    dumps_financial_observation,
    dumps_financial_period,
    dumps_security,
    loads_company,
    loads_finance_workspace,
    loads_financial_observation,
    loads_financial_period,
    loads_security,
)
from finance_domain.identity import canonical_json_bytes, validate_sha256_id

from .serialization import FROZEN_DATASET_SCHEMA_VERSION, derive_dataset_identity

_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "dataset_id",
        "dataset_version",
        "dataset_identity",
        "workspace",
        "target_company_id",
        "comparable_company_ids",
        "companies",
        "securities",
        "periods",
        "observations",
    }
)


@dataclass(frozen=True, slots=True)
class ValidatedFrozenDataset:
    dataset_id: str
    dataset_version: str
    dataset_identity: str
    workspace: FinanceWorkspace
    target_company_id: str
    comparable_company_ids: tuple[str, ...]
    companies: tuple[Company, ...]
    securities: tuple[Security, ...]
    periods: tuple[FinancialPeriod, ...]
    observations: tuple[FinancialObservation, ...]


def _required_text(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be non-empty trimmed text.")
    return value


def _required_list(value: Any, *, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a JSON array.")
    return value


def _canonical_record_text(value: Any, *, field_name: str) -> str:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} entry must be a JSON object.")
    return canonical_json_bytes(value).decode("utf-8")


def _require_sorted_unique(values: tuple[str, ...], *, field_name: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} identities must be unique.")
    if values != tuple(sorted(values)):
        raise ValueError(f"{field_name} must use canonical identity-sorted order.")


def validate_frozen_dataset_document(
    data: dict[str, Any],
    *,
    expected_dataset_id: str | None = None,
    expected_dataset_version: str | None = None,
    expected_provider: str | None = None,
) -> ValidatedFrozenDataset:
    """Validate cross-record lineage and return immutable F1 records."""

    if not isinstance(data, dict):
        raise ValueError("Frozen finance dataset must be a dictionary.")
    if set(data) != _ROOT_KEYS:
        missing = sorted(_ROOT_KEYS - set(data))
        extra = sorted(set(data) - _ROOT_KEYS)
        raise ValueError(f"Frozen dataset root fields mismatch; missing={missing}, extra={extra}.")
    if data["schema_version"] != FROZEN_DATASET_SCHEMA_VERSION:
        raise ValueError("Unsupported frozen finance dataset schema_version.")

    dataset_id = _required_text(data["dataset_id"], field_name="dataset_id")
    dataset_version = _required_text(data["dataset_version"], field_name="dataset_version")
    dataset_identity = _required_text(data["dataset_identity"], field_name="dataset_identity")
    validate_sha256_id(dataset_identity, field_name="dataset_identity")

    if expected_dataset_id is not None and dataset_id != expected_dataset_id:
        raise ValueError("Frozen dataset_id does not match requested provider authority.")
    if expected_dataset_version is not None and dataset_version != expected_dataset_version:
        raise ValueError("Frozen dataset_version does not match requested provider authority.")

    expected_identity = derive_dataset_identity(data)
    if dataset_identity != expected_identity:
        raise ValueError("dataset_identity does not match canonical frozen dataset content.")

    workspace = loads_finance_workspace(
        _canonical_record_text(data["workspace"], field_name="workspace")
    )
    target_company_id = _required_text(data["target_company_id"], field_name="target_company_id")
    comparable_company_ids_raw = _required_list(
        data["comparable_company_ids"], field_name="comparable_company_ids"
    )
    comparable_company_ids = tuple(
        _required_text(item, field_name="comparable_company_id")
        for item in comparable_company_ids_raw
    )

    companies = tuple(
        loads_company(_canonical_record_text(item, field_name="companies"))
        for item in _required_list(data["companies"], field_name="companies")
    )
    securities = tuple(
        loads_security(_canonical_record_text(item, field_name="securities"))
        for item in _required_list(data["securities"], field_name="securities")
    )
    periods = tuple(
        loads_financial_period(_canonical_record_text(item, field_name="periods"))
        for item in _required_list(data["periods"], field_name="periods")
    )
    observations = tuple(
        loads_financial_observation(_canonical_record_text(item, field_name="observations"))
        for item in _required_list(data["observations"], field_name="observations")
    )

    company_ids = tuple(item.company_id for item in companies)
    security_ids = tuple(item.security_id for item in securities)
    period_ids = tuple(item.financial_period_id for item in periods)
    observation_ids = tuple(item.observation_id for item in observations)

    _require_sorted_unique(company_ids, field_name="companies")
    _require_sorted_unique(security_ids, field_name="securities")
    _require_sorted_unique(period_ids, field_name="periods")
    _require_sorted_unique(observation_ids, field_name="observations")

    company_by_id = {item.company_id: item for item in companies}
    if target_company_id not in company_by_id:
        raise ValueError("target_company_id references an unknown company.")
    if len(comparable_company_ids) != 5:
        raise ValueError("FIN-DEMO comparable_company_ids must contain exactly five companies.")
    if len(set(comparable_company_ids)) != len(comparable_company_ids):
        raise ValueError("comparable_company_ids must be unique.")
    if comparable_company_ids != tuple(sorted(comparable_company_ids)):
        raise ValueError("comparable_company_ids must use canonical sorted order.")
    if target_company_id in comparable_company_ids:
        raise ValueError("target_company_id must not also be a comparable company.")
    if set(comparable_company_ids) != (set(company_by_id) - {target_company_id}):
        raise ValueError("comparable_company_ids must identify every non-target demo company exactly once.")
    security_by_id = {item.security_id: item for item in securities}
    period_by_id = {item.financial_period_id: item for item in periods}

    for company in companies:
        if company.workspace_id != workspace.workspace_id:
            raise ValueError("Company workspace_id does not match frozen dataset workspace.")

    for security in securities:
        if security.workspace_id != workspace.workspace_id:
            raise ValueError("Security workspace_id does not match frozen dataset workspace.")
        if security.company_id not in company_by_id:
            raise ValueError("Security references an unknown company_id.")

    for period in periods:
        if period.workspace_id != workspace.workspace_id:
            raise ValueError("FinancialPeriod workspace_id does not match frozen dataset workspace.")
        if period.company_id not in company_by_id:
            raise ValueError("FinancialPeriod references an unknown company_id.")

    for observation in observations:
        if observation.workspace_id != workspace.workspace_id:
            raise ValueError("FinancialObservation workspace_id does not match frozen dataset workspace.")
        if observation.company_id not in company_by_id:
            raise ValueError("FinancialObservation references an unknown company_id.")
        if expected_provider is not None and observation.provider != expected_provider:
            raise ValueError("FinancialObservation provider differs from frozen provider authority.")
        if not observation.source_id.startswith(dataset_id + "/"):
            raise ValueError("FinancialObservation source_id is outside frozen dataset authority.")
        if observation.security_id is not None:
            security = security_by_id.get(observation.security_id)
            if security is None:
                raise ValueError("FinancialObservation references an unknown security_id.")
            if security.company_id != observation.company_id:
                raise ValueError("FinancialObservation security/company lineage mismatch.")
        if observation.financial_period_id is not None:
            period = period_by_id.get(observation.financial_period_id)
            if period is None:
                raise ValueError("FinancialObservation references an unknown financial_period_id.")
            if period.company_id != observation.company_id:
                raise ValueError("FinancialObservation period/company lineage mismatch.")

    # Round-trip exactness protects against hidden alternate encodings inside
    # individual F1 records even though the outer dataset may be pretty-printed.
    for item, dumper in (
        *((company, dumps_company) for company in companies),
        *((security, dumps_security) for security in securities),
        *((period, dumps_financial_period) for period in periods),
        *((observation, dumps_financial_observation) for observation in observations),
    ):
        dumper(item)
    dumps_finance_workspace(workspace)

    return ValidatedFrozenDataset(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        dataset_identity=dataset_identity,
        workspace=workspace,
        target_company_id=target_company_id,
        comparable_company_ids=comparable_company_ids,
        companies=companies,
        securities=securities,
        periods=periods,
        observations=observations,
    )


__all__ = ["ValidatedFrozenDataset", "validate_frozen_dataset_document"]
