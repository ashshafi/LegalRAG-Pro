from datetime import datetime, timezone

import pytest

from finance_comps import (
    ComparableRole, PeerInclusionState, build_comparable_company_analysis,
    create_comparable_member_selection, create_comparable_set_definition,
    dumps_comparable_company_analysis, loads_comparable_company_analysis,
)
from finance_data import FrozenDemoProvider


def _analysis():
    p=FrozenDemoProvider(); asof=datetime(2026,3,2,16,30,tzinfo=timezone.utc); members=[]
    for c in p.list_companies():
        s=p.list_securities(company_id=c.company_id)[0]; ps=sorted(p.list_periods(company_id=c.company_id),key=lambda x:x.end_date)
        members.append(create_comparable_member_selection(company_id=c.company_id,security_id=s.security_id,role=ComparableRole.TARGET if c.company_id==p.target_company_id else ComparableRole.PEER,inclusion_state=PeerInclusionState.INCLUDED,current_period_id=ps[-1].financial_period_id,prior_period_id=ps[-2].financial_period_id))
    d=create_comparable_set_definition(workspace_id=p.workspace.workspace_id,as_of=asof,members=tuple(members))
    return build_comparable_company_analysis(provider=p,definition=d)


def test_canonical_round_trip_preserves_analysis_identity():
    a=_analysis(); payload=dumps_comparable_company_analysis(a); loaded=loads_comparable_company_analysis(payload)
    assert loaded==a and loaded.analysis_id==a.analysis_id


def test_duplicate_json_key_is_rejected():
    payload=dumps_comparable_company_analysis(_analysis())
    tampered=payload.replace('"analysis_id":', '"analysis_id":"sha256:'+'0'*64+'","analysis_id":',1)
    with pytest.raises(ValueError, match="Duplicate"):
        loads_comparable_company_analysis(tampered)


def test_extra_root_key_is_rejected():
    payload=dumps_comparable_company_analysis(_analysis())
    base=payload.rstrip('\n')
    tampered=base[:-1]+',\"unexpected\":true}\n'
    with pytest.raises(ValueError, match="fields"):
        loads_comparable_company_analysis(tampered)


def test_non_utc_f4_datetime_is_rejected():
    payload=dumps_comparable_company_analysis(_analysis())
    tampered=payload.replace('2026-03-02T16:30:00.000000Z','2026-03-02T16:30:00.000000+01:00',1)
    with pytest.raises(ValueError):
        loads_comparable_company_analysis(tampered)
