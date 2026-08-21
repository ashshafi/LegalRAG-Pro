from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Final

from finance_domain.identity import canonical_json_bytes, derive_finance_id, validate_sha256_id
from finance_domain.models import (
    Company,
    FinanceWorkspace,
    FinancialObservation,
    FinancialPeriod,
    Security,
)
from finance_domain.serialization import (
    loads_company,
    loads_finance_workspace,
    loads_financial_observation,
    loads_financial_period,
    loads_security,
)
from finance_domain.validation import (
    validate_company,
    validate_finance_workspace,
    validate_financial_observation,
    validate_financial_period,
    validate_security,
)


IMMUTABLE_DATASET_SCHEMA_VERSION: Final[str] = "finance-immutable-dataset/1.0"

_REQUIRED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "provider_id",
        "dataset_id",
        "dataset_version",
        "dataset_identity",
        "workspace",
        "companies",
        "securities",
        "periods",
        "observations",
    }
)


@dataclass(frozen=True, slots=True)
class ValidatedImmutableDataset:
    provider_id: str
    dataset_id: str
    dataset_version: str
    dataset_identity: str
    workspace: FinanceWorkspace
    companies: tuple[Company, ...]
    securities: tuple[Security, ...]
    periods: tuple[FinancialPeriod, ...]
    observations: tuple[FinancialObservation, ...]


def _reject_number(value: str) -> None:
    raise ValueError(f"Raw JSON numbers are not permitted: {value!r}.")


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON constants are not permitted: {value!r}.")


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key is not permitted: {key!r}.")
        result[key] = value
    return result


def dumps_immutable_dataset_document(value: dict[str, Any]) -> str:
    if not isinstance(value, dict):
        raise ValueError("Immutable finance dataset must be a JSON object.")
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def loads_immutable_dataset_document(payload: str) -> dict[str, Any]:
    if not isinstance(payload, str):
        raise ValueError("Immutable finance dataset payload must be text.")
    data = json.loads(
        payload,
        parse_int=_reject_number,
        parse_float=_reject_number,
        parse_constant=_reject_constant,
        object_pairs_hook=_object_without_duplicates,
    )
    if not isinstance(data, dict):
        raise ValueError("Immutable finance dataset must be a JSON object.")
    if payload != dumps_immutable_dataset_document(data):
        raise ValueError("Immutable finance dataset JSON must use exact canonical form.")
    return data


