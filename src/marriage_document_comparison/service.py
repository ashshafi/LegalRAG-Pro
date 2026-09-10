from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
import re
from typing import Iterable

from marriage_document_intelligence import (
    MarriageComparisonStatus,
    MarriageDocumentIntelligenceRecord,
    MarriageFact,
    MarriageFactField,
    validate_marriage_document_record,
)

from .models import (
    MarriageDocumentComparisonResult,
    MarriageFieldComparison,
    MarriageSourceProfile,
    MarriageSourceValue,
)


class MarriageDocumentComparisonError(ValueError):
    pass


_FUZZY_FIELDS = {
    MarriageFactField.BRIDE_NAME,
    MarriageFactField.GROOM_NAME,
    MarriageFactField.BRIDE_FATHER_OR_GUARDIAN_NAME,
    MarriageFactField.GROOM_FATHER_NAME,
    MarriageFactField.PLACE_OF_MARRIAGE,
    MarriageFactField.MARRIAGE_LOCALITY_OR_DISTRICT,
    MarriageFactField.NIKAH_REGISTRAR_OR_SOLEMNISING_OFFICIAL,
    MarriageFactField.UNION_COUNCIL_OR_LOCAL_AUTHORITY,
    MarriageFactField.ISSUING_OR_REGISTERING_AUTHORITY,
    MarriageFactField.WITNESS_NAME,
}

# These describe the presentation/physical fragment rather than a marriage
# particular that should ordinarily be compared between independent records.
_NON_COMPARABLE_FIELDS = {
    MarriageFactField.DOCUMENT_LANGUAGE_MIX,
    MarriageFactField.HANDWRITTEN_ENTRY,
}

_TRANSLITERATION_THRESHOLD = 0.82


def _normalise(value: str) -> str:
    lowered = value.casefold()
    lowered = re.sub(r"[^\w]+", " ", lowered, flags=re.UNICODE)
    return " ".join(lowered.split())


def _record_provenances(
    record: MarriageDocumentIntelligenceRecord,
):
    values = [fact.provenance for fact in record.facts]
    values.extend(
        item.provenance
        for item in record.text_representations
    )
    return tuple(values)


def _source_blob_for_record(
    record: MarriageDocumentIntelligenceRecord,
) -> str:
    provenances = _record_provenances(record)
    if not provenances:
        raise MarriageDocumentComparisonError(
            "A record must carry at least one source provenance before comparison."
        )

    blobs = {
        provenance.original_blob_sha256
        for provenance in provenances
    }
    if len(blobs) != 1:
        raise MarriageDocumentComparisonError(
            "One marriage-document intelligence record spans multiple original source blobs."
        )
    return next(iter(blobs))


def build_source_profiles(
    records: Iterable[MarriageDocumentIntelligenceRecord],
) -> tuple[MarriageSourceProfile, ...]:
    material = tuple(records)
    if not material:
        raise MarriageDocumentComparisonError(
            "At least one marriage-document intelligence record is required."
        )

    grouped: dict[str, list[MarriageDocumentIntelligenceRecord]] = defaultdict(list)

    for record in material:
        validate_marriage_document_record(record)
        grouped[_source_blob_for_record(record)].append(record)

    profiles: list[MarriageSourceProfile] = []

    for blob_sha in sorted(grouped):
        group = grouped[blob_sha]
        provenances = tuple(
            provenance
            for record in group
            for provenance in _record_provenances(record)
        )

        facts: list[MarriageFact] = []
        seen_fact_keys: set[tuple[object, ...]] = set()

        for record in group:
            for fact in record.facts:
                key = (
                    fact.field.value,
                    fact.value,
                    fact.provenance.candidate_record_id,
                    fact.provenance.page_number,
                    fact.provenance.crop_name,
                )
                if key in seen_fact_keys:
                    continue
                seen_fact_keys.add(key)
                facts.append(fact)

        profiles.append(
            MarriageSourceProfile(
                source_blob_sha256=blob_sha,
                original_filenames=tuple(sorted({
                    value.original_filename
                    for value in provenances
                })),
                source_document_instance_ids=tuple(sorted({
                    value.source_document_instance_id
                    for value in provenances
                })),
                candidate_record_ids=tuple(sorted({
                    value.candidate_record_id
                    for value in provenances
                })),
                page_numbers=tuple(sorted({
                    value.page_number
                    for value in provenances
                })),
                crop_names=tuple(sorted({
                    value.crop_name
                    for value in provenances
                    if value.crop_name is not None
                })),
                facts=tuple(facts),
            )
        )

    return tuple(profiles)


def _profile_values(
    profile: MarriageSourceProfile,
    field: MarriageFactField,
) -> tuple[str, ...]:
    values: list[str] = []
    seen: set[str] = set()
    for fact in profile.facts:
        if fact.field is not field:
            continue
        if fact.value in seen:
            continue
        seen.add(fact.value)
        values.append(fact.value)
    return tuple(values)


