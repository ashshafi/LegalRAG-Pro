import json, pytest
from test_finance_evidence_models import analysis
from finance_evidence import *

def _manifest():
    a=analysis(); entries=[build_non_documentary_binding(observation=o,source_channel=ObservationSourceChannel.STRUCTURED_PROVIDER) for o in a.source_observations]; return a,build_finance_observation_evidence_manifest(analysis=a,documents=(),entries=entries)

def test_canonical_round_trip_and_deterministic_manifest_identity():
    a,m=_manifest(); payload=dumps_finance_observation_evidence_manifest(m); loaded=loads_finance_observation_evidence_manifest(payload); assert loaded==m; validate_finance_observation_evidence_manifest(loaded,a)
    m2=build_finance_observation_evidence_manifest(analysis=a,documents=(),entries=reversed(m.entries)); assert m2.document_evidence_manifest_id==m.document_evidence_manifest_id

def test_duplicate_extra_and_non_utc_json_are_rejected():
    _,m=_manifest(); p=dumps_finance_observation_evidence_manifest(m)
    dup=p.replace('{','{"schema_version":"duplicate",',1)
    with pytest.raises(ValueError,match="Duplicate"): loads_finance_observation_evidence_manifest(dup)
    d=json.loads(p); d["extra"]=1
    with pytest.raises(ValueError): loads_finance_observation_evidence_manifest(json.dumps(d,separators=(",",":"),sort_keys=True)+"\n")
    d=json.loads(p); d["as_of"]=d["as_of"].replace("Z","+01:00")
    with pytest.raises(ValueError): loads_finance_observation_evidence_manifest(json.dumps(d,separators=(",",":"),sort_keys=True)+"\n")


def test_document_bound_nested_manifest_round_trip(monkeypatch,tmp_path):
    from test_finance_evidence_models import MemoryBlobStore, extraction
    import finance_evidence.capture as capture
    a=analysis(); o=a.source_observations[0]; store=MemoryBlobStore(); path=tmp_path/"report.pdf"; path.write_bytes(b"%PDF-nested"); monkeypatch.setattr(capture,"extract_pdf_pages",lambda b:extraction("exact evidence")); d=capture_finance_pdf_source(pdf_path=path,workspace_id=o.workspace_id,company_id=o.company_id,provider=o.provider,source_id=o.source_id,source_version=o.source_version,publication_at=o.publication_at,blob_store=store); page=store.read_blob(d.pages[0].page_text_sha256); b=build_document_text_binding(observation=o,document=d,page_number=1,page_byte_start=0,page_byte_end=5,blob_reader=store); entries=[b]+[build_non_documentary_binding(observation=x,source_channel=ObservationSourceChannel.STRUCTURED_PROVIDER) for x in a.source_observations if x.observation_id!=o.observation_id]; m=build_finance_observation_evidence_manifest(analysis=a,documents=(d,),entries=entries); payload=dumps_finance_observation_evidence_manifest(m); loaded=loads_finance_observation_evidence_manifest(payload); assert loaded==m; validate_finance_observation_evidence_manifest(loaded,a)
