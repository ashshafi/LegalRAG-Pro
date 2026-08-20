from datetime import datetime, timezone
from decimal import Decimal

from finance_calculations import AnalyticalStatus
from finance_comps import (
    CellValueClassification, ComparableMetricCell,
    build_peer_metric_summary, validate_peer_metric_summary,
)

ASOF=datetime(2026,3,2,16,30,tzinfo=timezone.utc)
W="11111111-1111-4111-8111-111111111111"
C="22222222-2222-4222-8222-222222222222"
S="33333333-3333-4333-8333-333333333333"


def _id(n): return "sha256:" + f"{n:064x}"

def _cell(n,value,status=AnalyticalStatus.ESTABLISHED,currency="GBP",unit="multiple"):
    return ComparableMetricCell(
        schema_version="finance-comparable-cell/1.0",workspace_id=W,company_id=C,security_id=S,metric_code="EV_EBITDA",
        value_classification=CellValueClassification.DERIVED_METRIC,calculation_classification=None,status=status,
        value=value if status is AnalyticalStatus.ESTABLISHED else None,currency=currency if status is AnalyticalStatus.ESTABLISHED else None,
        unit=unit if status is AnalyticalStatus.ESTABLISHED else None,financial_period_id=None,as_of=ASOF,
        source_fact_id=None,source_result_id=_id(100+n),input_fact_ids=(),observation_ids=(),
        note=None if status is AnalyticalStatus.ESTABLISHED else "unavailable",cell_id=_id(n),
    )


def test_five_peer_statistics_are_exact_decimal():
    cells=tuple(_cell(i,Decimal(v)) for i,v in enumerate(("1","3","5","7","9"),1))
    s=build_peer_metric_summary(workspace_id=W,metric_code="EV_EBITDA",selected_peer_cells=cells,as_of=ASOF)
    validate_peer_metric_summary(s)
    assert (s.mean,s.median,s.minimum,s.maximum)==(Decimal("5"),Decimal("5"),Decimal("1"),Decimal("9"))


def test_even_peer_median_is_exact_average():
    cells=tuple(_cell(i,Decimal(v)) for i,v in enumerate(("1","3","7","9"),1))
    s=build_peer_metric_summary(workspace_id=W,metric_code="EV_EBITDA",selected_peer_cells=cells,as_of=ASOF)
    assert s.median==Decimal("5") and s.selected_peer_count==4


def test_source_conflict_precedence_fails_closed():
    cells=(_cell(1,Decimal("1")),_cell(2,None,AnalyticalStatus.SOURCE_CONFLICT),_cell(3,Decimal("3")))
    s=build_peer_metric_summary(workspace_id=W,metric_code="EV_EBITDA",selected_peer_cells=cells,as_of=ASOF)
    assert s.status is AnalyticalStatus.SOURCE_CONFLICT
    assert s.mean is s.median is None


def test_assumption_required_precedence_fails_closed():
    cells=(_cell(1,Decimal("1")),_cell(2,None,AnalyticalStatus.ASSUMPTION_REQUIRED),_cell(3,Decimal("3")))
    s=build_peer_metric_summary(workspace_id=W,metric_code="EV_EBITDA",selected_peer_cells=cells,as_of=ASOF)
    assert s.status is AnalyticalStatus.ASSUMPTION_REQUIRED


def test_fewer_than_two_established_values_is_insufficient():
    cells=(_cell(1,Decimal("1")),_cell(2,None,AnalyticalStatus.DATA_NOT_AVAILABLE))
    s=build_peer_metric_summary(workspace_id=W,metric_code="EV_EBITDA",selected_peer_cells=cells,as_of=ASOF)
    assert s.status is AnalyticalStatus.INSUFFICIENT_DATA
    assert s.established_peer_count==1 and len(s.unavailable_cell_ids)==1


def test_currency_mismatch_requires_assumption_not_fx_conversion():
    cells=(_cell(1,Decimal("1"),currency="GBP"),_cell(2,Decimal("2"),currency="USD"))
    s=build_peer_metric_summary(workspace_id=W,metric_code="EV_EBITDA",selected_peer_cells=cells,as_of=ASOF)
    assert s.status is AnalyticalStatus.ASSUMPTION_REQUIRED
    assert s.mean is None
