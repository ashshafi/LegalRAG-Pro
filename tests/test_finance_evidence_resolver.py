from dataclasses import replace
import pytest
from test_finance_evidence_models import analysis, MemoryBlobStore, extraction
from finance_evidence import *
import finance_evidence.capture as capture

def _authority(monkeypatch,tmp_path):
    a=analysis(); o=a.source_observations[0]; s=MemoryBlobStore(); p=tmp_path/"f.pdf"; p.write_bytes(b"%PDF-original"); text="Revenue evidence exact"; monkeypatch.setattr(capture,"extract_pdf_pages",lambda b:extraction(text)); d=capture_finance_pdf_source(pdf_path=p,workspace_id=o.workspace_id,company_id=o.company_id,provider=o.provider,source_id=o.source_id,source_version=o.source_version,publication_at=o.publication_at,blob_store=s); pb=s.read_blob(d.pages[0].page_text_sha256); needle=b"evidence"; start=pb.index(needle); bound=build_document_text_binding(observation=o,document=d,page_number=1,page_byte_start=start,page_byte_end=start+len(needle),blob_reader=s); entries=[bound]+[build_non_documentary_binding(observation=x,source_channel=ObservationSourceChannel.STRUCTURED_PROVIDER) for x in a.source_observations if x.observation_id!=o.observation_id]; m=build_finance_observation_evidence_manifest(analysis=a,documents=(d,),entries=entries); return a,o,d,s,m

def test_resolver_returns_exact_span_page_and_original_bytes(monkeypatch,tmp_path):
    a,o,d,s,m=_authority(monkeypatch,tmp_path); r=resolve_finance_observation_evidence(analysis=a,manifest=m,observation_id=o.observation_id,blob_reader=s)
    assert r.exact_bound_text=="evidence" and r.exact_page_text=="Revenue evidence exact" and r.original_pdf_bytes==b"%PDF-original"

def test_resolver_fails_closed_on_missing_or_corrupt_blobs(monkeypatch,tmp_path):
    a,o,d,s,m=_authority(monkeypatch,tmp_path); del s.data[d.pages[0].page_text_sha256]
    with pytest.raises(FinanceEvidenceResolverError): resolve_finance_observation_evidence(analysis=a,manifest=m,observation_id=o.observation_id,blob_reader=s)
    a,o,d,s,m=_authority(monkeypatch,tmp_path); s.data[d.original_blob_sha256]=b"corrupt"
    with pytest.raises(FinanceEvidenceResolverError): resolve_finance_observation_evidence(analysis=a,manifest=m,observation_id=o.observation_id,blob_reader=s)

def test_resolver_has_no_fallback_for_unbound_document():
    a=analysis(); o=a.source_observations[0]; entries=[build_unbound_document_binding(observation=o,note="gap")]+[build_non_documentary_binding(observation=x,source_channel=ObservationSourceChannel.STRUCTURED_PROVIDER) for x in a.source_observations if x.observation_id!=o.observation_id]; m=build_finance_observation_evidence_manifest(analysis=a,documents=(),entries=entries)
    with pytest.raises(FinanceEvidenceResolverError,match="does not have"): resolve_finance_observation_evidence(analysis=a,manifest=m,observation_id=o.observation_id,blob_reader=MemoryBlobStore())
