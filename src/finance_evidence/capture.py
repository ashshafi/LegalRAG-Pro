"""Deterministic Finance F5 PDF capture over an explicit content-addressed blob store."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
from typing import Protocol
from finance_domain.identity import canonical_uuid, derive_finance_id
from source_evidence.identity import sha256_bytes
from source_evidence.extraction import extract_pdf_pages
from .models import FINANCE_SOURCE_DOCUMENT_SCHEMA_VERSION, PDF_MEDIA_TYPE, FinanceSourceDocumentManifest, FinanceSourcePageSnapshot
from .serialization import document_identity_payload_to_dict
from .validation import validate_finance_source_document_manifest

class BlobStore(Protocol):
    def put_blob(self, content: bytes) -> str: ...
    def read_blob(self, sha256_hex: str) -> bytes: ...

def _text(v,field):
    if not isinstance(v,str) or not v or v!=v.strip(): raise ValueError(f"{field} must be non-empty trimmed text.")

def capture_finance_pdf_source(*,pdf_path,workspace_id:str,company_id:str,provider:str,source_id:str,source_version:str,publication_at,blob_store:BlobStore,original_filename:str|None=None)->FinanceSourceDocumentManifest:
    canonical_uuid(workspace_id,field_name="workspace_id"); canonical_uuid(company_id,field_name="company_id")
    for n,v in (("provider",provider),("source_id",source_id),("source_version",source_version)):_text(v,n)
    path=Path(pdf_path)
    name=original_filename if original_filename is not None else path.name
    _text(name,"original_filename")
    if Path(name).name!=name: raise ValueError("original_filename must be a plain filename.")
    if not name.lower().endswith(".pdf"): raise ValueError("original_filename must use a .pdf filename.")
    if publication_at is not None and (not isinstance(publication_at,datetime) or publication_at.tzinfo is None or publication_at.utcoffset() is None or publication_at.utcoffset().total_seconds()!=0): raise ValueError("publication_at must be UTC when supplied.")
    content=path.read_bytes()
    if not content: raise ValueError("PDF source bytes must not be empty.")
    digest=sha256_bytes(content)
    if blob_store.put_blob(content)!=digest: raise ValueError("Blob store returned wrong digest for original PDF bytes.")
    extraction=extract_pdf_pages(content)
    pages=[]
    for item in extraction.pages:
        page_bytes=item.text.encode("utf-8")
        page_sha=sha256_bytes(page_bytes)
        if blob_store.put_blob(page_bytes)!=page_sha: raise ValueError("Blob store returned wrong digest for page text bytes.")
        pages.append(FinanceSourcePageSnapshot(page_number=item.page_number,extraction_method=item.extraction_method,page_text_sha256=page_sha,page_text_byte_length=len(page_bytes)))
    provisional=FinanceSourceDocumentManifest(schema_version=FINANCE_SOURCE_DOCUMENT_SCHEMA_VERSION,workspace_id=workspace_id,company_id=company_id,provider=provider,source_id=source_id,source_version=source_version,publication_at=publication_at,original_filename=name,media_type=PDF_MEDIA_TYPE,original_blob_sha256=digest,original_byte_length=len(content),extraction_profile=extraction.extraction_profile,pages=tuple(pages),document_snapshot_id="sha256:"+"0"*64)
    did=derive_finance_id(document_identity_payload_to_dict(provisional))
    result=FinanceSourceDocumentManifest(**{**{f:getattr(provisional,f) for f in provisional.__dataclass_fields__},"document_snapshot_id":did})
    validate_finance_source_document_manifest(result)
    return result
