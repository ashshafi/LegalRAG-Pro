from finance_reporting import render_finance_html_report
from test_finance_reporting_models import projection, analysis, mixed_manifest_for
from finance_reporting import build_finance_report_projection

def test_html_is_deterministic_and_section_order_matches_projection_contract():
    p=projection(); html=render_finance_html_report(p); assert html==render_finance_html_report(p)
    headings=["Report Header","Analytical Lineage","Comparable Set","Metric Matrix","Peer Statistics","Target Peer Positions","Calculation Lineage","Evidence Coverage","Evidence Register","Limitations"]
    positions=[html.index(x) for x in headings]; assert positions==sorted(positions)
    assert p.report_projection_id in html and p.manifest.manifest_id in html

def test_html_displays_document_unbound_evidence_gap_without_source_text():
    a=analysis(); p=build_finance_report_projection(analysis=a,evidence_manifest=mixed_manifest_for(a)); html=render_finance_html_report(p)
    assert "DOCUMENT_UNBOUND" in html and "archived filing unavailable" in html
    assert "governed source text" not in html

def test_html_and_markdown_do_not_silently_round_decimal_values():
    from finance_reporting import render_finance_markdown_report
    p=projection(); cell=next(x for x in p.cells if x.value is not None)
    from finance_domain.identity import canonical_decimal_text
    exact=canonical_decimal_text(cell.value)
    assert exact in render_finance_html_report(p) and exact in render_finance_markdown_report(p)
