from finance_reporting import render_finance_markdown_report
from test_finance_reporting_models import analysis, manifest_for, projection
from finance_comps import PeerInclusionState

def test_markdown_is_deterministic_and_contains_all_required_section_headings():
    p=projection(); a=render_finance_markdown_report(p); b=render_finance_markdown_report(p)
    assert a==b
    headings=["## Report Header","## Analytical Lineage","## Comparable Set","## Metric Matrix","## Peer Statistics","## Target Peer Positions","## Calculation Lineage","## Evidence Coverage","## Evidence Register","## Limitations"]
    positions=[a.index(x) for x in headings]; assert positions==sorted(positions)
    assert p.report_projection_id in a and p.source_analysis_id in a and p.source_document_evidence_manifest_id in a

def test_markdown_preserves_excluded_peer_and_raw_inclusion_state():
    a=analysis(); peer=next(x for x in a.definition.members if x.role.value=="PEER")
    a2=analysis(exclude_company_id=peer.company_id)
    from finance_reporting import build_finance_report_projection
    p=build_finance_report_projection(analysis=a2,evidence_manifest=manifest_for(a2)); text=render_finance_markdown_report(p)
    excluded=next(x for x in p.members if x.inclusion_state is PeerInclusionState.EXCLUDED)
    assert excluded.company_name in text and "EXCLUDED" in text and "governed exclusion" in text

def test_markdown_contains_no_investment_recommendation_section():
    text=render_finance_markdown_report(projection()).lower()
    assert "buy/sell/hold" not in text and "investment recommendation" not in text and "target price" not in text
