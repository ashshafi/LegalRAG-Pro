from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from marriage_document_comparison import (
    MarriageDocumentComparisonResult,
    compare_marriage_document_records,
)
from marriage_document_intelligence import (
    MarriageDocumentIntelligenceRecord,
    MarriageFact,
    MarriageFactField,
    validate_marriage_document_record,
)


@dataclass(frozen=True)
class WorkspaceDisplayItem:
    label: str
    value: str
    note: str | None = None


@dataclass(frozen=True)
class WorkspaceSpecialCondition:
    item_number: str
    subject: str
    recorded_answer: str
    note: str | None = None


@dataclass(frozen=True)
class WorkspaceSource:
    filename: str
    pages: tuple[int, ...]
    crop_names: tuple[str, ...]
    candidate_record_ids: tuple[str, ...]
    source_blob_sha256: str


@dataclass(frozen=True)
class MarriageDocumentWorkspace:
    title: str
    summary: str
    partial: bool
    source_document_count: int
    approved_fragment_count: int
    particulars: tuple[WorkspaceDisplayItem, ...]
    special_conditions: tuple[WorkspaceSpecialCondition, ...]
    missing_core_particulars: tuple[str, ...]
    issues: tuple[str, ...]
    actions: tuple[str, ...]
    sources: tuple[WorkspaceSource, ...]
    comparison: MarriageDocumentComparisonResult


_STANDARD_NIKAH_CONDITIONS = {
    "18": "Delegation of the right of divorce to the wife",
    "19": "Any restriction on the husband's right of divorce",
    "20": "Any separate document about dower, maintenance or related terms",
    "21": "Existing wife / permission of the Arbitration Council",
    "22": "Arbitration Council permission for a further marriage",
}

_CORE_FIELDS = (
    (MarriageFactField.BRIDE_NAME, "Bride"),
    (MarriageFactField.GROOM_NAME, "Groom"),
    (MarriageFactField.MARRIAGE_DATE, "Marriage date"),
    (MarriageFactField.PLACE_OF_MARRIAGE, "Place of marriage"),
    (
        MarriageFactField.MARRIAGE_LOCALITY_OR_DISTRICT,
        "Locality / district",
    ),
    (
        MarriageFactField.NIKAH_REGISTRAR_OR_SOLEMNISING_OFFICIAL,
        "Nikah registrar / solemnising official",
    ),
    (MarriageFactField.REGISTRATION_DATE, "Registration date"),
    (MarriageFactField.REGISTRATION_NUMBER, "Registration number"),
    (
        MarriageFactField.UNION_COUNCIL_OR_LOCAL_AUTHORITY,
        "Union Council / local authority",
    ),
    (MarriageFactField.MEHR_PROMPT_AMOUNT, "Prompt mehr"),
    (MarriageFactField.MEHR_DEFERRED_AMOUNT, "Deferred mehr"),
    (MarriageFactField.WITNESS_NAME, "Witness"),
)

_IMPORTANT_MISSING = {
    MarriageFactField.BRIDE_NAME: "Bride's name",
    MarriageFactField.GROOM_NAME: "Groom's name",
    MarriageFactField.MARRIAGE_DATE: "Marriage date",
    MarriageFactField.REGISTRATION_NUMBER: "Registration number",
    MarriageFactField.UNION_COUNCIL_OR_LOCAL_AUTHORITY: "Union Council / authority",
    MarriageFactField.MEHR_PROMPT_AMOUNT: "Mehr / dower",
    MarriageFactField.WITNESS_NAME: "Witness details",
}


def _all_facts(records):
    return tuple(
        fact
        for record in records
        for fact in record.facts
    )


def _first_fact(facts, field):
    for fact in facts:
        if fact.field is field:
            return fact
    return None


def _condition_number(value: str) -> str | None:
    match = re.match(r"\s*(18|19|20|21|22)", value)
    return None if match is None else match.group(1)


def _recorded_answer(fact: MarriageFact) -> str:
    note = fact.provenance.quality_note.casefold()
    if "recorded answer is 'no'" in note or "recorded 'no'" in note:
        return "No"
    if 'recorded answer is "no"' in note:
        return "No"
    return "See original"


