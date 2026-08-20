from __future__ import annotations

from datetime import datetime, timezone

from finance_data import FrozenDemoProvider


def _company(provider: FrozenDemoProvider, name: str):
    return next(item for item in provider.list_companies() if item.display_name == name)


def test_fin_demo_001_cardinality_and_fictional_universe() -> None:
    provider = FrozenDemoProvider()
    companies = provider.list_companies()

    assert len(companies) == 6
    assert len(provider.list_securities()) == 6
    assert sum(len(provider.list_periods(company_id=c.company_id)) for c in companies) == 12
    assert sum(len(provider.get_observations(company_id=c.company_id)) for c in companies) == 66
    assert provider.target_company.display_name == "Aurora Systems"
    assert len(provider.list_comparable_companies()) == 5
    assert {c.company_id for c in provider.list_comparable_companies()} == set(provider.comparable_company_ids)
    assert provider.target_company_id not in provider.comparable_company_ids
    assert {c.display_name for c in companies} == {
        "Aurora Systems",
        "Borealis Data",
        "Cobalt Analytics",
        "Delta Networks",
        "Ember Software",
        "Fathom Digital",
    }


def test_reloads_are_exactly_deterministic() -> None:
    first = FrozenDemoProvider()
    second = FrozenDemoProvider()

    assert first.dataset_identity == second.dataset_identity
    assert first.workspace == second.workspace
    assert first.list_companies() == second.list_companies()
    assert first.list_securities() == second.list_securities()
    assert tuple(
        first.get_observations(company_id=c.company_id) for c in first.list_companies()
    ) == tuple(
        second.get_observations(company_id=c.company_id) for c in second.list_companies()
    )


def test_as_of_filter_prevents_fy2025_lookahead() -> None:
    provider = FrozenDemoProvider()
    aurora = _company(provider, "Aurora Systems")

    before_2025_results = provider.get_observations(
        company_id=aurora.company_id,
        as_of=datetime(2025, 2, 17, 23, 59, tzinfo=timezone.utc),
    )
    after_2024_results = provider.get_observations(
        company_id=aurora.company_id,
        as_of=datetime(2025, 3, 1, tzinfo=timezone.utc),
    )
    before_2025_publication = provider.get_observations(
        company_id=aurora.company_id,
        as_of=datetime(2026, 2, 16, 23, 59, tzinfo=timezone.utc),
    )
    after_2025_publication = provider.get_observations(
        company_id=aurora.company_id,
        as_of=datetime(2026, 2, 17, 7, 0, tzinfo=timezone.utc),
    )

    assert before_2025_results == ()
    assert {item.metric_code for item in after_2024_results} == {"REVENUE", "EBITDA"}
    assert len(before_2025_publication) == 2
    assert len(after_2025_publication) == 9
    assert all(item.metric_code not in {"SHARE_PRICE", "SHARES_OUTSTANDING"} for item in after_2025_publication)


def test_market_snapshot_does_not_leak_before_observed_time() -> None:
    provider = FrozenDemoProvider()
    aurora = _company(provider, "Aurora Systems")

    just_before = provider.get_observations(
        company_id=aurora.company_id,
        as_of=datetime(2026, 3, 2, 16, 29, 59, tzinfo=timezone.utc),
    )
    at_snapshot = provider.get_observations(
        company_id=aurora.company_id,
        as_of=datetime(2026, 3, 2, 16, 30, 0, tzinfo=timezone.utc),
    )

    assert len(just_before) == 9
    assert len(at_snapshot) == 11
    assert {item.metric_code for item in at_snapshot} >= {"SHARE_PRICE", "SHARES_OUTSTANDING"}


def test_metric_and_period_filters_preserve_source_provenance() -> None:
    provider = FrozenDemoProvider()
    aurora = _company(provider, "Aurora Systems")
    fy2025 = next(p for p in provider.list_periods(company_id=aurora.company_id) if p.label == "FY2025")

    values = provider.get_observations(
        company_id=aurora.company_id,
        metric_code="EBITDA",
        financial_period_id=fy2025.financial_period_id,
    )

    assert len(values) == 1
    value = values[0]
    assert str(value.value) == "225"
    assert value.currency == "GBP"
    assert value.unit == "million_currency"
    assert value.provider == "frozen-demo"
    assert value.source_id == "FIN-DEMO-001/aurora/FY2025-results"
    assert value.source_version == "1.0"
