from __future__ import annotations
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone

from finance_comps import ComparableRole, PeerInclusionState, build_comparable_company_analysis, create_comparable_member_selection, create_comparable_set_definition
from finance_data import FrozenDemoProvider
from finance_evidence import ObservationSourceChannel, build_finance_observation_evidence_manifest, build_non_documentary_binding
from finance_reporting import build_finance_report_projection

ASOF=datetime(2026,3,2,16,30,tzinfo=timezone.utc)

def analysis(*, as_of=ASOF, exclude_company_id=None):
    p=FrozenDemoProvider(); members=[]
    for c in p.list_companies():
        s=p.list_securities(company_id=c.company_id)[0]
        periods=sorted(p.list_periods(company_id=c.company_id),key=lambda x:x.end_date)
        target=c.company_id==p.target_company_id
        excluded=(not target and c.company_id==exclude_company_id)
        members.append(create_comparable_member_selection(
            company_id=c.company_id,security_id=s.security_id,
            role=ComparableRole.TARGET if target else ComparableRole.PEER,
            inclusion_state=PeerInclusionState.EXCLUDED if excluded else PeerInclusionState.INCLUDED,
            current_period_id=periods[-1].financial_period_id,prior_period_id=periods[-2].financial_period_id,
            exclusion_reason="governed exclusion" if excluded else None,
        ))
    d=create_comparable_set_definition(workspace_id=p.workspace.workspace_id,as_of=as_of,members=tuple(members))
    return build_comparable_company_analysis(provider=p,definition=d)

def manifest_for(a):
    entries=tuple(build_non_documentary_binding(observation=o,source_channel=ObservationSourceChannel.STRUCTURED_PROVIDER) for o in a.source_observations)
    return build_finance_observation_evidence_manifest(analysis=a,documents=(),entries=entries)

def projection(*, as_of=ASOF, exclude_company_id=None):
    a=analysis(as_of=as_of,exclude_company_id=exclude_company_id)
    return build_finance_report_projection(analysis=a,evidence_manifest=manifest_for(a))

def mixed_manifest_for(a):
    from finance_domain import derive_finance_id
    from finance_evidence import (
        FINANCE_SOURCE_DOCUMENT_SCHEMA_VERSION, OBSERVATION_EVIDENCE_BINDING_SCHEMA_VERSION,
        FinanceSourceDocumentManifest, FinanceSourcePageSnapshot, ObservationDocumentBindingClass,
        ObservationEvidenceBinding, build_unbound_document_binding,
    )
    from finance_evidence.serialization import binding_identity_payload_to_dict, document_identity_payload_to_dict
    from source_evidence.identity import sha256_bytes
    from source_evidence.models import EXTRACTION_PROFILE_ID, EXTRACTION_PROFILE_SCHEMA_VERSION, ExtractionMethod, ExtractionProfile
    obs=list(a.source_observations); first=obs[0]; page_bytes=b"governed source text"
    profile=ExtractionProfile(profile_id=EXTRACTION_PROFILE_ID,profile_schema_version=EXTRACTION_PROFILE_SCHEMA_VERSION,pypdf_package_version="5.9.0",pdf2image_package_version=None,pytesseract_package_version=None,tesseract_engine_version=None,poppler_version=None,ocr_language="eng",ocr_config="",ocr_dpi=200)
    page=FinanceSourcePageSnapshot(page_number=1,extraction_method=ExtractionMethod.PYPDF_TEXT,page_text_sha256=sha256_bytes(page_bytes),page_text_byte_length=len(page_bytes))
    pdoc=FinanceSourceDocumentManifest(schema_version=FINANCE_SOURCE_DOCUMENT_SCHEMA_VERSION,workspace_id=first.workspace_id,company_id=first.company_id,provider=first.provider,source_id=first.source_id,source_version=first.source_version,publication_at=first.publication_at,original_filename="governed.pdf",media_type="application/pdf",original_blob_sha256=sha256_bytes(b"%PDF-governed"),original_byte_length=len(b"%PDF-governed"),extraction_profile=profile,pages=(page,),document_snapshot_id="sha256:"+"0"*64)
    doc=replace(pdoc,document_snapshot_id=derive_finance_id(document_identity_payload_to_dict(pdoc)))
    pb=ObservationEvidenceBinding(schema_version=OBSERVATION_EVIDENCE_BINDING_SCHEMA_VERSION,workspace_id=first.workspace_id,company_id=first.company_id,observation_id=first.observation_id,source_channel=ObservationSourceChannel.DOCUMENT,binding_class=ObservationDocumentBindingClass.DOCUMENT_TEXT_BOUND,document_snapshot_id=doc.document_snapshot_id,page_number=1,page_byte_start=0,page_byte_end=8,bound_text_sha256=sha256_bytes(page_bytes[:8]),note=None,evidence_binding_id="sha256:"+"0"*64)
    bound=replace(pb,evidence_binding_id=derive_finance_id(binding_identity_payload_to_dict(pb)))
    entries=[bound,build_unbound_document_binding(observation=obs[1],note="archived filing unavailable")]
    entries.append(build_non_documentary_binding(observation=obs[2],source_channel=ObservationSourceChannel.MARKET))
    entries.extend(build_non_documentary_binding(observation=o,source_channel=ObservationSourceChannel.STRUCTURED_PROVIDER) for o in obs[3:])
    return build_finance_observation_evidence_manifest(analysis=a,documents=(doc,),entries=tuple(entries))

def test_projection_models_are_frozen_and_tuple_normalised():
    p=projection(); assert isinstance(p.cells,tuple) and isinstance(p.manifest.sections,tuple)
    try:
        p.report_projection_id="x"; assert False
    except FrozenInstanceError: pass

def test_projection_cardinality_is_lossless_for_frozen_demo():
    a=analysis(); p=build_finance_report_projection(analysis=a,evidence_manifest=manifest_for(a))
    assert (len(p.members),len(p.cells),len(p.summaries),len(p.positions),len(p.calculations),len(p.evidence))==(6,54,9,9,42,66)
    assert p.source_analysis_id==a.analysis_id
