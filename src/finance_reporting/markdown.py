"""Deterministic Markdown renderer for Finance F7A projections."""
from __future__ import annotations
from finance_domain.identity import canonical_decimal_text
from .models import FinanceReportProjection
from .validation import validate_finance_report_projection

def _v(value):
    return "—" if value is None else canonical_decimal_text(value)

def _money(value, currency, unit):
    parts = [_v(value)]
    if currency: parts.append(currency)
    if unit: parts.append(unit)
    return " ".join(parts)

def render_finance_markdown_report(projection: FinanceReportProjection) -> str:
    validate_finance_report_projection(projection)
    h = projection.header
    lines = [
        "# Finance Comparable-Company Report", "",
        "## Report Header",
        f"- Report projection ID: `{projection.report_projection_id}`",
        f"- Analysis ID: `{h.analysis_id}`",
        f"- Evidence manifest ID: `{h.document_evidence_manifest_id}`",
        f"- As of: {h.as_of.isoformat()}",
        f"- Provider: {h.provider_id}", f"- Dataset: {h.dataset_id} / {h.dataset_version}",
        f"- Dataset identity: `{h.dataset_identity}`", "",
        "## Analytical Lineage",
        f"F4 `{projection.source_analysis_id}` → F5 `{projection.source_document_evidence_manifest_id}` → F7A `{projection.report_projection_id}`", "",
        "## Comparable Set", "",
        "| Company | Role | Inclusion | Current period | Prior period | Exclusion reason |",
        "|---|---|---|---|---|---|",
    ]
    for x in projection.members:
        lines.append(f"| {x.company_name} | {x.role.value} | {x.inclusion_state.value} | {x.current_period_label} | {x.prior_period_label} | {x.exclusion_reason or '—'} |")
    lines += ["", "## Metric Matrix", "", "| Company | Metric | Status | Value | Period | Classification |", "|---|---|---|---|---|---|"]
    for x in projection.cells:
        cls = x.value_classification.value + (f" / {x.calculation_classification.value}" if x.calculation_classification else "")
        lines.append(f"| {x.company_name} | {x.metric_code} | {x.analytical_status.value} | {_money(x.value,x.currency,x.unit)} | {x.financial_period_label or '—'} | {cls} |")
    lines += ["", "## Peer Statistics", "", "| Metric | Status | Mean | Median | Minimum | Maximum | Established/Selected |", "|---|---|---|---|---|---|---|"]
    for x in projection.summaries:
        lines.append(f"| {x.metric_code} | {x.analytical_status.value} | {_money(x.mean,x.currency,x.unit)} | {_money(x.median,x.currency,x.unit)} | {_money(x.minimum,x.currency,x.unit)} | {_money(x.maximum,x.currency,x.unit)} | {x.established_peer_count}/{x.selected_peer_count} |")
    lines += ["", "## Target Peer Positions", "", "| Metric | Status | Relationship |", "|---|---|---|"]
    for x in projection.positions:
        lines.append(f"| {x.metric_code} | {x.analytical_status.value} | {x.relationship.value if x.relationship else '—'} |")
    lines += ["", "## Calculation Lineage", "", "| Company | Metric | Status | Calculation | Version | Formula |", "|---|---|---|---|---|---|"]
    for x in projection.calculations:
        lines.append(f"| {x.company_name} | {x.metric_code} | {x.analytical_status.value} | {x.calculation_code} | {x.calculation_version} | `{x.formula}` |")
    lines += ["", "## Evidence Coverage", f"- Coverage: **{projection.manifest.evidence_coverage.value}**", "", "## Evidence Register", "", "| Company | Provider | Source | Version | Channel | Binding | Document/Page |", "|---|---|---|---|---|---|---|"]
    for x in projection.evidence:
        loc = f"{x.document_snapshot_id} / p.{x.page_number}" if x.document_snapshot_id else "—"
        lines.append(f"| {x.company_name} | {x.provider} | {x.source_id} | {x.source_version} | {x.source_channel.value} | {x.binding_class.value} | {loc} |")
    lines += ["", "## Limitations"]
    if not projection.limitations:
        lines.append("- None projected from frozen analytical/evidence state.")
    else:
        for x in projection.limitations:
            lines.append(f"- **{x.limitation_type.value}** `{x.authority_id}` — {x.raw_status}" + (f": {x.note}" if x.note else ""))
    lines += ["", "---", f"Manifest ID: `{projection.manifest.manifest_id}`", f"Projection payload SHA-256: `{projection.projection_payload_sha256}`", ""]
    return "\n".join(lines)

__all__ = ["render_finance_markdown_report"]
