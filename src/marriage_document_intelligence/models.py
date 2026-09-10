from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .contract import MDI_SCHEMA_VERSION


class MarriageDocumentType(str, Enum):
    NIKAH_NAMA = "nikah_nama"
    PAKISTANI_MARRIAGE_REGISTRATION_RECORD = (
        "pakistani_marriage_registration_record"
    )
    UNION_COUNCIL_MARRIAGE_RECORD = "union_council_marriage_record"
    BILINGUAL_PAKISTANI_MARRIAGE_CERTIFICATE = (
        "bilingual_pakistani_marriage_certificate"
    )
    MARRIAGE_AFFIDAVIT_OR_DECLARATION = "marriage_affidavit_or_declaration"


class MarriageFactField(str, Enum):
    BRIDE_NAME = "bride_name"
    GROOM_NAME = "groom_name"
    BRIDE_FATHER_OR_GUARDIAN_NAME = "bride_father_or_guardian_name"
    GROOM_FATHER_NAME = "groom_father_name"
    OTHER_IDENTIFYING_PARTICULAR = "other_identifying_particular"

    MARRIAGE_DATE = "marriage_date"
    PLACE_OF_MARRIAGE = "place_of_marriage"
    MARRIAGE_LOCALITY_OR_DISTRICT = "marriage_locality_or_district"
    NIKAH_REGISTRAR_OR_SOLEMNISING_OFFICIAL = (
        "nikah_registrar_or_solemnising_official"
    )

    REGISTRATION_DATE = "registration_date"
    REGISTRATION_NUMBER = "registration_number"
    UNION_COUNCIL_OR_LOCAL_AUTHORITY = "union_council_or_local_authority"
    ISSUING_OR_REGISTERING_AUTHORITY = "issuing_or_registering_authority"
    CERTIFICATE_OR_RECORD_IDENTIFIER = "certificate_or_record_identifier"

    MEHR_PROMPT_AMOUNT = "mehr_prompt_amount"
    MEHR_DEFERRED_AMOUNT = "mehr_deferred_amount"
    MEHR_OTHER_TERMS = "mehr_other_terms"
    SPECIAL_CONDITION = "special_condition"

    WITNESS_NAME = "witness_name"
    WITNESS_IDENTIFYING_PARTICULAR = "witness_identifying_particular"

    STAMP = "stamp"
    SEAL = "seal"
    SIGNATURE = "signature"
    HANDWRITTEN_ENTRY = "handwritten_entry"
    OVERWRITING_OR_CORRECTION = "overwriting_or_correction"
    ADDITIONAL_DATE = "additional_date"
    DOCUMENT_LANGUAGE_MIX = "document_language_mix"


class MarriageFactDerivationKind(str, Enum):
    NATIVE_TEXT = "native_text"
    OCR_DERIVED = "ocr_derived"
    AI_TRANSLATED = "ai_translated"
    INFERRED = "inferred"


class MarriageTextRepresentationKind(str, Enum):
    AI_TRANSCRIPTION = "AI transcription"
    AI_ASSISTED_ENGLISH_TRANSLATION = "AI-assisted English translation"
    PLAIN_ENGLISH_EXPLANATION = "plain-English explanation"
    CERTIFIED_TRANSLATION = "certified translation"


class MarriageComparisonStatus(str, Enum):
    EXACT_MATCH = "exact match"
    LIKELY_TRANSLITERATION_VARIATION = (
        "likely transliteration/spelling variation"
    )
    POSSIBLE_INCONSISTENCY = "possible inconsistency"
    MATERIAL_CONTRADICTION = "material contradiction"
    UNRESOLVED_OR_UNCLEAR = "unresolved/unclear"


@dataclass(frozen=True)
class SourceRegion:
    left: int
    top: int
    right: int
    bottom: int


@dataclass(frozen=True)
class MarriageFactProvenance:
    source_document_instance_id: str
    source_snapshot_id: str
    original_filename: str
    original_blob_sha256: str
    page_number: int
    candidate_record_id: str
    transcription_sha256: str
    review_event_id: str
    derivation_kind: MarriageFactDerivationKind
    quality_note: str
    binding_id: str | None = None
    publication_receipt_id: str | None = None
    crop_name: str | None = None
    bbox: SourceRegion | None = None


@dataclass(frozen=True)
class MarriageFact:
    field: MarriageFactField
    value: str
    provenance: MarriageFactProvenance


@dataclass(frozen=True)
class MarriageTextRepresentation:
    kind: MarriageTextRepresentationKind
    text: str
    provenance: MarriageFactProvenance
    produced_by_legalrag: bool


@dataclass(frozen=True)
class MarriageComparisonNote:
    status: MarriageComparisonStatus
    summary: str
    related_fields: tuple[MarriageFactField, ...] = ()


@dataclass(frozen=True)
class MarriagePotentialIssue:
    summary: str
    verification_required: bool = True


@dataclass(frozen=True)
class MarriageDocumentIntelligenceRecord:
    schema_version: str
    document_type: MarriageDocumentType
    document_label: str
    facts: tuple[MarriageFact, ...]
    text_representations: tuple[MarriageTextRepresentation, ...] = ()
    comparisons: tuple[MarriageComparisonNote, ...] = ()
    potential_issues: tuple[MarriagePotentialIssue, ...] = ()
    next_professional_actions: tuple[str, ...] = ()

    @classmethod
    def create(
        cls,
        *,
        document_type: MarriageDocumentType,
        document_label: str,
        facts: tuple[MarriageFact, ...],
        text_representations: tuple[MarriageTextRepresentation, ...] = (),
        comparisons: tuple[MarriageComparisonNote, ...] = (),
        potential_issues: tuple[MarriagePotentialIssue, ...] = (),
        next_professional_actions: tuple[str, ...] = (),
    ) -> "MarriageDocumentIntelligenceRecord":
        return cls(
            schema_version=MDI_SCHEMA_VERSION,
            document_type=document_type,
            document_label=document_label,
            facts=facts,
            text_representations=text_representations,
            comparisons=comparisons,
            potential_issues=potential_issues,
            next_professional_actions=next_professional_actions,
        )


@dataclass(frozen=True)
class SolicitorSourceReference:
    original_filename: str
    page_number: int
    crop_name: str | None
    bbox: SourceRegion | None


@dataclass(frozen=True)
class SolicitorMarriageDocumentResult:
    document: str
    key_marriage_particulars: tuple[MarriageFact, ...]
    registration_particulars: tuple[MarriageFact, ...]
    translation_or_transcription: tuple[MarriageTextRepresentation, ...]
    comparison: tuple[MarriageComparisonNote, ...]
    potential_issues: tuple[MarriagePotentialIssue, ...]
    source: tuple[SolicitorSourceReference, ...]
    next_professional_action: tuple[str, ...]
