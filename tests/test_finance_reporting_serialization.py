import json
import pytest
from finance_reporting import dumps_finance_report_projection, loads_finance_report_projection
from test_finance_reporting_models import projection

def test_canonical_round_trip_is_byte_exact_and_decimal_strings_remain_exact():
    p=projection(); payload=dumps_finance_report_projection(p); q=loads_finance_report_projection(payload)
    assert q==p and dumps_finance_report_projection(q)==payload
    data=json.loads(payload)
    established=next(x for x in data["cells"] if x["value"] is not None)
    assert isinstance(established["value"],str)

def test_duplicate_json_key_rejected():
    p=projection(); payload=dumps_finance_report_projection(p)
    bad=payload.replace('{"calculations":','{"schema_version":"finance-report-projection/1.0","calculations":',1)
    with pytest.raises(ValueError,match="Duplicate"): loads_finance_report_projection(bad)

def test_unknown_schema_rejected_even_when_json_is_valid():
    p=projection(); data=json.loads(dumps_finance_report_projection(p)); data["schema_version"]="finance-report-projection/9.0"
    bad=json.dumps(data,separators=(",",":"),sort_keys=True)
    with pytest.raises(ValueError): loads_finance_report_projection(bad)
