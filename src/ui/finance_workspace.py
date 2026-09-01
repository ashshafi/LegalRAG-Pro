"""Read-only Finance F7B2 analyst presentation over F7A + F7B1 authorities."""
from __future__ import annotations

from dataclasses import fields, is_dataclass
from decimal import Decimal
from typing import Iterable

import streamlit as st

from finance_reporting import FinanceReportProjection, validate_finance_report_projection
from finance_workspace_index import (
    FinanceWorkspaceIndex,
    FinanceWorkspaceObjectKey,
    build_finance_workspace_index,
    literal_query_matches,
)
from ui.finance_reports import render_finance_report_exports
from finance_historical_report import (
    HistoricalFinanceReport,
    render_historical_finance_markdown,
)

_VIEW_LABELS = {
    "overview": "Overview",
    "matrix": "Comparable Matrix",
    "summaries": "Peer Statistics",
    "positions": "Target Position",
    "calculations": "Calculation Trace",
    "evidence": "Source & Evidence Register",
    "limitations": "Limitations",
    "traceability": "Exact Traceability",
    "reports": "Reports / Export",
}
_VIEW_ORDER = tuple(_VIEW_LABELS)
_KIND_LABELS = {
    "member": "Member",
    "cell": "Metric Cell",
    "summary": "Peer Summary",
    "position": "Target Position",
    "calculation": "Calculation",
    "evidence": "Evidence",
    "limitation": "Limitation",
}
_KIND_ORDER = tuple(_KIND_LABELS)
_BINDING_KEYS = (
    "finance_workspace_id",
    "finance_report_projection_id",
    "finance_projection_payload_sha256",
    "finance_report_manifest_id",
)
_TRANSIENT_KEYS = (
    "finance_workspace_view",
    "finance_matrix_query",
    "finance_matrix_companies",
    "finance_matrix_metrics",
    "finance_matrix_statuses",
    "finance_evidence_query",
    "finance_evidence_channels",
    "finance_evidence_binding_classes",
    "finance_trace_kind",
    "finance_trace_query",
    "finance_trace_selected_key",
)


def _defaults() -> dict[str, object]:
    return {
        "finance_workspace_view": "overview",
        "finance_matrix_query": "",
        "finance_matrix_companies": [],
        "finance_matrix_metrics": [],
        "finance_matrix_statuses": [],
        "finance_evidence_query": "",
        "finance_evidence_channels": [],
        "finance_evidence_binding_classes": [],
        "finance_trace_kind": "member",
        "finance_trace_query": "",
        "finance_trace_selected_key": None,
    }


def _binding(workspace_id: str, projection: FinanceReportProjection) -> tuple[str, str, str, str]:
    return (
        workspace_id,
        projection.report_projection_id,
        projection.projection_payload_sha256,
        projection.manifest.manifest_id,
    )


def synchronise_finance_workspace_session_state(
    workspace_id: str,
    projection: FinanceReportProjection,
) -> bool:
    """Bind all transient Finance UI state to one exact frozen projection identity."""

    validate_finance_report_projection(projection)
    current = _binding(workspace_id, projection)
    stored = tuple(st.session_state.get(key) for key in _BINDING_KEYS)
    changed = current != stored

    if changed:
        for key, value in zip(_BINDING_KEYS, current, strict=True):
            st.session_state[key] = value
        for key, value in _defaults().items():
            st.session_state[key] = value.copy() if isinstance(value, list) else value
    else:
        for key, value in _defaults().items():
            st.session_state.setdefault(key, value.copy() if isinstance(value, list) else value)

    if st.session_state.get("finance_workspace_view") not in _VIEW_ORDER:
        st.session_state["finance_workspace_view"] = "overview"
    if st.session_state.get("finance_trace_kind") not in _KIND_ORDER:
        st.session_state["finance_trace_kind"] = "member"
        st.session_state["finance_trace_selected_key"] = None
    return changed


def _assert_index_binding(projection: FinanceReportProjection, index: FinanceWorkspaceIndex) -> None:
    if index.report_projection_id != projection.report_projection_id:
        raise ValueError("FinanceWorkspaceIndex report_projection_id does not match projection.")
    if index.projection_payload_sha256 != projection.projection_payload_sha256:
        raise ValueError("FinanceWorkspaceIndex projection_payload_sha256 does not match projection.")
    if index.manifest_id != projection.manifest.manifest_id:
        raise ValueError("FinanceWorkspaceIndex manifest_id does not match projection.")


