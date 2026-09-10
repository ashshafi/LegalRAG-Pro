from __future__ import annotations

from .models import (
    MarriageDocumentIntelligenceRecord,
    MarriageFactField,
    SolicitorMarriageDocumentResult,
    SolicitorSourceReference,
)
from .validation import validate_marriage_document_record

_REGISTRATION_FIELDS = {
    MarriageFactField.REGISTRATION_DATE,
    MarriageFactField.REGISTRATION_NUMBER,
    MarriageFactField.UNION_COUNCIL_OR_LOCAL_AUTHORITY,
    MarriageFactField.ISSUING_OR_REGISTERING_AUTHORITY,
    MarriageFactField.CERTIFICATE_OR_RECORD_IDENTIFIER,
}

_DOCUMENT_TYPE_LABELS = {
    "nikah_nama": "Nikah Nama",
    "pakistani_marriage_registration_record": "Pakistani marriage registration record",
    "union_council_marriage_record": "Union Council marriage record",
    "bilingual_pakistani_marriage_certificate": "Bilingual Pakistani marriage certificate",
    "marriage_affidavit_or_declaration": "Marriage affidavit or declaration",
}


def build_solicitor_marriage_document_result(
    record: MarriageDocumentIntelligenceRecord,
) -> SolicitorMarriageDocumentResult:
    validate_marriage_document_record(record)

    registration = tuple(
        fact
        for fact in record.facts
        if fact.field in _REGISTRATION_FIELDS
    )
    key_particulars = tuple(
        fact
        for fact in record.facts
        if fact.field not in _REGISTRATION_FIELDS
    )

    seen_sources: set[tuple[object, ...]] = set()
    sources: list[SolicitorSourceReference] = []

    for fact in record.facts:
        provenance = fact.provenance
        key = (
            provenance.original_filename,
            provenance.page_number,
            provenance.crop_name,
            provenance.bbox,
        )
        if key in seen_sources:
            continue
        seen_sources.add(key)
        sources.append(
            SolicitorSourceReference(
                original_filename=provenance.original_filename,
                page_number=provenance.page_number,
                crop_name=provenance.crop_name,
                bbox=provenance.bbox,
            )
        )

    document_type = _DOCUMENT_TYPE_LABELS[record.document_type.value]
    document = f"{document_type} â€” {record.document_label}"

    return SolicitorMarriageDocumentResult(
        document=document,
        key_marriage_particulars=key_particulars,
        registration_particulars=registration,
        translation_or_transcription=record.text_representations,
        comparison=record.comparisons,
        potential_issues=record.potential_issues,
        source=tuple(sources),
        next_professional_action=record.next_professional_actions,
    )
