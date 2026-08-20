"""Frozen fictional Finance F2 provider for deterministic investment-banking demos."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Final

from finance_domain import (
    Company,
    FinanceWorkspace,
    FinancialObservation,
    FinancialPeriod,
    Security,
    observation_available_as_of,
)
from finance_domain.identity import canonical_uuid, validate_sha256_id

from .provider import FinanceDataLookupError, FinancialDataProvider
from .serialization import loads_dataset_document
from .validation import ValidatedFrozenDataset, validate_frozen_dataset_document

FROZEN_DEMO_PROVIDER_ID: Final[str] = "frozen-demo"
FROZEN_DEMO_DATASET_ID: Final[str] = "FIN-DEMO-001"
FROZEN_DEMO_DATASET_VERSION: Final[str] = "1.0"
FROZEN_DEMO_RESOURCE_NAME: Final[str] = "FIN-DEMO-001.json"

_EXPECTED_COMPANY_COUNT: Final[int] = 6
_EXPECTED_SECURITY_COUNT: Final[int] = 6
_EXPECTED_PERIOD_COUNT: Final[int] = 12
_EXPECTED_OBSERVATION_COUNT: Final[int] = 66
_METRIC_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")


class FrozenDemoProvider(FinancialDataProvider):
    """Read only, local-only provider backed by immutable FIN-DEMO-001."""

    def __init__(self, *, dataset_path: Path | None = None) -> None:
        path = dataset_path or Path(__file__).with_name("datasets") / FROZEN_DEMO_RESOURCE_NAME
        if not isinstance(path, Path):
            path = Path(path)
        try:
            payload = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise FinanceDataLookupError(f"Frozen demo dataset is unavailable: {path}") from exc

        document = loads_dataset_document(payload)
        validated = validate_frozen_dataset_document(
            document,
            expected_dataset_id=FROZEN_DEMO_DATASET_ID,
            expected_dataset_version=FROZEN_DEMO_DATASET_VERSION,
            expected_provider=FROZEN_DEMO_PROVIDER_ID,
        )
        self._validate_demo_cardinality(validated)

        self._dataset = validated
        self._companies = {item.company_id: item for item in validated.companies}
        self._securities = {item.security_id: item for item in validated.securities}
        self._periods = {item.financial_period_id: item for item in validated.periods}

    @staticmethod
    def _validate_demo_cardinality(value: ValidatedFrozenDataset) -> None:
        observed = (
            len(value.companies),
            len(value.securities),
            len(value.periods),
            len(value.observations),
        )
        expected = (
            _EXPECTED_COMPANY_COUNT,
            _EXPECTED_SECURITY_COUNT,
            _EXPECTED_PERIOD_COUNT,
            _EXPECTED_OBSERVATION_COUNT,
        )
        if observed != expected:
            raise ValueError(f"FIN-DEMO-001 cardinality mismatch; expected={expected}, observed={observed}.")

    @property
    def provider_id(self) -> str:
        return FROZEN_DEMO_PROVIDER_ID

    @property
    def dataset_id(self) -> str:
        return self._dataset.dataset_id

    @property
    def dataset_version(self) -> str:
        return self._dataset.dataset_version

    @property
    def dataset_identity(self) -> str:
        return self._dataset.dataset_identity

    @property
    def workspace(self) -> FinanceWorkspace:
        return self._dataset.workspace

    @property
    def target_company_id(self) -> str:
        return self._dataset.target_company_id

    @property
    def comparable_company_ids(self) -> tuple[str, ...]:
        return self._dataset.comparable_company_ids

    @property
    def target_company(self) -> Company:
        return self._companies[self._dataset.target_company_id]

    def list_comparable_companies(self) -> tuple[Company, ...]:
        return tuple(self._companies[item] for item in self._dataset.comparable_company_ids)

    def list_companies(self) -> tuple[Company, ...]:
        return self._dataset.companies

    def list_securities(self, *, company_id: str | None = None) -> tuple[Security, ...]:
        if company_id is None:
            return self._dataset.securities
        canonical_uuid(company_id, field_name="company_id")
        if company_id not in self._companies:
            raise FinanceDataLookupError(f"Unknown company_id {company_id!r}.")
        return tuple(item for item in self._dataset.securities if item.company_id == company_id)

    def list_periods(self, *, company_id: str) -> tuple[FinancialPeriod, ...]:
        canonical_uuid(company_id, field_name="company_id")
        if company_id not in self._companies:
            raise FinanceDataLookupError(f"Unknown company_id {company_id!r}.")
        return tuple(item for item in self._dataset.periods if item.company_id == company_id)

    def get_company(self, *, company_id: str) -> Company | None:
        canonical_uuid(company_id, field_name="company_id")
        return self._companies.get(company_id)

    def get_security(self, *, security_id: str) -> Security | None:
        canonical_uuid(security_id, field_name="security_id")
        return self._securities.get(security_id)

    def get_observations(
        self,
        *,
        company_id: str,
        security_id: str | None = None,
        metric_code: str | None = None,
        financial_period_id: str | None = None,
        as_of: datetime | None = None,
    ) -> tuple[FinancialObservation, ...]:
        canonical_uuid(company_id, field_name="company_id")
        if company_id not in self._companies:
            raise FinanceDataLookupError(f"Unknown company_id {company_id!r}.")

        if security_id is not None:
            canonical_uuid(security_id, field_name="security_id")
            security = self._securities.get(security_id)
            if security is None:
                raise FinanceDataLookupError(f"Unknown security_id {security_id!r}.")
            if security.company_id != company_id:
                raise FinanceDataLookupError("security_id does not belong to requested company_id.")

        if metric_code is not None:
            if not isinstance(metric_code, str) or not _METRIC_CODE.fullmatch(metric_code):
                raise ValueError("metric_code must use canonical uppercase identifier syntax.")

        if financial_period_id is not None:
            validate_sha256_id(financial_period_id, field_name="financial_period_id")
            period = self._periods.get(financial_period_id)
            if period is None:
                raise FinanceDataLookupError(
                    f"Unknown financial_period_id {financial_period_id!r}."
                )
            if period.company_id != company_id:
                raise FinanceDataLookupError(
                    "financial_period_id does not belong to requested company_id."
                )

        if as_of is not None:
            if not isinstance(as_of, datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:
                raise ValueError("as_of must be timezone-aware UTC datetime.")
            if as_of.utcoffset().total_seconds() != 0:
                raise ValueError("as_of must be expressed in UTC.")

        values = self._dataset.observations
        result = tuple(
            item
            for item in values
            if item.company_id == company_id
            and (security_id is None or item.security_id == security_id)
            and (metric_code is None or item.metric_code == metric_code)
            and (financial_period_id is None or item.financial_period_id == financial_period_id)
            and (as_of is None or observation_available_as_of(item, as_of))
        )
        return result


__all__ = [
    "FROZEN_DEMO_DATASET_ID",
    "FROZEN_DEMO_DATASET_VERSION",
    "FROZEN_DEMO_PROVIDER_ID",
    "FrozenDemoProvider",
]
