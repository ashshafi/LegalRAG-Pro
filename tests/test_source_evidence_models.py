from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from uuid import UUID

import pytest

from source_evidence.identity import (
    derive_sha256_id,
    derive_source_document_instance_id,
    sha256_bytes,
)
from source_evidence.models import (
    CHUNKING_PROFILE_ID,
    CHUNKING_PROFILE_SCHEMA_VERSION,
    EVIDENCE_BINDING_SCHEMA_VERSION,
    EXTRACTION_PROFILE_ID,
    EXTRACTION_PROFILE_SCHEMA_VERSION,
    PROJECTION_EVIDENCE_BINDING_SCHEMA_VERSION,
    SOURCE_BOUND_ANALYSIS_RECEIPT_SCHEMA_VERSION,
    SOURCE_BOUND_RETRIEVAL_VERIFIER_VERSION,
    SOURCE_DOCUMENT_MANIFEST_SCHEMA_VERSION,
    BindingClass,
    BoundTextRole,
    ChunkingProfile,
    EvidenceBinding,
    ExtractionMethod,
    ExtractionProfile,
    ProjectionBindingCoverage,
    ProjectionBindingEntry,
    ProjectionEvidenceBindingManifest,
    SourceBoundAnalysisReceipt,
    SourceChunkSnapshot,
    SourceDocumentManifest,
    SourcePageSnapshot,
    VerifiedEvidenceUse,
)
from source_evidence.serialization import (
    evidence_binding_identity_payload_to_dict,
    projection_evidence_binding_manifest_identity_payload_to_dict,
    source_bound_analysis_receipt_identity_payload_to_dict,
    source_document_manifest_identity_payload_to_dict,
)
from source_evidence.validation import (
    validate_chunking_profile,
    validate_evidence_binding,
    validate_extraction_profile,
    validate_projection_evidence_binding_manifest,
    validate_source_bound_analysis_receipt,
    validate_source_document_manifest,
)

CASE_ID = "12345678-1234-4234-8234-123456789abc"
REPORT_ID = "11111111-1111-4111-8111-111111111111"
REPORT_MANIFEST_ID = "22222222-2222-4222-8222-222222222222"
SHA_A = sha256_bytes(b"original-pdf")
SHA_B = sha256_bytes("page text".encode())
SHA_C = sha256_bytes("chunk text".encode())


def extraction_profile(*, ocr: bool = False) -> ExtractionProfile:
    return ExtractionProfile(
        profile_id=EXTRACTION_PROFILE_ID,
        profile_schema_version=EXTRACTION_PROFILE_SCHEMA_VERSION,
        pypdf_package_version="6.14.2",
        pdf2image_package_version="1.17.0" if ocr else None,
        pytesseract_package_version="0.3.13" if ocr else None,
        tesseract_engine_version="5.5.0" if ocr else None,
        poppler_version="25.01.0" if ocr else None,
        ocr_language="eng",
        ocr_config="",
        ocr_dpi=200,
    )


def chunking_profile() -> ChunkingProfile:
    return ChunkingProfile(
        profile_id=CHUNKING_PROFILE_ID,
        profile_schema_version=CHUNKING_PROFILE_SCHEMA_VERSION,
        library="langchain-text-splitters",
        library_version="1.1.2",
        chunk_size=1000,
        chunk_overlap=200,
        separators=("\n\n", "\n", " ", ""),
        length_function="len",
        is_separator_regex=False,
    )


def make_manifest(*, ocr: bool = False) -> SourceDocumentManifest:
    filename = "evidence.pdf"
    document_id = derive_source_document_instance_id(
        case_id=CASE_ID,
        original_filename=filename,
        original_blob_sha256=SHA_A,
    )
    chunk = SourceChunkSnapshot(
        page_number=1,
        chunk_ordinal=0,
        chunk_id="chunk-1",
        evidence_key="chunk-1",
        chunk_text_sha256=SHA_C,
        chunk_text_byte_length=len(b"chunk text"),
    )
    page = SourcePageSnapshot(
        page_number=1,
        extraction_method=ExtractionMethod.PAGE_OCR if ocr else ExtractionMethod.PYPDF_TEXT,
        page_text_sha256=SHA_B,
        page_text_byte_length=len(b"page text"),
        chunk_snapshots=(chunk,),
    )
    value = SourceDocumentManifest(
        schema_version=SOURCE_DOCUMENT_MANIFEST_SCHEMA_VERSION,
        case_id=CASE_ID,
        source_document_instance_id=document_id,
        original_filename=filename,
        media_type="application/pdf",
        original_blob_sha256=SHA_A,
        original_byte_length=len(b"original-pdf"),
        extraction_profile=extraction_profile(ocr=ocr),
        chunking_profile=chunking_profile(),
        pages=(page,),
        source_snapshot_id="sha256:" + "0" * 64,
    )
    return replace(
        value,
        source_snapshot_id=derive_sha256_id(source_document_manifest_identity_payload_to_dict(value)),
    )


