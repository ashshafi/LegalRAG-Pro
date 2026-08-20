from datetime import datetime, timezone
from dataclasses import replace

import pytest

from finance_comps import (
    ComparableRole,
    PeerInclusionState,
    create_comparable_member_selection,
    create_comparable_set_definition,
    validate_comparable_member_selection,
    validate_comparable_set_definition,
)
from finance_data import FrozenDemoProvider


def _members(provider):
    out=[]
    for company in provider.list_companies():
        security=provider.list_securities(company_id=company.company_id)[0]
        periods=sorted(provider.list_periods(company_id=company.company_id), key=lambda x:x.end_date)
        out.append(create_comparable_member_selection(
            company_id=company.company_id, security_id=security.security_id,
            role=ComparableRole.TARGET if company.company_id==provider.target_company_id else ComparableRole.PEER,
            inclusion_state=PeerInclusionState.INCLUDED,
            current_period_id=periods[-1].financial_period_id, prior_period_id=periods[-2].financial_period_id,
        ))
    return tuple(out)


def test_definition_has_exactly_one_included_target_and_canonical_order():
    p=FrozenDemoProvider(); asof=datetime(2026,3,2,16,30,tzinfo=timezone.utc)
    d=create_comparable_set_definition(workspace_id=p.workspace.workspace_id,as_of=asof,members=_members(p))
    assert sum(m.role is ComparableRole.TARGET for m in d.members)==1
    assert d.members[0].role is ComparableRole.TARGET
    assert d.members[0].inclusion_state is PeerInclusionState.INCLUDED
    validate_comparable_set_definition(d)


def test_target_cannot_be_excluded():
    p=FrozenDemoProvider(); target=next(m for m in _members(p) if m.role is ComparableRole.TARGET)
    bad=replace(target,inclusion_state=PeerInclusionState.EXCLUDED,exclusion_reason="manual exclusion")
    with pytest.raises(ValueError, match="TARGET"):
        validate_comparable_member_selection(bad)


def test_excluded_peer_requires_reason_and_included_peer_forbids_reason():
    p=FrozenDemoProvider(); peer=next(m for m in _members(p) if m.role is ComparableRole.PEER)
    with pytest.raises(ValueError, match="exclusion_reason"):
        validate_comparable_member_selection(replace(peer,inclusion_state=PeerInclusionState.EXCLUDED))
    with pytest.raises(ValueError, match="exclusion_reason"):
        validate_comparable_member_selection(replace(peer,exclusion_reason="not allowed"))


def test_duplicate_company_selection_is_rejected():
    p=FrozenDemoProvider(); asof=datetime(2026,3,2,16,30,tzinfo=timezone.utc); members=list(_members(p))
    peer=next(m for m in members if m.role is ComparableRole.PEER)
    members.append(peer)
    with pytest.raises(ValueError, match="unique"):
        create_comparable_set_definition(workspace_id=p.workspace.workspace_id,as_of=asof,members=tuple(members))
