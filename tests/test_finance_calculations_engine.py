from datetime import datetime, timezone
from decimal import Decimal

from finance_calculations import AnalyticalStatus, CalculationClassification, DeterministicCalculationEngine, SUPPORTED_METRICS, ValueClassification
from finance_data import FrozenDemoProvider

AS_OF = datetime(2026, 3, 2, 16, 30, tzinfo=timezone.utc)


def _ids(provider):
    c = provider.target_company
    s = provider.list_securities(company_id=c.company_id)[0]
    periods = {p.label: p for p in provider.list_periods(company_id=c.company_id)}
    return c.company_id, s.security_id, periods["FY2025"].financial_period_id, periods["FY2024"].financial_period_id


def test_aurora_all_nine_comps_metrics_are_exact_and_provenanced():
    provider = FrozenDemoProvider()
    engine = DeterministicCalculationEngine(provider)
    company_id, security_id, current, prior = _ids(provider)
    results = engine.calculate_comps_metrics(company_id=company_id, security_id=security_id, current_period_id=current, prior_period_id=prior, as_of=AS_OF)
    by_metric = {r.metric_code: r for r in results}
    assert tuple(r.metric_code for r in results) == SUPPORTED_METRICS
    assert all(r.status is AnalyticalStatus.ESTABLISHED for r in results)
    assert all(r.classification is ValueClassification.DERIVED_METRIC for r in results)
    assert all(r.calculation_classification is CalculationClassification.MODEL_CALCULATION for r in results)
    assert all(r.input_fact_ids for r in results)
    assert by_metric["REVENUE_GROWTH"].value == Decimal("1050") / Decimal("920") - Decimal(1)
    assert by_metric["EBITDA_MARGIN"].value == Decimal("225") / Decimal("1050")
    assert by_metric["EQUITY_VALUE"].value == Decimal("2247.00")
    assert by_metric["NET_DEBT"].value == Decimal("150")
    assert by_metric["ENTERPRISE_VALUE"].value == Decimal("2397.00")
    assert by_metric["EV_REVENUE"].value == Decimal("2397") / Decimal("1050")
    assert by_metric["EV_EBITDA"].value == Decimal("2397") / Decimal("225")
    assert by_metric["PE_RATIO"].value == Decimal("12.84") / Decimal("0.72")
    assert by_metric["NET_DEBT_EBITDA"].value == Decimal("150") / Decimal("225")


def test_point_in_time_market_data_is_not_leaked_backwards():
    provider = FrozenDemoProvider()
    engine = DeterministicCalculationEngine(provider)
    company_id, security_id, current, prior = _ids(provider)
    before_market = datetime(2026, 3, 2, 16, 29, 59, tzinfo=timezone.utc)
    result = engine.calculate(company_id=company_id, security_id=security_id, metric_code="EQUITY_VALUE", current_period_id=current, prior_period_id=prior, as_of=before_market)
    assert result.status is AnalyticalStatus.INSUFFICIENT_DATA
    assert result.value is None
    assert result.note is not None


def test_result_identity_is_deterministic():
    provider = FrozenDemoProvider()
    engine = DeterministicCalculationEngine(provider)
    company_id, security_id, current, prior = _ids(provider)
    a = engine.calculate(company_id=company_id, security_id=security_id, metric_code="EV_EBITDA", current_period_id=current, prior_period_id=prior, as_of=AS_OF)
    b = engine.calculate(company_id=company_id, security_id=security_id, metric_code="EV_EBITDA", current_period_id=current, prior_period_id=prior, as_of=AS_OF)
    assert a == b
    assert a.result_id == b.result_id


def test_all_six_demo_companies_produce_nine_established_metrics():
    provider = FrozenDemoProvider()
    engine = DeterministicCalculationEngine(provider)
    for company in provider.list_companies():
        security = provider.list_securities(company_id=company.company_id)[0]
        periods = {p.label: p for p in provider.list_periods(company_id=company.company_id)}
        results = engine.calculate_comps_metrics(
            company_id=company.company_id,
            security_id=security.security_id,
            current_period_id=periods["FY2025"].financial_period_id,
            prior_period_id=periods["FY2024"].financial_period_id,
            as_of=AS_OF,
        )
        assert len(results) == 9
        assert all(result.status is AnalyticalStatus.ESTABLISHED for result in results)


def test_current_and_prior_period_authority_is_fail_closed():
    provider = FrozenDemoProvider()
    engine = DeterministicCalculationEngine(provider)
    company_id, security_id, current, prior = _ids(provider)
    try:
        engine.calculate(
            company_id=company_id, security_id=security_id, metric_code="EQUITY_VALUE",
            current_period_id=prior, prior_period_id=current, as_of=AS_OF,
        )
    except ValueError as exc:
        assert "period ordering" in str(exc)
    else:
        raise AssertionError("reversed current/prior periods must fail closed")
