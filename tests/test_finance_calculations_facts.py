from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from finance_calculations import AnalyticalStatus, resolve_financial_fact
from finance_data import FrozenDemoProvider
from finance_domain import derive_finance_id, financial_observation_identity_payload_to_dict

AS_OF = datetime(2026, 3, 2, 16, 30, tzinfo=timezone.utc)


def _aurora(provider):
    company = provider.target_company
    periods = {p.label: p for p in provider.list_periods(company_id=company.company_id)}
    return company, periods


def test_single_source_observation_resolves_to_valid_fact():
    provider = FrozenDemoProvider()
    company, periods = _aurora(provider)
    result = resolve_financial_fact(provider, company_id=company.company_id, metric_code="REVENUE", financial_period_id=periods["FY2025"].financial_period_id, as_of=AS_OF)
    assert result.status is AnalyticalStatus.ESTABLISHED
    assert result.fact is not None
    assert result.fact.value == 1050
    assert result.fact.reconciliation_note == "single_source_observation"
    assert result.fact.observation_ids == result.observation_ids


def test_as_of_prevents_future_observation_from_becoming_fact():
    provider = FrozenDemoProvider()
    company, periods = _aurora(provider)
    before_publication = datetime(2026, 2, 16, 23, 59, tzinfo=timezone.utc)
    result = resolve_financial_fact(provider, company_id=company.company_id, metric_code="REVENUE", financial_period_id=periods["FY2025"].financial_period_id, as_of=before_publication)
    assert result.status is AnalyticalStatus.DATA_NOT_AVAILABLE
    assert result.fact is None


class DuplicateProvider(FrozenDemoProvider):
    def __init__(self, *, conflict=False):
        super().__init__()
        self._conflict = conflict

    def get_observations(self, **kwargs):
        values = super().get_observations(**kwargs)
        if len(values) != 1 or kwargs.get("metric_code") != "REVENUE":
            return values
        original = values[0]
        clone = replace(original, source_id=original.source_id + "/duplicate", observation_id="sha256:" + "0" * 64)
        if self._conflict:
            clone = replace(clone, value=original.value + 1)
        clone = replace(clone, observation_id=derive_finance_id(financial_observation_identity_payload_to_dict(clone)))
        return tuple(sorted((original, clone), key=lambda x: x.observation_id))


def test_identical_sources_reconcile_and_preserve_both_observations():
    provider = DuplicateProvider()
    company, periods = _aurora(provider)
    result = resolve_financial_fact(provider, company_id=company.company_id, metric_code="REVENUE", financial_period_id=periods["FY2025"].financial_period_id, as_of=AS_OF)
    assert result.status is AnalyticalStatus.ESTABLISHED
    assert result.fact is not None
    assert len(result.fact.observation_ids) == 2
    assert result.fact.reconciliation_note == "identical_source_observations_reconciled"


def test_material_source_discrepancy_is_not_silently_normalised():
    provider = DuplicateProvider(conflict=True)
    company, periods = _aurora(provider)
    result = resolve_financial_fact(provider, company_id=company.company_id, metric_code="REVENUE", financial_period_id=periods["FY2025"].financial_period_id, as_of=AS_OF)
    assert result.status is AnalyticalStatus.SOURCE_CONFLICT
    assert result.fact is None
    assert len(result.observation_ids) == 2
