from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any, Mapping, Protocol

from marriage_document_intelligence import (
    FACT_FIELDS,
    SUPPORTED_DOCUMENT_TYPES,
    MarriageDocumentIntelligenceRecord,
    MarriageDocumentType,
    MarriageFact,
    MarriageFactDerivationKind,
    MarriageFactField,
    MarriageFactProvenance,
    MarriagePotentialIssue,
    MarriageTextRepresentation,
    MarriageTextRepresentationKind,
    SourceRegion,
    validate_marriage_document_record,
)
from targeted_candidate_search_activation.validation import (
    validate_targeted_candidate_governance_gate,
)


MARRIAGE_FACT_EXTRACTION_SCHEMA_VERSION = "marriage-fact-extraction/1.0"

DERIVATION_KINDS = (
    "native_text",
    "ocr_derived",
    "ai_translated",
    "inferred",
)

_TOP_LEVEL_KEYS = {
    "document_type",
    "document_label",
    "facts",
    "ai_assisted_english_translation",
    "plain_english_explanation",
    "potential_issues",
    "next_professional_actions",
}

_FACT_KEYS = {
    "field",
    "value",
    "derivation_kind",
    "quality_note",
}

_PROHIBITED_CONCLUSIONS = (
    "the marriage is valid",
    "the marriage is invalid",
    "recognised under english law",
    "recognized under english law",
    "the document is authentic",
    "the document is forged",
    "fraud was committed",
    "committed fraud",
)


_NUMBERED_NIKAH_CONDITION_NUMBERS = ("18", "19", "20", "21", "22")

# Numbered form items are normally transcribed at the start of a line. Match
# every numbered item so item 22 is correctly bounded by item 23 when present.
_NUMBERED_NIKAH_ITEM = re.compile(
    r"(?m)^[ \t]*(\d{1,2})(?:[ \t]*[\u06d4.):\-][ \t]*|[ \t]+)"
)


def _ascii_decimal_digits(value: str) -> str | None:
    digits = []
    for character in value:
        try:
            digits.append(str(unicodedata.decimal(character)))
        except (TypeError, ValueError):
            return None
    return "".join(digits)


def _nikah_condition_number(value: str) -> str | None:
    match = re.match(r"\s*(\d{1,2})(?:\D|$)", value)
    if match is None:
        return None
    number = _ascii_decimal_digits(match.group(1))
    if number not in _NUMBERED_NIKAH_CONDITION_NUMBERS:
        return None
    return number


def _approved_numbered_nikah_condition_payloads(
    transcription_text: str,
) -> tuple[dict[str, str], ...]:
    # Recover items 18-22 directly from one approved transcription.
    matches = list(_NUMBERED_NIKAH_ITEM.finditer(transcription_text))
    recovered: dict[str, dict[str, str]] = {}

    for index, match in enumerate(matches):
        raw_number = match.group(1)
        number = _ascii_decimal_digits(raw_number)
        if (
            number not in _NUMBERED_NIKAH_CONDITION_NUMBERS
            or number in recovered
        ):
            continue

        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(transcription_text)
        )
        segment = transcription_text[match.start():end].strip()
        segment = " ".join(segment.split())
        if not segment:
            continue

        # Preserve the approved source wording while normalising only the
        # leading item number to ASCII so downstream solicitor projection is
        # independent of whether the approved transcription uses 18 or \u06f1\u06f8.
        if segment.startswith(raw_number):
            segment = number + segment[len(raw_number):]

        folded = segment.casefold()
        answer_is_no = (
            "\u0646\u06c1\u06cc\u06ba" in segment
            or re.search(r"(?:^|\W)no(?:\W|$)", folded) is not None
        )
        is_unclear = (
            "[unclear]" in folded
            or "unclear" in folded
        )

        notes = [
            "Recovered deterministically from the approved transcription.",
            "Item number normalised from the approved transcription to ASCII digits.",
        ]
        if answer_is_no:
            notes.append("Recorded answer is 'No'.")
        else:
            notes.append(
                "The recorded answer should be checked against the original image."
            )
        if is_unclear:
            notes.append(
                "Part of this item is unclear and should be checked against the original image."
            )

        recovered[number] = {
            "field": "special_condition",
            "value": segment,
            "derivation_kind": "ocr_derived",
            "quality_note": " ".join(notes),
        }

    return tuple(
        recovered[number]
        for number in _NUMBERED_NIKAH_CONDITION_NUMBERS
        if number in recovered
    )


