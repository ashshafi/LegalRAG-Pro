"""Finance F5 evidence binding and manifest construction."""
from __future__ import annotations
from typing import Protocol
from finance_domain import FinancialObservation, validate_financial_observation
from finance_domain.identity import derive_finance_id
from finance_comps import ComparableCompanyAnalysis, validate_comparable_company_analysis
from source_evidence.identity import sha256_bytes
from .models import *
from .serialization import binding_identity_payload_to_dict, manifest_identity_payload_to_dict
from .validation import validate_document_observation_compatibility, validate_observation_evidence_binding, validate_finance_observation_evidence_manifest

class BlobReader(Protocol):
    def read_blob(self, sha256_hex:str)->bytes: ...

def _finalize_binding(v):
    bid=derive_finance_id(binding_identity_payload_to_dict(v))
    result=ObservationEvidenceBinding(**{**{f:getattr(v,f) for f in v.__dataclass_fields__},"evidence_binding_id":bid})
    validate_observation_evidence_binding(result); return result

def build_document_text_binding(*,observation:FinancialObservation,document:FinanceSourceDocumentManifest,page_number:int,page_byte_start:int,page_byte_end:int,blob_reader:BlobReader,note:str|None=None)->ObservationEvidenceBinding:
    validate_financial_observation(observation); validate_document_observation_compatibility(observation=observation,document=document)
    if type(page_number) is not int or page_number<1: raise ValueError("page_number invalid.")
    page=next((p for p in document.pages if p.page_number==page_number),None)
    if page is None: raise ValueError("page_number is not present in document.")
    page_bytes=blob_reader.read_blob(page.page_text_sha256)
    if type(page_bytes) is not bytes or sha256_bytes(page_bytes)!=page.page_text_sha256 or len(page_bytes)!=page.page_text_byte_length: raise ValueError("stored page bytes do not match document manifest.")
    if type(page_byte_start) is not int or type(page_byte_end) is not int or page_byte_start<0 or page_byte_end<=page_byte_start or page_byte_end>len(page_bytes): raise ValueError("invalid page byte interval.")
    span=page_bytes[page_byte_start:page_byte_end]
    try: span.decode("utf-8")
    except UnicodeDecodeError as exc: raise ValueError("page byte interval must align to valid UTF-8 text boundaries.") from exc
    provisional=ObservationEvidenceBinding(schema_version=OBSERVATION_EVIDENCE_BINDING_SCHEMA_VERSION,workspace_id=observation.workspace_id,company_id=observation.company_id,observation_id=observation.observation_id,source_channel=ObservationSourceChannel.DOCUMENT,binding_class=ObservationDocumentBindingClass.DOCUMENT_TEXT_BOUND,document_snapshot_id=document.document_snapshot_id,page_number=page_number,page_byte_start=page_byte_start,page_byte_end=page_byte_end,bound_text_sha256=sha256_bytes(span),note=note,evidence_binding_id="sha256:"+"0"*64)
    return _finalize_binding(provisional)

def build_unbound_document_binding(*,observation:FinancialObservation,note:str)->ObservationEvidenceBinding:
    validate_financial_observation(observation)
    provisional=ObservationEvidenceBinding(schema_version=OBSERVATION_EVIDENCE_BINDING_SCHEMA_VERSION,workspace_id=observation.workspace_id,company_id=observation.company_id,observation_id=observation.observation_id,source_channel=ObservationSourceChannel.DOCUMENT,binding_class=ObservationDocumentBindingClass.DOCUMENT_UNBOUND,document_snapshot_id=None,page_number=None,page_byte_start=None,page_byte_end=None,bound_text_sha256=None,note=note,evidence_binding_id="sha256:"+"0"*64)
    return _finalize_binding(provisional)

def build_non_documentary_binding(*,observation:FinancialObservation,source_channel:ObservationSourceChannel,note:str|None=None)->ObservationEvidenceBinding:
    validate_financial_observation(observation)
    if source_channel not in {ObservationSourceChannel.STRUCTURED_PROVIDER,ObservationSourceChannel.MARKET}: raise ValueError("source_channel must be explicitly STRUCTURED_PROVIDER or MARKET.")
    provisional=ObservationEvidenceBinding(schema_version=OBSERVATION_EVIDENCE_BINDING_SCHEMA_VERSION,workspace_id=observation.workspace_id,company_id=observation.company_id,observation_id=observation.observation_id,source_channel=source_channel,binding_class=ObservationDocumentBindingClass.NOT_APPLICABLE,document_snapshot_id=None,page_number=None,page_byte_start=None,page_byte_end=None,bound_text_sha256=None,note=note,evidence_binding_id="sha256:"+"0"*64)
    return _finalize_binding(provisional)

def _coverage(entries):
    docs=[e for e in entries if e.source_channel is ObservationSourceChannel.DOCUMENT]
    if not docs:return FinanceDocumentEvidenceCoverage.NOT_APPLICABLE
    count=sum(e.binding_class is ObservationDocumentBindingClass.DOCUMENT_TEXT_BOUND for e in docs)
    if count==len(docs): return FinanceDocumentEvidenceCoverage.FULLY_DOCUMENT_BOUND
    if count==0:return FinanceDocumentEvidenceCoverage.DOCUMENT_UNBOUND
    return FinanceDocumentEvidenceCoverage.MIXED_DOCUMENT_BINDING

def build_finance_observation_evidence_manifest(*,analysis:ComparableCompanyAnalysis,documents,entries)->FinanceObservationEvidenceManifest:
    validate_comparable_company_analysis(analysis)
    docs=tuple(sorted(tuple(documents),key=lambda x:x.document_snapshot_id)); ents=tuple(sorted(tuple(entries),key=lambda x:x.observation_id)); obsids=tuple(sorted(o.observation_id for o in analysis.source_observations))
    provisional=FinanceObservationEvidenceManifest(schema_version=FINANCE_OBSERVATION_EVIDENCE_MANIFEST_SCHEMA_VERSION,identity_version=FINANCE_EVIDENCE_IDENTITY_VERSION,workspace_id=analysis.workspace_id,source_analysis_id=analysis.analysis_id,as_of=analysis.as_of,observation_ids=obsids,documents=docs,entries=ents,coverage=_coverage(ents),document_evidence_manifest_id="sha256:"+"0"*64)
    mid=derive_finance_id(manifest_identity_payload_to_dict(provisional))
    result=FinanceObservationEvidenceManifest(**{**{f:getattr(provisional,f) for f in provisional.__dataclass_fields__},"document_evidence_manifest_id":mid})
    validate_finance_observation_evidence_manifest(result,analysis); return result
