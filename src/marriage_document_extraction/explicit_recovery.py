from __future__ import annotations

import re
import unicodedata
from typing import Any, Mapping


_DATE_TOKEN = re.compile(
    r"(?<!\d)(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})(?!\d)"
)

_REGISTRATION_DATE_LABEL = re.compile(
    r"(?i)\b(?:date\s+of\s+registration(?:\s+of\s+marriage)?|"
    r"registration\s+date)\b"
    r"[^0-9\u06f0-\u06f9\u0660-\u0669]{0,16}"
    r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"
)

_MARRIAGE_DATE_LABEL = re.compile(
    r"(?i)\b(?:date\s+of\s+marriage|marriage\s+date)\b"
    r"[^0-9\u06f0-\u06f9\u0660-\u0669]{0,16}"
    r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"
)

_REGISTRATION_NUMBER_LABEL = re.compile(
    r"(?i)\b(?:registration\s+(?:no|number)|reg\.?\s*no)\b"
    r"\s*[:#=\-]?\s*([A-Za-z0-9][A-Za-z0-9/.\-]{1,39})"
)

# U+0648 U+0627 U+0631 U+0688 is the Urdu word "ward".
# U+06D4 is the Urdu full stop.
_WARD_LINE = re.compile(
    r"(?m)^[ \t]*(?:\d{1,2})[ \t]*(?:\u06d4|[.):\-])"
    r"[^\n]*\u0648\u0627\u0631\u0688[^\n]{0,48}?(\d{1,4})"
)

_UNCLEAR_MARKER = re.compile(r"\[unclear\]", re.IGNORECASE)

_AUTHORITY_KEYWORD = re.compile(
    r"(?i)\b(?:union\s+council|council|town|govt|government|district)\b"
)

_STRONG_AUTHORITY = re.compile(r"(?i)\bunion\s+council\b")
_COUNCIL = re.compile(r"(?i)\bcouncil\b")
_AUTHORITY_SUPPORT = re.compile(
    r"(?i)\b(?:town|govt|government|district)\b"
)

_QUESTION_WORDS = re.compile(
    r"(?i)\b(?:whether|permission|wife|husband|bridegroom|question)\b"
)


def _ascii_decimal_digits(value: str) -> str | None:
    result = []
    for character in value:
        try:
            result.append(str(unicodedata.decimal(character)))
        except (TypeError, ValueError):
            return None
    return "".join(result)


def _ascii_decimal_text(value: str) -> str:
    result = []
    for character in value:
        try:
            result.append(str(unicodedata.decimal(character)))
        except (TypeError, ValueError):
            result.append(character)
    return "".join(result)


def _has_arabic_script_letter(value: str) -> bool:
    for character in value:
        if not unicodedata.category(character).startswith("L"):
            continue
        if "ARABIC" in unicodedata.name(character, ""):
            return True
    return False


def _has_latin_script_letter(value: str) -> bool:
    for character in value:
        if not unicodedata.category(character).startswith("L"):
            continue
        if "LATIN" in unicodedata.name(character, ""):
            return True
    return False


def _clean_lines(value: str) -> tuple[str, ...]:
    return tuple(
        " ".join(line.strip().split())
        for line in value.splitlines()
        if line.strip()
    )


def _fact_key(item: Mapping[str, Any]) -> tuple[str, str]:
    return (
        str(item["field"]),
        " ".join(str(item["value"]).split()).casefold(),
    )


def _looks_like_authority_line(value: str) -> bool:
    if not value or len(value) > 80:
        return False
    if _has_arabic_script_letter(value):
        return False
    if _QUESTION_WORDS.search(value):
        return False
    return _AUTHORITY_KEYWORD.search(value) is not None


