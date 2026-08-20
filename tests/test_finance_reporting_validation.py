from dataclasses import replace
import pytest
from finance_reporting import validate_finance_report_projection
from test_finance_reporting_models import projection

def test_manifest_inventory_tamper_fails_closed():
    p=projection(); badm=replace(p.manifest,ordered_cell_ids=p.manifest.ordered_cell_ids[:-1]); bad=replace(p,manifest=badm)
    with pytest.raises(ValueError,match="inventory|manifest"): validate_finance_report_projection(bad)

def test_payload_hash_tamper_fails_closed():
    p=projection(); bad=replace(p,projection_payload_sha256="1"*64)
    with pytest.raises(ValueError): validate_finance_report_projection(bad)

def test_evidence_link_tamper_fails_closed():
    p=projection(); c=p.cells[0]; other=p.evidence[-1].evidence_binding_id
    badc=replace(c,evidence_binding_ids=(other,)+c.evidence_binding_ids[1:]); bad=replace(p,cells=(badc,)+p.cells[1:])
    with pytest.raises(ValueError): validate_finance_report_projection(bad)

def test_raw_status_inventory_tamper_fails_closed():
    p=projection(); badm=replace(p.manifest,raw_status_inventory=(("ESTABLISHED",1),)); bad=replace(p,manifest=badm)
    with pytest.raises(ValueError): validate_finance_report_projection(bad)
