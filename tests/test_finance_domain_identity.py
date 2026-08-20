from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from finance_domain.identity import canonical_decimal_text, derive_finance_id
from finance_domain.models import (
    FINANCIAL_OBSERVATION_SCHEMA_VERSION,
    FINANCIAL_PERIOD_SCHEMA_VERSION,
    FinancialObservation,
    FinancialPeriod,
    FinancialPeriodType,
)
from finance_domain.serialization import (
    financial_observation_identity_payload_to_dict,
    financial_period_identity_payload_to_dict,
)

WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
COMPANY_ID = "22222222-2222-4222-8222-222222222222"


def _period():
    value = FinancialPeriod(
        schema_version=FINANCIAL_PERIOD_SCHEMA_VERSION,
        workspace_id=WORKSPACE_ID,
        company_id=COMPANY_ID,
        period_type=FinancialPeriodType.FY,
        label="FY2025",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        financial_period_id="sha256:" + "0" * 64,
    )
    return replace(value, financial_period_id=derive_finance_id(financial_period_identity_payload_to_dict(value)))


def _observation(value=Decimal("1842.00"), period_id=None):
    item = FinancialObservation(
        schema_version=FINANCIAL_OBSERVATION_SCHEMA_VERSION,
        workspace_id=WORKSPACE_ID,
        company_id=COMPANY_ID,
        security_id=None,
        metric_code="REVENUE",
        value=value,
        currency="GBP",
        unit="currency",
        financial_period_id=period_id,
        provider="DemoProvider",
        source_id="annual-report-2025",
        source_version="1",
        publication_at=datetime(2026, 2, 17, 7, 0, tzinfo=timezone.utc),
        effective_at=None,
        observed_at=datetime(2026, 2, 17, 7, 0, tzinfo=timezone.utc),
        retrieved_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        observation_id="sha256:" + "0" * 64,
    )
    return replace(item, observation_id=derive_finance_id(financial_observation_identity_payload_to_dict(item)))


def test_decimal_identity_is_numeric_not_scale_sensitive():
    assert canonical_decimal_text(Decimal("1842.00")) == "1842"
    assert canonical_decimal_text(Decimal("1842")) == "1842"
    a = _observation(Decimal("1842.00"))
    b = _observation(Decimal("1842"))
    assert a.observation_id == b.observation_id


def test_material_period_change_changes_observation_identity():
    period = _period()
    a = _observation(period_id=period.financial_period_id)
    b = _observation(period_id=None)
    assert a.observation_id != b.observation_id


def test_non_finite_decimals_are_rejected_from_canonical_identity():
    with pytest.raises(ValueError):
        canonical_decimal_text(Decimal("NaN"))
