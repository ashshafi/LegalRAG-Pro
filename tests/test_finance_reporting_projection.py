from datetime import datetime, timezone
from dataclasses import replace
import pytest
from finance_calculations import AnalyticalStatus
from finance_evidence import FinanceDocumentEvidenceCoverage, ObservationDocumentBindingClass, ObservationSourceChannel
from finance_reporting import build_finance_report_projection
from test_finance_reporting_models import analysis, manifest_for, mixed_manifest_for

def test_projection_preserves_exact_member_cell_and_formula_authority():
    a=analysis(); m=manifest_for(a); p=build_finance_report_projection(analysis=a,evidence_manifest=m)
    assert tuple(x.member_id for x in p.members)==tuple(x.member_id for x in a.definition.members)
    assert tuple(x.cell_id for x in p.cells)==tuple(x.cell_id for x in a.cells)
    assert tuple(x.result_id for x in p.calculations)==tuple(x.result_id for x in a.calculation_results)
    assert tuple(x.formula for x in p.calculations)==tuple(x.formula for x in a.calculation_results)

def test_projection_derives_evidence_ids_only_from_observation_lineage():
    a=analysis(); m=manifest_for(a); p=build_finance_report_projection(analysis=a,evidence_manifest=m)
    e={x.observation_id:x.evidence_binding_id for x in p.evidence}
    for c in p.cells:
        assert c.evidence_binding_ids==tuple(e[o] for o in c.observation_ids)
    for s in p.summaries:
        assert s.evidence_binding_ids==tuple(e[o] for o in s.observation_ids)

def test_projection_preserves_all_f5_source_states_and_creates_evidence_gap_limitations():
    a=analysis(); m=mixed_manifest_for(a); p=build_finance_report_projection(analysis=a,evidence_manifest=m)
    pairs={(x.source_channel,x.binding_class) for x in p.evidence}
    from finance_evidence import ObservationDocumentBindingClass as B, ObservationSourceChannel as C
    assert (C.DOCUMENT,B.DOCUMENT_TEXT_BOUND) in pairs
    assert (C.DOCUMENT,B.DOCUMENT_UNBOUND) in pairs
    assert (C.MARKET,B.NOT_APPLICABLE) in pairs
    assert (C.STRUCTURED_PROVIDER,B.NOT_APPLICABLE) in pairs
    assert p.manifest.evidence_coverage is FinanceDocumentEvidenceCoverage.MIXED_DOCUMENT_BINDING
    assert any(x.raw_status==B.DOCUMENT_UNBOUND.value for x in p.limitations)

def test_early_asof_preserves_non_established_statuses_as_limitations():
    early=datetime(2026,3,2,16,29,59,tzinfo=timezone.utc)
    a=analysis(as_of=early); p=build_finance_report_projection(analysis=a,evidence_manifest=manifest_for(a))
    statuses={x.analytical_status for x in p.cells}
    assert AnalyticalStatus.INSUFFICIENT_DATA in statuses
    assert any(x.raw_status==AnalyticalStatus.INSUFFICIENT_DATA.value for x in p.limitations)

def test_projection_is_deterministic_for_same_frozen_authority():
    a=analysis(); m=manifest_for(a)
    p1=build_finance_report_projection(analysis=a,evidence_manifest=m); p2=build_finance_report_projection(analysis=a,evidence_manifest=m)
    assert p1==p2 and p1.report_projection_id==p2.report_projection_id and p1.projection_payload_sha256==p2.projection_payload_sha256

def test_wrong_f5_binding_fails_closed_before_projection():
    a=analysis(); m=manifest_for(a); bad=replace(m,source_analysis_id="sha256:"+"1"*64)
    with pytest.raises(ValueError): build_finance_report_projection(analysis=a,evidence_manifest=bad)
