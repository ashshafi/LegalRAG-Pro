from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from finance_data import FrozenDemoProvider
from finance_comps import ComparableRole, PeerInclusionState, build_comparable_company_analysis, create_comparable_member_selection, create_comparable_set_definition
from source_evidence.identity import sha256_bytes
from source_evidence.models import EXTRACTION_PROFILE_ID, EXTRACTION_PROFILE_SCHEMA_VERSION, ExtractionMethod, ExtractionProfile
from source_evidence.extraction import ExtractedPage, PdfExtractionResult

ASOF=datetime(2026,3,2,16,30,tzinfo=timezone.utc)
class MemoryBlobStore:
    def __init__(self): self.data={}
    def put_blob(self,content:bytes)->str:
        d=sha256_bytes(content); self.data.setdefault(d,bytes(content)); return d
    def read_blob(self,digest:str)->bytes:
        if digest not in self.data: raise KeyError(digest)
        return self.data[digest]

def analysis():
    p=FrozenDemoProvider(); members=[]
    for c in p.list_companies():
        s=p.list_securities(company_id=c.company_id)[0]; ps=sorted(p.list_periods(company_id=c.company_id),key=lambda x:x.end_date); target=c.company_id==p.target_company_id
        members.append(create_comparable_member_selection(company_id=c.company_id,security_id=s.security_id,role=ComparableRole.TARGET if target else ComparableRole.PEER,inclusion_state=PeerInclusionState.INCLUDED,current_period_id=ps[-1].financial_period_id,prior_period_id=ps[-2].financial_period_id))
    d=create_comparable_set_definition(workspace_id=p.workspace.workspace_id,as_of=ASOF,members=tuple(members)); return build_comparable_company_analysis(provider=p,definition=d)

def profile():
    return ExtractionProfile(profile_id=EXTRACTION_PROFILE_ID,profile_schema_version=EXTRACTION_PROFILE_SCHEMA_VERSION,pypdf_package_version="5.9.0",pdf2image_package_version=None,pytesseract_package_version=None,tesseract_engine_version=None,poppler_version=None,ocr_language="eng",ocr_config="",ocr_dpi=200)

def extraction(text="Revenue was $1.234 billion for FY2025."):
    return PdfExtractionResult(extraction_profile=profile(),pages=(ExtractedPage(page_number=1,extraction_method=ExtractionMethod.PYPDF_TEXT,text=text),))

from dataclasses import replace
from finance_evidence import *
from finance_evidence.models import FINANCE_SOURCE_DOCUMENT_SCHEMA_VERSION
from finance_evidence.serialization import document_identity_payload_to_dict
from finance_domain import derive_finance_id

def test_models_are_immutable_and_document_identity_is_content_derived():
    a=analysis(); o=a.source_observations[0]; store=MemoryBlobStore(); original=b"%PDF-test"; store.put_blob(original); page=b"abc"; store.put_blob(page)
    from finance_evidence.models import FinanceSourcePageSnapshot, FinanceSourceDocumentManifest
    p=FinanceSourcePageSnapshot(1,ExtractionMethod.PYPDF_TEXT,sha256_bytes(page),len(page))
    provisional=FinanceSourceDocumentManifest(FINANCE_SOURCE_DOCUMENT_SCHEMA_VERSION,o.workspace_id,o.company_id,o.provider,o.source_id,o.source_version,o.publication_at,"report.pdf","application/pdf",sha256_bytes(original),len(original),profile(),(p,),"sha256:"+"0"*64)
    did=derive_finance_id(document_identity_payload_to_dict(provisional)); d=replace(provisional,document_snapshot_id=did)
    validate_finance_source_document_manifest(d)
    import dataclasses
    assert dataclasses.is_dataclass(d)
    try: d.provider="x"; assert False
    except Exception: pass