def make_binding(binding_class: BindingClass = BindingClass.FULL_CHAIN_BOUND) -> EvidenceBinding:
    if binding_class is BindingClass.FULL_CHAIN_BOUND:
        kwargs = dict(
            chunk_id="chunk-1",
            bound_text_role=BoundTextRole.CHUNK_TEXT,
            source_document_instance_id=make_manifest().source_document_instance_id,
            source_snapshot_id=make_manifest().source_snapshot_id,
            page=1,
            chunk_ordinal=0,
            original_blob_sha256=SHA_A,
            page_text_sha256=SHA_B,
            chunk_text_sha256=SHA_C,
            bound_text_sha256=SHA_C,
            extraction_profile_id=EXTRACTION_PROFILE_ID,
            chunking_profile_id=CHUNKING_PROFILE_ID,
        )
    elif binding_class is BindingClass.ANALYTICAL_TEXT_BOUND:
        kwargs = dict(
            chunk_id="chunk-1",
            bound_text_role=BoundTextRole.ANALYTICAL_SUMMARY,
            source_document_instance_id=None,
            source_snapshot_id=None,
            page=1,
            chunk_ordinal=None,
            original_blob_sha256=None,
            page_text_sha256=None,
            chunk_text_sha256=None,
            bound_text_sha256=sha256_bytes(b"historical summary"),
            extraction_profile_id=None,
            chunking_profile_id=None,
        )
    else:
        kwargs = dict(
            chunk_id="chunk-1",
            bound_text_role=BoundTextRole.LEGACY_CURRENT_INDEX_TEXT,
            source_document_instance_id=None,
            source_snapshot_id=None,
            page=1,
            chunk_ordinal=None,
            original_blob_sha256=None,
            page_text_sha256=None,
            chunk_text_sha256=None,
            bound_text_sha256=sha256_bytes(b"current index"),
            extraction_profile_id=None,
            chunking_profile_id=None,
        )
    value = EvidenceBinding(
        schema_version=EVIDENCE_BINDING_SCHEMA_VERSION,
        case_id=CASE_ID,
        evidence_key="chunk-1",
        binding_class=binding_class,
        document_name="evidence.pdf",
        document_id=None,
        evidence_binding_id="sha256:" + "0" * 64,
        **kwargs,
    )
    return replace(
        value,
        evidence_binding_id=derive_sha256_id(evidence_binding_identity_payload_to_dict(value)),
    )


def make_receipt() -> SourceBoundAnalysisReceipt:
    binding = make_binding()
    use = VerifiedEvidenceUse(
        evidence_key=binding.evidence_key,
        evidence_binding_id=binding.evidence_binding_id,
        chunk_text_sha256=SHA_C,
    )
    value = SourceBoundAnalysisReceipt(
        schema_version=SOURCE_BOUND_ANALYSIS_RECEIPT_SCHEMA_VERSION,
        case_id=CASE_ID,
        verifier_version=SOURCE_BOUND_RETRIEVAL_VERIFIER_VERSION,
        verified_evidence=(use,),
        source_bound_analysis_receipt_id="sha256:" + "0" * 64,
    )
    return replace(
        value,
        source_bound_analysis_receipt_id=derive_sha256_id(
            source_bound_analysis_receipt_identity_payload_to_dict(value)
        ),
    )