def _enum_text(value: object) -> object:
    return getattr(value, "value", value)


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _selected_values(key: str) -> set[str]:
    value = st.session_state.get(key, [])
    return {str(item) for item in (value or ())}


def metric_matrix_rows(
    index: FinanceWorkspaceIndex,
    *,
    query: str = "",
    company_ids: Iterable[str] = (),
    metric_codes: Iterable[str] = (),
    statuses: Iterable[str] = (),
) -> tuple[dict[str, object], ...]:
    """Return display-only rows from existing F7A metric cells; perform no Finance maths."""

    company_filter = set(company_ids)
    metric_filter = set(metric_codes)
    status_filter = set(statuses)
    rows: list[dict[str, object]] = []
    for key in index.cell_keys:
        cell = index.cells_by_id[key.primary_id]
        status = cell.analytical_status.value
        if company_filter and cell.company_id not in company_filter:
            continue
        if metric_filter and cell.metric_code not in metric_filter:
            continue
        if status_filter and status not in status_filter:
            continue
        if not literal_query_matches(
            query,
            (
                cell.company_id,
                cell.company_name,
                cell.security_id,
                cell.metric_code,
                status,
                cell.value_classification.value,
                cell.calculation_classification.value if cell.calculation_classification else None,
                cell.financial_period_id,
                cell.financial_period_label,
                cell.source_fact_id,
                cell.source_result_id,
                cell.note,
            ),
        ):
            continue
        rows.append(
            {
                "cell_id": cell.cell_id,
                "company_id": cell.company_id,
                "company": cell.company_name,
                "security_id": cell.security_id,
                "metric": cell.metric_code,
                "raw_status": status,
                "value": _decimal_text(cell.value),
                "currency": cell.currency,
                "unit": cell.unit,
                "period": cell.financial_period_label,
                "value_classification": cell.value_classification.value,
                "calculation_classification": (
                    cell.calculation_classification.value if cell.calculation_classification else None
                ),
                "note": cell.note,
            }
        )
    return tuple(rows)


def evidence_register_rows(
    index: FinanceWorkspaceIndex,
    *,
    query: str = "",
    source_channels: Iterable[str] = (),
    binding_classes: Iterable[str] = (),
) -> tuple[dict[str, object], ...]:
    """Return exact frozen evidence metadata without source-text resolution."""

    channel_filter = set(source_channels)
    binding_filter = set(binding_classes)
    rows: list[dict[str, object]] = []
    for key in index.evidence_keys:
        evidence = index.evidence_by_id[key.primary_id]
        channel = evidence.source_channel.value
        binding = evidence.binding_class.value
        if channel_filter and channel not in channel_filter:
            continue
        if binding_filter and binding not in binding_filter:
            continue
        if not literal_query_matches(
            query,
            (
                evidence.evidence_binding_id,
                evidence.observation_id,
                evidence.company_id,
                evidence.company_name,
                evidence.provider,
                evidence.source_id,
                evidence.source_version,
                channel,
                binding,
                evidence.document_snapshot_id,
                evidence.bound_text_sha256,
                evidence.note,
            ),
        ):
            continue
        rows.append(
            {
                "evidence_binding_id": evidence.evidence_binding_id,
                "observation_id": evidence.observation_id,
                "company_id": evidence.company_id,
                "company": evidence.company_name,
                "provider": evidence.provider,
                "source_id": evidence.source_id,
                "source_version": evidence.source_version,
                "publication_at": evidence.publication_at.isoformat() if evidence.publication_at else None,
                "source_channel": channel,
                "binding_class": binding,
                "document_snapshot_id": evidence.document_snapshot_id,
                "page_number": evidence.page_number,
                "bound_text_sha256": evidence.bound_text_sha256,
                "note": evidence.note,
            }
        )
    return tuple(rows)


def _object_keys(index: FinanceWorkspaceIndex, kind: str) -> tuple[FinanceWorkspaceObjectKey, ...]:
    return {
        "member": index.member_keys,
        "cell": index.cell_keys,
        "summary": index.summary_keys,
        "position": index.position_keys,
        "calculation": index.calculation_keys,
        "evidence": index.evidence_keys,
        "limitation": index.limitation_keys,
    }[kind]


def _search_values(value: object) -> tuple[object, ...]:
    if not is_dataclass(value):
        return (value,)
    result: list[object] = []
    for item in fields(value):
        field_value = getattr(value, item.name)
        if isinstance(field_value, tuple):
            result.extend(field_value)
        else:
            result.append(_enum_text(field_value))
    return tuple(result)


