from dataclasses import replace
import pytest
from test_finance_evidence_models import analysis, MemoryBlobStore, extraction
from finance_evidence import *
from finance_evidence.serialization import manifest_identity_payload_to_dict
from finance_domain import derive_finance_id
import finance_evidence.capture as capture

def _full_entries(a, bound_first=None):
    entries=[]
    for i,o in enumerate(a.source_observations):
        if i==0 and bound_first is not None: entries.append(bound_first)
        else: entries.append(build_non_documentary_binding(observation=o,source_channel=ObservationSourceChannel.STRUCTURED_PROVIDER))
    return entries

def test_manifest_requires_exact_one_entry_per_f4_observation_and_not_applicable_coverage():
    a=analysis(); entries=_full_entries(a); m=build_finance_observation_evidence_manifest(analysis=a,documents=(),entries=entries)
    assert m.coverage is FinanceDocumentEvidenceCoverage.NOT_APPLICABLE and len(m.entries)==66
    with pytest.raises(ValueError): build_finance_observation_evidence_manifest(analysis=a,documents=(),entries=entries[:-1])

def test_coverage_full_mixed_and_unbound(monkeypatch,tmp_path):
    a=analysis(); obs=list(a.source_observations)
    # all non-documentary except explicit document items makes coverage depend only on document items
    u1=build_unbound_document_binding(observation=obs[0],note="gap")
    u2=build_unbound_document_binding(observation=obs[1],note="gap")
    entries=[u1,u2]+[build_non_documentary_binding(observation=o,source_channel=ObservationSourceChannel.STRUCTURED_PROVIDER) for o in obs[2:]]
    assert build_finance_observation_evidence_manifest(analysis=a,documents=(),entries=entries).coverage is FinanceDocumentEvidenceCoverage.DOCUMENT_UNBOUND


def _captured(monkeypatch,tmp_path,o,name,text):
    s=MemoryBlobStore(); p=tmp_path/name; p.write_bytes(("%PDF-"+name).encode()); monkeypatch.setattr(capture,"extract_pdf_pages",lambda b:extraction(text)); d=capture_finance_pdf_source(pdf_path=p,workspace_id=o.workspace_id,company_id=o.company_id,provider=o.provider,source_id=o.source_id,source_version=o.source_version,publication_at=o.publication_at,blob_store=s); page=s.read_blob(d.pages[0].page_text_sha256); return d,s,page

def test_coverage_fully_bound_and_mixed(monkeypatch,tmp_path):
    a=analysis(); obs=list(a.source_observations)
    d1,s1,p1=_captured(monkeypatch,tmp_path,obs[0],"one.pdf","one evidence")
    b1=build_document_text_binding(observation=obs[0],document=d1,page_number=1,page_byte_start=0,page_byte_end=3,blob_reader=s1)
    rest=[build_non_documentary_binding(observation=o,source_channel=ObservationSourceChannel.STRUCTURED_PROVIDER) for o in obs[1:]]
    full=build_finance_observation_evidence_manifest(analysis=a,documents=(d1,),entries=[b1]+rest)
    assert full.coverage is FinanceDocumentEvidenceCoverage.FULLY_DOCUMENT_BOUND
    u2=build_unbound_document_binding(observation=obs[1],note="source document unavailable")
    rest2=[build_non_documentary_binding(observation=o,source_channel=ObservationSourceChannel.STRUCTURED_PROVIDER) for o in obs[2:]]
    mixed=build_finance_observation_evidence_manifest(analysis=a,documents=(d1,),entries=[b1,u2]+rest2)
    assert mixed.coverage is FinanceDocumentEvidenceCoverage.MIXED_DOCUMENT_BINDING

def test_manifest_rejects_wrong_analysis_authority_and_extra_document(monkeypatch,tmp_path):
    a=analysis(); obs=list(a.source_observations); entries=[build_non_documentary_binding(observation=o,source_channel=ObservationSourceChannel.STRUCTURED_PROVIDER) for o in obs]
    m=build_finance_observation_evidence_manifest(analysis=a,documents=(),entries=entries)
    bad0=replace(m,source_analysis_id="sha256:"+"1"*64,document_evidence_manifest_id="sha256:"+"0"*64)
    bad=replace(bad0,document_evidence_manifest_id=derive_finance_id(manifest_identity_payload_to_dict(bad0)))
    with pytest.raises(ValueError,match="authority"):
        validate_finance_observation_evidence_manifest(bad,a)
    d,s,p=_captured(monkeypatch,tmp_path,obs[0],"unused.pdf","unused")
    with pytest.raises(ValueError,match="exactly the referenced"):
        build_finance_observation_evidence_manifest(analysis=a,documents=(d,),entries=entries)
