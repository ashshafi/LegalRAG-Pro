"""Project frozen F4/F5 authority into an ephemeral Finance F6 answer context."""
from __future__ import annotations

from finance_comps.models import ComparableCompanyAnalysis
from finance_comps.validation import validate_comparable_company_analysis
from finance_evidence.models import FinanceObservationEvidenceManifest
from finance_evidence.validation import validate_finance_observation_evidence_manifest

from .models import (
    RuntimeFinanceAnswerAuthorityContext,
    RuntimeFinanceCalculation,
    RuntimeFinanceCell,
    RuntimeFinanceEvidenceBinding,
    RuntimeFinanceMember,
    RuntimeFinancePeerSummary,
    RuntimeFinanceTargetPosition,
)
from .validation import validate_runtime_finance_answer_context


def build_runtime_finance_answer_context(
    *,
    analysis: ComparableCompanyAnalysis,
    evidence_manifest: FinanceObservationEvidenceManifest,
) -> RuntimeFinanceAnswerAuthorityContext:
    """Build a read-only, lossless F6 projection without creating analytical state."""
    validate_comparable_company_analysis(analysis)
    validate_finance_observation_evidence_manifest(evidence_manifest, analysis)

    companies = {item.company_id: item for item in analysis.companies}
    periods = {item.financial_period_id: item for item in analysis.periods}
    facts = {item.fact_id: item for item in analysis.source_facts}
    observations = {item.observation_id: item for item in analysis.source_observations}

    members = tuple(
        RuntimeFinanceMember(
            member_id=item.member_id,
            company_id=item.company_id,
            company_name=companies[item.company_id].display_name,
            security_id=item.security_id,
            role=item.role,
            inclusion_state=item.inclusion_state,
            current_period_id=item.current_period_id,
            prior_period_id=item.prior_period_id,
            exclusion_reason=item.exclusion_reason,
        )
        for item in analysis.definition.members
    )

    cells = tuple(
        RuntimeFinanceCell(
            cell_id=item.cell_id,
            company_id=item.company_id,
            company_name=companies[item.company_id].display_name,
            security_id=item.security_id,
            metric_code=item.metric_code,
            value_classification=item.value_classification,
            calculation_classification=item.calculation_classification,
            status=item.status,
            value=item.value,
            currency=item.currency,
            unit=item.unit,
            financial_period_id=item.financial_period_id,
            financial_period_label=(periods[item.financial_period_id].label if item.financial_period_id is not None else None),
            as_of=item.as_of,
            source_fact_id=item.source_fact_id,
            source_result_id=item.source_result_id,
            input_fact_ids=item.input_fact_ids,
            observation_ids=item.observation_ids,
            note=item.note,
        )
        for item in analysis.cells
    )

    summaries = tuple(
        RuntimeFinancePeerSummary(
            summary_id=item.summary_id,
            metric_code=item.metric_code,
            status=item.status,
            selected_peer_count=item.selected_peer_count,
            established_peer_count=item.established_peer_count,
            currency=item.currency,
            unit=item.unit,
            mean=item.mean,
            median=item.median,
            minimum=item.minimum,
            maximum=item.maximum,
            input_cell_ids=item.input_cell_ids,
            unavailable_cell_ids=item.unavailable_cell_ids,
            as_of=item.as_of,
            note=item.note,
        )
        for item in analysis.summaries
    )

    positions = tuple(
        RuntimeFinanceTargetPosition(
            position_id=item.position_id,
            metric_code=item.metric_code,
            status=item.status,
            relationship=item.relationship,
            target_cell_id=item.target_cell_id,
            peer_summary_id=item.peer_summary_id,
            as_of=item.as_of,
            note=item.note,
        )
        for item in analysis.positions
    )

    calculations = []
    for item in analysis.calculation_results:
        observation_ids = tuple(sorted({
            observation_id
            for fact_id in item.input_fact_ids
            for observation_id in facts[fact_id].observation_ids
        }))
        calculations.append(RuntimeFinanceCalculation(
            result_id=item.result_id,
            company_id=item.company_id,
            company_name=companies[item.company_id].display_name,
            metric_code=item.metric_code,
            status=item.status,
            calculation_code=item.calculation_code,
            calculation_version=item.calculation_version,
            formula=item.formula,
            input_fact_ids=item.input_fact_ids,
            observation_ids=observation_ids,
            note=item.note,
        ))

    entry_by_observation = {item.observation_id: item for item in evidence_manifest.entries}
    evidence_bindings = tuple(
        RuntimeFinanceEvidenceBinding(
            evidence_binding_id=entry_by_observation[observation.observation_id].evidence_binding_id,
            observation_id=observation.observation_id,
            company_id=observation.company_id,
            company_name=companies[observation.company_id].display_name,
            provider=observation.provider,
            source_id=observation.source_id,
            source_version=observation.source_version,
            publication_at=observation.publication_at,
            source_channel=entry_by_observation[observation.observation_id].source_channel,
            binding_class=entry_by_observation[observation.observation_id].binding_class,
            document_snapshot_id=entry_by_observation[observation.observation_id].document_snapshot_id,
            page_number=entry_by_observation[observation.observation_id].page_number,
            bound_text_sha256=entry_by_observation[observation.observation_id].bound_text_sha256,
            note=entry_by_observation[observation.observation_id].note,
        )
        for observation in sorted(observations.values(), key=lambda value: value.observation_id)
    )

    result = RuntimeFinanceAnswerAuthorityContext(
        workspace_id=analysis.workspace_id,
        analysis_id=analysis.analysis_id,
        as_of=analysis.as_of,
        provider_id=analysis.provider_id,
        dataset_id=analysis.dataset_id,
        dataset_version=analysis.dataset_version,
        dataset_identity=analysis.dataset_identity,
        definition_id=analysis.definition.definition_id,
        document_evidence_manifest_id=evidence_manifest.document_evidence_manifest_id,
        document_evidence_coverage=evidence_manifest.coverage,
        members=members,
        cells=cells,
        summaries=summaries,
        positions=positions,
        calculations=tuple(calculations),
        evidence_bindings=evidence_bindings,
    )
    validate_runtime_finance_answer_context(result)
    return result
