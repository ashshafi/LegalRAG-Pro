"""Build immutable F4 comparable-company analysis from frozen F1-F3 authorities."""

from __future__ import annotations

from datetime import datetime

from finance_calculations import (
    AnalyticalStatus,
    CalculationClassification,
    DeterministicCalculationEngine,
    resolve_financial_fact,
)
from finance_data import FinancialDataProvider
from finance_domain import FinancialFact, derive_finance_id

from .models import (
    COMPARABLE_ANALYSIS_IDENTITY_VERSION,
    COMPARABLE_ANALYSIS_SCHEMA_VERSION,
    COMPARABLE_CELL_SCHEMA_VERSION,
    COMPARABLE_MEMBER_SCHEMA_VERSION,
    COMPARABLE_SET_SCHEMA_VERSION,
    TARGET_POSITION_SCHEMA_VERSION,
    CellValueClassification,
    ComparableCompanyAnalysis,
    ComparableMemberSelection,
    ComparableMetricCell,
    ComparableRole,
    ComparableSetDefinition,
    DERIVED_MATRIX_METRICS,
    MATRIX_METRICS,
    PeerInclusionState,
    TargetPeerPosition,
    TargetPeerRelationship,
)
from .serialization import (
    comparable_analysis_identity_payload_to_dict,
    comparable_member_identity_payload_to_dict,
    comparable_metric_cell_identity_payload_to_dict,
    comparable_set_identity_payload_to_dict,
    target_peer_position_identity_payload_to_dict,
)
from .statistics import build_peer_metric_summary
from .validation import validate_comparable_company_analysis, validate_comparable_set_definition


def _member_sort_key(value: ComparableMemberSelection) -> tuple[int, str]:
    return (0 if value.role is ComparableRole.TARGET else 1, value.company_id)


def create_comparable_member_selection(
    *,
    company_id: str,
    security_id: str,
    role: ComparableRole,
    inclusion_state: PeerInclusionState,
    current_period_id: str,
    prior_period_id: str,
    exclusion_reason: str | None = None,
) -> ComparableMemberSelection:
    provisional = ComparableMemberSelection(
        schema_version=COMPARABLE_MEMBER_SCHEMA_VERSION,
        company_id=company_id,
        security_id=security_id,
        role=role,
        inclusion_state=inclusion_state,
        current_period_id=current_period_id,
        prior_period_id=prior_period_id,
        exclusion_reason=exclusion_reason,
        member_id="sha256:" + "0" * 64,
    )
    member_id = derive_finance_id(comparable_member_identity_payload_to_dict(provisional))
    return ComparableMemberSelection(
        schema_version=provisional.schema_version, company_id=provisional.company_id, security_id=provisional.security_id,
        role=provisional.role, inclusion_state=provisional.inclusion_state, current_period_id=provisional.current_period_id,
        prior_period_id=provisional.prior_period_id, exclusion_reason=provisional.exclusion_reason, member_id=member_id,
    )


def create_comparable_set_definition(
    *, workspace_id: str, as_of: datetime, members: tuple[ComparableMemberSelection, ...]
) -> ComparableSetDefinition:
    ordered = tuple(sorted(tuple(members), key=_member_sort_key))
    provisional = ComparableSetDefinition(
        schema_version=COMPARABLE_SET_SCHEMA_VERSION,
        workspace_id=workspace_id,
        as_of=as_of,
        members=ordered,
        definition_id="sha256:" + "0" * 64,
    )
    definition_id = derive_finance_id(comparable_set_identity_payload_to_dict(provisional))
    result = ComparableSetDefinition(
        schema_version=provisional.schema_version, workspace_id=workspace_id, as_of=as_of,
        members=ordered, definition_id=definition_id,
    )
    validate_comparable_set_definition(result)
    return result


