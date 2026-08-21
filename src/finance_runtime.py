"""Pure Finance runtime composition from explicit provider selection to report projection."""

from __future__ import annotations

from pathlib import Path

from finance_comps import ComparableSetDefinition, build_comparable_company_analysis
from finance_data.provider_selection import select_financial_data_provider
from finance_evidence import build_finance_observation_evidence_manifest
from finance_reporting import FinanceReportProjection, build_finance_report_projection


def build_finance_runtime_projection(
    *,
    provider_mode: str,
    definition: ComparableSetDefinition,
    documents,
    entries,
    dataset_path: Path | None = None,
    expected_provider_id: str | None = None,
    expected_dataset_id: str | None = None,
    expected_dataset_version: str | None = None,
) -> FinanceReportProjection:
    """Compose the governed pure Finance pipeline without publication or UI activation."""

    provider = select_financial_data_provider(
        mode=provider_mode,
        dataset_path=dataset_path,
        expected_provider_id=expected_provider_id,
        expected_dataset_id=expected_dataset_id,
        expected_dataset_version=expected_dataset_version,
    )
    analysis = build_comparable_company_analysis(
        provider=provider,
        definition=definition,
    )
    evidence_manifest = build_finance_observation_evidence_manifest(
        analysis=analysis,
        documents=documents,
        entries=entries,
    )
    return build_finance_report_projection(
        analysis=analysis,
        evidence_manifest=evidence_manifest,
    )
