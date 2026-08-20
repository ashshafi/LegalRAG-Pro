"""Fail-closed validation for Finance F4 comparable-company authorities."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from finance_calculations import AnalyticalStatus, CalculationClassification, validate_calculation_result
from finance_domain import (
    derive_finance_id,
    observation_available_as_of,
    validate_company,
    validate_financial_fact,
    validate_financial_observation,
    validate_financial_period,
    validate_security,
)
from finance_domain.identity import canonical_uuid, validate_sha256_id

from .models import (
    COMPARABLE_ANALYSIS_IDENTITY_VERSION,
    COMPARABLE_ANALYSIS_SCHEMA_VERSION,
    COMPARABLE_CELL_SCHEMA_VERSION,
    COMPARABLE_MEMBER_SCHEMA_VERSION,
    COMPARABLE_SET_SCHEMA_VERSION,
    MATRIX_METRICS,
    PEER_SUMMARY_SCHEMA_VERSION,
    SOURCE_FACT_METRICS,
    TARGET_POSITION_SCHEMA_VERSION,
    CellValueClassification,
    ComparableCompanyAnalysis,
    ComparableMemberSelection,
    ComparableMetricCell,
    ComparableRole,
    ComparableSetDefinition,
    PeerInclusionState,
    PeerMetricSummary,
    TargetPeerPosition,
)
from .serialization import (
    comparable_analysis_identity_payload_to_dict,
    comparable_member_identity_payload_to_dict,
    comparable_metric_cell_identity_payload_to_dict,
    comparable_set_identity_payload_to_dict,
    peer_metric_summary_identity_payload_to_dict,
    target_peer_position_identity_payload_to_dict,
)


def _utc(value: datetime, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field} must be UTC-aware.")


def _trimmed(value: str | None, field: str, optional: bool = False) -> None:
    if value is None and optional:
        return
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be non-empty trimmed text.")


def validate_comparable_member_selection(value: ComparableMemberSelection) -> None:
    if not isinstance(value, ComparableMemberSelection) or value.schema_version != COMPARABLE_MEMBER_SCHEMA_VERSION:
        raise ValueError("Unsupported ComparableMemberSelection.")
    canonical_uuid(value.company_id, field_name="company_id")
    canonical_uuid(value.security_id, field_name="security_id")
    if not isinstance(value.role, ComparableRole) or not isinstance(value.inclusion_state, PeerInclusionState):
        raise ValueError("Comparable role/inclusion state is invalid.")
    validate_sha256_id(value.current_period_id, field_name="current_period_id")
    validate_sha256_id(value.prior_period_id, field_name="prior_period_id")
    if value.current_period_id == value.prior_period_id:
        raise ValueError("Current and prior periods must differ.")
    if value.role is ComparableRole.TARGET and value.inclusion_state is not PeerInclusionState.INCLUDED:
        raise ValueError("TARGET must be INCLUDED.")
    if value.inclusion_state is PeerInclusionState.EXCLUDED:
        _trimmed(value.exclusion_reason, "exclusion_reason")
    elif value.exclusion_reason is not None:
        raise ValueError("INCLUDED member must not have exclusion_reason.")
    validate_sha256_id(value.member_id, field_name="member_id")
    if value.member_id != derive_finance_id(comparable_member_identity_payload_to_dict(value)):
        raise ValueError("member_id does not match canonical identity.")


def validate_comparable_set_definition(value: ComparableSetDefinition) -> None:
    if not isinstance(value, ComparableSetDefinition) or value.schema_version != COMPARABLE_SET_SCHEMA_VERSION:
        raise ValueError("Unsupported ComparableSetDefinition.")
    canonical_uuid(value.workspace_id, field_name="workspace_id")
    _utc(value.as_of, "as_of")
    if len(value.members) < 3:
        raise ValueError("Comparable set requires target plus at least two peers.")
    for item in value.members:
        validate_comparable_member_selection(item)
    targets = [m for m in value.members if m.role is ComparableRole.TARGET]
    if len(targets) != 1:
        raise ValueError("Comparable set must contain exactly one TARGET.")
    if any(m.role is ComparableRole.PEER and m.company_id == targets[0].company_id for m in value.members):
        raise ValueError("TARGET company cannot also be a PEER.")
    if len({m.company_id for m in value.members}) != len(value.members):
        raise ValueError("Comparable company selections must be unique.")
    if len({m.security_id for m in value.members}) != len(value.members):
        raise ValueError("Comparable security selections must be unique.")
    expected_order = tuple(sorted(value.members, key=lambda m: (0 if m.role is ComparableRole.TARGET else 1, m.company_id)))
    if value.members != expected_order:
        raise ValueError("Comparable members are not in canonical target/peer order.")
    validate_sha256_id(value.definition_id, field_name="definition_id")
    if value.definition_id != derive_finance_id(comparable_set_identity_payload_to_dict(value)):
        raise ValueError("definition_id does not match canonical identity.")


def validate_comparable_metric_cell(value: ComparableMetricCell) -> None:
    if not isinstance(value, ComparableMetricCell) or value.schema_version != COMPARABLE_CELL_SCHEMA_VERSION:
        raise ValueError("Unsupported ComparableMetricCell.")
    canonical_uuid(value.workspace_id, field_name="workspace_id")
    canonical_uuid(value.company_id, field_name="company_id")
    canonical_uuid(value.security_id, field_name="security_id")
    if value.metric_code not in MATRIX_METRICS:
        raise ValueError("F4 cell metric is outside fixed matrix authority.")
    if not isinstance(value.value_classification, CellValueClassification) or not isinstance(value.status, AnalyticalStatus):
        raise ValueError("F4 cell classification/status is invalid.")
    _utc(value.as_of, "cell.as_of")
    if value.value is not None and (not isinstance(value.value, Decimal) or not value.value.is_finite()):
        raise ValueError("Cell value must be finite Decimal when present.")
    if value.metric_code in SOURCE_FACT_METRICS:
        if value.value_classification is not CellValueClassification.SOURCE_FACT or value.calculation_classification is not None or value.source_result_id is not None:
            raise ValueError("Source-fact cell classification is invalid.")
        if value.status is AnalyticalStatus.ESTABLISHED:
            if value.source_fact_id is None or len(value.input_fact_ids) != 1:
                raise ValueError("Established source-fact cell must bind one fact.")
    else:
        if value.value_classification is not CellValueClassification.DERIVED_METRIC or value.calculation_classification is not CalculationClassification.MODEL_CALCULATION or value.source_fact_id is not None or value.source_result_id is None:
            raise ValueError("Derived cell classification is invalid.")
    if value.status is AnalyticalStatus.ESTABLISHED:
        if value.value is None or value.unit is None or value.note is not None:
            raise ValueError("Established cell must expose value/unit and no failure note.")
    else:
        if value.value is not None or value.currency is not None or value.unit is not None or value.note is None:
            raise ValueError("Non-established cell must fail closed and explain status.")
    for item in value.input_fact_ids + value.observation_ids:
        validate_sha256_id(item, field_name="cell provenance id")
    if value.input_fact_ids != tuple(sorted(set(value.input_fact_ids))) or value.observation_ids != tuple(sorted(set(value.observation_ids))):
        raise ValueError("Cell provenance IDs must be unique canonical order.")
    for item in (value.source_fact_id, value.source_result_id, value.financial_period_id):
        if item is not None:
            validate_sha256_id(item, field_name="cell referenced id")
    validate_sha256_id(value.cell_id, field_name="cell_id")
    if value.cell_id != derive_finance_id(comparable_metric_cell_identity_payload_to_dict(value)):
        raise ValueError("cell_id does not match canonical identity.")


def validate_peer_metric_summary(value: PeerMetricSummary) -> None:
    if not isinstance(value, PeerMetricSummary) or value.schema_version != PEER_SUMMARY_SCHEMA_VERSION:
        raise ValueError("Unsupported PeerMetricSummary.")
    canonical_uuid(value.workspace_id, field_name="workspace_id")
    if value.metric_code not in MATRIX_METRICS or value.value_classification is not CellValueClassification.DERIVED_METRIC or value.calculation_classification is not CalculationClassification.MODEL_CALCULATION:
        raise ValueError("Peer summary classification is invalid.")
    if not isinstance(value.status, AnalyticalStatus):
        raise ValueError("Peer summary status is invalid.")
    if type(value.selected_peer_count) is not int or type(value.established_peer_count) is not int or value.selected_peer_count < 0 or not (0 <= value.established_peer_count <= value.selected_peer_count):
        raise ValueError("Peer coverage counts are invalid.")
    _utc(value.as_of, "summary.as_of")
    values = (value.mean, value.median, value.minimum, value.maximum)
    if value.status is AnalyticalStatus.ESTABLISHED:
        if any(item is None for item in values) or value.unit is None or value.note is not None or len(value.input_cell_ids) != value.established_peer_count:
            raise ValueError("Established peer summary is incomplete.")
    else:
        if any(item is not None for item in values) or value.currency is not None or value.unit is not None or value.note is None:
            raise ValueError("Non-established peer summary must fail closed.")
    for item in value.input_cell_ids + value.unavailable_cell_ids:
        validate_sha256_id(item, field_name="summary cell id")
    if value.input_cell_ids != tuple(sorted(set(value.input_cell_ids))) or value.unavailable_cell_ids != tuple(sorted(set(value.unavailable_cell_ids))):
        raise ValueError("Summary cell IDs must use canonical unique order.")
    validate_sha256_id(value.summary_id, field_name="summary_id")
    if value.summary_id != derive_finance_id(peer_metric_summary_identity_payload_to_dict(value)):
        raise ValueError("summary_id does not match canonical identity.")


def validate_target_peer_position(value: TargetPeerPosition) -> None:
    if not isinstance(value, TargetPeerPosition) or value.schema_version != TARGET_POSITION_SCHEMA_VERSION:
        raise ValueError("Unsupported TargetPeerPosition.")
    canonical_uuid(value.workspace_id, field_name="workspace_id")
    if value.metric_code not in MATRIX_METRICS or not isinstance(value.status, AnalyticalStatus):
        raise ValueError("Target position metric/status is invalid.")
    _utc(value.as_of, "position.as_of")
    validate_sha256_id(value.target_cell_id, field_name="target_cell_id")
    validate_sha256_id(value.peer_summary_id, field_name="peer_summary_id")
    if value.status is AnalyticalStatus.ESTABLISHED:
        if value.relationship is None or value.note is not None:
            raise ValueError("Established target position must contain relationship only.")
    else:
        if value.relationship is not None or value.note is None:
            raise ValueError("Non-established target position must fail closed.")
    validate_sha256_id(value.position_id, field_name="position_id")
    if value.position_id != derive_finance_id(target_peer_position_identity_payload_to_dict(value)):
        raise ValueError("position_id does not match canonical identity.")


def validate_comparable_company_analysis(value: ComparableCompanyAnalysis) -> None:
    if not isinstance(value, ComparableCompanyAnalysis) or value.schema_version != COMPARABLE_ANALYSIS_SCHEMA_VERSION or value.identity_version != COMPARABLE_ANALYSIS_IDENTITY_VERSION:
        raise ValueError("Unsupported ComparableCompanyAnalysis.")
    canonical_uuid(value.workspace_id, field_name="workspace_id")
    for field, text in (("provider_id",value.provider_id),("dataset_id",value.dataset_id),("dataset_version",value.dataset_version)):
        _trimmed(text, field)
    validate_sha256_id(value.dataset_identity, field_name="dataset_identity")
    _utc(value.as_of, "analysis.as_of")
    validate_comparable_set_definition(value.definition)
    if value.definition.workspace_id != value.workspace_id or value.definition.as_of != value.as_of:
        raise ValueError("Definition is outside analysis workspace/as_of authority.")

    for collection, validator, key in (
        (value.companies, validate_company, "company_id"), (value.securities, validate_security, "security_id"),
        (value.periods, validate_financial_period, "financial_period_id"), (value.source_observations, validate_financial_observation, "observation_id"),
        (value.source_facts, validate_financial_fact, "fact_id"), (value.calculation_results, validate_calculation_result, "result_id"),
    ):
        for item in collection:
            validator(item)
        ids = [getattr(item, key) for item in collection]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate {key} in F4 authority.")

    company_by_id = {c.company_id:c for c in value.companies}; security_by_id = {s.security_id:s for s in value.securities}
    period_by_id = {p.financial_period_id:p for p in value.periods}; obs_by_id={o.observation_id:o for o in value.source_observations}
    fact_by_id={f.fact_id:f for f in value.source_facts}; result_by_id={r.result_id:r for r in value.calculation_results}
    selected_companies={m.company_id for m in value.definition.members}
    if set(company_by_id) != selected_companies or len(security_by_id) != len(selected_companies) or len(period_by_id) != 2*len(selected_companies):
        raise ValueError("F4 entity/period snapshot cardinality does not match definition.")
    for member in value.definition.members:
        if member.security_id not in security_by_id or security_by_id[member.security_id].company_id != member.company_id:
            raise ValueError("Definition security does not resolve inside F4 snapshot.")
        if member.current_period_id not in period_by_id or member.prior_period_id not in period_by_id:
            raise ValueError("Definition period does not resolve inside F4 snapshot.")
    for obs in value.source_observations:
        if obs.company_id not in selected_companies or obs.workspace_id != value.workspace_id or not observation_available_as_of(obs, value.as_of):
            raise ValueError("Observation is outside F4 authority/as_of.")
    for fact in value.source_facts:
        if fact.company_id not in selected_companies or fact.workspace_id != value.workspace_id or fact.as_of != value.as_of or any(oid not in obs_by_id for oid in fact.observation_ids):
            raise ValueError("Fact provenance is outside F4 authority.")
    expected_derived_pairs={(m.company_id, metric) for m in value.definition.members for metric in MATRIX_METRICS if metric not in SOURCE_FACT_METRICS}
    actual_derived_pairs={(r.company_id,r.metric_code) for r in value.calculation_results}
    if actual_derived_pairs != expected_derived_pairs:
        raise ValueError("F3 calculation result set is not exact for F4 matrix.")
    for result in value.calculation_results:
        if result.workspace_id != value.workspace_id or result.as_of != value.as_of or any(fid not in fact_by_id for fid in result.input_fact_ids):
            raise ValueError("Calculation result provenance is outside F4 authority.")

    for cell in value.cells: validate_comparable_metric_cell(cell)
    cell_by_id={c.cell_id:c for c in value.cells}
    expected_pairs={(m.company_id,metric) for m in value.definition.members for metric in MATRIX_METRICS}
    if {(c.company_id,c.metric_code) for c in value.cells} != expected_pairs or len(value.cells) != len(expected_pairs):
        raise ValueError("F4 matrix cell set is not exact.")
    for cell in value.cells:
        if cell.workspace_id != value.workspace_id or cell.as_of != value.as_of:
            raise ValueError("Cell is outside F4 workspace/as_of.")
        if cell.source_fact_id is not None and cell.source_fact_id not in fact_by_id:
            raise ValueError("Cell source_fact_id does not resolve.")
        if cell.source_result_id is not None and cell.source_result_id not in result_by_id:
            raise ValueError("Cell source_result_id does not resolve.")
        if any(fid not in fact_by_id for fid in cell.input_fact_ids) or any(oid not in obs_by_id for oid in cell.observation_ids):
            raise ValueError("Cell provenance does not resolve inside F4 authority.")
        expected_obs=tuple(sorted({oid for fid in cell.input_fact_ids for oid in fact_by_id[fid].observation_ids}))
        if cell.status is AnalyticalStatus.ESTABLISHED and cell.observation_ids != expected_obs:
            raise ValueError("Established cell observation provenance is not exact through facts.")
        if cell.source_result_id is not None:
            result=result_by_id[cell.source_result_id]
            if (result.company_id,result.metric_code,result.input_fact_ids,result.status,result.value)!=(cell.company_id,cell.metric_code,cell.input_fact_ids,cell.status,cell.value):
                raise ValueError("Derived cell does not exactly mirror F3 result authority.")

    for summary in value.summaries: validate_peer_metric_summary(summary)
    if tuple(s.metric_code for s in value.summaries) != MATRIX_METRICS:
        raise ValueError("Peer summaries must follow fixed metric order.")
    summary_by_id={s.summary_id:s for s in value.summaries}
    included_peer_ids={m.company_id for m in value.definition.members if m.role is ComparableRole.PEER and m.inclusion_state is PeerInclusionState.INCLUDED}
    for summary in value.summaries:
        referenced=[cell_by_id[cid] for cid in summary.input_cell_ids+summary.unavailable_cell_ids]
        if any(c.company_id not in included_peer_ids or c.metric_code != summary.metric_code for c in referenced):
            raise ValueError("Peer summary references non-included or wrong-metric cell.")

    for pos in value.positions: validate_target_peer_position(pos)
    if tuple(p.metric_code for p in value.positions) != MATRIX_METRICS:
        raise ValueError("Target positions must follow fixed metric order.")
    target_id=next(m.company_id for m in value.definition.members if m.role is ComparableRole.TARGET)
    for pos in value.positions:
        if pos.target_cell_id not in cell_by_id or cell_by_id[pos.target_cell_id].company_id != target_id or pos.peer_summary_id not in summary_by_id:
            raise ValueError("Target position provenance does not resolve.")

    validate_sha256_id(value.analysis_id, field_name="analysis_id")
    if value.analysis_id != derive_finance_id(comparable_analysis_identity_payload_to_dict(value)):
        raise ValueError("analysis_id does not match canonical F4 authority content.")


__all__ = [
    "validate_comparable_company_analysis",
    "validate_comparable_member_selection",
    "validate_comparable_metric_cell",
    "validate_comparable_set_definition",
    "validate_peer_metric_summary",
    "validate_target_peer_position",
]
