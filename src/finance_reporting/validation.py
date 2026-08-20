"""Fail-closed validation for Finance F7A report projections."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import datetime
import hashlib

from finance_calculations import AnalyticalStatus
from finance_domain import derive_finance_id
from finance_domain.identity import canonical_json_bytes, validate_sha256_id
from finance_evidence import FinanceDocumentEvidenceCoverage, ObservationDocumentBindingClass, ObservationSourceChannel

from .models import *
from .serialization import finance_report_manifest_identity_payload_to_dict, projection_semantic_payload_to_dict

_SECTION_ORDER = (
    "report_header", "analytical_lineage", "comparable_set", "metric_matrix",
    "peer_statistics", "target_peer_positions", "calculation_lineage",
    "evidence_coverage", "evidence_register", "limitations",
)

def _utc(value: datetime, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field} must be UTC-aware.")

def _unique(values, field):
    if len(values) != len(set(values)):
        raise ValueError(f"{field} must be unique.")

def _known_status(value):
    if not isinstance(value, AnalyticalStatus):
        raise ValueError("analytical_status invalid.")

def _check_evidence_links(observation_ids, evidence_binding_ids, evidence_by_obs):
    expected = tuple(evidence_by_obs[x] for x in observation_ids)
    if evidence_binding_ids != expected:
        raise ValueError("evidence binding lineage does not match observation lineage.")

def validate_finance_report_projection(value: FinanceReportProjection) -> None:
    if not isinstance(value, FinanceReportProjection):
        raise ValueError("value must be FinanceReportProjection.")
    if value.schema_version != FINANCE_REPORT_PROJECTION_SCHEMA_VERSION or value.projector_version != FINANCE_REPORT_PROJECTOR_VERSION:
        raise ValueError("Unsupported F7A projection version.")
    validate_sha256_id(value.report_projection_id, field_name="report_projection_id")
    validate_sha256_id(value.source_analysis_id, field_name="source_analysis_id")
    validate_sha256_id(value.source_document_evidence_manifest_id, field_name="source_document_evidence_manifest_id")
    if len(value.projection_payload_sha256) != 64 or any(c not in "0123456789abcdef" for c in value.projection_payload_sha256):
        raise ValueError("projection_payload_sha256 invalid.")
    if value.header.analysis_id != value.source_analysis_id or value.header.document_evidence_manifest_id != value.source_document_evidence_manifest_id:
        raise ValueError("F7A header/source authority mismatch.")
    _utc(value.header.as_of, "header.as_of")

    ids = {
        "member": tuple(x.member_id for x in value.members),
        "cell": tuple(x.cell_id for x in value.cells),
        "summary": tuple(x.summary_id for x in value.summaries),
        "position": tuple(x.position_id for x in value.positions),
        "calculation": tuple(x.result_id for x in value.calculations),
        "evidence": tuple(x.evidence_binding_id for x in value.evidence),
        "limitation": tuple(x.limitation_id for x in value.limitations),
    }
    for label, vals in ids.items():
        _unique(vals, label + " ids")

    member_by_company = {x.company_id: x for x in value.members}
    cell_by_id = {x.cell_id: x for x in value.cells}
    summary_by_id = {x.summary_id: x for x in value.summaries}
    calc_by_id = {x.result_id: x for x in value.calculations}
    evidence_by_obs = {x.observation_id: x.evidence_binding_id for x in value.evidence}
    if len(evidence_by_obs) != len(value.evidence):
        raise ValueError("F7A evidence observations must be unique.")

    for x in value.members:
        validate_sha256_id(x.member_id, field_name="member_id")
        if x.company_id not in member_by_company:
            raise ValueError("member company invalid.")
        if not x.company_name or not x.current_period_label or not x.prior_period_label:
            raise ValueError("member display metadata missing.")

    for x in value.cells:
        validate_sha256_id(x.cell_id, field_name="cell_id"); _known_status(x.analytical_status)
        if x.company_id not in member_by_company:
            raise ValueError("cell company not in comparable set.")
        _unique(x.observation_ids, "cell observation_ids")
        _check_evidence_links(x.observation_ids, x.evidence_binding_ids, evidence_by_obs)
        if x.source_result_id is not None and x.source_result_id not in calc_by_id:
            raise ValueError("cell source_result_id not found in calculations.")
        if x.analytical_status is AnalyticalStatus.ESTABLISHED and x.value is None:
            raise ValueError("ESTABLISHED cell requires value.")

    for x in value.summaries:
        validate_sha256_id(x.summary_id, field_name="summary_id"); _known_status(x.analytical_status)
        for cid in x.input_cell_ids + x.unavailable_cell_ids:
            if cid not in cell_by_id:
                raise ValueError("summary references unknown cell.")
        expected_obs = tuple(sorted({oid for cid in x.input_cell_ids + x.unavailable_cell_ids for oid in cell_by_id[cid].observation_ids}))
        if x.observation_ids != expected_obs:
            raise ValueError("summary observation lineage mismatch.")
        _check_evidence_links(x.observation_ids, x.evidence_binding_ids, evidence_by_obs)

    for x in value.positions:
        validate_sha256_id(x.position_id, field_name="position_id"); _known_status(x.analytical_status)
        if x.target_cell_id not in cell_by_id or x.peer_summary_id not in summary_by_id:
            raise ValueError("position dependency unknown.")
        expected_obs = tuple(sorted(set(cell_by_id[x.target_cell_id].observation_ids + summary_by_id[x.peer_summary_id].observation_ids)))
        if x.observation_ids != expected_obs:
            raise ValueError("position observation lineage mismatch.")
        _check_evidence_links(x.observation_ids, x.evidence_binding_ids, evidence_by_obs)

    for x in value.calculations:
        validate_sha256_id(x.result_id, field_name="result_id"); _known_status(x.analytical_status)
        if x.company_id not in member_by_company:
            raise ValueError("calculation company not in comparable set.")
        _check_evidence_links(x.observation_ids, x.evidence_binding_ids, evidence_by_obs)
        if not x.formula or not x.calculation_code or not x.calculation_version:
            raise ValueError("calculation lineage metadata missing.")

    for x in value.evidence:
        validate_sha256_id(x.evidence_binding_id, field_name="evidence_binding_id")
        validate_sha256_id(x.observation_id, field_name="observation_id")
        if x.company_id not in member_by_company:
            raise ValueError("evidence company not in comparable set.")
        if not isinstance(x.source_channel, ObservationSourceChannel) or not isinstance(x.binding_class, ObservationDocumentBindingClass):
            raise ValueError("evidence source classification invalid.")
        if x.binding_class is ObservationDocumentBindingClass.DOCUMENT_TEXT_BOUND:
            if x.source_channel is not ObservationSourceChannel.DOCUMENT or x.document_snapshot_id is None or x.page_number is None or x.bound_text_sha256 is None:
                raise ValueError("document-text-bound evidence coordinates incomplete.")
        elif x.binding_class is ObservationDocumentBindingClass.DOCUMENT_UNBOUND:
            if x.source_channel is not ObservationSourceChannel.DOCUMENT or not x.note:
                raise ValueError("document-unbound evidence requires explicit note.")
        elif x.source_channel is ObservationSourceChannel.DOCUMENT:
            raise ValueError("DOCUMENT evidence cannot be NOT_APPLICABLE.")

    authority_ids = set(ids["cell"] + ids["summary"] + ids["position"] + ids["evidence"] + (value.source_document_evidence_manifest_id,))
    for x in value.limitations:
        validate_sha256_id(x.limitation_id, field_name="limitation_id")
        if x.authority_id not in authority_ids:
            raise ValueError("limitation authority_id unknown.")
        expected = derive_finance_id({
            "schema": "finance-report-limitation/1.0", "limitation_type": x.limitation_type.value,
            "authority_id": x.authority_id, "raw_status": x.raw_status, "note": x.note,
        })
        if x.limitation_id != expected:
            raise ValueError("limitation_id mismatch.")

    expected_status = Counter(x.analytical_status.value for x in value.cells + value.summaries + value.positions + value.calculations)
    expected_channels = Counter(x.source_channel.value for x in value.evidence)
    expected_bindings = Counter(x.binding_class.value for x in value.evidence)

    manifest = value.manifest
    if manifest.schema_version != FINANCE_REPORT_MANIFEST_SCHEMA_VERSION:
        raise ValueError("Unsupported F7A manifest version.")
    validate_sha256_id(manifest.manifest_id, field_name="manifest_id")
    if manifest.report_projection_id != value.report_projection_id or manifest.projection_payload_sha256 != value.projection_payload_sha256:
        raise ValueError("manifest projection binding mismatch.")
    if manifest.ordered_section_ids != _SECTION_ORDER or tuple(x.section_id for x in manifest.sections) != _SECTION_ORDER:
        raise ValueError("manifest section order mismatch.")
    expected_sections = (
        ("report_header", (value.source_analysis_id,)),
        ("analytical_lineage", (value.source_analysis_id, value.source_document_evidence_manifest_id)),
        ("comparable_set", ids["member"]), ("metric_matrix", ids["cell"]),
        ("peer_statistics", ids["summary"]), ("target_peer_positions", ids["position"]),
        ("calculation_lineage", ids["calculation"]),
        ("evidence_coverage", (value.source_document_evidence_manifest_id,)),
        ("evidence_register", ids["evidence"]), ("limitations", ids["limitation"]),
    )
    if tuple((x.section_id, x.ordered_object_ids) for x in manifest.sections) != expected_sections:
        raise ValueError("manifest section inventory mismatch.")
    for field, expected in (
        (manifest.ordered_member_ids, ids["member"]), (manifest.ordered_cell_ids, ids["cell"]),
        (manifest.ordered_summary_ids, ids["summary"]), (manifest.ordered_position_ids, ids["position"]),
        (manifest.ordered_calculation_ids, ids["calculation"]), (manifest.ordered_evidence_binding_ids, ids["evidence"]),
        (manifest.ordered_limitation_ids, ids["limitation"]),
    ):
        if field != expected:
            raise ValueError("manifest ordered inventory mismatch.")
    if manifest.raw_status_inventory != tuple(sorted(expected_status.items())):
        raise ValueError("manifest raw-status inventory mismatch.")
    if manifest.source_channel_inventory != tuple(sorted(expected_channels.items())):
        raise ValueError("manifest source-channel inventory mismatch.")
    if manifest.binding_class_inventory != tuple(sorted(expected_bindings.items())):
        raise ValueError("manifest binding-class inventory mismatch.")
    if not isinstance(manifest.evidence_coverage, FinanceDocumentEvidenceCoverage):
        raise ValueError("manifest evidence coverage invalid.")

    semantic_sha = hashlib.sha256(canonical_json_bytes(projection_semantic_payload_to_dict(value))).hexdigest()
    if value.projection_payload_sha256 != semantic_sha:
        raise ValueError("projection_payload_sha256 mismatch.")
    expected_projection_id = derive_finance_id({
        "schema_version": value.schema_version, "projector_version": value.projector_version,
        "source_analysis_id": value.source_analysis_id,
        "source_document_evidence_manifest_id": value.source_document_evidence_manifest_id,
        "projection_payload_sha256": value.projection_payload_sha256,
    })
    if value.report_projection_id != expected_projection_id:
        raise ValueError("report_projection_id mismatch.")
    expected_manifest_id = derive_finance_id(finance_report_manifest_identity_payload_to_dict(replace(manifest, manifest_id="sha256:" + "0" * 64)))
    # identity helper payload excludes manifest_id; replace is used only to emphasize that generated ID is not input
    if manifest.manifest_id != expected_manifest_id:
        raise ValueError("manifest_id mismatch.")

__all__ = ["validate_finance_report_projection"]