def _render_scalar_object(value: object) -> None:
    if not is_dataclass(value):
        st.text(str(value))
        return
    for item in fields(value):
        value_for_field = getattr(value, item.name)
        if isinstance(value_for_field, tuple):
            display = tuple(_enum_text(v) for v in value_for_field)
        else:
            display = _enum_text(value_for_field)
        st.text(f"{item.name}: {display}")


def _render_overview(projection: FinanceReportProjection, index: FinanceWorkspaceIndex) -> None:
    header = projection.header
    st.subheader("Frozen analytical authority")
    for label, value in (
        ("Workspace ID", header.workspace_id),
        ("Analysis ID", header.analysis_id),
        ("As of", header.as_of.isoformat()),
        ("Provider", header.provider_id),
        ("Dataset", f"{header.dataset_id} / {header.dataset_version}"),
        ("Dataset identity", header.dataset_identity),
        ("Definition ID", header.definition_id),
        ("Evidence manifest ID", header.document_evidence_manifest_id),
        ("Report projection ID", projection.report_projection_id),
        ("Projection payload SHA-256", projection.projection_payload_sha256),
        ("Manifest ID", projection.manifest.manifest_id),
        ("Evidence coverage", projection.manifest.evidence_coverage.value),
    ):
        st.text(f"{label}: {value}")
    st.caption(
        "Projected objects: "
        f"members={len(index.member_keys)}, cells={len(index.cell_keys)}, "
        f"summaries={len(index.summary_keys)}, positions={len(index.position_keys)}, "
        f"calculations={len(index.calculation_keys)}, evidence={len(index.evidence_keys)}, "
        f"limitations={len(index.limitation_keys)}"
    )


def _render_matrix(index: FinanceWorkspaceIndex) -> None:
    company_options = tuple(dict.fromkeys(index.cells_by_id[k.primary_id].company_id for k in index.cell_keys))
    metric_options = tuple(index.cells_by_metric)
    status_options = tuple(index.cells_by_status)
    with st.form(key="finance_matrix_filter_form", clear_on_submit=False):
        st.text_input("Literal search", key="finance_matrix_query")
        st.multiselect("Company IDs", company_options, key="finance_matrix_companies")
        st.multiselect("Metric codes", metric_options, key="finance_matrix_metrics")
        st.multiselect("Raw statuses", status_options, key="finance_matrix_statuses")
        st.form_submit_button("APPLY MATRIX FILTERS", use_container_width=True)
    rows = metric_matrix_rows(
        index,
        query=str(st.session_state.get("finance_matrix_query", "")),
        company_ids=_selected_values("finance_matrix_companies"),
        metric_codes=_selected_values("finance_matrix_metrics"),
        statuses=_selected_values("finance_matrix_statuses"),
    )
    st.caption(f"Showing {len(rows)} of {len(index.cell_keys)} projected metric cells")
    st.dataframe(rows, width="stretch", hide_index=True)


def _render_summaries(index: FinanceWorkspaceIndex) -> None:
    rows = []
    for key in index.summary_keys:
        value = index.summaries_by_id[key.primary_id]
        rows.append(
            {
                "summary_id": value.summary_id,
                "metric": value.metric_code,
                "raw_status": value.analytical_status.value,
                "selected_peer_count": value.selected_peer_count,
                "established_peer_count": value.established_peer_count,
                "currency": value.currency,
                "unit": value.unit,
                "mean": _decimal_text(value.mean),
                "median": _decimal_text(value.median),
                "minimum": _decimal_text(value.minimum),
                "maximum": _decimal_text(value.maximum),
                "unavailable_cell_ids": value.unavailable_cell_ids,
                "note": value.note,
            }
        )
    st.dataframe(tuple(rows), width="stretch", hide_index=True)


def _render_positions(index: FinanceWorkspaceIndex) -> None:
    rows = []
    for key in index.position_keys:
        value = index.positions_by_id[key.primary_id]
        rows.append(
            {
                "position_id": value.position_id,
                "metric": value.metric_code,
                "raw_status": value.analytical_status.value,
                "relationship": value.relationship.value if value.relationship else None,
                "target_cell_id": value.target_cell_id,
                "peer_summary_id": value.peer_summary_id,
                "note": value.note,
            }
        )
    st.dataframe(tuple(rows), width="stretch", hide_index=True)


