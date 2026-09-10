from __future__ import annotations

import re

from .contract import MDI_SCHEMA_VERSION
from .models import (
    MarriageDocumentIntelligenceRecord,
    MarriageFact,
    MarriageFactProvenance,
    MarriageTextRepresentation,
    MarriageTextRepresentationKind,
    SourceRegion,
)

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_SHA256_ID = re.compile(r"^sha256:[0-9a-f]{64}$")


class MarriageDocumentIntelligenceError(ValueError):
    pass


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarriageDocumentIntelligenceError(
            f"{field_name} must be non-empty text."
        )
    return value


def _require_sha256_hex(value: object, field_name: str) -> None:
    text = _require_text(value, field_name)
    if not _SHA256_HEX.fullmatch(text):
        raise MarriageDocumentIntelligenceError(
            f"{field_name} must be a lower-case SHA256 hex digest."
        )


def _require_sha256_id(value: object, field_name: str) -> None:
    text = _require_text(value, field_name)
    if not _SHA256_ID.fullmatch(text):
        raise MarriageDocumentIntelligenceError(
            f"{field_name} must be a sha256:<hex> identity."
        )


def validate_source_region(region: SourceRegion) -> None:
    if not isinstance(region, SourceRegion):
        raise MarriageDocumentIntelligenceError(
            "bbox must be a SourceRegion."
        )

    values = (region.left, region.top, region.right, region.bottom)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise MarriageDocumentIntelligenceError(
            "SourceRegion coordinates must be integers."
        )

    if region.left < 0 or region.top < 0:
        raise MarriageDocumentIntelligenceError(
            "SourceRegion origin must be non-negative."
        )

    if region.right <= region.left or region.bottom <= region.top:
        raise MarriageDocumentIntelligenceError(
            "SourceRegion must have positive width and height."
        )


def validate_provenance(provenance: MarriageFactProvenance) -> None:
    if not isinstance(provenance, MarriageFactProvenance):
        raise MarriageDocumentIntelligenceError(
            "Fact provenance is required."
        )

    _require_text(
        provenance.source_document_instance_id,
        "source_document_instance_id",
    )
    _require_text(provenance.source_snapshot_id, "source_snapshot_id")
    _require_text(provenance.original_filename, "original_filename")
    _require_sha256_hex(
        provenance.original_blob_sha256,
        "original_blob_sha256",
    )

    if (
        isinstance(provenance.page_number, bool)
        or not isinstance(provenance.page_number, int)
        or provenance.page_number <= 0
    ):
        raise MarriageDocumentIntelligenceError(
            "page_number must be a positive integer."
        )

    _require_sha256_id(
        provenance.candidate_record_id,
        "candidate_record_id",
    )
    _require_sha256_hex(
        provenance.transcription_sha256,
        "transcription_sha256",
    )
    _require_sha256_id(provenance.review_event_id, "review_event_id")
    _require_text(provenance.quality_note, "quality_note")

    if provenance.binding_id is not None:
        _require_sha256_id(provenance.binding_id, "binding_id")

    if provenance.publication_receipt_id is not None:
        _require_sha256_id(
            provenance.publication_receipt_id,
            "publication_receipt_id",
        )

    region_values = (
        provenance.crop_name,
        provenance.bbox,
        provenance.binding_id,
        provenance.publication_receipt_id,
    )
    any_region = any(value is not None for value in region_values)
    all_region = all(value is not None for value in region_values)

    if any_region and not all_region:
        raise MarriageDocumentIntelligenceError(
            "Exact crop provenance must provide crop_name, bbox, binding_id "
            "and publication_receipt_id together."
        )

    if provenance.crop_name is not None:
        _require_text(provenance.crop_name, "crop_name")

    if provenance.bbox is not None:
        validate_source_region(provenance.bbox)


def validate_fact(fact: MarriageFact) -> None:
    if not isinstance(fact, MarriageFact):
        raise MarriageDocumentIntelligenceError(
            "facts must contain MarriageFact values."
        )
    _require_text(fact.value, f"fact[{fact.field.value}].value")
    validate_provenance(fact.provenance)


def validate_text_representation(
    representation: MarriageTextRepresentation,
) -> None:
    if not isinstance(representation, MarriageTextRepresentation):
        raise MarriageDocumentIntelligenceError(
            "text_representations must contain MarriageTextRepresentation values."
        )

    _require_text(representation.text, "text_representation.text")
    validate_provenance(representation.provenance)

    if (
        representation.kind
        is MarriageTextRepresentationKind.CERTIFIED_TRANSLATION
        and representation.produced_by_legalrag
    ):
        raise MarriageDocumentIntelligenceError(
            "LegalRAG-produced text must not be represented as a certified translation."
        )


def validate_marriage_document_record(
    record: MarriageDocumentIntelligenceRecord,
) -> None:
    if not isinstance(record, MarriageDocumentIntelligenceRecord):
        raise MarriageDocumentIntelligenceError(
            "record must be MarriageDocumentIntelligenceRecord."
        )

    if record.schema_version != MDI_SCHEMA_VERSION:
        raise MarriageDocumentIntelligenceError(
            "Marriage-document schema version mismatch."
        )

    _require_text(record.document_label, "document_label")

    seen_exact: set[tuple[str, str, str, int]] = set()
    for fact in record.facts:
        validate_fact(fact)
        key = (
            fact.field.value,
            fact.value,
            fact.provenance.candidate_record_id,
            fact.provenance.page_number,
        )
        if key in seen_exact:
            raise MarriageDocumentIntelligenceError(
                "Exact duplicate marriage fact is not permitted."
            )
        seen_exact.add(key)

    for representation in record.text_representations:
        validate_text_representation(representation)

    for comparison in record.comparisons:
        _require_text(comparison.summary, "comparison.summary")

    for issue in record.potential_issues:
        _require_text(issue.summary, "potential_issue.summary")

    for action in record.next_professional_actions:
        _require_text(action, "next_professional_action")