def _source_value(
    profile: MarriageSourceProfile,
    values: tuple[str, ...],
) -> MarriageSourceValue:
    return MarriageSourceValue(
        source_blob_sha256=profile.source_blob_sha256,
        original_filenames=profile.original_filenames,
        values=values,
        candidate_record_ids=profile.candidate_record_ids,
    )


def _all_normalised_value_sets_equal(
    value_sets: list[tuple[str, ...]],
) -> bool:
    normalized = [
        tuple(sorted({_normalise(value) for value in values}))
        for values in value_sets
    ]
    return len(set(normalized)) == 1


def _single_values_are_close(
    value_sets: list[tuple[str, ...]],
) -> bool:
    if not value_sets or any(len(values) != 1 for values in value_sets):
        return False

    normalized = [_normalise(values[0]) for values in value_sets]
    first = normalized[0]
    return all(
        SequenceMatcher(None, first, other).ratio()
        >= _TRANSLITERATION_THRESHOLD
        for other in normalized[1:]
    )


def compare_marriage_document_records(
    records: Iterable[MarriageDocumentIntelligenceRecord],
) -> MarriageDocumentComparisonResult:
    profiles = build_source_profiles(records)

    if len(profiles) == 1:
        profile = profiles[0]
        issue = (
            "Only one underlying original source document is represented. "
            "Its approved candidates are treated as complementary fragments/crops, "
            "so a particular missing from one crop is not treated as a discrepancy."
        )
        action = (
            "Add an independent marriage record or certificate before drawing "
            "cross-document consistency conclusions."
        )
        return MarriageDocumentComparisonResult(
            source_profiles=profiles,
            field_comparisons=(),
            potential_issues=(issue,),
            next_professional_actions=(action,),
        )

    comparisons: list[MarriageFieldComparison] = []
    issues: list[str] = []
    actions: list[str] = []

    all_fields = sorted(
        {
            fact.field
            for profile in profiles
            for fact in profile.facts
            if fact.field not in _NON_COMPARABLE_FIELDS
        },
        key=lambda field: field.value,
    )

    for field in all_fields:
        values_by_profile = [
            _profile_values(profile, field)
            for profile in profiles
        ]
        present_count = sum(bool(values) for values in values_by_profile)

        source_values = tuple(
            _source_value(profile, values)
            for profile, values in zip(
                profiles,
                values_by_profile,
                strict=True,
            )
        )

        if present_count < len(profiles):
            status = MarriageComparisonStatus.UNRESOLVED_OR_UNCLEAR
            summary = (
                f"{field.value}: extracted in {present_count} of "
                f"{len(profiles)} independent source documents. "
                "Non-extraction is not proof that the source lacks the particular."
            )
        else:
            present_sets = [
                values
                for values in values_by_profile
                if values
            ]

            if _all_normalised_value_sets_equal(present_sets):
                status = MarriageComparisonStatus.EXACT_MATCH
                summary = (
                    f"{field.value}: the extracted value agrees across "
                    f"all {len(profiles)} independent source documents."
                )
            elif (
                field in _FUZZY_FIELDS
                and _single_values_are_close(present_sets)
            ):
                status = (
                    MarriageComparisonStatus
                    .LIKELY_TRANSLITERATION_VARIATION
                )
                summary = (
                    f"{field.value}: values are similar enough to be a likely "
                    "spelling/transliteration variation, subject to source review."
                )
            else:
                status = MarriageComparisonStatus.POSSIBLE_INCONSISTENCY
                summary = (
                    f"{field.value}: extracted values differ across independent "
                    "source documents and require professional/source verification."
                )

        comparisons.append(
            MarriageFieldComparison(
                field=field,
                status=status,
                source_values=source_values,
                summary=summary,
            )
        )

        if status is MarriageComparisonStatus.POSSIBLE_INCONSISTENCY:
            issues.append(summary)
            actions.append(
                f"Check {field.value} against the original documents and "
                "any authoritative registration record."
            )
        elif status is MarriageComparisonStatus.LIKELY_TRANSLITERATION_VARIATION:
            actions.append(
                f"Check the spelling/transliteration of {field.value} against "
                "identity documents and the original-language records."
            )
        elif status is MarriageComparisonStatus.UNRESOLVED_OR_UNCLEAR:
            actions.append(
                f"Check whether {field.value} is actually absent or merely "
                "not captured in the extracted fragment."
            )

    # Do not auto-escalate any comparison to "material contradiction".
    if any(
        comparison.status
        is MarriageComparisonStatus.POSSIBLE_INCONSISTENCY
        for comparison in comparisons
    ):
        issues.append(
            "Possible inconsistencies are extraction-level comparison flags only; "
            "MDI3 does not automatically decide that any difference is a material contradiction."
        )

    return MarriageDocumentComparisonResult(
        source_profiles=profiles,
        field_comparisons=tuple(comparisons),
        potential_issues=tuple(dict.fromkeys(issues)),
        next_professional_actions=tuple(dict.fromkeys(actions)),
    )
