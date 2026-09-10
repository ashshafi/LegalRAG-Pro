from __future__ import annotations

import hashlib
import json

MDI_SCHEMA_VERSION = "marriage-document-intelligence/1.0"
MDI_PRODUCT_CONTRACT_SHA256 = (
    "98a1c8d854aa500599db52aa66d6dfb27c10e0169d2c0798f7917818dae1e51"
)

SUPPORTED_DOCUMENT_TYPES = (
    "nikah_nama",
    "pakistani_marriage_registration_record",
    "union_council_marriage_record",
    "bilingual_pakistani_marriage_certificate",
    "marriage_affidavit_or_declaration",
)

SOLICITOR_RESULT_HEADINGS = (
    "Document",
    "Key marriage particulars",
    "Registration particulars",
    "Translation / transcription",
    "Comparison",
    "Potential issues",
    "Source",
    "Next professional action",
)

FACT_FIELDS = (
    "bride_name",
    "groom_name",
    "bride_father_or_guardian_name",
    "groom_father_name",
    "other_identifying_particular",
    "marriage_date",
    "place_of_marriage",
    "marriage_locality_or_district",
    "nikah_registrar_or_solemnising_official",
    "registration_date",
    "registration_number",
    "union_council_or_local_authority",
    "issuing_or_registering_authority",
    "certificate_or_record_identifier",
    "mehr_prompt_amount",
    "mehr_deferred_amount",
    "mehr_other_terms",
    "special_condition",
    "witness_name",
    "witness_identifying_particular",
    "stamp",
    "seal",
    "signature",
    "handwritten_entry",
    "overwriting_or_correction",
    "additional_date",
    "document_language_mix",
)

DERIVATION_KINDS = (
    "native_text",
    "ocr_derived",
    "ai_translated",
    "inferred",
)

TEXT_REPRESENTATION_KINDS = (
    "AI transcription",
    "AI-assisted English translation",
    "plain-English explanation",
    "certified translation",
)

COMPARISON_STATUSES = (
    "exact match",
    "likely transliteration/spelling variation",
    "possible inconsistency",
    "material contradiction",
    "unresolved/unclear",
)

PROHIBITED_AUTOMATIC_CONCLUSIONS = (
    "validity of the marriage under Pakistani law",
    "recognition under English law",
    "authenticity of a disputed document",
    "fraud",
    "forgery",
)

MARRIAGE_DOCUMENT_DOMAIN_CONTRACT = {
    "schema": MDI_SCHEMA_VERSION,
    "product_contract_sha256": MDI_PRODUCT_CONTRACT_SHA256,
    "governing_principle": "The original document remains the evidence.",
    "supported_document_types": SUPPORTED_DOCUMENT_TYPES,
    "fact_fields": FACT_FIELDS,
    "fact_provenance_required": (
        "source_document_instance_id",
        "source_snapshot_id",
        "original_filename",
        "original_blob_sha256",
        "page_number",
        "candidate_record_id",
        "transcription_sha256",
        "review_event_id",
        "derivation_kind",
        "quality_note",
    ),
    "optional_exact_region_provenance": (
        "binding_id",
        "publication_receipt_id",
        "crop_name",
        "bbox",
    ),
    "text_representation_kinds": TEXT_REPRESENTATION_KINDS,
    "comparison_statuses": COMPARISON_STATUSES,
    "solicitor_result_headings": SOLICITOR_RESULT_HEADINGS,
    "prohibited_automatic_conclusions": PROHIBITED_AUTOMATIC_CONCLUSIONS,
    "translation_rule": (
        "LegalRAG-produced text must not be represented as a certified translation."
    ),
    "zero_hit_rule": (
        "A zero-result search is discovery-only and is never proof that a fact is absent."
    ),
}


def _canonical_bytes() -> bytes:
    return json.dumps(
        MARRIAGE_DOCUMENT_DOMAIN_CONTRACT,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


MARRIAGE_DOCUMENT_DOMAIN_CONTRACT_SHA256 = hashlib.sha256(
    _canonical_bytes()
).hexdigest()
