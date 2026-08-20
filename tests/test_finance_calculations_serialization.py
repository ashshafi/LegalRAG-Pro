from datetime import datetime, timezone
import json
import pytest

from finance_calculations import DeterministicCalculationEngine, dumps_calculation_result, loads_calculation_result
from finance_data import FrozenDemoProvider

AS_OF = datetime(2026, 3, 2, 16, 30, tzinfo=timezone.utc)


def _result():
    p = FrozenDemoProvider()
    c = p.target_company
    s = p.list_securities(company_id=c.company_id)[0]
    periods = {x.label: x for x in p.list_periods(company_id=c.company_id)}
    return DeterministicCalculationEngine(p).calculate(company_id=c.company_id, security_id=s.security_id, metric_code="EV_EBITDA", current_period_id=periods["FY2025"].financial_period_id, prior_period_id=periods["FY2024"].financial_period_id, as_of=AS_OF)


def test_round_trip_is_byte_canonical():
    result = _result()
    payload = dumps_calculation_result(result)
    assert loads_calculation_result(payload) == result
    assert dumps_calculation_result(loads_calculation_result(payload)) == payload


def test_noncanonical_json_is_rejected():
    result = _result()
    payload = dumps_calculation_result(result)
    pretty = json.dumps(json.loads(payload), indent=2)
    with pytest.raises(ValueError):
        loads_calculation_result(pretty)