def _render_calculations(index: FinanceWorkspaceIndex) -> None:
    rows = []
    for key in index.calculation_keys:
        value = index.calculations_by_id[key.primary_id]
        rows.append(
            {
                "result_id": value.result_id,
                "company_id": value.company_id,
                "company": value.company_name,
                "metric": value.metric_code,
                "raw_status": value.analytical_status.value,
                "classification": value.calculation_classification.value,
                "calculation_code": value.calculation_code,
                "calculation_version": value.calculation_version,
                "formula": value.formula,
                "input_fact_ids": value.input_fact_ids,
                "observation_ids": value.observation_ids,
                "evidence_binding_ids": value.evidence_binding_ids,
                "note": value.note,
            }
        )
    st.dataframe(tuple(rows), width="stretch", hide_index=True)


def _render_evidence(index: FinanceWorkspaceIndex) -> None:
    with st.form(key="finance_evidence_filter_form", clear_on_submit=False):
        st.text_input("Literal search", key="finance_evidence_query")
        st.multiselect("Source channels", tuple(index.evidence_by_source_channel), key="finance_evidence_channels")
        st.multiselect("Binding classes", tuple(index.evidence_by_binding_class), key="finance_evidence_binding_classes")
        st.form_submit_button("APPLY EVIDENCE FILTERS", use_container_width=True)
    rows = evidence_register_rows(
        index,
        query=str(st.session_state.get("finance_evidence_query", "")),
        source_channels=_selected_values("finance_evidence_channels"),
        binding_classes=_selected_values("finance_evidence_binding_classes"),
    )
    st.caption(f"Showing {len(rows)} of {len(index.evidence_keys)} projected evidence records")
    st.dataframe(rows, width="stretch", hide_index=True)
    st.caption("Source text is not resolved in F7B2; only frozen F7A coordinates are displayed.")


def _render_limitations(index: FinanceWorkspaceIndex) -> None:
    rows = []
    for key in index.limitation_keys:
        value = index.limitations_by_id[key.primary_id]
        rows.append(
            {
                "limitation_id": value.limitation_id,
                "limitation_type": value.limitation_type.value,
                "authority_id": value.authority_id,
                "raw_status": value.raw_status,
                "note": value.note,
            }
        )
    st.dataframe(tuple(rows), width="stretch", hide_index=True)


def _render_traceability(index: FinanceWorkspaceIndex) -> None:
    with st.form(key="finance_traceability_filter_form", clear_on_submit=False):
        st.selectbox(
            "Object kind",
            _KIND_ORDER,
            format_func=lambda kind: _KIND_LABELS[kind],
            key="finance_trace_kind",
        )
        st.text_input("Literal search", key="finance_trace_query")
        st.form_submit_button("APPLY TRACEABILITY FILTER", use_container_width=True)
    kind = st.session_state.get("finance_trace_kind", "member")
    query = str(st.session_state.get("finance_trace_query", ""))
    keys = tuple(
        key for key in _object_keys(index, kind)
        if literal_query_matches(query, _search_values(index.object_by_key[key]))
    )
    st.caption(f"Showing {len(keys)} projected {kind} objects")
    if not keys:
        st.info("No projected objects match the current literal filter.")
        return

    labels = {key: f"{_KIND_LABELS[key.kind]} · {key.primary_id}" for key in keys}
    selected = st.selectbox(
        "Frozen object",
        keys,
        format_func=lambda key: labels[key],
        key="finance_trace_selected_key",
    )
    value = index.object_by_key[selected]
    _render_scalar_object(value)

    st.markdown("**Outgoing frozen references**")
    if index.outgoing[selected]:
        for source_field, target in index.outgoing[selected]:
            st.text(f"{source_field} -> {target.kind}:{target.primary_id}")
    else:
        st.text("None")

    st.markdown("**Mechanical backlinks**")
    if index.backlinks[selected]:
        for backlink in index.backlinks[selected]:
            st.text(
                f"{backlink.source.kind}:{backlink.source.primary_id} <- {backlink.source_field}"
            )
    else:
        st.text("None")


