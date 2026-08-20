from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from finance_domain.identity import derive_finance_id
from finance_domain.models import (
    FINANCIAL_FACT_SCHEMA_VERSION,
    FINANCIAL_OBSERVATION_SCHEMA_VERSION,
    FINANCIAL_PERIOD_SCHEMA_VERSION,
    FinancialFact,
    FinancialObservation,
    FinancialPeriod,
    FinancialPeriodType,
)
from finance_domain.serialization import (
    financial_fact_identity_payload_to_dict,
    financial_observation_identity_payload_to_dict,
    financial_period_identity_payload_to_dict,
)
from finance_domain.validation import (
    observation_available_as_of,
    validate_financial_fact,
    validate_financial_observation,
    validate_financial_period,
)

WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
COMPANY_ID = "22222222-2222-4222-8222-222222222222"


def _period(start=date(2025, 1, 1), end=date(2025, 12, 31)):
    value = FinancialPeriod(
        schema_version=FINANCIAL_PERIOD_SCHEMA_VERSION,
        workspace_id=WORKSPACE_ID,
        company_id=COMPANY_ID,
        period_type=FinancialPeriodType.FY,
        label="FY2025",
        start_date=start,
        end_date=end,
        financial_period_id="sha256:" + "0" * 64,
    )
    return replace(value, financial_period_id=derive_finance_id(financial_period_identity_payload_to_dict(value)))


def _observation(publication_at=datetime(2026, 3, 15, tzinfo=timezone.utc), metric="REVENUE"):
    value = FinancialObservation(
        schema_version=FINANCIAL_OBSERVATION_SCHEMA_VERSION,
        workspace_id=WORKSPACE_ID,
        company_id=COMPANY_ID,
        security_id=None,
        metric_code=metric,
        value=Decimal("100"),
        currency="GBP",
        unit="currency",
        financial_period_id=None,
        provider="DemoProvider",
        source_id="source-1",
        source_version="1",
        publication_at=publication_at,
        effective_at=None,
        observed_at=publication_at,
        retrieved_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
        observation_id="sha256:" + "0" * 64,
    )
    return replace(value, observation_id=derive_finance_id(financial_observation_identity_payload_to_dict(value)))


def _fact(observation_ids):
    value = FinancialFact(
        schema_version=FINANCIAL_FACT_SCHEMA_VERSION,
        workspace_id=WORKSPACE_ID,
        company_id=COMPANY_ID,
        security_id=None,
        metric_code="REVENUE",
        value=Decimal("100"),
        currency="GBP",
        unit="currency",
        financial_period_id=None,
        as_of=datetime(2026, 3, 20, tzinfo=timezone.utc),
        observation_ids=tuple(observation_ids),
        reconciliation_note=None,
        fact_id="sha256:" + "0" * 64,
    )
    return replace(value, fact_id=derive_finance_id(financial_fact_identity_payload_to_dict(value)))


def test_point_in_time_rule_rejects_look_ahead_eligibility():
    obs = _observation()
    validate_financial_observation(obs)
    assert observation_available_as_of(obs, datetime(2026, 3, 1, tzinfo=timezone.utc)) is False
    assert observation_available_as_of(obs, datetime(2026, 3, 15, tzinfo=timezone.utc)) is True


def test_retrieval_after_as_of_does_not_create_look_ahead_if_source_was_published():
    obs = _observation(publication_at=datetime(2026, 2, 17, tzinfo=timezone.utc))
    assert obs.retrieved_at > datetime(2026, 3, 1, tzinfo=timezone.utc)
    assert observation_available_as_of(obs, datetime(2026, 3, 1, tzinfo=timezone.utc)) is True


def test_period_end_before_start_fails_closed():
    period = _period(start=date(2025, 12, 31), end=date(2025, 1, 1))
    with pytest.raises(ValueError, match="end_date"):
        validate_financial_period(period)


def test_observation_retrieval_cannot_precede_publication():
    obs = _observation(publication_at=datetime(2026, 3, 25, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="retrieved_at"):
        validate_financial_observation(obs)


def test_financial_fact_requires_unique_sorted_observation_lineage():
    a = _observation(metric="REVENUE")
    b = _observation(metric="EBITDA")
    good = _fact(sorted([a.observation_id, b.observation_id]))
    validate_financial_fact(good)
    bad = _fact([b.observation_id, a.observation_id])
    if bad.observation_ids != tuple(sorted(bad.observation_ids)):
        with pytest.raises(ValueError, match="sorted"):
            validate_financial_fact(bad)


def test_non_utc_timestamp_fails_closed():
    obs = _observation()
    shifted = obs.publication_at.astimezone(timezone(timedelta(hours=1)))
    candidate = replace(obs, publication_at=shifted, observation_id="sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="UTC"):
        validate_financial_observation(candidate)
