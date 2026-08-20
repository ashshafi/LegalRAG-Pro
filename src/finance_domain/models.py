"""Immutable Finance MVP domain models.

F1 deliberately contains no provider, retrieval, calculation, UI, or LLM logic.
It establishes only deterministic finance identities and point-in-time semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final

FINANCE_WORKSPACE_SCHEMA_VERSION: Final[str] = "finance-workspace/1.0"
COMPANY_SCHEMA_VERSION: Final[str] = "finance-company/1.0"
SECURITY_SCHEMA_VERSION: Final[str] = "finance-security/1.0"
FINANCIAL_PERIOD_SCHEMA_VERSION: Final[str] = "financial-period/1.0"
FINANCIAL_OBSERVATION_SCHEMA_VERSION: Final[str] = "financial-observation/1.0"
FINANCIAL_FACT_SCHEMA_VERSION: Final[str] = "financial-fact/1.0"


class WorkspaceStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class SecurityType(StrEnum):
    COMMON_EQUITY = "common_equity"
    PREFERRED_EQUITY = "preferred_equity"
    DEBT = "debt"
    OTHER = "other"


class FinancialPeriodType(StrEnum):
    FY = "fy"
    H1 = "h1"
    H2 = "h2"
    Q1 = "q1"
    Q2 = "q2"
    Q3 = "q3"
    Q4 = "q4"
    LTM = "ltm"
    NTM = "ntm"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class FinanceWorkspace:
    schema_version: str
    workspace_id: str
    name: str
    status: WorkspaceStatus
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Company:
    schema_version: str
    workspace_id: str
    company_id: str
    legal_name: str
    display_name: str
    country_code: str
    reporting_currency: str


@dataclass(frozen=True, slots=True)
class Security:
    schema_version: str
    workspace_id: str
    security_id: str
    company_id: str
    security_type: SecurityType
    ticker: str
    exchange_mic: str
    currency: str


@dataclass(frozen=True, slots=True)
class FinancialPeriod:
    schema_version: str
    workspace_id: str
    company_id: str
    period_type: FinancialPeriodType
    label: str
    start_date: date
    end_date: date
    financial_period_id: str


@dataclass(frozen=True, slots=True)
class FinancialObservation:
    schema_version: str
    workspace_id: str
    company_id: str
    security_id: str | None
    metric_code: str
    value: Decimal
    currency: str | None
    unit: str
    financial_period_id: str | None
    provider: str
    source_id: str
    source_version: str
    publication_at: datetime | None
    effective_at: datetime | None
    observed_at: datetime
    retrieved_at: datetime
    observation_id: str


@dataclass(frozen=True, slots=True)
class FinancialFact:
    schema_version: str
    workspace_id: str
    company_id: str
    security_id: str | None
    metric_code: str
    value: Decimal
    currency: str | None
    unit: str
    financial_period_id: str | None
    as_of: datetime
    observation_ids: tuple[str, ...]
    reconciliation_note: str | None
    fact_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_ids", tuple(self.observation_ids))


__all__ = [
    "COMPANY_SCHEMA_VERSION",
    "FINANCIAL_FACT_SCHEMA_VERSION",
    "FINANCIAL_OBSERVATION_SCHEMA_VERSION",
    "FINANCIAL_PERIOD_SCHEMA_VERSION",
    "FINANCE_WORKSPACE_SCHEMA_VERSION",
    "SECURITY_SCHEMA_VERSION",
    "Company",
    "FinanceWorkspace",
    "FinancialFact",
    "FinancialObservation",
    "FinancialPeriod",
    "FinancialPeriodType",
    "Security",
    "SecurityType",
    "WorkspaceStatus",
]