def make_projection_binding(
    binding_class: BindingClass = BindingClass.FULL_CHAIN_BOUND,
) -> ProjectionEvidenceBindingManifest:
    if binding_class is BindingClass.FULL_CHAIN_BOUND:
        binding_id = make_binding().evidence_binding_id
        receipt_id = make_receipt().source_bound_analysis_receipt_id
        coverage = ProjectionBindingCoverage.FULLY_SOURCE_BOUND
    elif binding_class is BindingClass.UNBOUND:
        binding_id = None
        receipt_id = None
        coverage = ProjectionBindingCoverage.UNBOUND
    else:
        binding_id = make_binding(binding_class).evidence_binding_id
        receipt_id = None
        coverage = ProjectionBindingCoverage.MIXED_BINDING
    entry = ProjectionBindingEntry(
        citation_id="chunk-1",
        evidence_key="chunk-1",
        binding_class=binding_class,
        evidence_binding_id=binding_id,
        source_bound_analysis_receipt_id=receipt_id,
    )
    value = ProjectionEvidenceBindingManifest(
        schema_version=PROJECTION_EVIDENCE_BINDING_SCHEMA_VERSION,
        case_id=CASE_ID,
        report_projection_id=REPORT_ID,
        projection_payload_sha256=sha256_bytes(b"projection"),
        manifest_id=REPORT_MANIFEST_ID,
        coverage=coverage,
        entries=(entry,),
        projection_evidence_binding_manifest_id="sha256:" + "0" * 64,
    )
    return replace(
        value,
        projection_evidence_binding_manifest_id=derive_sha256_id(
            projection_evidence_binding_manifest_identity_payload_to_dict(value)
        ),
    )


def test_core_dataclasses_are_frozen() -> None:
    manifest = make_manifest()
    with pytest.raises(FrozenInstanceError):
        manifest.case_id = CASE_ID  # type: ignore[misc]


def test_document_identity_separates_content_case_and_filename() -> None:
    same = derive_source_document_instance_id(
        case_id=CASE_ID,
        original_filename="a.pdf",
        original_blob_sha256=SHA_A,
    )
    assert same == derive_source_document_instance_id(
        case_id=CASE_ID,
        original_filename="a.pdf",
        original_blob_sha256=SHA_A,
    )
    assert same != derive_source_document_instance_id(
        case_id="87654321-4321-4321-8321-cba987654321",
        original_filename="a.pdf",
        original_blob_sha256=SHA_A,
    )
    assert same != derive_source_document_instance_id(
        case_id=CASE_ID,
        original_filename="b.pdf",
        original_blob_sha256=SHA_A,
    )
    assert UUID(same).version == 5


def test_valid_source_document_manifest() -> None:
    validate_source_document_manifest(make_manifest())
    validate_source_document_manifest(make_manifest(ocr=True))


def test_manifest_rejects_wrong_document_instance_identity() -> None:
    value = replace(make_manifest(), source_document_instance_id=REPORT_ID)
    value = replace(
        value,
        source_snapshot_id=derive_sha256_id(source_document_manifest_identity_payload_to_dict(value)),
    )
    with pytest.raises(ValueError, match="source_document_instance_id"):
        validate_source_document_manifest(value)


def test_manifest_rejects_non_contiguous_pages_and_chunks() -> None:
    manifest = make_manifest()
    bad_page = replace(manifest.pages[0], page_number=2)
    bad = replace(manifest, pages=(bad_page,))
    bad = replace(bad, source_snapshot_id=derive_sha256_id(source_document_manifest_identity_payload_to_dict(bad)))
    with pytest.raises(ValueError, match="pages must be exactly"):
        validate_source_document_manifest(bad)

    bad_chunk = replace(manifest.pages[0].chunk_snapshots[0], chunk_ordinal=2)
    bad_page = replace(manifest.pages[0], chunk_snapshots=(bad_chunk,))
    bad = replace(manifest, pages=(bad_page,))
    bad = replace(bad, source_snapshot_id=derive_sha256_id(source_document_manifest_identity_payload_to_dict(bad)))
    with pytest.raises(ValueError, match="ordinals"):
        validate_source_document_manifest(bad)


def test_manifest_rejects_ocr_without_runtime_provenance() -> None:
    manifest = make_manifest(ocr=True)
    bad = replace(
        manifest,
        extraction_profile=replace(manifest.extraction_profile, tesseract_engine_version=None),
    )
    bad = replace(bad, source_snapshot_id=derive_sha256_id(source_document_manifest_identity_payload_to_dict(bad)))
    with pytest.raises(ValueError, match="tesseract_engine_version"):
        validate_source_document_manifest(bad)