def _reconcile_numbered_nikah_conditions(
    payload: dict[str, Any],
    transcription_text: str,
) -> dict[str, Any]:
    # General facts remain model-extracted. Numbered standard form items are
    # replaced with direct recovery from the approved transcription.
    deterministic = _approved_numbered_nikah_condition_payloads(
        transcription_text
    )
    if not deterministic:
        return payload

    deterministic_numbers = {
        _nikah_condition_number(item["value"])
        for item in deterministic
    }

    retained = []
    for item in payload["facts"]:
        if item["field"] != "special_condition":
            retained.append(item)
            continue

        number = _nikah_condition_number(item["value"])
        if number not in deterministic_numbers:
            retained.append(item)

    reconciled = dict(payload)
    reconciled["facts"] = retained + [
        dict(item)
        for item in deterministic
    ]
    return reconciled


class MarriageFactExtractionError(ValueError):
    pass


class MarriageFactExtractionProvider(Protocol):
    def extract(
        self,
        *,
        model: str,
        transcription_text: str,
    ) -> Mapping[str, Any]:
        ...


def build_marriage_fact_extraction_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(_TOP_LEVEL_KEYS),
        "properties": {
            "document_type": {
                "type": "string",
                "enum": list(SUPPORTED_DOCUMENT_TYPES),
            },
            "document_label": {
                "type": "string",
                "minLength": 1,
            },
            "facts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": sorted(_FACT_KEYS),
                    "properties": {
                        "field": {
                            "type": "string",
                            "enum": list(FACT_FIELDS),
                        },
                        "value": {
                            "type": "string",
                            "minLength": 1,
                        },
                        "derivation_kind": {
                            "type": "string",
                            "enum": list(DERIVATION_KINDS),
                        },
                        "quality_note": {
                            "type": "string",
                            "minLength": 1,
                        },
                    },
                },
            },
            "ai_assisted_english_translation": {
                "type": ["string", "null"],
            },
            "plain_english_explanation": {
                "type": ["string", "null"],
            },
            "potential_issues": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            },
            "next_professional_actions": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            },
        },
    }


def build_marriage_fact_extraction_prompt(
    transcription_text: str,
) -> str:
    if not isinstance(transcription_text, str) or not transcription_text.strip():
        raise MarriageFactExtractionError(
            "Approved transcription text must be non-empty."
        )

    return f"""
You are extracting factual particulars from one APPROVED Urdu-derived
Pakistani marriage-document transcription for a solicitor in England & Wales.

Use ONLY the transcription supplied below. Do not guess missing facts.

Supported document types:
{", ".join(SUPPORTED_DOCUMENT_TYPES)}

Permitted structured fact fields:
{", ".join(FACT_FIELDS)}

Rules:
1. Omit a fact if the transcription does not support a value.
2. Preserve names, dates, numbers and authorities as faithfully as possible.
3. Use ocr_derived for facts directly represented in the approved transcription.
4. Use ai_translated only when the value itself is an English translation.
5. Use inferred only where semantic interpretation is unavoidable.
6. quality_note must identify legibility, ambiguity or normalisation.
7. Do not decide whether the marriage is legally valid or recognised.
8. Do not decide authenticity, fraud or forgery.
9. Potential issues are matters for verification, not conclusions.
10. AI translation is not a certified translation.
11. Plain-English explanation must remain descriptive, not a legal conclusion.
12. If the document family is uncertain, choose the closest supported family
    and record that uncertainty under potential_issues.
13. For Nikah Nama form items 18, 19, 20, 21 and 22, emit one
    special_condition fact for every numbered item explicitly present in the
    transcription. Preserve the item number and source text. Do not silently
    omit a supported numbered item.

APPROVED TRANSCRIPTION
----------------------
{transcription_text}
""".strip()


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarriageFactExtractionError(
            f"{name} must be non-empty text."
        )
    return value.strip()