def _cell_from_fact(*, definition, member, metric_code, resolution) -> ComparableMetricCell:
    fact = resolution.fact
    if fact is not None:
        value, currency, unit = fact.value, fact.currency, fact.unit
        source_fact_id = fact.fact_id
        input_fact_ids = (fact.fact_id,)
        period_id = fact.financial_period_id
        note = None
    else:
        value = currency = unit = source_fact_id = period_id = None
        input_fact_ids = ()
        note = resolution.note
    provisional = ComparableMetricCell(
        schema_version=COMPARABLE_CELL_SCHEMA_VERSION,
        workspace_id=definition.workspace_id, company_id=member.company_id, security_id=member.security_id,
        metric_code=metric_code, value_classification=CellValueClassification.SOURCE_FACT,
        calculation_classification=None, status=resolution.status, value=value, currency=currency, unit=unit,
        financial_period_id=period_id, as_of=definition.as_of, source_fact_id=source_fact_id,
        source_result_id=None, input_fact_ids=input_fact_ids,
        observation_ids=tuple(sorted(resolution.observation_ids)), note=note, cell_id="sha256:" + "0" * 64,
    )
    cid = derive_finance_id(comparable_metric_cell_identity_payload_to_dict(provisional))
    return ComparableMetricCell(
        schema_version=provisional.schema_version, workspace_id=provisional.workspace_id, company_id=provisional.company_id,
        security_id=provisional.security_id, metric_code=provisional.metric_code, value_classification=provisional.value_classification,
        calculation_classification=provisional.calculation_classification, status=provisional.status, value=provisional.value,
        currency=provisional.currency, unit=provisional.unit, financial_period_id=provisional.financial_period_id,
        as_of=provisional.as_of, source_fact_id=provisional.source_fact_id, source_result_id=provisional.source_result_id,
        input_fact_ids=provisional.input_fact_ids, observation_ids=provisional.observation_ids, note=provisional.note, cell_id=cid,
    )


def _cell_from_result(*, definition, member, result, fact_by_id) -> ComparableMetricCell:
    obs_ids = sorted({oid for fid in result.input_fact_ids for oid in fact_by_id[fid].observation_ids if fid in fact_by_id})
    provisional = ComparableMetricCell(
        schema_version=COMPARABLE_CELL_SCHEMA_VERSION,
        workspace_id=definition.workspace_id, company_id=member.company_id, security_id=member.security_id,
        metric_code=result.metric_code, value_classification=CellValueClassification.DERIVED_METRIC,
        calculation_classification=CalculationClassification.MODEL_CALCULATION, status=result.status,
        value=result.value, currency=result.currency, unit=result.unit, financial_period_id=result.financial_period_id,
        as_of=definition.as_of, source_fact_id=None, source_result_id=result.result_id,
        input_fact_ids=result.input_fact_ids, observation_ids=tuple(obs_ids), note=result.note,
        cell_id="sha256:" + "0" * 64,
    )
    cid = derive_finance_id(comparable_metric_cell_identity_payload_to_dict(provisional))
    return ComparableMetricCell(
        schema_version=provisional.schema_version, workspace_id=provisional.workspace_id, company_id=provisional.company_id,
        security_id=provisional.security_id, metric_code=provisional.metric_code, value_classification=provisional.value_classification,
        calculation_classification=provisional.calculation_classification, status=provisional.status, value=provisional.value,
        currency=provisional.currency, unit=provisional.unit, financial_period_id=provisional.financial_period_id,
        as_of=provisional.as_of, source_fact_id=provisional.source_fact_id, source_result_id=provisional.source_result_id,
        input_fact_ids=provisional.input_fact_ids, observation_ids=provisional.observation_ids, note=provisional.note, cell_id=cid,
    )


def _validate_provider_selection(provider: FinancialDataProvider, definition: ComparableSetDefinition) -> None:
    if definition.workspace_id != provider.workspace.workspace_id:
        raise ValueError("Comparable definition workspace is outside provider authority.")
    period_semantics = None
    for member in definition.members:
        company = provider.get_company(company_id=member.company_id)
        security = provider.get_security(security_id=member.security_id)
        if company is None:
            raise ValueError("Comparable member company is outside provider authority.")
        if security is None or security.company_id != member.company_id:
            raise ValueError("Comparable member security does not belong to selected company.")
        periods = {p.financial_period_id: p for p in provider.list_periods(company_id=member.company_id)}
        current = periods.get(member.current_period_id)
        prior = periods.get(member.prior_period_id)
        if current is None or prior is None:
            raise ValueError("Comparable member period is outside selected company authority.")
        if current.end_date <= prior.end_date:
            raise ValueError("Comparable current/prior period ordering is invalid.")
        if member.inclusion_state is PeerInclusionState.INCLUDED or member.role is ComparableRole.TARGET:
            semantics = (current.period_type, current.start_date, current.end_date, prior.period_type, prior.start_date, prior.end_date)
            if period_semantics is None:
                period_semantics = semantics
            elif period_semantics != semantics:
                raise ValueError("Included comparable periods are not exactly comparable; calendarisation is out of scope.")


