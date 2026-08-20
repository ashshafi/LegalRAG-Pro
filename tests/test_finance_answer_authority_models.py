from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone

from finance_comps import (
    ComparableRole,
    PeerInclusionState,
    build_comparable_company_analysis,
    create_comparable_member_selection,
    create_comparable_set_definition,
)
from finance_data import FrozenDemoProvider
from finance_evidence import (
    ObservationSourceChannel,
    build_finance_observation_evidence_manifest,
    build_non_documentary_binding,
)
from finance_answer_authority import *

ASOF = datetime(2026, 3, 2, 16, 30, tzinfo=timezone.utc)


def analysis(*, as_of=ASOF):
    provider = FrozenDemoProvider()
    members = []
    for company in provider.list_companies():
        security = provider.list_securities(company_id=company.company_id)[0]
        periods = sorted(provider.list_periods(company_id=company.company_id), key=lambda item: item.end_date)
        is_target = company.company_id == provider.target_company_id
        members.append(create_comparable_member_selection(
            company_id=company.company_id,
            security_id=security.security_id,
            role=ComparableRole.TARGET if is_target else ComparableRole.PEER,
            inclusion_state=PeerInclusionState.INCLUDED,
            current_period_id=periods[-1].financial_period_id,
            prior_period_id=periods[-2].financial_period_id,
        ))
    definition = create_comparable_set_definition(
        workspace_id=provider.workspace.workspace_id,
        as_of=as_of,
        members=tuple(members),
    )
    return build_comparable_company_analysis(provider=provider, definition=definition)


def manifest_for(analysis_value):
    entries = tuple(
        build_non_documentary_binding(
            observation=observation,
            source_channel=ObservationSourceChannel.STRUCTURED_PROVIDER,
        )
        for observation in analysis_value.source_observations
    )
    return build_finance_observation_evidence_manifest(
        analysis=analysis_value,
        documents=(),
        entries=entries,
    )


def context(*, as_of=ASOF):
    a = analysis(as_of=as_of)
    return build_runtime_finance_answer_context(analysis=a, evidence_manifest=manifest_for(a))


def target_company_id(ctx):
    return next(item.company_id for item in ctx.members if item.role is ComparableRole.TARGET)


def cell(ctx, metric, *, target=True):
    target_id = target_company_id(ctx)
    return next(item for item in ctx.cells if item.metric_code == metric and ((item.company_id == target_id) if target else (item.company_id != target_id)))


def summary(ctx, metric):
    return next(item for item in ctx.summaries if item.metric_code == metric)


def position(ctx, metric):
    return next(item for item in ctx.positions if item.metric_code == metric)


def calculation(ctx, metric):
    target_id = target_company_id(ctx)
    return next(item for item in ctx.calculations if item.metric_code == metric and item.company_id == target_id)


def output(ctx, claims, *, mode="ANSWER", reason=None):
    import json
    return json.dumps({
        "analysis_id": ctx.analysis_id,
        "document_evidence_manifest_id": ctx.document_evidence_manifest_id,
        "mode": mode,
        "claims": claims,
        "unavailable_reason": reason,
    }, separators=(",", ":"))


def claim(claim_id, claim_type, authority_id, selector=None):
    return {"claim_id": claim_id, "claim_type": claim_type, "authority_id": authority_id, "selector": selector}


def test_runtime_models_are_frozen_and_use_tuple_collections():
    ctx = context()
    assert isinstance(ctx.cells, tuple) and isinstance(ctx.evidence_bindings, tuple)
    try:
        ctx.analysis_id = "x"
        assert False
    except FrozenInstanceError:
        pass


def test_content_classification_enum_preserves_all_five_governing_classes():
    assert {item.value for item in FinanceContentClassification} == {
        "SOURCE_FACT", "DERIVED_METRIC", "MODEL_CALCULATION", "ANALYST_INTERPRETATION", "AI_GENERATED_COMMENTARY"
    }


