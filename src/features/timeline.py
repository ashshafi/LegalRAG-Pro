"""Conservative legacy UI timeline extraction from governed search results.

This module is presentation-only. It intentionally avoids treating arbitrary
four-digit tokens, legislation years, case-number fragments, or clock values
as chronology events.
"""

from __future__ import annotations

import re
from datetime import datetime


_MONTH_PATTERN = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Sept|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)"
)

_EXACT_PATTERNS = (
    re.compile(
        r"(?<![\d/])(?P<date>\d{1,2}/\d{1,2}/(?:19|20)\d{2})(?![\d/])"
    ),
    re.compile(
        r"(?<![\d-])(?P<date>\d{1,2}-\d{1,2}-(?:19|20)\d{2})(?![\d-])"
    ),
    re.compile(
        rf"\b(?P<date>\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH_PATTERN}\s+(?:19|20)\d{{2}})\b",
        re.I,
    ),
)

_CONTEXT_YEAR = re.compile(
    r"\b(?:in|during|since|from|by|until|through|throughout)\s+"
    r"(?P<date>(?:19|20)\d{2})\b",
    re.I,
)

_LEADING_YEAR = re.compile(
    r"(?m)^\s*(?P<date>(?:19|20)\d{2})\s*(?:[–—-]|:)"
)

_ORDINAL_SUFFIX = re.compile(r"(?<=\d)(?:st|nd|rd|th)\b", re.I)


def _parse_date(value: str) -> datetime | None:
    cleaned = _ORDINAL_SUFFIX.sub("", str(value).strip())
    for fmt in (
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d %B %Y",
        "%d %b %Y",
        "%Y",
    ):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def _candidate_matches(text: str):
    for pattern in _EXACT_PATTERNS:
        yield from pattern.finditer(text)
    yield from _CONTEXT_YEAR.finditer(text)
    yield from _LEADING_YEAR.finditer(text)


def extract_timeline_events(results):
    """Extract conservative timeline events from Chroma-style search results.

    Exact day/month/year dates are accepted only when the month/date is
    calendrically valid. Year-only events are accepted only with explicit
    temporal context (for example ``during 2005``) or a leading timeline-style
    year marker (for example ``2005 — ...``).

    Arbitrary standalone four-digit tokens are deliberately rejected.
    """

    events = []
    documents = (results or {}).get("documents") or []
    metadatas = (results or {}).get("metadatas") or []

    if not documents or not documents[0]:
        return events

    metadata_row = metadatas[0] if metadatas else ()
    seen = set()

    for index, raw_text in enumerate(documents[0]):
        text = str(raw_text or "")
        metadata = metadata_row[index] if index < len(metadata_row) else {}
        file_name = metadata.get("file", "Unknown source")
        page = metadata.get("page", "?")

        for match in _candidate_matches(text):
            candidate = _ORDINAL_SUFFIX.sub("", match.group("date").strip())
            parsed = _parse_date(candidate)
            if parsed is None:
                continue

            identity = (
                parsed.date().isoformat(),
                str(file_name),
                str(page),
            )
            if identity in seen:
                continue
            seen.add(identity)

            events.append(
                {
                    "date": candidate,
                    "event": text[:250] + ("..." if len(text) > 250 else ""),
                    "file": file_name,
                    "page": page,
                }
            )

    return events


def sort_events(events):
    """Sort events chronologically and deterministically."""

    def key(event):
        parsed = _parse_date(event.get("date", ""))
        return (
            parsed if parsed is not None else datetime.max,
            str(event.get("file", "")),
            str(event.get("page", "")),
            str(event.get("event", "")),
        )

    return sorted(events, key=key)