def _render_finance_workspace_analyst(
    workspace_id: str,
    projection: FinanceReportProjection,
    index: FinanceWorkspaceIndex | None = None,

    historical_report: HistoricalFinanceReport | None = None,
    historical_report_error: str | None = None,
) -> None:
    """Render a lens over F7A/F7B1; never perform Finance analysis or persistence."""
    if historical_report_error:
        st.warning(f"Historical finance report unavailable: {historical_report_error}")
    elif historical_report is not None:
        st.subheader("Historical Finance Report")
        st.markdown(render_historical_finance_markdown(historical_report))

    validate_finance_report_projection(projection)
    if index is None:
        index = build_finance_workspace_index(projection)
    _assert_index_binding(projection, index)
    synchronise_finance_workspace_session_state(workspace_id, projection)

    st.header("Finance Analyst Workspace")
    st.caption("Read-only lens over the frozen Finance report projection; no new analysis is performed here.")
    st.radio(
        "Workspace view",
        _VIEW_ORDER,
        format_func=lambda key: _VIEW_LABELS[key],
        horizontal=True,
        key="finance_workspace_view",
    )

    view = st.session_state.get("finance_workspace_view", "overview")
    if view == "overview":
        _render_overview(projection, index)
    elif view == "matrix":
        _render_matrix(index)
    elif view == "summaries":
        _render_summaries(index)
    elif view == "positions":
        _render_positions(index)
    elif view == "calculations":
        _render_calculations(index)
    elif view == "evidence":
        _render_evidence(index)
    elif view == "limitations":
        _render_limitations(index)
    elif view == "traceability":
        _render_traceability(index)
    elif view == "reports":
        render_finance_report_exports(projection)


def _ui2_period_rows(report: HistoricalFinanceReport) -> tuple[tuple[str, tuple[object, ...]], ...]:
    """Return existing historical rows grouped in governed report period order."""
    result = []
    for period_id in report.period_ids:
        rows = tuple(row for row in report.values if row.financial_period_id == period_id)
        if rows:
            result.append((rows[0].period_label, rows))
    return tuple(result)


def _ui2_value(report: HistoricalFinanceReport, period_id: str, metric_code: str) -> object:
    """Select one already-governed historical value without creating analytical state."""
    rows = tuple(
        row
        for row in report.values
        if row.financial_period_id == period_id and row.metric_code == metric_code
    )
    if len(rows) != 1:
        raise ValueError(
            f"Historical Finance display requires exactly one {metric_code} value for {period_id}."
        )
    return rows[0]


def _ui2_money_display(value_text: str, *, decimals: int) -> str:
    """Presentation-only GBP millions formatting; this is not an analytical calculation."""
    value = Decimal(value_text)
    return f"£{value:.{decimals}f}m"


def _ui2_exact_display(row: object) -> str:
    """Human-readable exact stored value formatting without changing the underlying authority."""
    if row.unit == "COUNT":
        return f"{Decimal(row.value_text):,.0f}"
    if row.currency == "GBP":
        return f"£{Decimal(row.value_text):,.0f}"
    if row.currency:
        return f"{row.currency} {Decimal(row.value_text):,.0f}"
    return row.value_text


_UI2_LABELS = {
    "REVENUE": "Revenue",
    "OPERATING_PROFIT": "Operating profit",
    "PROFIT_BEFORE_TAX": "Profit before tax",
    "PROFIT_AFTER_TAX": "Profit after tax",
    "CASH": "Cash",
    "STAFF_COSTS": "Staff costs",
    "EMPLOYEES": "Employees",
    "TECHNICAL_EMPLOYEES": "Technical staff",
    "SHAREHOLDERS_FUNDS": "Shareholders' funds",
}


