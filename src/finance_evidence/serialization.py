"""Canonical JSON serialization for Finance F5 evidence authorities."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any
from finance_domain.identity import canonical_json_bytes
from source_evidence.models import ExtractionMethod, ExtractionProfile
from .models import (
    FinanceDocumentEvidenceCoverage, FinanceObservationEvidenceManifest,
    FinanceSourceDocumentManifest, FinanceSourcePageSnapshot,
    ObservationDocumentBindingClass, ObservationEvidenceBinding, ObservationSourceChannel,
)

def _dt(value: datetime | None) -> str | None:
    if value is None: return None
    if value.tzinfo is None or value.utcoffset() is None or value.utcoffset().total_seconds()!=0:
        raise ValueError("F5 datetime must be UTC.")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00","Z")

def extraction_profile_to_dict(v: ExtractionProfile) -> dict[str, Any]:
    return {"profile_id":v.profile_id,"profile_schema_version":v.profile_schema_version,"pypdf_package_version":v.pypdf_package_version,"pdf2image_package_version":v.pdf2image_package_version,"pytesseract_package_version":v.pytesseract_package_version,"tesseract_engine_version":v.tesseract_engine_version,"poppler_version":v.poppler_version,"ocr_language":v.ocr_language,"ocr_config":v.ocr_config,"ocr_dpi":v.ocr_dpi}

def page_to_dict(v: FinanceSourcePageSnapshot)->dict[str,Any]:
    return {"page_number":v.page_number,"extraction_method":v.extraction_method.value,"page_text_sha256":v.page_text_sha256,"page_text_byte_length":v.page_text_byte_length}

def document_to_dict(v: FinanceSourceDocumentManifest)->dict[str,Any]:
    return {"schema_version":v.schema_version,"workspace_id":v.workspace_id,"company_id":v.company_id,"provider":v.provider,"source_id":v.source_id,"source_version":v.source_version,"publication_at":_dt(v.publication_at),"original_filename":v.original_filename,"media_type":v.media_type,"original_blob_sha256":v.original_blob_sha256,"original_byte_length":v.original_byte_length,"extraction_profile":extraction_profile_to_dict(v.extraction_profile),"pages":[page_to_dict(x) for x in v.pages],"document_snapshot_id":v.document_snapshot_id}

def document_identity_payload_to_dict(v: FinanceSourceDocumentManifest)->dict[str,Any]:
    d=document_to_dict(v); d.pop("document_snapshot_id"); return d

def binding_to_dict(v: ObservationEvidenceBinding)->dict[str,Any]:
    return {"schema_version":v.schema_version,"workspace_id":v.workspace_id,"company_id":v.company_id,"observation_id":v.observation_id,"source_channel":v.source_channel.value,"binding_class":v.binding_class.value,"document_snapshot_id":v.document_snapshot_id,"page_number":v.page_number,"page_byte_start":v.page_byte_start,"page_byte_end":v.page_byte_end,"bound_text_sha256":v.bound_text_sha256,"note":v.note,"evidence_binding_id":v.evidence_binding_id}

def binding_identity_payload_to_dict(v: ObservationEvidenceBinding)->dict[str,Any]:
    d=binding_to_dict(v); d.pop("evidence_binding_id"); return d

def manifest_to_dict(v: FinanceObservationEvidenceManifest)->dict[str,Any]:
    return {"schema_version":v.schema_version,"identity_version":v.identity_version,"workspace_id":v.workspace_id,"source_analysis_id":v.source_analysis_id,"as_of":_dt(v.as_of),"observation_ids":list(v.observation_ids),"documents":[document_to_dict(x) for x in v.documents],"entries":[binding_to_dict(x) for x in v.entries],"coverage":v.coverage.value,"document_evidence_manifest_id":v.document_evidence_manifest_id}

def manifest_identity_payload_to_dict(v: FinanceObservationEvidenceManifest)->dict[str,Any]:
    d=manifest_to_dict(v); d.pop("document_evidence_manifest_id"); return d

def dumps_finance_observation_evidence_manifest(v: FinanceObservationEvidenceManifest)->str:
    from .validation import validate_finance_observation_evidence_manifest_structure
    validate_finance_observation_evidence_manifest_structure(v)
    return canonical_json_bytes(manifest_to_dict(v)).decode("utf-8")

def _loads_obj(payload:str)->dict[str,Any]:
    if not isinstance(payload,str): raise ValueError("F5 payload must be text.")
    def hook(pairs):
        out={}
        for k,v in pairs:
            if k in out: raise ValueError(f"Duplicate JSON object key {k!r} is not allowed.")
            out[k]=v
        return out
    try: data=json.loads(payload,object_pairs_hook=hook)
    except json.JSONDecodeError as exc: raise ValueError("Invalid F5 JSON.") from exc
    if not isinstance(data,dict): raise ValueError("F5 JSON root must be an object.")
    return data

def _utc(v:Any)->datetime:
    if not isinstance(v,str) or not v.endswith("Z"): raise ValueError("F5 datetime must use canonical UTC Z form.")
    try: d=datetime.fromisoformat(v[:-1]+"+00:00")
    except ValueError as exc: raise ValueError("Invalid F5 datetime.") from exc
    if _dt(d)!=v: raise ValueError("F5 datetime is not canonical.")
    return d

def _profile(d:Any)->ExtractionProfile:
    keys={"profile_id","profile_schema_version","pypdf_package_version","pdf2image_package_version","pytesseract_package_version","tesseract_engine_version","poppler_version","ocr_language","ocr_config","ocr_dpi"}
    if not isinstance(d,dict) or set(d)!=keys: raise ValueError("ExtractionProfile fields are not exact.")
    return ExtractionProfile(**d)

def _page(d:Any)->FinanceSourcePageSnapshot:
    keys={"page_number","extraction_method","page_text_sha256","page_text_byte_length"}
    if not isinstance(d,dict) or set(d)!=keys: raise ValueError("F5 page fields are not exact.")
    return FinanceSourcePageSnapshot(page_number=d["page_number"],extraction_method=ExtractionMethod(d["extraction_method"]),page_text_sha256=d["page_text_sha256"],page_text_byte_length=d["page_text_byte_length"])

def _document(d:Any)->FinanceSourceDocumentManifest:
    keys={"schema_version","workspace_id","company_id","provider","source_id","source_version","publication_at","original_filename","media_type","original_blob_sha256","original_byte_length","extraction_profile","pages","document_snapshot_id"}
    if not isinstance(d,dict) or set(d)!=keys or not isinstance(d["pages"],list): raise ValueError("F5 document fields are not exact.")
    return FinanceSourceDocumentManifest(schema_version=d["schema_version"],workspace_id=d["workspace_id"],company_id=d["company_id"],provider=d["provider"],source_id=d["source_id"],source_version=d["source_version"],publication_at=_utc(d["publication_at"]) if d["publication_at"] is not None else None,original_filename=d["original_filename"],media_type=d["media_type"],original_blob_sha256=d["original_blob_sha256"],original_byte_length=d["original_byte_length"],extraction_profile=_profile(d["extraction_profile"]),pages=tuple(_page(x) for x in d["pages"]),document_snapshot_id=d["document_snapshot_id"])

def _binding(d:Any)->ObservationEvidenceBinding:
    keys={"schema_version","workspace_id","company_id","observation_id","source_channel","binding_class","document_snapshot_id","page_number","page_byte_start","page_byte_end","bound_text_sha256","note","evidence_binding_id"}
    if not isinstance(d,dict) or set(d)!=keys: raise ValueError("F5 binding fields are not exact.")
    return ObservationEvidenceBinding(schema_version=d["schema_version"],workspace_id=d["workspace_id"],company_id=d["company_id"],observation_id=d["observation_id"],source_channel=ObservationSourceChannel(d["source_channel"]),binding_class=ObservationDocumentBindingClass(d["binding_class"]),document_snapshot_id=d["document_snapshot_id"],page_number=d["page_number"],page_byte_start=d["page_byte_start"],page_byte_end=d["page_byte_end"],bound_text_sha256=d["bound_text_sha256"],note=d["note"],evidence_binding_id=d["evidence_binding_id"])

def loads_finance_observation_evidence_manifest(payload:str)->FinanceObservationEvidenceManifest:
    d=_loads_obj(payload)
    keys={"schema_version","identity_version","workspace_id","source_analysis_id","as_of","observation_ids","documents","entries","coverage","document_evidence_manifest_id"}
    if set(d)!=keys or not isinstance(d["observation_ids"],list) or not isinstance(d["documents"],list) or not isinstance(d["entries"],list): raise ValueError("F5 manifest fields are not exact.")
    v=FinanceObservationEvidenceManifest(schema_version=d["schema_version"],identity_version=d["identity_version"],workspace_id=d["workspace_id"],source_analysis_id=d["source_analysis_id"],as_of=_utc(d["as_of"]),observation_ids=tuple(d["observation_ids"]),documents=tuple(_document(x) for x in d["documents"]),entries=tuple(_binding(x) for x in d["entries"]),coverage=FinanceDocumentEvidenceCoverage(d["coverage"]),document_evidence_manifest_id=d["document_evidence_manifest_id"])
    from .validation import validate_finance_observation_evidence_manifest_structure
    validate_finance_observation_evidence_manifest_structure(v)
    if dumps_finance_observation_evidence_manifest(v)!=payload: raise ValueError("F5 payload is not canonical JSON.")
    return v
