from datetime import datetime, timezone
from dataclasses import replace

import pytest

from finance_calculations import AnalyticalStatus
from finance_comps import (
    MATRIX_METRICS, ComparableRole, PeerInclusionState, TargetPeerRelationship,
    build_comparable_company_analysis, create_comparable_member_selection, create_comparable_set_definition,
)
from finance_data import FrozenDemoProvider

ASOF=datetime(2026,3,2,16,30,tzinfo=timezone.utc)


def _definition(provider, *, exclude_company_id=None, as_of=ASOF):
    members=[]
    for c in provider.list_companies():
        s=provider.list_securities(company_id=c.company_id)[0]
        ps=sorted(provider.list_periods(company_id=c.company_id), key=lambda x:x.end_date)
        is_target=c.company_id==provider.target_company_id
        excluded=(not is_target and c.company_id==exclude_company_id)
        members.append(create_comparable_member_selection(
            company_id=c.company_id, security_id=s.security_id,
            role=ComparableRole.TARGET if is_target else ComparableRole.PEER,
            inclusion_state=PeerInclusionState.EXCLUDED if excluded else PeerInclusionState.INCLUDED,
            current_period_id=ps[-1].financial_period_id, prior_period_id=ps[-2].financial_period_id,
            exclusion_reason="governed analyst exclusion" if excluded else None,
        ))
    return create_comparable_set_definition(workspace_id=provider.workspace.workspace_id,as_of=as_of,members=tuple(members))


def test_fin_demo_exact_authority_cardinality_and_provenance_closure():
    p=FrozenDemoProvider(); a=build_comparable_company_analysis(provider=p,definition=_definition(p))
    assert (len(a.companies),len(a.securities),len(a.periods))==(6,6,12)
    assert (len(a.source_observations),len(a.source_facts))==(66,66)
    assert len(a.calculation_results)==42
    assert len(a.cells)==54
    assert len(a.summaries)==9
    assert len(a.positions)==9
    facts={f.fact_id:f for f in a.source_facts}; obs={o.observation_id for o in a.source_observations}
    for cell in a.cells:
        for fid in cell.input_fact_ids:
            assert fid in facts
            assert set(facts[fid].observation_ids) <= obs
        if cell.status is AnalyticalStatus.ESTABLISHED:
            expected=tuple(sorted({oid for fid in cell.input_fact_ids for oid in facts[fid].observation_ids}))
            assert cell.observation_ids==expected


def test_all_nine_peer_summaries_and_positions_are_established():
    p=FrozenDemoProvider(); a=build_comparable_company_analysis(provider=p,definition=_definition(p))
    assert tuple(s.metric_code for s in a.summaries)==MATRIX_METRICS
    assert all(s.status is AnalyticalStatus.ESTABLISHED for s in a.summaries)
    assert all(pos.status is AnalyticalStatus.ESTABLISHED for pos in a.positions)
    expected={m:TargetPeerRelationship.ABOVE_PEER_MEDIAN for m in MATRIX_METRICS}
    expected["EV_EBITDA"]=TargetPeerRelationship.BELOW_PEER_MEDIAN
    assert {p.metric_code:p.relationship for p in a.positions}==expected


def test_excluded_peer_stays_in_matrix_but_is_removed_from_statistics():
    p=FrozenDemoProvider(); excluded=p.comparable_company_ids[0]
    a=build_comparable_company_analysis(provider=p,definition=_definition(p,exclude_company_id=excluded))
    assert sum(c.company_id==excluded for c in a.cells)==9
    assert all(s.selected_peer_count==4 for s in a.summaries)
    excluded_cell_ids={c.cell_id for c in a.cells if c.company_id==excluded}
    assert all(not (excluded_cell_ids & set(s.input_cell_ids+s.unavailable_cell_ids)) for s in a.summaries)


def test_point_in_time_gate_prevents_1630_market_snapshot_lookahead():
    p=FrozenDemoProvider(); early=datetime(2026,3,2,16,29,59,tzinfo=timezone.utc)
    a=build_comparable_company_analysis(provider=p,definition=_definition(p,as_of=early))
    assert len(a.source_observations)==54
    assert all(o.metric_code not in {"SHARE_PRICE","SHARES_OUTSTANDING"} for o in a.source_observations)
    price_dependent={"ENTERPRISE_VALUE","EV_REVENUE","EV_EBITDA","PE_RATIO"}
    summaries={s.metric_code:s for s in a.summaries}
    assert all(summaries[m].status is AnalyticalStatus.INSUFFICIENT_DATA for m in price_dependent)


def test_security_must_belong_to_selected_company():
    p=FrozenDemoProvider(); d=_definition(p); members=list(d.members)
    target=members[0]
    members[0]=create_comparable_member_selection(company_id=target.company_id,security_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",role=target.role,inclusion_state=target.inclusion_state,current_period_id=target.current_period_id,prior_period_id=target.prior_period_id)
    bad=create_comparable_set_definition(workspace_id=d.workspace_id,as_of=d.as_of,members=tuple(members))
    with pytest.raises(ValueError, match="security"):
        build_comparable_company_analysis(provider=p,definition=bad)
