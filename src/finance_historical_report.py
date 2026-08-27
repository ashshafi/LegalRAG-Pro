"""Deterministic single-company historical Finance reporting over one validated immutable dataset."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Final

from finance_data.immutable_dataset import ValidatedImmutableDataset
from finance_domain.identity import canonical_decimal_text, derive_finance_id
from finance_domain.validation import (
    validate_company,
    validate_financial_observation,
    validate_financial_period,
    validate_finance_workspace,
)

HISTORICAL_FINANCE_REPORT_SCHEMA_VERSION: Final[str] = "finance-historical-report/1.0"


@dataclass(frozen=True, slots=True)
class HistoricalFinanceValue:
    financial_period_id: str
    period_label: str
    period_end_date: str
    metric_code: str
    value_text: str
    currency: str | None
    unit: str
    security_id: str | None
    provider: str
    source_id: str
    source_version: str
    publication_at: str | None
    effective_at: str | None
    observed_at: str
    retrieved_at: str
    observation_id: str


@dataclass(frozen=True, slots=True)
class HistoricalFinanceReport:
    schema_version: str
    report_id: str
    workspace_id: str
    workspace_name: str
    provider_id: str
    dataset_id: str
    dataset_version: str
    dataset_identity: str
    company_id: str
    company_legal_name: str
    company_display_name: str
    reporting_currency: str
    period_ids: tuple[str, ...]
    metric_codes: tuple[str, ...]
    values: tuple[HistoricalFinanceValue, ...]


def _dt(value) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _semantic_payload(report: HistoricalFinanceReport) -> dict:
    return {
        "schema_version": report.schema_version,
        "workspace_id": report.workspace_id,
        "workspace_name": report.workspace_name,
        "provider_id": report.provider_id,
        "dataset_id": report.dataset_id,
        "dataset_version": report.dataset_version,
        "dataset_identity": report.dataset_identity,
        "company_id": report.company_id,
        "company_legal_name": report.company_legal_name,
        "company_display_name": report.company_display_name,
        "reporting_currency": report.reporting_currency,
        "period_ids": list(report.period_ids),
        "metric_codes": list(report.metric_codes),
        "values": [
            {
                "financial_period_id": row.financial_period_id,
                "period_label": row.period_label,
                "period_end_date": row.period_end_date,
                "metric_code": row.metric_code,
                "value_text": row.value_text,
                "currency": row.currency,
                "unit": row.unit,
                "security_id": row.security_id,
                "provider": row.provider,
                "source_id": row.source_id,
                "source_version": row.source_version,
                "publication_at": row.publication_at,
                "effective_at": row.effective_at,
                "observed_at": row.observed_at,
                "retrieved_at": row.retrieved_at,
                "observation_id": row.observation_id,
            }
            for row in report.values
        ],
    }


def build_historical_finance_report(*, dataset: ValidatedImmutableDataset) -> HistoricalFinanceReport:
    """Build one deterministic one-company historical report without creating analytical facts."""
    if not isinstance(dataset, ValidatedImmutableDataset):
        raise TypeError("dataset must be ValidatedImmutableDataset authority.")

    validate_finance_workspace(dataset.workspace)
    if len(dataset.companies) != 1:
        raise ValueError("historical report v1 requires exactly one company.")
    company = dataset.companies[0]
    validate_company(company)

    if dataset.securities:
        raise ValueError("historical report v1 shortest path requires no Security authority.")

    periods = tuple(sorted(dataset.periods, key=lambda item: (item.end_date, item.financial_period_id)))
    if not periods:
        raise ValueError("historical report requires at least one financial period.")
    for period in periods:
        validate_financial_period(period)
        if period.workspace_id != dataset.workspace.workspace_id or period.company_id != company.company_id:
            raise ValueError("period lineage differs from historical report authority.")

    period_by_id = {item.financial_period_id: item for item in periods}
    if len(period_by_id) != len(periods):
        raise ValueError("duplicate historical financial period identity.")

    ordered_observations = tuple(
        sorted(
            dataset.observations,
            key=lambda item: (
                period_by_id[item.financial_period_id].end_date if item.financial_period_id in period_by_id else None,
                item.metric_code,
                item.observation_id,
            ),
        )
    )
    if not ordered_observations:
        raise ValueError("historical report requires observations.")

    seen_coordinates: set[tuple[str, str]] = set()
    rows: list[HistoricalFinanceValue] = []
    for observation in ordered_observations:
        validate_financial_observation(observation)
        if observation.workspace_id != dataset.workspace.workspace_id:
            raise ValueError("observation workspace differs from historical report authority.")
        if observation.company_id != company.company_id:
            raise ValueError("observation company differs from historical report authority.")
        if observation.security_id is not None:
            raise ValueError("historical report shortest path does not invent or require Security.")
        if observation.financial_period_id is None or observation.financial_period_id not in period_by_id:
            raise ValueError("historical observation lacks governed period authority.")
        coordinate = (observation.financial_period_id, observation.metric_code)
        if coordinate in seen_coordinates:
            raise ValueError("duplicate period/metric historical observation coordinate.")
        seen_coordinates.add(coordinate)
        period = period_by_id[observation.financial_period_id]
        rows.append(
            HistoricalFinanceValue(
                financial_period_id=observation.financial_period_id,
                period_label=period.label,
                period_end_date=period.end_date.isoformat(),
                metric_code=observation.metric_code,
                value_text=canonical_decimal_text(observation.value),
                currency=observation.currency,
                unit=observation.unit,
                security_id=observation.security_id,
                provider=observation.provider,
                source_id=observation.source_id,
                source_version=observation.source_version,
                publication_at=_dt(observation.publication_at),
                effective_at=_dt(observation.effective_at),
                observed_at=_dt(observation.observed_at) or "",
                retrieved_at=_dt(observation.retrieved_at) or "",
                observation_id=observation.observation_id,
            )
        )

    period_ids = tuple(item.financial_period_id for item in periods)
    metric_codes = tuple(sorted({item.metric_code for item in ordered_observations}))
    provisional = HistoricalFinanceReport(
        schema_version=HISTORICAL_FINANCE_REPORT_SCHEMA_VERSION,
        report_id="sha256:" + "0" * 64,
        workspace_id=dataset.workspace.workspace_id,
        workspace_name=dataset.workspace.name,
        provider_id=dataset.provider_id,
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.dataset_version,
        dataset_identity=dataset.dataset_identity,
        company_id=company.company_id,
        company_legal_name=company.legal_name,
        company_display_name=company.display_name,
        reporting_currency=company.reporting_currency,
        period_ids=period_ids,
        metric_codes=metric_codes,
        values=tuple(rows),
    )
    return HistoricalFinanceReport(
        schema_version=provisional.schema_version,
        report_id=derive_finance_id(_semantic_payload(provisional)),
        workspace_id=provisional.workspace_id,
        workspace_name=provisional.workspace_name,
        provider_id=provisional.provider_id,
        dataset_id=provisional.dataset_id,
        dataset_version=provisional.dataset_version,
        dataset_identity=provisional.dataset_identity,
        company_id=provisional.company_id,
        company_legal_name=provisional.company_legal_name,
        company_display_name=provisional.company_display_name,
        reporting_currency=provisional.reporting_currency,
        period_ids=provisional.period_ids,
        metric_codes=provisional.metric_codes,
        values=provisional.values,
    )


def render_historical_finance_markdown(report: HistoricalFinanceReport) -> str:
    """Render exact stored historical observations without derived financial analysis."""
    lines = [
        f"# Historical Finance Report — {report.company_display_name}",
        "",
        f"- Report ID: `{report.report_id}`",
        f"- Dataset: `{report.dataset_id}` / version `{report.dataset_version}`",
        f"- Dataset identity: `{report.dataset_identity}`",
        f"- Provider: `{report.provider_id}`",
        f"- Company: {report.company_legal_name}",
        f"- Reporting currency: `{report.reporting_currency}`",
        "",
    ]
    for period_id in report.period_ids:
        period_rows = [row for row in report.values if row.financial_period_id == period_id]
        if not period_rows:
            continue
        lines.extend([
            f"## {period_rows[0].period_label}",
            "",
            "| Metric | Value | Currency | Unit |",
            "| --- | ---: | --- | --- |",
        ])
        for row in period_rows:
            currency = row.currency or ""
            lines.append(f"| {row.metric_code} | {row.value_text} | {currency} | {row.unit} |")
        lines.append("")

    lines.extend(["## Source traceability", ""])
    for row in report.values:
        lines.extend([
            f"### {row.period_label} — {row.metric_code}",
            "",
            f"- Observation ID: `{row.observation_id}`",
            f"- Source ID: `{row.source_id}`",
            f"- Source version: `{row.source_version}`",
            f"- Provider: `{row.provider}`",
            f"- Period ID: `{row.financial_period_id}`",
            f"- Security ID: `{row.security_id or 'NONE'}`",
            f"- Publication at: `{row.publication_at or 'NONE'}`",
            f"- Effective at: `{row.effective_at or 'NONE'}`",
            f"- Observed at: `{row.observed_at}`",
            f"- Retrieved at: `{row.retrieved_at}`",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def render_historical_finance_html(report: HistoricalFinanceReport) -> str:
    """Render one standalone escaped HTML document from the same historical report authority."""
    parts = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>Historical Finance Report — {escape(report.company_display_name)}</title>",
        "</head>",
        "<body>",
        f"<h1>Historical Finance Report — {escape(report.company_display_name)}</h1>",
        "<dl>",
        f"<dt>Report ID</dt><dd><code>{escape(report.report_id)}</code></dd>",
        f"<dt>Dataset</dt><dd><code>{escape(report.dataset_id)}</code> / version <code>{escape(report.dataset_version)}</code></dd>",
        f"<dt>Dataset identity</dt><dd><code>{escape(report.dataset_identity)}</code></dd>",
        f"<dt>Provider</dt><dd><code>{escape(report.provider_id)}</code></dd>",
        f"<dt>Company</dt><dd>{escape(report.company_legal_name)}</dd>",
        f"<dt>Reporting currency</dt><dd><code>{escape(report.reporting_currency)}</code></dd>",
        "</dl>",
    ]
    for period_id in report.period_ids:
        rows = [row for row in report.values if row.financial_period_id == period_id]
        if not rows:
            continue
        parts.extend([
            f"<section><h2>{escape(rows[0].period_label)}</h2>",
            "<table><thead><tr><th>Metric</th><th>Value</th><th>Currency</th><th>Unit</th></tr></thead><tbody>",
        ])
        for row in rows:
            parts.append(
                "<tr>"
                f"<td>{escape(row.metric_code)}</td>"
                f"<td>{escape(row.value_text)}</td>"
                f"<td>{escape(row.currency or '')}</td>"
                f"<td>{escape(row.unit)}</td>"
                "</tr>"
            )
        parts.extend(["</tbody></table>", "</section>"])

    parts.append("<section><h2>Source traceability</h2>")
    for row in report.values:
        parts.extend([
            "<article>",
            f"<h3>{escape(row.period_label)} — {escape(row.metric_code)}</h3>",
            "<dl>",
            f"<dt>Observation ID</dt><dd><code>{escape(row.observation_id)}</code></dd>",
            f"<dt>Source ID</dt><dd><code>{escape(row.source_id)}</code></dd>",
            f"<dt>Source version</dt><dd><code>{escape(row.source_version)}</code></dd>",
            f"<dt>Provider</dt><dd><code>{escape(row.provider)}</code></dd>",
            f"<dt>Period ID</dt><dd><code>{escape(row.financial_period_id)}</code></dd>",
            f"<dt>Security ID</dt><dd><code>{escape(row.security_id or 'NONE')}</code></dd>",
            f"<dt>Publication at</dt><dd><code>{escape(row.publication_at or 'NONE')}</code></dd>",
            f"<dt>Effective at</dt><dd><code>{escape(row.effective_at or 'NONE')}</code></dd>",
            f"<dt>Observed at</dt><dd><code>{escape(row.observed_at)}</code></dd>",
            f"<dt>Retrieved at</dt><dd><code>{escape(row.retrieved_at)}</code></dd>",
            "</dl>",
            "</article>",
        ])
    parts.extend(["</section>", "</body>", "</html>"])
    return "\n".join(parts) + "\n"


__all__ = [
    "HISTORICAL_FINANCE_REPORT_SCHEMA_VERSION",
    "HistoricalFinanceReport",
    "HistoricalFinanceValue",
    "build_historical_finance_report",
    "render_historical_finance_html",
    "render_historical_finance_markdown",
]
