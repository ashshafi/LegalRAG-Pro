"""Fail-closed validation for Finance F5 document evidence."""
from __future__ import annotations
from datetime import datetime
from pathlib import PurePath
from finance_domain import FinancialObservation, validate_financial_observation
from finance_domain.identity import canonical_uuid, derive_finance_id, validate_sha256_id
from finance_comps import ComparableCompanyAnalysis, validate_comparable_company_analysis
from source_evidence.identity import validate_sha256_hex
from source_evidence.models import ExtractionMethod
from source_evidence.validation import validate_extraction_profile
from .models import *
from .serialization import document_identity_payload_to_dict, binding_identity_payload_to_dict, manifest_identity_payload_to_dict

def _text(v,field,optional=False):
    if v is None and optional:return
    if not isinstance(v,str) or not v or v!=v.strip(): raise ValueError(f"{field} must be non-empty trimmed text.")

def _utc(v,field):
    if not isinstance(v,datetime) or v.tzinfo is None or v.utcoffset() is None or v.utcoffset().total_seconds()!=0: raise ValueError(f"{field} must be UTC.")

def _nonneg(v,field):
    if type(v) is not int or v<0: raise ValueError(f"{field} must be a non-negative integer.")

def _positive(v,field):
    if type(v) is not int or v<=0: raise ValueError(f"{field} must be a positive integer.")

def validate_finance_source_document_manifest(v: FinanceSourceDocumentManifest)->None:
    if not isinstance(v,FinanceSourceDocumentManifest): raise ValueError("value must be FinanceSourceDocumentManifest.")
    if v.schema_version!=FINANCE_SOURCE_DOCUMENT_SCHEMA_VERSION: raise ValueError("Unsupported F5 document schema_version.")
    canonical_uuid(v.workspace_id,field_name="workspace_id"); canonical_uuid(v.company_id,field_name="company_id")
    for n in ("provider","source_id","source_version","original_filename"): _text(getattr(v,n),n)
    if PurePath(v.original_filename).name!=v.original_filename or v.original_filename in {".",".."}: raise ValueError("original_filename must be a plain filename.")
    if not v.original_filename.lower().endswith(".pdf"): raise ValueError("original_filename must use a .pdf filename.")
    if v.publication_at is not None:_utc(v.publication_at,"publication_at")
    if v.media_type!=PDF_MEDIA_TYPE: raise ValueError("F5 document media_type must be application/pdf.")
    validate_sha256_hex(v.original_blob_sha256,field_name="original_blob_sha256"); _positive(v.original_byte_length,"original_byte_length")
    if not v.pages: raise ValueError("F5 document must contain pages.")
    if tuple(p.page_number for p in v.pages)!=tuple(range(1,len(v.pages)+1)): raise ValueError("F5 pages must be exactly 1..N in order.")
    requires_ocr=any(p.extraction_method is ExtractionMethod.PAGE_OCR for p in v.pages)
    validate_extraction_profile(v.extraction_profile,requires_ocr=requires_ocr)
    for p in v.pages:
        _positive(p.page_number,"page_number")
        if not isinstance(p.extraction_method,ExtractionMethod): raise ValueError("extraction_method must be ExtractionMethod.")
        validate_sha256_hex(p.page_text_sha256,field_name="page_text_sha256"); _nonneg(p.page_text_byte_length,"page_text_byte_length")
    validate_sha256_id(v.document_snapshot_id,field_name="document_snapshot_id")
    if v.document_snapshot_id!=derive_finance_id(document_identity_payload_to_dict(v)): raise ValueError("document_snapshot_id does not match canonical identity payload.")

