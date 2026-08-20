"""Build immutable Finance F7A report projections from frozen F4/F5 authority."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
import hashlib

from finance_calculations import AnalyticalStatus
from finance_comps import ComparableCompanyAnalysis, PeerInclusionState, validate_comparable_company_analysis
from finance_domain import derive_finance_id
from finance_domain.identity import canonical_json_bytes
from finance_evidence import (
    FinanceDocumentEvidenceCoverage,
    FinanceObservationEvidenceManifest,
    ObservationDocumentBindingClass,
    validate_finance_observation_evidence_manifest,
)

from .models import *
from .serialization import finance_report_manifest_identity_payload_to_dict, projection_semantic_payload_to_dict

_SECTION_ORDER = (
    "report_header", "analytical_lineage", "comparable_set", "metric_matrix",
    "peer_statistics", "target_peer_positions", "calculation_lineage",
    "evidence_coverage", "evidence_register", "limitations",
)

def _ordered_unique(values):
    return tuple(dict.fromkeys(values))

def _evidence_ids(observation_ids, evidence_by_observation):
    return tuple(evidence_by_observation[oid].evidence_binding_id for oid in observation_ids)

def _limitation_id(limitation_type, authority_id, raw_status, note):
    return derive_finance_id({
        "schema": "finance-report-limitation/1.0",
        "limitation_type": limitation_type.value,
        "authority_id": authority_id,
        "raw_status": raw_status,
        "note": note,
    })

def build_finance_report_projection(*, analysis: ComparableCompanyAnalysis, evidence_manifest: FinanceObservationEvidenceManifest) -> FinanceReportProjection:
    """Project exact F4/F5 authority into one deterministic presentation authority."""
    validate_comparable_company_analysis(analysis)
    validate_finance_observation_evidence_manifest(evidence_manifest, analysis)

    company_by_id = {x.company_id: x for x in analysis.companies}
    period_by_id = {x.financial_period_id: x for x in analysis.periods}
    fact_by_id = {x.fact_id: x for x in analysis.source_facts}
    observation_by_id = {x.observation_id: x for x in analysis.source_observations}
    evidence_by_observation = {x.observation_id: x for x in evidence_manifest.entries}

    header = FinanceReportHeader(
        workspace_id=analysis.workspace_id,
        analysis_id=analysis.analysis_id,
        as_of=analysis.as_of,
        provider_id=analysis.provider_id,
        dataset_id=analysis.dataset_id,
        dataset_version=analysis.dataset_version,
        dataset_identity=analysis.dataset_identity,
        definition_id=analysis.definition.definition_id,
        document_evidence_manifest_id=evidence_manifest.document_evidence_manifest_id,
    )

    members = tuple(FinanceReportMember(
        member_id=m.member_id,
        company_id=m.company_id,
        company_name=company_by_id[m.company_id].display_name,
        security_id=m.security_id,
        role=m.role,
        inclusion_state=m.inclusion_state,
        current_period_id=m.current_period_id,
        current_period_label=period_by_id[m.current_period_id].label,
        prior_period_id=m.prior_period_id,
        prior_period_label=period_by_id[m.prior_period_id].label,
        exclusion_reason=m.exclusion_reason,
    ) for m in analysis.definition.members)

    cells = tuple(FinanceReportMetricCell(
        cell_id=c.cell_id,
        company_id=c.company_id,
        company_name=company_by_id[c.company_id].display_name,
        security_id=c.security_id,
        metric_code=c.metric_code,
        value_classification=c.value_classification,
        calculation_classification=c.calculation_classification,
        analytical_status=c.status,
        value=c.value,
        currency=c.currency,
        unit=c.unit,
        financial_period_id=c.financial_period_id,
        financial_period_label=(period_by_id[c.financial_period_id].label if c.financial_period_id else None),
        source_fact_id=c.source_fact_id,
        source_result_id=c.source_result_id,
        input_fact_ids=c.input_fact_ids,
        observation_ids=c.observation_ids,
        evidence_binding_ids=_evidence_ids(c.observation_ids, evidence_by_observation),
        note=c.note,
    ) for c in analysis.cells)
    cell_by_id = {c.cell_id: c for c in cells}

    summaries = []
    for s in analysis.summaries:
        referenced = tuple(s.input_cell_ids) + tuple(s.unavailable_cell_ids)
        observation_ids = tuple(sorted({oid for cid in referenced for oid in cell_by_id[cid].observation_ids}))
        summaries.append(FinanceReportPeerSummary(
            summary_id=s.summary_id, metric_code=s.metric_code, analytical_status=s.status,
            selected_peer_count=s.selected_peer_count, established_peer_count=s.established_peer_count,
            currency=s.currency, unit=s.unit, mean=s.mean, median=s.median, minimum=s.minimum, maximum=s.maximum,
            input_cell_ids=s.input_cell_ids, unavailable_cell_ids=s.unavailable_cell_ids,
            observation_ids=observation_ids, evidence_binding_ids=_evidence_ids(observation_ids, evidence_by_observation),
            note=s.note,
        ))
    summaries = tuple(summaries)
    summary_by_id = {s.summary_id: s for s in summaries}

    positions = []
    for p in analysis.positions:
        target_cell = cell_by_id[p.target_cell_id]
        summary = summary_by_id[p.peer_summary_id]
        observation_ids = tuple(sorted(set(target_cell.observation_ids + summary.observation_ids)))
        positions.append(FinanceReportTargetPosition(
            position_id=p.position_id, metric_code=p.metric_code, analytical_status=p.status,
            relationship=p.relationship, target_cell_id=p.target_cell_id, peer_summary_id=p.peer_summary_id,
            observation_ids=observation_ids, evidence_binding_ids=_evidence_ids(observation_ids, evidence_by_observation),
            note=p.note,
        ))
    positions = tuple(positions)

    calculations = []
    for result in analysis.calculation_results:
        observation_ids = tuple(sorted({oid for fid in result.input_fact_ids for oid in fact_by_id[fid].observation_ids}))
        calculations.append(FinanceReportCalculation(
            result_id=result.result_id,
            company_id=result.company_id,
            company_name=company_by_id[result.company_id].display_name,
            metric_code=result.metric_code,
            analytical_status=result.status,
            calculation_classification=result.calculation_classification,
            calculation_code=result.calculation_code,
            calculation_version=result.calculation_version,
            formula=result.formula,
            input_fact_ids=result.input_fact_ids,
            observation_ids=observation_ids,
            evidence_binding_ids=_evidence_ids(observation_ids, evidence_by_observation),
            note=result.note,
        ))
    calculations = tuple(calculations)

    evidence = tuple(FinanceReportEvidenceRecord(
        evidence_binding_id=evidence_by_observation[o.observation_id].evidence_binding_id,
        observation_id=o.observation_id,
        company_id=o.company_id,
        company_name=company_by_id[o.company_id].display_name,
        provider=o.provider,
        source_id=o.source_id,
        source_version=o.source_version,
        publication_at=o.publication_at,
        source_channel=evidence_by_observation[o.observation_id].source_channel,
        binding_class=evidence_by_observation[o.observation_id].binding_class,
        document_snapshot_id=evidence_by_observation[o.observation_id].document_snapshot_id,
        page_number=evidence_by_observation[o.observation_id].page_number,
        bound_text_sha256=evidence_by_observation[o.observation_id].bound_text_sha256,
        note=evidence_by_observation[o.observation_id].note,
    ) for o in sorted(observation_by_id.values(), key=lambda x: x.observation_id))

    limitations = []
    for row in cells:
        if row.analytical_status is not AnalyticalStatus.ESTABLISHED:
            lt = FinanceReportLimitationType.ANALYTICAL_STATUS
            limitations.append(FinanceReportLimitation(_limitation_id(lt,row.cell_id,row.analytical_status.value,row.note),lt,row.cell_id,row.analytical_status.value,row.note))
    for row in summaries:
        if row.analytical_status is not AnalyticalStatus.ESTABLISHED:
            lt = FinanceReportLimitationType.ANALYTICAL_STATUS
            limitations.append(FinanceReportLimitation(_limitation_id(lt,row.summary_id,row.analytical_status.value,row.note),lt,row.summary_id,row.analytical_status.value,row.note))
    for row in positions:
        if row.analytical_status is not AnalyticalStatus.ESTABLISHED:
            lt = FinanceReportLimitationType.ANALYTICAL_STATUS
            limitations.append(FinanceReportLimitation(_limitation_id(lt,row.position_id,row.analytical_status.value,row.note),lt,row.position_id,row.analytical_status.value,row.note))
    for row in evidence:
        if row.binding_class is ObservationDocumentBindingClass.DOCUMENT_UNBOUND:
            lt = FinanceReportLimitationType.EVIDENCE_GAP
            limitations.append(FinanceReportLimitation(_limitation_id(lt,row.evidence_binding_id,row.binding_class.value,row.note),lt,row.evidence_binding_id,row.binding_class.value,row.note))
    if evidence_manifest.coverage in {FinanceDocumentEvidenceCoverage.MIXED_DOCUMENT_BINDING, FinanceDocumentEvidenceCoverage.DOCUMENT_UNBOUND}:
        lt = FinanceReportLimitationType.EVIDENCE_COVERAGE
        limitations.append(FinanceReportLimitation(
            _limitation_id(lt,evidence_manifest.document_evidence_manifest_id,evidence_manifest.coverage.value,None),
            lt,evidence_manifest.document_evidence_manifest_id,evidence_manifest.coverage.value,None,
        ))
    limitations = tuple(sorted(limitations, key=lambda x: (x.limitation_type.value, x.authority_id, x.limitation_id)))

    sections = (
        FinanceReportManifestSection("report_header", (analysis.analysis_id,)),
        FinanceReportManifestSection("analytical_lineage", (analysis.analysis_id, evidence_manifest.document_evidence_manifest_id)),
        FinanceReportManifestSection("comparable_set", tuple(x.member_id for x in members)),
        FinanceReportManifestSection("metric_matrix", tuple(x.cell_id for x in cells)),
        FinanceReportManifestSection("peer_statistics", tuple(x.summary_id for x in summaries)),
        FinanceReportManifestSection("target_peer_positions", tuple(x.position_id for x in positions)),
        FinanceReportManifestSection("calculation_lineage", tuple(x.result_id for x in calculations)),
        FinanceReportManifestSection("evidence_coverage", (evidence_manifest.document_evidence_manifest_id,)),
        FinanceReportManifestSection("evidence_register", tuple(x.evidence_binding_id for x in evidence)),
        FinanceReportManifestSection("limitations", tuple(x.limitation_id for x in limitations)),
    )

    status_counter = Counter(x.analytical_status.value for x in cells + summaries + positions + calculations)
    channel_counter = Counter(x.source_channel.value for x in evidence)
    binding_counter = Counter(x.binding_class.value for x in evidence)

    placeholder_manifest = FinanceReportManifest(
        schema_version=FINANCE_REPORT_MANIFEST_SCHEMA_VERSION,
        manifest_id="sha256:" + "0" * 64,
        report_projection_id="sha256:" + "0" * 64,
        projection_payload_sha256="0" * 64,
        ordered_section_ids=_SECTION_ORDER,
        sections=sections,
        ordered_member_ids=tuple(x.member_id for x in members),
        ordered_cell_ids=tuple(x.cell_id for x in cells),
        ordered_summary_ids=tuple(x.summary_id for x in summaries),
        ordered_position_ids=tuple(x.position_id for x in positions),
        ordered_calculation_ids=tuple(x.result_id for x in calculations),
        ordered_evidence_binding_ids=tuple(x.evidence_binding_id for x in evidence),
        ordered_limitation_ids=tuple(x.limitation_id for x in limitations),
        raw_status_inventory=tuple(sorted(status_counter.items())),
        source_channel_inventory=tuple(sorted(channel_counter.items())),
        binding_class_inventory=tuple(sorted(binding_counter.items())),
        evidence_coverage=evidence_manifest.coverage,
    )

    provisional = FinanceReportProjection(
        schema_version=FINANCE_REPORT_PROJECTION_SCHEMA_VERSION,
        projector_version=FINANCE_REPORT_PROJECTOR_VERSION,
        report_projection_id="sha256:" + "0" * 64,
        source_analysis_id=analysis.analysis_id,
        source_document_evidence_manifest_id=evidence_manifest.document_evidence_manifest_id,
        projection_payload_sha256="0" * 64,
        header=header, members=members, cells=cells, summaries=summaries, positions=positions,
        calculations=calculations, evidence=evidence, limitations=limitations, manifest=placeholder_manifest,
    )
    payload_sha = hashlib.sha256(canonical_json_bytes(projection_semantic_payload_to_dict(provisional))).hexdigest()
    projection_id = derive_finance_id({
        "schema_version": FINANCE_REPORT_PROJECTION_SCHEMA_VERSION,
        "projector_version": FINANCE_REPORT_PROJECTOR_VERSION,
        "source_analysis_id": analysis.analysis_id,
        "source_document_evidence_manifest_id": evidence_manifest.document_evidence_manifest_id,
        "projection_payload_sha256": payload_sha,
    })
    manifest_without_id = replace(placeholder_manifest, report_projection_id=projection_id, projection_payload_sha256=payload_sha)
    manifest = replace(manifest_without_id, manifest_id=derive_finance_id(finance_report_manifest_identity_payload_to_dict(manifest_without_id)))
    result = replace(provisional, report_projection_id=projection_id, projection_payload_sha256=payload_sha, manifest=manifest)

    from .validation import validate_finance_report_projection
    validate_finance_report_projection(result)
    return result

__all__ = ["build_finance_report_projection"]