def _optional_text(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _text(value, name)


def _reject_conclusive_language(value: str) -> None:
    normalized = " ".join(value.lower().split())
    for phrase in _PROHIBITED_CONCLUSIONS:
        if phrase in normalized:
            raise MarriageFactExtractionError(
                "Extraction output contains a prohibited conclusive legal statement."
            )


def validate_extraction_payload(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise MarriageFactExtractionError(
            "Extraction payload must be an object."
        )

    value = dict(payload)
    if set(value) != _TOP_LEVEL_KEYS:
        raise MarriageFactExtractionError(
            "Extraction payload has unexpected or missing top-level fields."
        )

    document_type = _text(value["document_type"], "document_type")
    if document_type not in SUPPORTED_DOCUMENT_TYPES:
        raise MarriageFactExtractionError(
            "Unsupported marriage document type."
        )

    document_label = _text(value["document_label"], "document_label")

    raw_facts = value["facts"]
    if not isinstance(raw_facts, list):
        raise MarriageFactExtractionError("facts must be a list.")

    facts: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for index, raw in enumerate(raw_facts):
        if not isinstance(raw, Mapping):
            raise MarriageFactExtractionError(
                f"facts[{index}] must be an object."
            )

        item = dict(raw)
        if set(item) != _FACT_KEYS:
            raise MarriageFactExtractionError(
                f"facts[{index}] has unexpected or missing fields."
            )

        field = _text(item["field"], f"facts[{index}].field")
        if field not in FACT_FIELDS:
            raise MarriageFactExtractionError(
                f"facts[{index}] uses an unsupported field."
            )

        fact_value = _text(item["value"], f"facts[{index}].value")
        derivation = _text(
            item["derivation_kind"],
            f"facts[{index}].derivation_kind",
        )
        if derivation not in DERIVATION_KINDS:
            raise MarriageFactExtractionError(
                f"facts[{index}] uses an unsupported derivation kind."
            )

        quality_note = _text(
            item["quality_note"],
            f"facts[{index}].quality_note",
        )

        exact = (field, fact_value)
        if exact in seen:
            raise MarriageFactExtractionError(
                "Extraction payload contains an exact duplicate fact."
            )
        seen.add(exact)

        facts.append(
            {
                "field": field,
                "value": fact_value,
                "derivation_kind": derivation,
                "quality_note": quality_note,
            }
        )

    translation = _optional_text(
        value["ai_assisted_english_translation"],
        "ai_assisted_english_translation",
    )
    explanation = _optional_text(
        value["plain_english_explanation"],
        "plain_english_explanation",
    )

    if translation is not None:
        _reject_conclusive_language(translation)
    if explanation is not None:
        _reject_conclusive_language(explanation)

    raw_issues = value["potential_issues"]
    if not isinstance(raw_issues, list):
        raise MarriageFactExtractionError(
            "potential_issues must be a list."
        )
    issues = [_text(item, "potential_issues[]") for item in raw_issues]

    raw_actions = value["next_professional_actions"]
    if not isinstance(raw_actions, list):
        raise MarriageFactExtractionError(
            "next_professional_actions must be a list."
        )
    actions = [
        _text(item, "next_professional_actions[]")
        for item in raw_actions
    ]

    for advisory in (*issues, *actions):
        _reject_conclusive_language(advisory)

    return {
        "document_type": document_type,
        "document_label": document_label,
        "facts": facts,
        "ai_assisted_english_translation": translation,
        "plain_english_explanation": explanation,
        "potential_issues": issues,
        "next_professional_actions": actions,
    }


def _region(binding: Any) -> SourceRegion:
    values = tuple(binding.bbox)
    if len(values) != 4:
        raise MarriageFactExtractionError(
            "Targeted candidate bbox must contain four coordinates."
        )
    return SourceRegion(
        left=int(values[0]),
        top=int(values[1]),
        right=int(values[2]),
        bottom=int(values[3]),
    )


def _provenance(
    *,
    candidate: Any,
    binding: Any,
    receipt: Any,
    review_projection: Any,
    derivation_kind: MarriageFactDerivationKind,
    quality_note: str,
) -> MarriageFactProvenance:
    return MarriageFactProvenance(
        source_document_instance_id=candidate.source_document_instance_id,
        source_snapshot_id=candidate.source_snapshot_id,
        original_filename=candidate.original_filename,
        original_blob_sha256=candidate.original_blob_sha256,
        page_number=candidate.page_number,
        candidate_record_id=candidate.record_id,
        transcription_sha256=candidate.transcription_sha256,
        review_event_id=review_projection.latest_event_id,
        derivation_kind=derivation_kind,
        quality_note=quality_note,
        binding_id=binding.binding_id,
        publication_receipt_id=receipt.receipt_id,
        crop_name=binding.crop_name,
        bbox=_region(binding),
    )


def extract_marriage_document_intelligence(
    *,
    candidate: Any,
    transcription_text: str,
    binding: Any,
    receipt: Any,
    review_projection: Any,
    provider: MarriageFactExtractionProvider,
    model: str,
) -> MarriageDocumentIntelligenceRecord:
    if not isinstance(model, str) or not model.strip():
        raise MarriageFactExtractionError(
            "Extraction model must be non-empty text."
        )

    # Mandatory upstream governance gate before any provider call.
    validate_targeted_candidate_governance_gate(
        candidate=candidate,
        document=transcription_text,
        binding=binding,
        receipt=receipt,
        review_projection=review_projection,
    )

    raw = provider.extract(
        model=model,
        transcription_text=transcription_text,
    )
    payload = validate_extraction_payload(raw)
    payload = _reconcile_numbered_nikah_conditions(
        payload,
        transcription_text,
    )

    facts = tuple(
        MarriageFact(
            field=MarriageFactField(item["field"]),
            value=item["value"],
            provenance=_provenance(
                candidate=candidate,
                binding=binding,
                receipt=receipt,
                review_projection=review_projection,
                derivation_kind=MarriageFactDerivationKind(
                    item["derivation_kind"]
                ),
                quality_note=item["quality_note"],
            ),
        )
        for item in payload["facts"]
    )

    representations: list[MarriageTextRepresentation] = []

    translation = payload["ai_assisted_english_translation"]
    if translation is not None:
        representations.append(
            MarriageTextRepresentation(
                kind=(
                    MarriageTextRepresentationKind
                    .AI_ASSISTED_ENGLISH_TRANSLATION
                ),
                text=translation,
                provenance=_provenance(
                    candidate=candidate,
                    binding=binding,
                    receipt=receipt,
                    review_projection=review_projection,
                    derivation_kind=MarriageFactDerivationKind.AI_TRANSLATED,
                    quality_note=(
                        "AI-assisted English translation of the approved "
                        "transcription; not a certified translation."
                    ),
                ),
                produced_by_legalrag=True,
            )
        )

    explanation = payload["plain_english_explanation"]
    if explanation is not None:
        representations.append(
            MarriageTextRepresentation(
                kind=MarriageTextRepresentationKind.PLAIN_ENGLISH_EXPLANATION,
                text=explanation,
                provenance=_provenance(
                    candidate=candidate,
                    binding=binding,
                    receipt=receipt,
                    review_projection=review_projection,
                    derivation_kind=MarriageFactDerivationKind.INFERRED,
                    quality_note=(
                        "AI plain-English explanation grounded in the approved "
                        "transcription; professional review required."
                    ),
                ),
                produced_by_legalrag=True,
            )
        )

    record = MarriageDocumentIntelligenceRecord.create(
        document_type=MarriageDocumentType(payload["document_type"]),
        document_label=payload["document_label"],
        facts=facts,
        text_representations=tuple(representations),
        comparisons=(),
        potential_issues=tuple(
            MarriagePotentialIssue(summary=value)
            for value in payload["potential_issues"]
        ),
        next_professional_actions=tuple(
            payload["next_professional_actions"]
        ),
    )

    validate_marriage_document_record(record)
    return record


def extraction_record_receipt(
    record: MarriageDocumentIntelligenceRecord,
) -> dict[str, Any]:
    validate_marriage_document_record(record)

    payload = {
        "schema": MARRIAGE_FACT_EXTRACTION_SCHEMA_VERSION,
        "document_type": record.document_type.value,
        "document_label": record.document_label,
        "facts": [
            {
                "field": fact.field.value,
                "value": fact.value,
                "candidate_record_id": fact.provenance.candidate_record_id,
                "transcription_sha256": fact.provenance.transcription_sha256,
                "review_event_id": fact.provenance.review_event_id,
                "derivation_kind": fact.provenance.derivation_kind.value,
                "quality_note": fact.provenance.quality_note,
            }
            for fact in record.facts
        ],
        "text_representation_kinds": [
            value.kind.value
            for value in record.text_representations
        ],
        "potential_issues": [
            value.summary
            for value in record.potential_issues
        ],
        "next_professional_actions": list(
            record.next_professional_actions
        ),
    }

    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return {
        "payload": payload,
        "utf8_bytes": len(canonical),
        "sha256": hashlib.sha256(canonical).hexdigest(),
    }