def validate_observation_evidence_binding(v:ObservationEvidenceBinding)->None:
    if not isinstance(v,ObservationEvidenceBinding): raise ValueError("value must be ObservationEvidenceBinding.")
    if v.schema_version!=OBSERVATION_EVIDENCE_BINDING_SCHEMA_VERSION: raise ValueError("Unsupported F5 binding schema_version.")
    canonical_uuid(v.workspace_id,field_name="workspace_id"); canonical_uuid(v.company_id,field_name="company_id"); validate_sha256_id(v.observation_id,field_name="observation_id")
    if not isinstance(v.source_channel,ObservationSourceChannel): raise ValueError("source_channel invalid.")
    if not isinstance(v.binding_class,ObservationDocumentBindingClass): raise ValueError("binding_class invalid.")
    _text(v.note,"note",optional=True)
    coords=(v.document_snapshot_id,v.page_number,v.page_byte_start,v.page_byte_end,v.bound_text_sha256)
    if v.binding_class is ObservationDocumentBindingClass.DOCUMENT_TEXT_BOUND:
        if v.source_channel is not ObservationSourceChannel.DOCUMENT: raise ValueError("DOCUMENT_TEXT_BOUND requires DOCUMENT channel.")
        if any(x is None for x in coords): raise ValueError("DOCUMENT_TEXT_BOUND requires full document/page/span coordinates.")
        validate_sha256_id(v.document_snapshot_id,field_name="document_snapshot_id"); _positive(v.page_number,"page_number"); _nonneg(v.page_byte_start,"page_byte_start"); _nonneg(v.page_byte_end,"page_byte_end")
        if v.page_byte_end<=v.page_byte_start: raise ValueError("page_byte_end must exceed page_byte_start.")
        validate_sha256_hex(v.bound_text_sha256,field_name="bound_text_sha256")
    elif v.binding_class is ObservationDocumentBindingClass.DOCUMENT_UNBOUND:
        if v.source_channel is not ObservationSourceChannel.DOCUMENT: raise ValueError("DOCUMENT_UNBOUND requires DOCUMENT channel.")
        if any(x is not None for x in coords): raise ValueError("DOCUMENT_UNBOUND must not carry document coordinates.")
        _text(v.note,"note")
    else:
        if v.source_channel not in {ObservationSourceChannel.STRUCTURED_PROVIDER,ObservationSourceChannel.MARKET}: raise ValueError("NOT_APPLICABLE requires non-documentary channel.")
        if any(x is not None for x in coords): raise ValueError("NOT_APPLICABLE must not carry document coordinates.")
    validate_sha256_id(v.evidence_binding_id,field_name="evidence_binding_id")
    if v.evidence_binding_id!=derive_finance_id(binding_identity_payload_to_dict(v)): raise ValueError("evidence_binding_id does not match canonical identity payload.")

def validate_document_observation_compatibility(*,observation:FinancialObservation,document:FinanceSourceDocumentManifest)->None:
    validate_financial_observation(observation); validate_finance_source_document_manifest(document)
    pairs=(("workspace_id",observation.workspace_id,document.workspace_id),("company_id",observation.company_id,document.company_id),("provider",observation.provider,document.provider),("source_id",observation.source_id,document.source_id),("source_version",observation.source_version,document.source_version),("publication_at",observation.publication_at,document.publication_at))
    for field,a,b in pairs:
        if a!=b: raise ValueError(f"F5 document {field} does not match FinancialObservation.")

def _expected_coverage(entries):
    docs=[e for e in entries if e.source_channel is ObservationSourceChannel.DOCUMENT]
    if not docs:return FinanceDocumentEvidenceCoverage.NOT_APPLICABLE
    bound=sum(e.binding_class is ObservationDocumentBindingClass.DOCUMENT_TEXT_BOUND for e in docs)
    if bound==len(docs):return FinanceDocumentEvidenceCoverage.FULLY_DOCUMENT_BOUND
    if bound==0:return FinanceDocumentEvidenceCoverage.DOCUMENT_UNBOUND
    return FinanceDocumentEvidenceCoverage.MIXED_DOCUMENT_BINDING