def immutable_dataset_identity_payload_to_dict(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Immutable finance dataset must be a JSON object.")
    if "dataset_identity" not in value:
        raise ValueError("Immutable finance dataset is missing dataset_identity.")
    payload = dict(value)
    payload.pop("dataset_identity")
    return payload


def derive_immutable_dataset_identity(value: dict[str, Any]) -> str:
    return derive_finance_id(immutable_dataset_identity_payload_to_dict(value))


def _required_text(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be non-empty canonical text.")
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
        raise ValueError(f"{field_name} must contain unique identities.")
    if values != tuple(sorted(values)):
        raise ValueError(f"{field_name} must use canonical identity order.")


def validate_immutable_dataset_document(
    data: dict[str, Any],
    *,
    expected_provider_id: str | None = None,
    expected_dataset_id: str | None = None,
    expected_dataset_version: str | None = None,
) -> ValidatedImmutableDataset:
    if not isinstance(data, dict):
        raise ValueError("Immutable finance dataset must be a JSON object.")
    if frozenset(data) != _REQUIRED_KEYS:
        raise ValueError("Immutable finance dataset keys do not match the schema exactly.")
    if data["schema_version"] != IMMUTABLE_DATASET_SCHEMA_VERSION:
        raise ValueError("Unsupported immutable finance dataset schema_version.")

    provider_id = _required_text(data["provider_id"], field_name="provider_id")
    dataset_id = _required_text(data["dataset_id"], field_name="dataset_id")
    dataset_version = _required_text(data["dataset_version"], field_name="dataset_version")
    dataset_identity = _required_text(data["dataset_identity"], field_name="dataset_identity")
    validate_sha256_id(dataset_identity, field_name="dataset_identity")

    if expected_provider_id is not None and provider_id != expected_provider_id:
        raise ValueError("provider_id does not match requested provider authority.")
    if expected_dataset_id is not None and dataset_id != expected_dataset_id:
        raise ValueError("dataset_id does not match requested dataset authority.")
    if expected_dataset_version is not None and dataset_version != expected_dataset_version:
        raise ValueError("dataset_version does not match requested dataset authority.")

    expected_identity = derive_immutable_dataset_identity(data)
    if dataset_identity != expected_identity:
        raise ValueError("dataset_identity does not match canonical immutable dataset content.")

    workspace = loads_finance_workspace(
        _canonical_record_text(data["workspace"], field_name="workspace")
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

    validate_finance_workspace(workspace)
    for value in companies:
        validate_company(value)
    for value in securities:
        validate_security(value)
    for value in periods:
        validate_financial_period(value)
    for value in observations:
        validate_financial_observation(value)

    company_ids = tuple(item.company_id for item in companies)
    security_ids = tuple(item.security_id for item in securities)
    period_ids = tuple(item.financial_period_id for item in periods)
    observation_ids = tuple(item.observation_id for item in observations)

    _require_sorted_unique(company_ids, field_name="companies")
    _require_sorted_unique(security_ids, field_name="securities")
    _require_sorted_unique(period_ids, field_name="periods")
    _require_sorted_unique(observation_ids, field_name="observations")

    company_by_id = {item.company_id: item for item in companies}
    security_by_id = {item.security_id: item for item in securities}
    period_by_id = {item.financial_period_id: item for item in periods}

    for company in companies:
        if company.workspace_id != workspace.workspace_id:
            raise ValueError("Company workspace_id does not match immutable dataset workspace.")

    for security in securities:
        if security.workspace_id != workspace.workspace_id:
            raise ValueError("Security workspace_id does not match immutable dataset workspace.")
        if security.company_id not in company_by_id:
            raise ValueError("Security references an unknown company_id.")

    for period in periods:
        if period.workspace_id != workspace.workspace_id:
            raise ValueError("FinancialPeriod workspace_id does not match immutable dataset workspace.")
        if period.company_id not in company_by_id:
            raise ValueError("FinancialPeriod references an unknown company_id.")

    for observation in observations:
        if observation.workspace_id != workspace.workspace_id:
            raise ValueError(
                "FinancialObservation workspace_id does not match immutable dataset workspace."
            )
        if observation.company_id not in company_by_id:
            raise ValueError("FinancialObservation references an unknown company_id.")
        if observation.provider != provider_id:
            raise ValueError("FinancialObservation provider differs from immutable provider authority.")
        if not observation.source_id.startswith(dataset_id + "/"):
            raise ValueError("FinancialObservation source_id differs from immutable dataset authority.")

        if observation.security_id is not None:
            security = security_by_id.get(observation.security_id)
            if security is None:
                raise ValueError("FinancialObservation references an unknown security_id.")
            if security.company_id != observation.company_id:
                raise ValueError("FinancialObservation security/company lineage is inconsistent.")

        if observation.financial_period_id is not None:
            period = period_by_id.get(observation.financial_period_id)
            if period is None:
                raise ValueError("FinancialObservation references an unknown financial_period_id.")
            if period.company_id != observation.company_id:
                raise ValueError("FinancialObservation period/company lineage is inconsistent.")

    return ValidatedImmutableDataset(
        provider_id=provider_id,
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        dataset_identity=dataset_identity,
        workspace=workspace,
        companies=companies,
        securities=securities,
        periods=periods,
        observations=observations,
    )


__all__ = [
    "IMMUTABLE_DATASET_SCHEMA_VERSION",
    "ValidatedImmutableDataset",
    "derive_immutable_dataset_identity",
    "dumps_immutable_dataset_document",
    "immutable_dataset_identity_payload_to_dict",
    "loads_immutable_dataset_document",
    "validate_immutable_dataset_document",
]
