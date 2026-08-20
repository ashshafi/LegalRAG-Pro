"""Provider-independent read-only financial observation interface for Finance F2."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from finance_domain import Company, FinanceWorkspace, FinancialObservation, FinancialPeriod, Security


class FinanceDataProviderError(RuntimeError):
    """Base error for governed finance-data provider failures."""


class FinanceDataLookupError(FinanceDataProviderError):
    """Raised when a query names an entity or period outside provider authority."""


class FinancialDataProvider(ABC):
    """Read-only provider contract returning validated F1 finance-domain records.

    F2 deliberately does not define calculations, normalisation, retrieval from
    the network, or model-generated data. Implementations expose source
    observations only.
    """

    @property
    @abstractmethod
    def provider_id(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def dataset_id(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def dataset_version(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def dataset_identity(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def workspace(self) -> FinanceWorkspace:
        raise NotImplementedError

    @abstractmethod
    def list_companies(self) -> tuple[Company, ...]:
        raise NotImplementedError

    @abstractmethod
    def list_securities(self, *, company_id: str | None = None) -> tuple[Security, ...]:
        raise NotImplementedError

    @abstractmethod
    def list_periods(self, *, company_id: str) -> tuple[FinancialPeriod, ...]:
        raise NotImplementedError

    @abstractmethod
    def get_company(self, *, company_id: str) -> Company | None:
        raise NotImplementedError

    @abstractmethod
    def get_security(self, *, security_id: str) -> Security | None:
        raise NotImplementedError

    @abstractmethod
    def get_observations(
        self,
        *,
        company_id: str,
        security_id: str | None = None,
        metric_code: str | None = None,
        financial_period_id: str | None = None,
        as_of: datetime | None = None,
    ) -> tuple[FinancialObservation, ...]:
        raise NotImplementedError


__all__ = [
    "FinanceDataLookupError",
    "FinanceDataProviderError",
    "FinancialDataProvider",
]
