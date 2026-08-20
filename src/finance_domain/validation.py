"""Fail-closed validation and point-in-time eligibility for Finance MVP records."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal

from .identity import canonical_decimal_text, canonical_uuid, derive_finance_id, validate_sha256_id
from .models import (
    COMPANY_SCHEMA_VERSION,
    FINANCIAL_FACT_SCHEMA_VERSION,
    FINANCIAL_OBSERVATION_SCHEMA_VERSION,
    FINANCIAL_PERIOD_SCHEMA_VERSION,
    FINANCE_WORKSPACE_SCHEMA_VERSION,
    SECURITY_SCHEMA_VERSION,
    Company,
    FinanceWorkspace,
    FinancialFact,
    FinancialObservation,
    FinancialPeriod,
    FinancialPeriodType,
    Security,
    SecurityType,
    WorkspaceStatus,
)
from .serialization import (
    financial_fact_identity_payload_to_dict,
    financial_observation_identity_payload_to_dict,
    financial_period_identity_payload_to_dict,
)

_METRIC_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_COUNTRY = re.compile(r"^[A-Z]{2}$")
_MIC = re.compile(r"^[A-Z0-9]{4}$")
_UNIT = re.compile(r"^[a-z][a-z0-9_./-]{0,63}$")


def _required_text(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be non-empty trimmed text.")
    return value


def _optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name=field_name)


def _utc_datetime(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    if value.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field_name} must be expressed in UTC.")
    return value.astimezone(timezone.utc)


def _finite_decimal(value: Decimal, *, field_name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field_name} must be a finite Decimal.")
    canonical_decimal_text(value)
    return value


def _currency(value: str | None, *, field_name: str = "currency") -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _CURRENCY.fullmatch(value):
        raise ValueError(f"{field_name} must be an uppercase three-letter currency code.")
    return value


def _metric(value: str) -> str:
    if not isinstance(value, str) or not _METRIC_CODE.fullmatch(value):
        raise ValueError("metric_code must use canonical uppercase identifier syntax.")
    return value


def _unit(value: str) -> str:
    if not isinstance(value, str) or not _UNIT.fullmatch(value):
        raise ValueError("unit must use canonical lowercase unit syntax.")
    return value


def validate_finance_workspace(value: FinanceWorkspace) -> None:
    if not isinstance(value, FinanceWorkspace):
        raise ValueError("value must be a FinanceWorkspace instance.")
    if value.schema_version != FINANCE_WORKSPACE_SCHEMA_VERSION:
        raise ValueError("Unsupported FinanceWorkspace schema_version.")
    canonical_uuid(value.workspace_id, field_name="workspace_id")
    _required_text(value.name, field_name="name")
    if not isinstance(value.status, WorkspaceStatus):
        raise ValueError("FinanceWorkspace.status must be WorkspaceStatus.")
    _utc_datetime(value.created_at, field_name="created_at")


def validate_company(value: Company) -> None:
    if not isinstance(value, Company):
        raise ValueError("value must be a Company instance.")
    if value.schema_version != COMPANY_SCHEMA_VERSION:
        raise ValueError("Unsupported Company schema_version.")
    canonical_uuid(value.workspace_id, field_name="workspace_id")
    canonical_uuid(value.company_id, field_name="company_id")
    _required_text(value.legal_name, field_name="legal_name")
    _required_text(value.display_name, field_name="display_name")
    if not isinstance(value.country_code, str) or not _COUNTRY.fullmatch(value.country_code):
        raise ValueError("country_code must be an uppercase two-letter country code.")
    _currency(value.reporting_currency, field_name="reporting_currency")


def validate_security(value: Security) -> None:
    if not isinstance(value, Security):
        raise ValueError("value must be a Security instance.")
    if value.schema_version != SECURITY_SCHEMA_VERSION:
        raise ValueError("Unsupported Security schema_version.")
    canonical_uuid(value.workspace_id, field_name="workspace_id")
    canonical_uuid(value.security_id, field_name="security_id")
    canonical_uuid(value.company_id, field_name="company_id")
    if not isinstance(value.security_type, SecurityType):
        raise ValueError("Security.security_type must be SecurityType.")
    _required_text(value.ticker, field_name="ticker")
    if not _MIC.fullmatch(value.exchange_mic):
        raise ValueError("exchange_mic must use four uppercase alphanumeric characters.")
    _currency(value.currency)


def validate_financial_period(value: FinancialPeriod) -> None:
    if not isinstance(value, FinancialPeriod):
        raise ValueError("value must be a FinancialPeriod instance.")
    if value.schema_version != FINANCIAL_PERIOD_SCHEMA_VERSION:
        raise ValueError("Unsupported FinancialPeriod schema_version.")
    canonical_uuid(value.workspace_id, field_name="workspace_id")
    canonical_uuid(value.company_id, field_name="company_id")
    if not isinstance(value.period_type, FinancialPeriodType):
        raise ValueError("FinancialPeriod.period_type must be FinancialPeriodType.")
    _required_text(value.label, field_name="label")
    if value.end_date < value.start_date:
        raise ValueError("FinancialPeriod.end_date must not precede start_date.")
    validate_sha256_id(value.financial_period_id, field_name="financial_period_id")
    expected = derive_finance_id(financial_period_identity_payload_to_dict(value))
    if value.financial_period_id != expected:
        raise ValueError("financial_period_id does not match its canonical identity payload.")


def observation_knowledge_available_at(value: FinancialObservation) -> datetime:
    """Return when the observation was legitimately knowable for as-of analysis.

    A published source becomes knowable at publication time. Sources without a
    publication timestamp (for example a market observation) use observed_at.
    retrieval time is provenance and does not create look-ahead by itself.
    """

    validate_financial_observation(value)
    return value.publication_at if value.publication_at is not None else value.observed_at


def observation_available_as_of(value: FinancialObservation, as_of: datetime) -> bool:
    _utc_datetime(as_of, field_name="as_of")
    return observation_knowledge_available_at(value) <= as_of


def validate_financial_observation(value: FinancialObservation) -> None:
    if not isinstance(value, FinancialObservation):
        raise ValueError("value must be a FinancialObservation instance.")
    if value.schema_version != FINANCIAL_OBSERVATION_SCHEMA_VERSION:
        raise ValueError("Unsupported FinancialObservation schema_version.")
    canonical_uuid(value.workspace_id, field_name="workspace_id")
    canonical_uuid(value.company_id, field_name="company_id")
    if value.security_id is not None:
        canonical_uuid(value.security_id, field_name="security_id")
    _metric(value.metric_code)
    _finite_decimal(value.value, field_name="value")
    _currency(value.currency)
    _unit(value.unit)
    if value.financial_period_id is not None:
        validate_sha256_id(value.financial_period_id, field_name="financial_period_id")
    _required_text(value.provider, field_name="provider")
    _required_text(value.source_id, field_name="source_id")
    _required_text(value.source_version, field_name="source_version")
    publication_at = (
        _utc_datetime(value.publication_at, field_name="publication_at")
        if value.publication_at is not None
        else None
    )
    if value.effective_at is not None:
        _utc_datetime(value.effective_at, field_name="effective_at")
    observed_at = _utc_datetime(value.observed_at, field_name="observed_at")
    retrieved_at = _utc_datetime(value.retrieved_at, field_name="retrieved_at")
    if retrieved_at < observed_at:
        raise ValueError("retrieved_at must not precede observed_at.")
    if publication_at is not None and retrieved_at < publication_at:
        raise ValueError("retrieved_at must not precede publication_at.")
    validate_sha256_id(value.observation_id, field_name="observation_id")
    expected = derive_finance_id(financial_observation_identity_payload_to_dict(value))
    if value.observation_id != expected:
        raise ValueError("observation_id does not match its canonical identity payload.")


def validate_financial_fact(value: FinancialFact) -> None:
    if not isinstance(value, FinancialFact):
        raise ValueError("value must be a FinancialFact instance.")
    if value.schema_version != FINANCIAL_FACT_SCHEMA_VERSION:
        raise ValueError("Unsupported FinancialFact schema_version.")
    canonical_uuid(value.workspace_id, field_name="workspace_id")
    canonical_uuid(value.company_id, field_name="company_id")
    if value.security_id is not None:
        canonical_uuid(value.security_id, field_name="security_id")
    _metric(value.metric_code)
    _finite_decimal(value.value, field_name="value")
    _currency(value.currency)
    _unit(value.unit)
    if value.financial_period_id is not None:
        validate_sha256_id(value.financial_period_id, field_name="financial_period_id")
    _utc_datetime(value.as_of, field_name="as_of")
    if not value.observation_ids:
        raise ValueError("FinancialFact.observation_ids must not be empty.")
    for observation_id in value.observation_ids:
        validate_sha256_id(observation_id, field_name="observation_id")
    if len(set(value.observation_ids)) != len(value.observation_ids):
        raise ValueError("FinancialFact.observation_ids must be unique.")
    if value.observation_ids != tuple(sorted(value.observation_ids)):
        raise ValueError("FinancialFact.observation_ids must use canonical sorted order.")
    _optional_text(value.reconciliation_note, field_name="reconciliation_note")
    validate_sha256_id(value.fact_id, field_name="fact_id")
    expected = derive_finance_id(financial_fact_identity_payload_to_dict(value))
    if value.fact_id != expected:
        raise ValueError("fact_id does not match its canonical identity payload.")


__all__ = [
    "observation_available_as_of",
    "observation_knowledge_available_at",
    "validate_company",
    "validate_finance_workspace",
    "validate_financial_fact",
    "validate_financial_observation",
    "validate_financial_period",
    "validate_security",
]