def test_claim_grammar_is_exact_and_finite():
    assert tuple(item.value for item in FinanceClaimType) == (
        "ANALYSIS_AS_OF", "DATASET_IDENTITY", "MEMBER_STATUS", "CELL_VALUE", "CELL_STATUS",
        "PEER_SUMMARY_VALUE", "PEER_SUMMARY_STATUS", "TARGET_PEER_RELATIONSHIP",
        "CALCULATION_FORMULA", "EVIDENCE_BINDING", "EVIDENCE_COVERAGE",
    )


def mixed_manifest_for(analysis_value):
    """Create a structurally valid mixed F5 manifest without blob access or PDF capture."""
    from finance_domain import derive_finance_id
    from finance_evidence import (
        FINANCE_SOURCE_DOCUMENT_SCHEMA_VERSION,
        OBSERVATION_EVIDENCE_BINDING_SCHEMA_VERSION,
        FinanceSourceDocumentManifest,
        FinanceSourcePageSnapshot,
        ObservationDocumentBindingClass,
        ObservationEvidenceBinding,
        build_unbound_document_binding,
    )
    from finance_evidence.serialization import binding_identity_payload_to_dict, document_identity_payload_to_dict
    from source_evidence.identity import sha256_bytes
    from source_evidence.models import (
        EXTRACTION_PROFILE_ID,
        EXTRACTION_PROFILE_SCHEMA_VERSION,
        ExtractionMethod,
        ExtractionProfile,
    )

    observations = list(analysis_value.source_observations)
    first = observations[0]
    page_bytes = b"governed source text"
    profile = ExtractionProfile(
        profile_id=EXTRACTION_PROFILE_ID,
        profile_schema_version=EXTRACTION_PROFILE_SCHEMA_VERSION,
        pypdf_package_version="5.9.0",
        pdf2image_package_version=None,
        pytesseract_package_version=None,
        tesseract_engine_version=None,
        poppler_version=None,
        ocr_language="eng",
        ocr_config="",
        ocr_dpi=200,
    )
    page = FinanceSourcePageSnapshot(
        page_number=1,
        extraction_method=ExtractionMethod.PYPDF_TEXT,
        page_text_sha256=sha256_bytes(page_bytes),
        page_text_byte_length=len(page_bytes),
    )
    provisional_doc = FinanceSourceDocumentManifest(
        schema_version=FINANCE_SOURCE_DOCUMENT_SCHEMA_VERSION,
        workspace_id=first.workspace_id,
        company_id=first.company_id,
        provider=first.provider,
        source_id=first.source_id,
        source_version=first.source_version,
        publication_at=first.publication_at,
        original_filename="governed.pdf",
        media_type="application/pdf",
        original_blob_sha256=sha256_bytes(b"%PDF-governed"),
        original_byte_length=len(b"%PDF-governed"),
        extraction_profile=profile,
        pages=(page,),
        document_snapshot_id="sha256:" + "0" * 64,
    )
    document = replace(provisional_doc, document_snapshot_id=derive_finance_id(document_identity_payload_to_dict(provisional_doc)))
    provisional_binding = ObservationEvidenceBinding(
        schema_version=OBSERVATION_EVIDENCE_BINDING_SCHEMA_VERSION,
        workspace_id=first.workspace_id,
        company_id=first.company_id,
        observation_id=first.observation_id,
        source_channel=ObservationSourceChannel.DOCUMENT,
        binding_class=ObservationDocumentBindingClass.DOCUMENT_TEXT_BOUND,
        document_snapshot_id=document.document_snapshot_id,
        page_number=1,
        page_byte_start=0,
        page_byte_end=8,
        bound_text_sha256=sha256_bytes(page_bytes[:8]),
        note=None,
        evidence_binding_id="sha256:" + "0" * 64,
    )
    bound = replace(provisional_binding, evidence_binding_id=derive_finance_id(binding_identity_payload_to_dict(provisional_binding)))

    entries = [bound, build_unbound_document_binding(observation=observations[1], note="archived filing unavailable")]
    entries.append(build_non_documentary_binding(observation=observations[2], source_channel=ObservationSourceChannel.MARKET))
    entries.extend(
        build_non_documentary_binding(observation=observation, source_channel=ObservationSourceChannel.STRUCTURED_PROVIDER)
        for observation in observations[3:]
    )
    return build_finance_observation_evidence_manifest(analysis=analysis_value, documents=(document,), entries=tuple(entries))
