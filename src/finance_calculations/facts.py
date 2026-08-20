"""Conservative source-observation reconciliation into governed F1 facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from finance_data import FinancialDataProvider
from finance_domain import (
    FINANCIAL_FACT_SCHEMA_VERSION,
    FinancialFact,
    FinancialObservation,
    derive_finance_id,
    financial_fact_identity_payload_to_dict,
    validate_financial_fact,
)

from .models import AnalyticalStatus


@dataclass(frozen=True, slots=True)
class FactResolution:
    status: AnalyticalStatus
    fact: FinancialFact | None
    observation_ids: tuple[str, ...]
    note: str | None


def _semantic_key(value: FinancialObservation) -> tuple[object, ...]:
    return (
        value.workspace_id,
        value.company_id,
        value.security_id,
        value.metric_code,
        value.value,
        value.currency,
        value.unit,
        value.financial_period_id,
    )


def resolve_financial_fact(
    provider: FinancialDataProvider,
    *,
    company_id: str,
    metric_code: str,
    as_of: datetime,
    security_id: str | None = None,
    financial_period_id: str | None = None,
) -> FactResolution:
    """Resolve one governed fact without guessing across source discrepancies."""

    observations = provider.get_observations(
        company_id=company_id,
        security_id=security_id,
        metric_code=metric_code,
        financial_period_id=financial_period_id,
        as_of=as_of,
    )
    ordered = tuple(sorted(observations, key=lambda item: item.observation_id))
    ids = tuple(item.observation_id for item in ordered)

    if not ordered:
        return FactResolution(
            status=AnalyticalStatus.DATA_NOT_AVAILABLE,
            fact=None,
            observation_ids=(),
            note=f"No available source observation for {metric_code} at requested as_of.",
        )

    keys = {_semantic_key(item) for item in ordered}
    if len(keys) != 1:
        return FactResolution(
            status=AnalyticalStatus.SOURCE_CONFLICT,
            fact=None,
            observation_ids=ids,
            note=f"Available source observations for {metric_code} conflict materially.",
        )

    source = ordered[0]
    reconciliation_note = (
        "single_source_observation"
        if len(ordered) == 1
        else "identical_source_observations_reconciled"
    )
    provisional = FinancialFact(
        schema_version=FINANCIAL_FACT_SCHEMA_VERSION,
        workspace_id=source.workspace_id,
        company_id=source.company_id,
        security_id=source.security_id,
        metric_code=source.metric_code,
        value=source.value,
        currency=source.currency,
        unit=source.unit,
        financial_period_id=source.financial_period_id,
        as_of=as_of,
        observation_ids=ids,
        reconciliation_note=reconciliation_note,
        fact_id="sha256:" + "0" * 64,
    )
    fact_id = derive_finance_id(financial_fact_identity_payload_to_dict(provisional))
    fact = FinancialFact(
        schema_version=provisional.schema_version,
        workspace_id=provisional.workspace_id,
        company_id=provisional.company_id,
        security_id=provisional.security_id,
        metric_code=provisional.metric_code,
        value=provisional.value,
        currency=provisional.currency,
        unit=provisional.unit,
        financial_period_id=provisional.financial_period_id,
        as_of=provisional.as_of,
        observation_ids=provisional.observation_ids,
        reconciliation_note=provisional.reconciliation_note,
        fact_id=fact_id,
    )
    validate_financial_fact(fact)
    return FactResolution(
        status=AnalyticalStatus.ESTABLISHED,
        fact=fact,
        observation_ids=ids,
        note=None,
    )


__all__ = ["FactResolution", "resolve_financial_fact"]