def build_comparable_company_analysis(
    *, provider: FinancialDataProvider, definition: ComparableSetDefinition
) -> ComparableCompanyAnalysis:
    if not isinstance(provider, FinancialDataProvider):
        raise TypeError("provider must implement FinancialDataProvider.")
    validate_comparable_set_definition(definition)
    _validate_provider_selection(provider, definition)

    members = definition.members
    member_ids = {m.company_id for m in members}
    companies = tuple(sorted((provider.get_company(company_id=m.company_id) for m in members), key=lambda x: x.company_id))
    if any(item is None for item in companies):
        raise ValueError("Comparable company disappeared from provider authority.")
    companies = tuple(item for item in companies if item is not None)
    securities = tuple(sorted((provider.get_security(security_id=m.security_id) for m in members), key=lambda x: x.security_id))
    securities = tuple(item for item in securities if item is not None)
    periods = tuple(sorted(
        (p for m in members for p in provider.list_periods(company_id=m.company_id) if p.financial_period_id in {m.current_period_id, m.prior_period_id}),
        key=lambda x: x.financial_period_id,
    ))

    observations = tuple(sorted(
        (o for m in members for o in provider.get_observations(company_id=m.company_id, as_of=definition.as_of)),
        key=lambda x: x.observation_id,
    ))

    facts: dict[str, FinancialFact] = {}
    seen_queries = set()
    for obs in observations:
        key = (obs.company_id, obs.metric_code, obs.security_id, obs.financial_period_id)
        if key in seen_queries:
            continue
        seen_queries.add(key)
        resolution = resolve_financial_fact(
            provider, company_id=obs.company_id, metric_code=obs.metric_code, as_of=definition.as_of,
            security_id=obs.security_id, financial_period_id=obs.financial_period_id,
        )
        if resolution.fact is not None:
            facts[resolution.fact.fact_id] = resolution.fact

    engine = DeterministicCalculationEngine(provider)
    results = []
    result_by_company_metric = {}
    for member in members:
        for metric_code in DERIVED_MATRIX_METRICS:
            result = engine.calculate(
                company_id=member.company_id, security_id=member.security_id, metric_code=metric_code,
                current_period_id=member.current_period_id, prior_period_id=member.prior_period_id, as_of=definition.as_of,
            )
            results.append(result)
            result_by_company_metric[(member.company_id, metric_code)] = result
            for fid in result.input_fact_ids:
                if fid not in facts:
                    raise ValueError("F3 result references a fact not present in the F4 point-in-time source snapshot.")

    cells = []
    for member in members:
        for metric_code in MATRIX_METRICS:
            if metric_code in {"REVENUE", "EBITDA"}:
                resolution = resolve_financial_fact(
                    provider, company_id=member.company_id, metric_code=metric_code, as_of=definition.as_of,
                    financial_period_id=member.current_period_id,
                )
                cell = _cell_from_fact(definition=definition, member=member, metric_code=metric_code, resolution=resolution)
            else:
                cell = _cell_from_result(
                    definition=definition, member=member,
                    result=result_by_company_metric[(member.company_id, metric_code)], fact_by_id=facts,
                )
            cells.append(cell)

    cell_by_company_metric = {(c.company_id, c.metric_code): c for c in cells}
    included_peers = tuple(m for m in members if m.role is ComparableRole.PEER and m.inclusion_state is PeerInclusionState.INCLUDED)
    summaries = tuple(
        build_peer_metric_summary(
            workspace_id=definition.workspace_id, metric_code=metric,
            selected_peer_cells=tuple(cell_by_company_metric[(m.company_id, metric)] for m in included_peers),
            as_of=definition.as_of,
        )
        for metric in MATRIX_METRICS
    )
    target = next(m for m in members if m.role is ComparableRole.TARGET)
    summary_by_metric = {s.metric_code: s for s in summaries}
    positions = []
    for metric in MATRIX_METRICS:
        cell = cell_by_company_metric[(target.company_id, metric)]
        summary = summary_by_metric[metric]
        if cell.status is AnalyticalStatus.ESTABLISHED and summary.status is AnalyticalStatus.ESTABLISHED:
            if (cell.currency, cell.unit) != (summary.currency, summary.unit):
                status = AnalyticalStatus.ASSUMPTION_REQUIRED
                relationship = None
                note = "Target and peer-summary semantics require normalisation."
            else:
                assert cell.value is not None and summary.median is not None
                status = AnalyticalStatus.ESTABLISHED
                relationship = (
                    TargetPeerRelationship.BELOW_PEER_MEDIAN if cell.value < summary.median
                    else TargetPeerRelationship.ABOVE_PEER_MEDIAN if cell.value > summary.median
                    else TargetPeerRelationship.AT_PEER_MEDIAN
                )
                note = None
        else:
            status = cell.status if cell.status is not AnalyticalStatus.ESTABLISHED else summary.status
            relationship = None
            note = "Target position cannot be established from current target/peer analytical state."
        provisional = TargetPeerPosition(
            schema_version=TARGET_POSITION_SCHEMA_VERSION, workspace_id=definition.workspace_id, metric_code=metric,
            status=status, relationship=relationship, target_cell_id=cell.cell_id, peer_summary_id=summary.summary_id,
            as_of=definition.as_of, note=note, position_id="sha256:" + "0" * 64,
        )
        pid = derive_finance_id(target_peer_position_identity_payload_to_dict(provisional))
        positions.append(TargetPeerPosition(
            schema_version=provisional.schema_version, workspace_id=provisional.workspace_id, metric_code=provisional.metric_code,
            status=provisional.status, relationship=provisional.relationship, target_cell_id=provisional.target_cell_id,
            peer_summary_id=provisional.peer_summary_id, as_of=provisional.as_of, note=provisional.note, position_id=pid,
        ))

    provisional = ComparableCompanyAnalysis(
        schema_version=COMPARABLE_ANALYSIS_SCHEMA_VERSION, identity_version=COMPARABLE_ANALYSIS_IDENTITY_VERSION,
        workspace_id=definition.workspace_id, provider_id=provider.provider_id, dataset_id=provider.dataset_id,
        dataset_version=provider.dataset_version, dataset_identity=provider.dataset_identity, as_of=definition.as_of,
        definition=definition, companies=companies, securities=securities, periods=periods,
        source_observations=observations, source_facts=tuple(sorted(facts.values(), key=lambda x: x.fact_id)),
        calculation_results=tuple(sorted(results, key=lambda x: x.result_id)), cells=tuple(cells), summaries=summaries,
        positions=tuple(positions), analysis_id="sha256:" + "0" * 64,
    )
    aid = derive_finance_id(comparable_analysis_identity_payload_to_dict(provisional))
    analysis = ComparableCompanyAnalysis(
        schema_version=provisional.schema_version, identity_version=provisional.identity_version, workspace_id=provisional.workspace_id,
        provider_id=provisional.provider_id, dataset_id=provisional.dataset_id, dataset_version=provisional.dataset_version,
        dataset_identity=provisional.dataset_identity, as_of=provisional.as_of, definition=provisional.definition,
        companies=provisional.companies, securities=provisional.securities, periods=provisional.periods,
        source_observations=provisional.source_observations, source_facts=provisional.source_facts,
        calculation_results=provisional.calculation_results, cells=provisional.cells, summaries=provisional.summaries,
        positions=provisional.positions, analysis_id=aid,
    )
    validate_comparable_company_analysis(analysis)
    return analysis


__all__ = [
    "build_comparable_company_analysis",
    "create_comparable_member_selection",
    "create_comparable_set_definition",
]
