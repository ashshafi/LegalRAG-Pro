from dataclasses import FrozenInstanceError, replace
from types import MappingProxyType
import pytest

from finance_workspace_index import (
    FINANCE_WORKSPACE_INDEX_VERSION,
    FinanceWorkspaceObjectKey,
    build_finance_workspace_index,
    literal_query_matches,
)
from test_finance_reporting_models import analysis, manifest_for, mixed_manifest_for, projection
from finance_reporting import build_finance_report_projection


def test_index_binds_exact_f7a_identity_and_manifest_order():
    p = projection()
    i = build_finance_workspace_index(p)
    assert i.version == FINANCE_WORKSPACE_INDEX_VERSION
    assert i.report_projection_id == p.report_projection_id
    assert i.projection_payload_sha256 == p.projection_payload_sha256
    assert i.manifest_id == p.manifest.manifest_id
    assert tuple(k.primary_id for k in i.member_keys) == p.manifest.ordered_member_ids
    assert tuple(k.primary_id for k in i.cell_keys) == p.manifest.ordered_cell_ids
    assert tuple(k.primary_id for k in i.summary_keys) == p.manifest.ordered_summary_ids
    assert tuple(k.primary_id for k in i.position_keys) == p.manifest.ordered_position_ids
    assert tuple(k.primary_id for k in i.calculation_keys) == p.manifest.ordered_calculation_ids
    assert tuple(k.primary_id for k in i.evidence_keys) == p.manifest.ordered_evidence_binding_ids
    assert tuple(k.primary_id for k in i.limitation_keys) == p.manifest.ordered_limitation_ids


def test_all_projection_objects_are_registered_once():
    p = projection()
    i = build_finance_workspace_index(p)
    assert len(i.members_by_id) == len(p.members)
    assert len(i.cells_by_id) == len(p.cells)
    assert len(i.summaries_by_id) == len(p.summaries)
    assert len(i.positions_by_id) == len(p.positions)
    assert len(i.calculations_by_id) == len(p.calculations)
    assert len(i.evidence_by_id) == len(p.evidence)
    assert len(i.limitations_by_id) == len(p.limitations)
    assert len(i.object_by_key) == sum(map(len, (p.members, p.cells, p.summaries, p.positions, p.calculations, p.evidence, p.limitations)))


def test_member_cell_and_calculation_links_are_exact_and_backlinked():
    p = projection()
    i = build_finance_workspace_index(p)
    cell_key = next(k for k in i.cell_keys if i.cells_by_id[k.primary_id].source_result_id is not None)
    cell = i.cells_by_id[cell_key.primary_id]
    member_key = next(k for k in i.member_keys if i.members_by_id[k.primary_id].company_id == cell.company_id)
    calc_key = FinanceWorkspaceObjectKey("calculation", cell.source_result_id)
    assert ("FinanceReportMetricCell.company_id", member_key) in i.outgoing[cell_key]
    assert ("FinanceReportMetricCell.source_result_id", calc_key) in i.outgoing[cell_key]
    assert any(b.source == cell_key and b.source_field == "FinanceReportMetricCell.company_id" for b in i.backlinks[member_key])
    assert any(b.source == cell_key and b.source_field == "FinanceReportMetricCell.source_result_id" for b in i.backlinks[calc_key])
    assert any(target == cell_key for field, target in i.outgoing[member_key] if field == "FinanceReportMember.company_id/FinanceReportMetricCell.company_id")


def test_summary_position_calculation_and_evidence_links_are_mechanical():
    p = projection()
    i = build_finance_workspace_index(p)
    s_key = i.summary_keys[0]
    s = i.summaries_by_id[s_key.primary_id]
    assert all(("FinanceReportPeerSummary.input_cell_ids", FinanceWorkspaceObjectKey("cell", cid)) in i.outgoing[s_key] for cid in s.input_cell_ids)
    assert all(("FinanceReportPeerSummary.evidence_binding_ids", FinanceWorkspaceObjectKey("evidence", eid)) in i.outgoing[s_key] for eid in s.evidence_binding_ids)

    pos_key = i.position_keys[0]
    pos = i.positions_by_id[pos_key.primary_id]
    assert ("FinanceReportTargetPosition.target_cell_id", FinanceWorkspaceObjectKey("cell", pos.target_cell_id)) in i.outgoing[pos_key]
    assert ("FinanceReportTargetPosition.peer_summary_id", FinanceWorkspaceObjectKey("summary", pos.peer_summary_id)) in i.outgoing[pos_key]

    calc_key = i.calculation_keys[0]
    calc = i.calculations_by_id[calc_key.primary_id]
    member_key = next(k for k in i.member_keys if i.members_by_id[k.primary_id].company_id == calc.company_id)
    assert ("FinanceReportCalculation.company_id", member_key) in i.outgoing[calc_key]


