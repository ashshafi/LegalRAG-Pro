from dataclasses import replace
import pytest
from test_finance_evidence_models import analysis, MemoryBlobStore, extraction
from finance_evidence import *
from source_evidence.identity import sha256_bytes
from finance_evidence.serialization import document_identity_payload_to_dict
from finance_domain import derive_finance_id
import finance_evidence.capture as capture

def _doc(monkeypatch,tmp_path,o,text="prefix Ω revenue suffix"):
    store=MemoryBlobStore(); p=tmp_path/"f.pdf"; p.write_bytes(b"%PDF-doc"); monkeypatch.setattr(capture,"extract_pdf_pages",lambda b:extraction(text)); d=capture_finance_pdf_source(pdf_path=p,workspace_id=o.workspace_id,company_id=o.company_id,provider=o.provider,source_id=o.source_id,source_version=o.source_version,publication_at=o.publication_at,blob_store=store); return d,store

def test_document_binding_uses_explicit_exact_utf8_byte_coordinates(monkeypatch,tmp_path):
    a=analysis(); o=a.source_observations[0]; d,s=_doc(monkeypatch,tmp_path,o); page=s.read_blob(d.pages[0].page_text_sha256); needle="Ω revenue".encode(); start=page.index(needle); b=build_document_text_binding(observation=o,document=d,page_number=1,page_byte_start=start,page_byte_end=start+len(needle),blob_reader=s)
    assert b.source_channel is ObservationSourceChannel.DOCUMENT and b.binding_class is ObservationDocumentBindingClass.DOCUMENT_TEXT_BOUND
    assert b.bound_text_sha256==sha256_bytes(needle)
    assert b==build_document_text_binding(observation=o,document=d,page_number=1,page_byte_start=start,page_byte_end=start+len(needle),blob_reader=s)

def test_binding_rejects_non_utf8_boundary_and_source_mismatch(monkeypatch,tmp_path):
    a=analysis(); o=a.source_observations[0]; d,s=_doc(monkeypatch,tmp_path,o); page=s.read_blob(d.pages[0].page_text_sha256); omega="Ω".encode(); start=page.index(omega)
    with pytest.raises(ValueError,match="UTF-8"): build_document_text_binding(observation=o,document=d,page_number=1,page_byte_start=start+1,page_byte_end=start+2,blob_reader=s)
    bad0=replace(d,source_version="wrong",document_snapshot_id="sha256:"+"0"*64)
    bad=replace(bad0,document_snapshot_id=derive_finance_id(document_identity_payload_to_dict(bad0)))
    with pytest.raises(ValueError,match="source_version"): build_document_text_binding(observation=o,document=bad,page_number=1,page_byte_start=0,page_byte_end=1,blob_reader=s)

def test_unbound_and_non_documentary_are_explicit_not_inferred():
    o=analysis().source_observations[0]
    u=build_unbound_document_binding(observation=o,note="filing not archived")
    assert u.binding_class is ObservationDocumentBindingClass.DOCUMENT_UNBOUND
    for channel in (ObservationSourceChannel.STRUCTURED_PROVIDER,ObservationSourceChannel.MARKET):
        n=build_non_documentary_binding(observation=o,source_channel=channel); assert n.binding_class is ObservationDocumentBindingClass.NOT_APPLICABLE
    with pytest.raises(ValueError): build_non_documentary_binding(observation=o,source_channel=ObservationSourceChannel.DOCUMENT)


def test_document_binding_fails_on_missing_page_invalid_range_or_corrupt_page(monkeypatch,tmp_path):
    a=analysis(); o=a.source_observations[0]; d,s=_doc(monkeypatch,tmp_path,o,text="abc")
    with pytest.raises(ValueError,match="page_number"): build_document_text_binding(observation=o,document=d,page_number=2,page_byte_start=0,page_byte_end=1,blob_reader=s)
    with pytest.raises(ValueError,match="interval"): build_document_text_binding(observation=o,document=d,page_number=1,page_byte_start=0,page_byte_end=99,blob_reader=s)
    s.data[d.pages[0].page_text_sha256]=b"corrupt"
    with pytest.raises(ValueError,match="stored page bytes"): build_document_text_binding(observation=o,document=d,page_number=1,page_byte_start=0,page_byte_end=1,blob_reader=s)