def validate_finance_observation_evidence_manifest_structure(v:FinanceObservationEvidenceManifest)->None:
    if not isinstance(v,FinanceObservationEvidenceManifest): raise ValueError("value must be FinanceObservationEvidenceManifest.")
    if v.schema_version!=FINANCE_OBSERVATION_EVIDENCE_MANIFEST_SCHEMA_VERSION or v.identity_version!=FINANCE_EVIDENCE_IDENTITY_VERSION: raise ValueError("Unsupported F5 manifest version.")
    canonical_uuid(v.workspace_id,field_name="workspace_id"); validate_sha256_id(v.source_analysis_id,field_name="source_analysis_id"); _utc(v.as_of,"as_of")
    for oid in v.observation_ids: validate_sha256_id(oid,field_name="observation_id")
    if len(set(v.observation_ids))!=len(v.observation_ids) or v.observation_ids!=tuple(sorted(v.observation_ids)): raise ValueError("manifest observation_ids must be unique canonical sorted order.")
    if tuple(d.document_snapshot_id for d in v.documents)!=tuple(sorted(d.document_snapshot_id for d in v.documents)) or len({d.document_snapshot_id for d in v.documents})!=len(v.documents): raise ValueError("documents must use unique canonical sorted order.")
    if tuple(e.observation_id for e in v.entries)!=tuple(sorted(e.observation_id for e in v.entries)) or len({e.observation_id for e in v.entries})!=len(v.entries): raise ValueError("entries must use unique canonical observation order.")
    for d in v.documents:
        validate_finance_source_document_manifest(d)
        if d.workspace_id!=v.workspace_id: raise ValueError("F5 document workspace does not match manifest.")
    for e in v.entries:
        validate_observation_evidence_binding(e)
        if e.workspace_id!=v.workspace_id: raise ValueError("F5 entry workspace does not match manifest.")
    if tuple(e.observation_id for e in v.entries)!=v.observation_ids: raise ValueError("manifest entries must cover exactly observation_ids.")
    doc_ids={d.document_snapshot_id for d in v.documents}
    if any(e.document_snapshot_id not in doc_ids for e in v.entries if e.binding_class is ObservationDocumentBindingClass.DOCUMENT_TEXT_BOUND): raise ValueError("bound entry references missing document.")
    doc_by_id={d.document_snapshot_id:d for d in v.documents}
    for e in v.entries:
        if e.binding_class is ObservationDocumentBindingClass.DOCUMENT_TEXT_BOUND:
            d=doc_by_id[e.document_snapshot_id]
            if (e.workspace_id,e.company_id)!=(d.workspace_id,d.company_id): raise ValueError("bound entry identity does not match referenced document.")
    referenced={e.document_snapshot_id for e in v.entries if e.document_snapshot_id is not None}
    if referenced!=doc_ids: raise ValueError("manifest documents must be exactly the referenced document set.")
    if v.coverage is not _expected_coverage(v.entries): raise ValueError("F5 coverage is not canonical for entries.")
    validate_sha256_id(v.document_evidence_manifest_id,field_name="document_evidence_manifest_id")
    if v.document_evidence_manifest_id!=derive_finance_id(manifest_identity_payload_to_dict(v)): raise ValueError("document_evidence_manifest_id does not match canonical identity payload.")

def validate_finance_observation_evidence_manifest(v:FinanceObservationEvidenceManifest,analysis:ComparableCompanyAnalysis)->None:
    validate_comparable_company_analysis(analysis); validate_finance_observation_evidence_manifest_structure(v)
    if (v.workspace_id,v.source_analysis_id,v.as_of)!=(analysis.workspace_id,analysis.analysis_id,analysis.as_of): raise ValueError("F5 manifest authority does not match F4 analysis.")
    expected=tuple(sorted(o.observation_id for o in analysis.source_observations))
    if v.observation_ids!=expected: raise ValueError("F5 manifest observation inventory does not exactly match F4.")
    obs={o.observation_id:o for o in analysis.source_observations}; docs={d.document_snapshot_id:d for d in v.documents}
    for e in v.entries:
        o=obs[e.observation_id]
        if (e.workspace_id,e.company_id)!=(o.workspace_id,o.company_id): raise ValueError("F5 entry identity does not match FinancialObservation.")
        if e.binding_class is ObservationDocumentBindingClass.DOCUMENT_TEXT_BOUND:
            validate_document_observation_compatibility(observation=o,document=docs[e.document_snapshot_id])
