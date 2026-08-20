"""Deterministic HTML renderer for Finance F7A projections."""
from __future__ import annotations
from html import escape
from finance_domain.identity import canonical_decimal_text
from .models import FinanceReportProjection
from .validation import validate_finance_report_projection

def _e(value): return escape(str(value), quote=True)
def _v(value): return "—" if value is None else canonical_decimal_text(value)
def _money(value,currency,unit): return " ".join(x for x in (_v(value), currency, unit) if x)
def _table(headers, rows):
    head="".join(f"<th>{_e(x)}</th>" for x in headers)
    body="".join("<tr>"+"".join(f"<td>{_e(x)}</td>" for x in row)+"</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"

def render_finance_html_report(projection: FinanceReportProjection) -> str:
    validate_finance_report_projection(projection); h=projection.header
    parts=["<!doctype html><html><head><meta charset=\"utf-8\"><title>Finance Comparable-Company Report</title></head><body>",
           "<h1>Finance Comparable-Company Report</h1>","<h2>Report Header</h2><ul>",
           f"<li>Report projection ID: <code>{_e(projection.report_projection_id)}</code></li>",
           f"<li>Analysis ID: <code>{_e(h.analysis_id)}</code></li>",
           f"<li>Evidence manifest ID: <code>{_e(h.document_evidence_manifest_id)}</code></li>",
           f"<li>As of: {_e(h.as_of.isoformat())}</li><li>Provider: {_e(h.provider_id)}</li>",
           f"<li>Dataset: {_e(h.dataset_id)} / {_e(h.dataset_version)}</li><li>Dataset identity: <code>{_e(h.dataset_identity)}</code></li></ul>",
           "<h2>Analytical Lineage</h2>", f"<p>F4 <code>{_e(projection.source_analysis_id)}</code> → F5 <code>{_e(projection.source_document_evidence_manifest_id)}</code> → F7A <code>{_e(projection.report_projection_id)}</code></p>",
           "<h2>Comparable Set</h2>"]
    parts.append(_table(("Company","Role","Inclusion","Current period","Prior period","Exclusion reason"),[(x.company_name,x.role.value,x.inclusion_state.value,x.current_period_label,x.prior_period_label,x.exclusion_reason or "—") for x in projection.members]))
    parts.append("<h2>Metric Matrix</h2>")
    parts.append(_table(("Company","Metric","Status","Value","Period","Classification"),[(x.company_name,x.metric_code,x.analytical_status.value,_money(x.value,x.currency,x.unit),x.financial_period_label or "—",x.value_classification.value+(f" / {x.calculation_classification.value}" if x.calculation_classification else "")) for x in projection.cells]))
    parts.append("<h2>Peer Statistics</h2>")
    parts.append(_table(("Metric","Status","Mean","Median","Minimum","Maximum","Established/Selected"),[(x.metric_code,x.analytical_status.value,_money(x.mean,x.currency,x.unit),_money(x.median,x.currency,x.unit),_money(x.minimum,x.currency,x.unit),_money(x.maximum,x.currency,x.unit),f"{x.established_peer_count}/{x.selected_peer_count}") for x in projection.summaries]))
    parts.append("<h2>Target Peer Positions</h2>")
    parts.append(_table(("Metric","Status","Relationship"),[(x.metric_code,x.analytical_status.value,x.relationship.value if x.relationship else "—") for x in projection.positions]))
    parts.append("<h2>Calculation Lineage</h2>")
    parts.append(_table(("Company","Metric","Status","Calculation","Version","Formula"),[(x.company_name,x.metric_code,x.analytical_status.value,x.calculation_code,x.calculation_version,x.formula) for x in projection.calculations]))
    parts += ["<h2>Evidence Coverage</h2>",f"<p>Coverage: <strong>{_e(projection.manifest.evidence_coverage.value)}</strong></p>","<h2>Evidence Register</h2>"]
    parts.append(_table(("Company","Provider","Source","Version","Channel","Binding","Document/Page"),[(x.company_name,x.provider,x.source_id,x.source_version,x.source_channel.value,x.binding_class.value,(f"{x.document_snapshot_id} / p.{x.page_number}" if x.document_snapshot_id else "—")) for x in projection.evidence]))
    parts.append("<h2>Limitations</h2><ul>")
    if projection.limitations:
        parts.extend(f"<li><strong>{_e(x.limitation_type.value)}</strong> <code>{_e(x.authority_id)}</code> — {_e(x.raw_status)}"+(f": {_e(x.note)}" if x.note else "")+"</li>" for x in projection.limitations)
    else: parts.append("<li>None projected from frozen analytical/evidence state.</li>")
    parts += ["</ul>",f"<hr><p>Manifest ID: <code>{_e(projection.manifest.manifest_id)}</code><br>Projection payload SHA-256: <code>{_e(projection.projection_payload_sha256)}</code></p>","</body></html>"]
    return "".join(parts)

__all__ = ["render_finance_html_report"]