def _clean_condition_note(fact: MarriageFact) -> str | None:
    note = fact.provenance.quality_note
    lowered = note.casefold()
    if "unclear" in lowered:
        return "Part of this item is unclear and should be checked against the original image."
    return None


def build_marriage_document_workspace(
    records: Iterable[MarriageDocumentIntelligenceRecord],
) -> MarriageDocumentWorkspace:
    material = tuple(records)
    if not material:
        raise ValueError("At least one marriage-document record is required.")

    for record in material:
        validate_marriage_document_record(record)

    comparison = compare_marriage_document_records(material)
    facts = _all_facts(material)

    particulars = []
    for field, label in _CORE_FIELDS:
        fact = _first_fact(facts, field)
        if fact is None:
            continue
        particulars.append(
            WorkspaceDisplayItem(
                label=label,
                value=fact.value,
                note=(
                    fact.provenance.quality_note
                    if "unclear" in fact.provenance.quality_note.casefold()
                    else None
                ),
            )
        )

    additional_date = _first_fact(facts, MarriageFactField.ADDITIONAL_DATE)
    if additional_date is not None:
        particulars.append(
            WorkspaceDisplayItem(
                label="Other date shown",
                value=additional_date.value,
                note="The current material does not identify what this date relates to.",
            )
        )

    conditions = []
    for fact in facts:
        if fact.field is not MarriageFactField.SPECIAL_CONDITION:
            continue
        number = _condition_number(fact.value)
        if number is None:
            continue
        conditions.append(
            WorkspaceSpecialCondition(
                item_number=number,
                subject=_STANDARD_NIKAH_CONDITIONS[number],
                recorded_answer=_recorded_answer(fact),
                note=_clean_condition_note(fact),
            )
        )

    present_fields = {fact.field for fact in facts}
    missing = tuple(
        label
        for field, label in _IMPORTANT_MISSING.items()
        if field not in present_fields
    )

    issues = []
    if additional_date is not None:
        issues.append(
            f"The date {additional_date.value} is visible, but its purpose is unclear."
        )
    if any(condition.note for condition in conditions):
        issues.append(
            "Part of Nikah Nama item 21 is unclear and should be checked against the original image."
        )
    if missing:
        issues.append(
            "The reviewed sections do not yet contain the main party and registration particulars."
        )

    actions = []
    if any(condition.note for condition in conditions):
        actions.append("Check item 21 against the original page.")
    if missing:
        actions.append(
            "Review or transcribe the remaining Nikah Nama sections to capture the parties, "
            "marriage date, registration details, mehr and witnesses."
        )
    actions.append(
        "Use a qualified translator if a certified English translation is required."
    )

    sources = tuple(
        WorkspaceSource(
            filename=(
                profile.original_filenames[0]
                if profile.original_filenames
                else "Source document"
            ),
            pages=profile.page_numbers,
            crop_names=profile.crop_names,
            candidate_record_ids=profile.candidate_record_ids,
            source_blob_sha256=profile.source_blob_sha256,
        )
        for profile in comparison.source_profiles
    )

    readable = []
    if particulars:
        readable.append(
            f"{len(particulars)} usable particular"
            + ("" if len(particulars) == 1 else "s")
        )
    if conditions:
        readable.append(
            f"{len(conditions)} Nikah Nama condition answers"
        )

    summary = (
        "From the sections reviewed so far, LegalRAG can read "
        + (" and ".join(readable) if readable else "only limited information")
        + ". "
    )
    if missing:
        summary += (
            "The important party and registration details are not yet available "
            "from these sections."
        )
    else:
        summary += "The main marriage particulars are represented."

    return MarriageDocumentWorkspace(
        title="Pakistani marriage document",
        summary=summary,
        partial=bool(missing),
        source_document_count=len(comparison.source_profiles),
        approved_fragment_count=sum(
            len(profile.candidate_record_ids)
            for profile in comparison.source_profiles
        ),
        particulars=tuple(particulars),
        special_conditions=tuple(conditions),
        missing_core_particulars=missing,
        issues=tuple(issues),
        actions=tuple(actions),
        sources=sources,
        comparison=comparison,
    )