def _render_ui2_historical_finance(
    *,
    workspace_id: str,
    projection: FinanceReportProjection,
    index: FinanceWorkspaceIndex,
    historical_report: HistoricalFinanceReport,
) -> None:
    """Render the frozen R3 professional Finance presentation over existing authorities."""
    period_groups = _ui2_period_rows(historical_report)
    if not period_groups:
        raise ValueError("Historical Finance display requires at least one governed period.")

    latest_period_id = historical_report.period_ids[-1]
    latest_label = period_groups[-1][0]
    first_label = period_groups[0][0]

    st.markdown(
        "<style>"
        'div[data-baseweb="tab-list"] button p {'
        "font-size:1.02rem;font-weight:650;"
        "}"
        "</style>",
        unsafe_allow_html=True,
    )

    st.title(historical_report.company_display_name)
    st.caption(f"Historical financial analysis · {first_label}–{latest_label}")
    st.success("Active Finance workspace · " + historical_report.workspace_name)

    revenue = _ui2_value(historical_report, latest_period_id, "REVENUE")
    pbt = _ui2_value(historical_report, latest_period_id, "PROFIT_BEFORE_TAX")
    employees = _ui2_value(historical_report, latest_period_id, "EMPLOYEES")
    technical = _ui2_value(historical_report, latest_period_id, "TECHNICAL_EMPLOYEES")

    first_row = st.columns(2)
    first_row[0].metric(
        f"Revenue · {latest_label}",
        _ui2_money_display(revenue.value_text, decimals=1),
    )
    first_row[1].metric(
        f"Profit before tax · {latest_label}",
        _ui2_money_display(pbt.value_text, decimals=2),
    )
    second_row = st.columns(2)
    second_row[0].metric(f"Employees · {latest_label}", _ui2_exact_display(employees))
    second_row[1].metric(f"Technical staff · {latest_label}", _ui2_exact_display(technical))

    st.caption(
        "Headline values are rounded for display. Exact values are available in Financials."
    )

    overview_tab, financials_tab, sources_tab, analyst_tab = st.tabs(
        ["Overview", "Financials", "Source Evidence", "Analyst Workspace"]
    )

    overview_metrics = (
        "REVENUE",
        "OPERATING_PROFIT",
        "PROFIT_BEFORE_TAX",
        "PROFIT_AFTER_TAX",
        "EMPLOYEES",
        "TECHNICAL_EMPLOYEES",
    )

    with overview_tab:
        st.subheader("Financial history")
        header = "| Metric | " + " | ".join(label for label, _rows in period_groups) + " |"
        rule = "| --- | " + " | ".join("---:" for _ in period_groups) + " |"
        table = [header, rule]
        for metric_code in overview_metrics:
            cells = []
            for period_id in historical_report.period_ids:
                row = _ui2_value(historical_report, period_id, metric_code)
                if metric_code in {"EMPLOYEES", "TECHNICAL_EMPLOYEES"}:
                    cells.append(_ui2_exact_display(row))
                else:
                    cells.append(_ui2_money_display(row.value_text, decimals=2))
            table.append(
                "| "
                + _UI2_LABELS[metric_code]
                + " | "
                + " | ".join(cells)
                + " |"
            )
        st.markdown("\n".join(table))

    with financials_tab:
        st.subheader("Exact historical financials")
        exact_rows = []
        for metric_code in historical_report.metric_codes:
            row = {"Metric": _UI2_LABELS.get(metric_code, metric_code.replace("_", " ").title())}
            for period_id, period_group in zip(historical_report.period_ids, period_groups):
                period_label = period_group[0]
                value = _ui2_value(historical_report, period_id, metric_code)
                row[period_label] = _ui2_exact_display(value)
            exact_rows.append(row)
        st.dataframe(exact_rows, hide_index=True, width="stretch")
        st.caption(
            "Values above are presentation-formatted from the exact stored historical observations."
        )

    with sources_tab:
        st.subheader("Source evidence")
        st.caption(
            "Historical values remain bound to the published report authority and its source traceability."
        )
        _render_evidence(index)
        with st.expander("Historical report authority and provenance", expanded=False):
            st.markdown(render_historical_finance_markdown(historical_report))

    with analyst_tab:
        _render_finance_workspace_analyst(
            workspace_id=workspace_id,
            projection=projection,
            index=index,
            historical_report=None,
            historical_report_error=None,
        )


def render_finance_workspace(
    workspace_id: str,
    projection: FinanceReportProjection,
    index: FinanceWorkspaceIndex | None = None,
    historical_report: HistoricalFinanceReport | None = None,
    historical_report_error: str | None = None,
) -> None:
    """Render professional historical Finance UX or the existing read-only analyst lens."""
    validate_finance_report_projection(projection)
    if index is None:
        index = build_finance_workspace_index(projection)
    _assert_index_binding(projection, index)
    synchronise_finance_workspace_session_state(workspace_id, projection)

    if historical_report is None:
        _render_finance_workspace_analyst(
            workspace_id=workspace_id,
            projection=projection,
            index=index,
            historical_report=None,
            historical_report_error=historical_report_error,
        )
        return

    if historical_report_error:
        st.warning(f"Historical finance report unavailable: {historical_report_error}")

    _render_ui2_historical_finance(
        workspace_id=workspace_id,
        projection=projection,
        index=index,
        historical_report=historical_report,
    )


__all__ = [
    "evidence_register_rows",
    "metric_matrix_rows",
    "render_finance_workspace",
    "synchronise_finance_workspace_session_state",
]
