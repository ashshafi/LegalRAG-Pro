from dataclasses import replace
from datetime import datetime, timezone
import pytest

from finance_calculations import AnalyticalStatus, DeterministicCalculationEngine, validate_calculation_result
from finance_data import FrozenDemoProvider

AS_OF = datetime(2026, 3, 2, 16, 30, tzinfo=timezone.utc)


def _established():
    p = FrozenDemoProvider()
    c = p.target_company
    s = p.list_securities(company_id=c.company_id)[0]
    periods = {x.label: x for x in p.list_periods(company_id=c.company_id)}
    return DeterministicCalculationEngine(p).calculate(company_id=c.company_id, security_id=s.security_id, metric_code="NET_DEBT", current_period_id=periods["FY2025"].financial_period_id, prior_period_id=periods["FY2024"].financial_period_id, as_of=AS_OF)


def test_tampered_value_or_identity_is_rejected():
    result = _established()
    with pytest.raises(ValueError):
        validate_calculation_result(replace(result, value=result.value + 1))
    with pytest.raises(ValueError):
        validate_calculation_result(replace(result, result_id="sha256:" + "0" * 64))


def test_non_established_result_cannot_expose_value():
    result = _established()
    with pytest.raises(ValueError):
        validate_calculation_result(replace(result, status=AnalyticalStatus.NOT_ESTABLISHED, note="zero denominator"))
