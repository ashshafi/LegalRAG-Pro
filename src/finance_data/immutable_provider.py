from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import re

from finance_domain.identity import canonical_uuid, validate_sha256_id
from finance_domain.models import (
    Company,
    FinanceWorkspace,
    FinancialObservation,
    FinancialPeriod,
    Security,
)
from finance_domain.validation import observation_available_as_of

from .immutable_dataset import (
    loads_immutable_dataset_document,
    validate_immutable_dataset_document,
)
from .provider import FinanceDataLookupError, FinancialDataProvider


_METRIC_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")


class ImmutableDatasetProvider(FinancialDataProvider):
    def __init__(
        self,
        *,
        dataset_path: Path,
        expected_provider_id: str,
        expected_dataset_id: str,
        expected_dataset_version: str,
    ) -> None:
        path = Path(dataset_path)
        if not path.is_file():
            raise FinanceDataLookupError("Immutable finance dataset file does not exist.")

        try:
            payload = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise FinanceDataLookupError("Immutable finance dataset could not be read.") from exc

        data = loads_immutable_dataset_document(payload)
        validated = validate_immutable_dataset_document(
            data,
            expected_provider_id=expected_provider_id,
            expected_dataset_id=expected_dataset_id,
            expected_dataset_version=expected_dataset_version,
        )

        self._dataset = validated
        self._companies = {item.company_id: item for item in validated.companies}
        self._securities = {item.security_id: item for item in validated.securities}
        self._periods = {item.financial_period_id: item for item in validated.periods}

    @property
    def provider_id(self) -> str:
        return self._dataset.provider_id

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

    def list_companies(self) -> tuple[Company, ...]:
        return self._dataset.companies

    def list_securities(self, *, company_id: str | None = None) -> tuple[Security, ...]:
        if company_id is None:
            return self._dataset.securities
        canonical_uuid(company_id, field_name="company_id")
        if company_id not in self._companies:
            raise FinanceDataLookupError("Unknown company_id.")
        return tuple(item for item in self._dataset.securities if item.company_id == company_id)

    def list_periods(self, *, company_id: str) -> tuple[FinancialPeriod, ...]:
        canonical_uuid(company_id, field_name="company_id")
        if company_id not in self._companies:
            raise FinanceDataLookupError("Unknown company_id.")
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
            raise FinanceDataLookupError("Unknown company_id.")

        if security_id is not None:
            canonical_uuid(security_id, field_name="security_id")
            security = self._securities.get(security_id)
            if security is None:
                raise FinanceDataLookupError("Unknown security_id.")
            if security.company_id != company_id:
                raise FinanceDataLookupError("security_id does not belong to company_id.")

        if metric_code is not None:
            if not isinstance(metric_code, str) or not _METRIC_CODE.fullmatch(metric_code):
                raise ValueError("metric_code must use canonical uppercase identifier syntax.")

        if financial_period_id is not None:
            validate_sha256_id(financial_period_id, field_name="financial_period_id")
            period = self._periods.get(financial_period_id)
            if period is None:
                raise FinanceDataLookupError("Unknown financial_period_id.")
            if period.company_id != company_id:
                raise FinanceDataLookupError("financial_period_id does not belong to company_id.")

        if as_of is not None:
            if not isinstance(as_of, datetime):
                raise ValueError("as_of must be a datetime.")
            if as_of.tzinfo is None or as_of.utcoffset() is None:
                raise ValueError("as_of must be timezone-aware UTC.")
            if as_of.utcoffset() != timedelta(0):
                raise ValueError("as_of must use UTC.")

        result = []
        for observation in self._dataset.observations:
            if observation.company_id != company_id:
                continue
            if security_id is not None and observation.security_id != security_id:
                continue
            if metric_code is not None and observation.metric_code != metric_code:
                continue
            if (
                financial_period_id is not None
                and observation.financial_period_id != financial_period_id
            ):
                continue
            if as_of is not None and not observation_available_as_of(observation, as_of):
                continue
            result.append(observation)
        return tuple(result)


__all__ = ["ImmutableDatasetProvider"]
