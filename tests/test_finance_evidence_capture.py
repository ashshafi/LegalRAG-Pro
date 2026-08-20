from pathlib import Path
from datetime import timezone
from test_finance_evidence_models import analysis, MemoryBlobStore, extraction
from finance_evidence import capture_finance_pdf_source
import finance_evidence.capture as capture

def test_capture_reads_path_once_and_publishes_original_and_page(monkeypatch,tmp_path):
    a=analysis(); o=a.source_observations[0]; path=tmp_path/"filing.pdf"; path.write_bytes(b"%PDF-frozen-source"); store=MemoryBlobStore(); calls=[]
    monkeypatch.setattr(capture,"extract_pdf_pages",lambda b:(calls.append(b) or extraction("alpha revenue evidence")))
    d=capture_finance_pdf_source(pdf_path=path,workspace_id=o.workspace_id,company_id=o.company_id,provider=o.provider,source_id=o.source_id,source_version=o.source_version,publication_at=o.publication_at,blob_store=store)
    assert calls==[b"%PDF-frozen-source"]
    assert store.read_blob(d.original_blob_sha256)==b"%PDF-frozen-source"
    assert store.read_blob(d.pages[0].page_text_sha256)==b"alpha revenue evidence"

def test_capture_repeated_identical_source_has_same_document_identity(monkeypatch,tmp_path):
    a=analysis(); o=a.source_observations[0]; path=tmp_path/"filing.pdf"; path.write_bytes(b"%PDF-same"); monkeypatch.setattr(capture,"extract_pdf_pages",lambda b:extraction())
    ids=[]
    for _ in range(2):
        ids.append(capture_finance_pdf_source(pdf_path=path,workspace_id=o.workspace_id,company_id=o.company_id,provider=o.provider,source_id=o.source_id,source_version=o.source_version,publication_at=o.publication_at,blob_store=MemoryBlobStore()).document_snapshot_id)
    assert ids[0]==ids[1]


def test_capture_rejects_bad_metadata_before_blob_publication(monkeypatch,tmp_path):
    from datetime import timedelta
    a=analysis(); o=a.source_observations[0]; path=tmp_path/"filing.pdf"; path.write_bytes(b"%PDF-x"); store=MemoryBlobStore(); monkeypatch.setattr(capture,"extract_pdf_pages",lambda b:extraction())
    bad_time=o.observed_at.astimezone(timezone(timedelta(hours=1)))
    import pytest
    with pytest.raises(ValueError,match="UTC"):
        capture_finance_pdf_source(pdf_path=path,workspace_id=o.workspace_id,company_id=o.company_id,provider=o.provider,source_id=o.source_id,source_version=o.source_version,publication_at=bad_time,blob_store=store)
    assert store.data=={}
    with pytest.raises(ValueError,match=".pdf"):
        capture_finance_pdf_source(pdf_path=path,workspace_id=o.workspace_id,company_id=o.company_id,provider=o.provider,source_id=o.source_id,source_version=o.source_version,publication_at=o.publication_at,blob_store=store,original_filename="filing.txt")
    assert store.data=={}