def recover_source_explicit_fact_payloads(
    transcription_text: str,
) -> tuple[dict[str, str], ...]:
    """Recover only facts identifiable without semantic guessing."""

    if not isinstance(transcription_text, str) or not transcription_text.strip():
        return ()

    recovered: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    consumed_dates: set[str] = set()

    normalized_digits = _ascii_decimal_text(transcription_text)

    def add(
        field: str,
        value: str,
        quality_note: str,
    ) -> None:
        cleaned = " ".join(value.split())
        if not cleaned:
            return

        payload = {
            "field": field,
            "value": cleaned,
            "derivation_kind": "ocr_derived",
            "quality_note": quality_note,
        }
        key = _fact_key(payload)
        if key in seen:
            return
        seen.add(key)
        recovered.append(payload)

    for pattern, field, note in (
        (
            _MARRIAGE_DATE_LABEL,
            "marriage_date",
            "Marriage date recovered directly from an explicit label in the approved transcription.",
        ),
        (
            _REGISTRATION_DATE_LABEL,
            "registration_date",
            "Registration date recovered directly from an explicit label in the approved transcription.",
        ),
    ):
        for match in pattern.finditer(normalized_digits):
            value = match.group(1)
            consumed_dates.add(value)
            add(field, value, note)

    for match in _REGISTRATION_NUMBER_LABEL.finditer(normalized_digits):
        add(
            "registration_number",
            match.group(1),
            "Registration number recovered directly from an explicit label in the approved transcription.",
        )

    for match in _WARD_LINE.finditer(normalized_digits):
        ward = _ascii_decimal_digits(match.group(1)) or match.group(1)
        add(
            "marriage_locality_or_district",
            "Ward " + ward,
            (
                "Ward number recovered directly from Nikah Nama item 1 in the "
                "approved transcription. Other locality wording is not assigned "
                "unless it is independently explicit."
            ),
        )

    authority_lines = []
    for raw_line in _clean_lines(transcription_text):
        line = _UNCLEAR_MARKER.sub("", raw_line).strip()
        if not _looks_like_authority_line(line):
            continue
        if line not in authority_lines:
            authority_lines.append(line)

    if authority_lines:
        has_strong = any(
            _STRONG_AUTHORITY.search(line)
            for line in authority_lines
        )
        has_council = any(
            _COUNCIL.search(line)
            for line in authority_lines
        )
        support_count = sum(
            1
            for line in authority_lines
            if _AUTHORITY_SUPPORT.search(line)
        )

        if has_strong or (has_council and support_count >= 1):
            note = (
                "Local-authority wording recovered directly from English text "
                "in the approved transcription."
            )
            if not has_strong:
                note += (
                    " The exact council designation is incomplete and should "
                    "be checked against the original."
                )
            add(
                "union_council_or_local_authority",
                " | ".join(authority_lines[:6]),
                note,
            )

    for match in _DATE_TOKEN.finditer(normalized_digits):
        value = match.group(1)
        if value in consumed_dates:
            continue
        add(
            "additional_date",
            value,
            (
                "Date token recovered directly from the approved transcription; "
                "its documentary purpose is not assigned automatically."
            ),
        )

    language_source = _UNCLEAR_MARKER.sub("", transcription_text)
    has_urdu = _has_arabic_script_letter(language_source)
    has_english = _has_latin_script_letter(language_source)

    if has_urdu and has_english:
        add(
            "document_language_mix",
            "Urdu and English",
            (
                "Language mix identified deterministically from letter scripts "
                "in the approved transcription."
            ),
        )
    elif has_urdu:
        add(
            "document_language_mix",
            "Urdu",
            (
                "Language identified deterministically from letter scripts in "
                "the approved transcription."
            ),
        )

    return tuple(recovered)


def reconcile_source_explicit_facts(
    payload: Mapping[str, Any],
    transcription_text: str,
) -> dict[str, Any]:
    """Prepend deterministic source facts while retaining AI interpretation."""

    value = dict(payload)
    raw_facts = value.get("facts")
    if not isinstance(raw_facts, list):
        return value

    deterministic = list(
        recover_source_explicit_fact_payloads(transcription_text)
    )
    if not deterministic:
        return value

    deterministic_keys = {
        _fact_key(item)
        for item in deterministic
    }

    retained = [
        dict(item)
        for item in raw_facts
        if _fact_key(item) not in deterministic_keys
    ]

    value["facts"] = deterministic + retained
    return value


__all__ = [
    "recover_source_explicit_fact_payloads",
    "reconcile_source_explicit_facts",
]
