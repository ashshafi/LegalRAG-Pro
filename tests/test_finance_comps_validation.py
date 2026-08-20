from datetime import datetime, timezone
from dataclasses import replace

import pytest

from finance_comps import (
    ComparableRole, PeerInclusionState, build_comparable_company_analysis,
    create_comparable_member_selection, create_comparable_set_definition,
    validate_comparable_company_analysis, validate_comparable_metric_cell,
)
from finance_data import FrozenDemoProvider


def _analysis():
    p=FrozenDemoProvider(); asof=datetime(2026,3,2,16,30,tzinfo=timezone.utc); ms=[]
    for c in p.list_companies():
        s=p.list_securities(company_id=c.company_id)[0]; ps=sorted(p.list_periods(company_id=c.company_id),key=lambda x:x.end_date)
        ms.append(create_comparable_member_selection(company_id=c.company_id,security_id=s.security_id,role=ComparableRole.TARGET if c.company_id==p.target_company_id else ComparableRole.PEER,inclusion_state=PeerInclusionState.INCLUDED,current_period_id=ps[-1].financial_period_id,prior_period_id=ps[-2].financial_period_id))
    return build_comparable_company_analysis(provider=p,definition=create_comparable_set_definition(workspace_id=p.workspace.workspace_id,as_of=asof,members=tuple(ms)))


def test_repeated_build_is_identity_deterministic():
    assert _analysis().analysis_id==_analysis().analysis_id


def test_tampered_cell_result_binding_is_rejected():
    a=_analysis(); derived=next(c for c in a.cells if c.source_result_id is not None)
    other=next(r for r in a.calculation_results if r.result_id!=derived.source_result_id)
    bad=replace(derived,source_result_id=other.result_id)
    with pytest.raises(ValueError):
        validate_comparable_metric_cell(bad)


def test_analysis_rejects_missing_provenance_fact():
    a=_analysis(); bad=replace(a,source_facts=a.source_facts[1:])
    with pytest.raises(ValueError, match="provenance|fact"):
        validate_comparable_company_analysis(bad)


def test_analysis_rejects_tampered_identity():
    a=_analysis(); bad=replace(a,analysis_id="sha256:"+"0"*64)
    with pytest.raises(ValueError, match="analysis_id"):
        validate_comparable_company_analysis(bad)
