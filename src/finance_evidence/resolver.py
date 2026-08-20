"""No-fallback read-only resolver for Finance F5 document evidence."""
from __future__ import annotations
from typing import Protocol
from finance_domain.identity import validate_sha256_id
from finance_comps import ComparableCompanyAnalysis
from source_evidence.identity import sha256_bytes
from .models import *
from .validation import validate_finance_observation_evidence_manifest, validate_document_observation_compatibility

class BlobReader(Protocol):
    def read_blob(self, sha256_hex:str)->bytes: ...

class FinanceEvidenceResolverError(RuntimeError): pass

def resolve_finance_observation_evidence(*,analysis:ComparableCompanyAnalysis,manifest:FinanceObservationEvidenceManifest,observation_id:str,blob_reader:BlobReader)->ResolvedFinanceObservationEvidence:
    try:
        validate_sha256_id(observation_id,field_name="observation_id")
        validate_finance_observation_evidence_manifest(manifest,analysis)
        observation=next(o for o in analysis.source_observations if o.observation_id==observation_id)
        entry=next(e for e in manifest.entries if e.observation_id==observation_id)
        if entry.binding_class is not ObservationDocumentBindingClass.DOCUMENT_TEXT_BOUND: raise FinanceEvidenceResolverError("Observation does not have exact document-text evidence.")
        document=next(d for d in manifest.documents if d.document_snapshot_id==entry.document_snapshot_id)
        validate_document_observation_compatibility(observation=observation,document=document)
        original=blob_reader.read_blob(document.original_blob_sha256)
        if type(original) is not bytes or sha256_bytes(original)!=document.original_blob_sha256 or len(original)!=document.original_byte_length: raise FinanceEvidenceResolverError("Original PDF bytes failed immutable verification.")
        page=next(p for p in document.pages if p.page_number==entry.page_number)
        page_bytes=blob_reader.read_blob(page.page_text_sha256)
        if type(page_bytes) is not bytes or sha256_bytes(page_bytes)!=page.page_text_sha256 or len(page_bytes)!=page.page_text_byte_length: raise FinanceEvidenceResolverError("Page text bytes failed immutable verification.")
        start,end=entry.page_byte_start,entry.page_byte_end
        if start is None or end is None or start<0 or end<=start or end>len(page_bytes): raise FinanceEvidenceResolverError("Bound byte interval is invalid.")
        span=page_bytes[start:end]
        if entry.bound_text_sha256 is None or sha256_bytes(span)!=entry.bound_text_sha256: raise FinanceEvidenceResolverError("Bound text bytes failed immutable verification.")
        try: page_text=page_bytes.decode("utf-8"); bound_text=span.decode("utf-8")
        except UnicodeDecodeError as exc: raise FinanceEvidenceResolverError("Bound/page bytes are not exact UTF-8 text.") from exc
        return ResolvedFinanceObservationEvidence(workspace_id=analysis.workspace_id,source_analysis_id=analysis.analysis_id,observation_id=observation_id,source_channel=entry.source_channel,binding_class=entry.binding_class,document_snapshot_id=document.document_snapshot_id,original_filename=document.original_filename,page_number=page.page_number,original_blob_sha256=document.original_blob_sha256,page_text_sha256=page.page_text_sha256,bound_text_sha256=entry.bound_text_sha256,exact_bound_text=bound_text,exact_page_text=page_text,original_pdf_bytes=original)
    except FinanceEvidenceResolverError: raise
    except (StopIteration,KeyError,ValueError,TypeError) as exc: raise FinanceEvidenceResolverError("Finance evidence resolution failed closed.") from exc
