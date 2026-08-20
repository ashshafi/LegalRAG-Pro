from __future__ import annotations

from abc import ABC
from datetime import datetime, timedelta, timezone

import pytest

from finance_data import FinanceDataLookupError, FinancialDataProvider, FrozenDemoProvider


def _company(provider: FrozenDemoProvider, name: str):
    return next(item for item in provider.list_companies() if item.display_name == name)


def test_frozen_demo_implements_provider_contract() -> None:
    provider = FrozenDemoProvider()
    assert isinstance(provider, FinancialDataProvider)
    assert issubclass(FinancialDataProvider, ABC)
    assert provider.provider_id == "frozen-demo"
    assert provider.dataset_id == "FIN-DEMO-001"
    assert provider.dataset_version == "1.0"
    assert provider.dataset_identity.startswith("sha256:")


def test_provider_entity_and_period_queries_are_isolated() -> None:
    provider = FrozenDemoProvider()
    aurora = _company(provider, "Aurora Systems")
    borealis = _company(provider, "Borealis Data")

    assert provider.get_company(company_id=aurora.company_id) == aurora
    assert provider.get_company(company_id="11111111-1111-4111-8111-111111111111") is None

    securities = provider.list_securities(company_id=aurora.company_id)
    assert len(securities) == 1
    assert securities[0].company_id == aurora.company_id
    assert len(provider.list_periods(company_id=aurora.company_id)) == 2

    with pytest.raises(FinanceDataLookupError):
        provider.get_observations(
            company_id=aurora.company_id,
            security_id=provider.list_securities(company_id=borealis.company_id)[0].security_id,
        )


def test_provider_unknown_authority_fails_closed_but_missing_metric_is_empty() -> None:
    provider = FrozenDemoProvider()
    aurora = _company(provider, "Aurora Systems")

    with pytest.raises(FinanceDataLookupError):
        provider.get_observations(company_id="11111111-1111-4111-8111-111111111111")

    assert provider.get_observations(company_id=aurora.company_id, metric_code="FREE_CASH_FLOW") == ()


def test_provider_requires_canonical_utc_as_of() -> None:
    provider = FrozenDemoProvider()
    aurora = _company(provider, "Aurora Systems")

    with pytest.raises(ValueError, match="timezone-aware"):
        provider.get_observations(
            company_id=aurora.company_id,
            as_of=datetime(2026, 3, 1),
        )

    with pytest.raises(ValueError, match="UTC"):
        provider.get_observations(
            company_id=aurora.company_id,
            as_of=datetime(2026, 3, 1, tzinfo=timezone(timedelta(hours=1))),
        )