def test_grouping_indexes_preserve_existing_objects_without_new_math():
    p = projection()
    i = build_finance_workspace_index(p)
    for company_id, keys in i.cells_by_company.items():
        assert keys == tuple(k for k in i.cell_keys if i.cells_by_id[k.primary_id].company_id == company_id)
    for metric, keys in i.cells_by_metric.items():
        assert keys == tuple(k for k in i.cell_keys if i.cells_by_id[k.primary_id].metric_code == metric)
    for status, keys in i.cells_by_status.items():
        assert keys == tuple(k for k in i.cell_keys if i.cells_by_id[k.primary_id].analytical_status.value == status)
    assert len(i.evidence_by_observation) == len(p.evidence)


def test_mixed_evidence_groupings_and_limitations_are_preserved():
    a = analysis()
    p = build_finance_report_projection(analysis=a, evidence_manifest=mixed_manifest_for(a))
    i = build_finance_workspace_index(p)
    assert "DOCUMENT" in i.evidence_by_source_channel
    assert "STRUCTURED_PROVIDER" in i.evidence_by_source_channel
    assert "MARKET" in i.evidence_by_source_channel
    assert "DOCUMENT_TEXT_BOUND" in i.evidence_by_binding_class
    assert "DOCUMENT_UNBOUND" in i.evidence_by_binding_class
    assert "NOT_APPLICABLE" in i.evidence_by_binding_class
    assert p.source_document_evidence_manifest_id in i.limitations_by_authority
    coverage_limit_key = i.limitations_by_authority[p.source_document_evidence_manifest_id][0]
    assert i.outgoing[coverage_limit_key] == ()
    evidence_gap = next(x for x in p.limitations if x.authority_id in i.evidence_by_id)
    limitation_key = FinanceWorkspaceObjectKey("limitation", evidence_gap.limitation_id)
    assert ("FinanceReportLimitation.authority_id", FinanceWorkspaceObjectKey("evidence", evidence_gap.authority_id)) in i.outgoing[limitation_key]


def test_index_mappings_are_read_only_and_projection_is_not_mutated():
    p = projection()
    before = p
    i = build_finance_workspace_index(p)
    assert isinstance(i.object_by_key, MappingProxyType)
    assert isinstance(i.cells_by_company, MappingProxyType)
    with pytest.raises(TypeError):
        i.object_by_key[i.member_keys[0]] = object()
    with pytest.raises(FrozenInstanceError):
        i.version = "changed"
    assert p == before


def test_repeated_build_is_deterministic():
    p = projection()
    a = build_finance_workspace_index(p)
    b = build_finance_workspace_index(p)
    assert a == b


def test_invalid_projection_fails_before_indexing():
    p = projection()
    bad = replace(p, projection_payload_sha256="0" * 64)
    with pytest.raises(ValueError):
        build_finance_workspace_index(bad)


def test_literal_matching_is_empty_casefold_unicode_and_tuple_only():
    assert literal_query_matches("", ("Anything",))
    assert literal_query_matches("revenue", ("REVENUE_GROWTH",))
    assert literal_query_matches("café", ("cafe\u0301",))
    assert literal_query_matches("market", (("STRUCTURED_PROVIDER", "MARKET"),))
    assert not literal_query_matches("semantic alias", ("MARKET",))


def test_object_key_rejects_unknown_kind_and_empty_id():
    with pytest.raises(ValueError):
        FinanceWorkspaceObjectKey("issue", "x")
    with pytest.raises(ValueError):
        FinanceWorkspaceObjectKey("cell", "")