def test_chunking_profile_constants_are_enforced() -> None:
    validate_chunking_profile(chunking_profile())
    with pytest.raises(ValueError, match="chunk_size"):
        validate_chunking_profile(replace(chunking_profile(), chunk_size=999))


def test_extraction_profile_constants_are_enforced() -> None:
    validate_extraction_profile(extraction_profile())
    with pytest.raises(ValueError, match="ocr_dpi"):
        validate_extraction_profile(replace(extraction_profile(), ocr_dpi=300))


@pytest.mark.parametrize(
    "binding_class",
    [
        BindingClass.FULL_CHAIN_BOUND,
        BindingClass.ANALYTICAL_TEXT_BOUND,
        BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT,
    ],
)
def test_valid_evidence_binding_classes(binding_class: BindingClass) -> None:
    validate_evidence_binding(make_binding(binding_class))


def test_evidence_binding_rejects_unbound_object() -> None:
    value = replace(
        make_binding(BindingClass.ANALYTICAL_TEXT_BOUND),
        binding_class=BindingClass.UNBOUND,
    )
    value = replace(value, evidence_binding_id=derive_sha256_id(evidence_binding_identity_payload_to_dict(value)))
    with pytest.raises(ValueError, match="non-UNBOUND"):
        validate_evidence_binding(value)


def test_full_chain_binding_requires_hash_equivalence_and_profiles() -> None:
    value = replace(make_binding(), bound_text_sha256=sha256_bytes(b"different"))
    value = replace(value, evidence_binding_id=derive_sha256_id(evidence_binding_identity_payload_to_dict(value)))
    with pytest.raises(ValueError, match="bound_text_sha256"):
        validate_evidence_binding(value)


def test_binding_class_and_text_role_cannot_drift() -> None:
    value = replace(make_binding(BindingClass.ANALYTICAL_TEXT_BOUND), bound_text_role=BoundTextRole.CHUNK_TEXT)
    value = replace(value, evidence_binding_id=derive_sha256_id(evidence_binding_identity_payload_to_dict(value)))
    with pytest.raises(ValueError, match="ANALYTICAL_TEXT_BOUND"):
        validate_evidence_binding(value)


def test_receipt_requires_unique_evidence_keys_and_canonical_id() -> None:
    receipt = make_receipt()
    validate_source_bound_analysis_receipt(receipt)
    duplicate = replace(receipt, verified_evidence=receipt.verified_evidence * 2)
    duplicate = replace(
        duplicate,
        source_bound_analysis_receipt_id=derive_sha256_id(
            source_bound_analysis_receipt_identity_payload_to_dict(duplicate)
        ),
    )
    with pytest.raises(ValueError, match="unique"):
        validate_source_bound_analysis_receipt(duplicate)


def test_projection_binding_structural_rules() -> None:
    validate_projection_evidence_binding_manifest(make_projection_binding())
    validate_projection_evidence_binding_manifest(make_projection_binding(BindingClass.UNBOUND))
    validate_projection_evidence_binding_manifest(
        make_projection_binding(BindingClass.ANALYTICAL_TEXT_BOUND)
    )


def test_projection_full_chain_requires_receipt() -> None:
    manifest = make_projection_binding()
    bad_entry = replace(manifest.entries[0], source_bound_analysis_receipt_id=None)
    bad = replace(manifest, entries=(bad_entry,))
    bad = replace(
        bad,
        projection_evidence_binding_manifest_id=derive_sha256_id(
            projection_evidence_binding_manifest_identity_payload_to_dict(bad)
        ),
    )
    with pytest.raises(ValueError, match="receipt"):
        validate_projection_evidence_binding_manifest(bad)


def test_projection_coverage_is_derived_not_advisory() -> None:
    manifest = make_projection_binding(BindingClass.UNBOUND)
    bad = replace(manifest, coverage=ProjectionBindingCoverage.MIXED_BINDING)
    bad = replace(
        bad,
        projection_evidence_binding_manifest_id=derive_sha256_id(
            projection_evidence_binding_manifest_identity_payload_to_dict(bad)
        ),
    )
    with pytest.raises(ValueError, match="coverage"):
        validate_projection_evidence_binding_manifest(bad)
