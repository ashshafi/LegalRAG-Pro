"""Deterministic UK chronology date and period parsing.

The parser recognizes only explicit temporal grammar.  It never converts an
arbitrary four-digit token into a date and excludes common legal-authority and
case-number contexts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re

from .models import DatePrecision, PartialDate, TemporalExtent, TemporalKind

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
_MONTH_PATTERN = "(?:" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + ")"

# Boundary token used inside periods. Bare years are allowed only because the
# surrounding range/open-period grammar supplies the temporal context.
_BOUNDARY = rf"(?:\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH_PATTERN}\s+\d{{4}}|\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{4}}|{_MONTH_PATTERN}\s+\d{{4}}|\d{{4}})"

_RANGE_PATTERNS = (
    re.compile(rf"\bfrom\s+(?P<start>{_BOUNDARY})\s+(?:to|until|through)\s+(?P<end>{_BOUNDARY})\b", re.I),
    re.compile(rf"\bbetween\s+(?P<start>{_BOUNDARY})\s+and\s+(?P<end>{_BOUNDARY})\b", re.I),
)
_OPEN_PATTERNS = (
    re.compile(rf"\b(?:since|from)\s+(?P<start>{_BOUNDARY})\s+(?:onwards|onward|to date|until now)\b", re.I),
    re.compile(rf"\bsince\s+(?P<start>{_BOUNDARY})\b", re.I),
)
_EXACT_TEXT = re.compile(rf"\b(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month>{_MONTH_PATTERN})\s+(?P<year>\d{{4}})\b", re.I)
_EXACT_NUMERIC = re.compile(r"(?<![\d/-])(?P<day>\d{1,2})[/-](?P<month>\d{1,2})[/-](?P<year>\d{4})(?![\d/-])")
_MONTH_YEAR = re.compile(rf"\b(?P<month>{_MONTH_PATTERN})\s+(?P<year>\d{{4}})\b", re.I)
_CONTEXT_YEAR = re.compile(r"\b(?:in|during)\s+(?P<year>\d{4})\b", re.I)

_AUTHORITY_CONTEXT = re.compile(r"\[[12]\d{3}\]|\b(?:v|versus)\b.{0,80}\[[12]\d{3}\]", re.I)
_CASE_NUMBER_CONTEXT = re.compile(r"\b(?:case|claim|no\.?|number)\s*[:#-]?\s*[\w/-]*\d{4}[\w/-]*", re.I)


@dataclass(frozen=True, slots=True)
class ParsedTemporalExpression:
    """One explicit temporal expression and its source-text span."""

    start_offset: int
    end_offset: int
    extent: TemporalExtent


def _month(value: str) -> int:
    try:
        return _MONTHS[value.casefold()]
    except KeyError as exc:
        raise ValueError(f"Unknown month name {value!r}.") from exc


def _boundary(value: str) -> PartialDate:
    token = value.strip()
    match = _EXACT_TEXT.fullmatch(token)
    if match:
        return _exact(int(match.group("year")), _month(match.group("month")), int(match.group("day")))
    match = _EXACT_NUMERIC.fullmatch(token)
    if match:
        return _exact(int(match.group("year")), int(match.group("month")), int(match.group("day")))
    match = _MONTH_YEAR.fullmatch(token)
    if match:
        return PartialDate(
            year=int(match.group("year")),
            month=_month(match.group("month")),
            precision=DatePrecision.MONTH,
        )
    if re.fullmatch(r"\d{4}", token):
        return PartialDate(year=int(token), precision=DatePrecision.YEAR)
    raise ValueError(f"Unsupported date boundary {value!r}.")


def _exact(year: int, month: int, day: int) -> PartialDate:
    # Validate before constructing so invalid matches are simply ignored by the
    # public parser rather than corrupting a complete chronology build.
    date(year, month, day)
    return PartialDate(year=year, month=month, day=day, precision=DatePrecision.EXACT)


def _overlaps(span: tuple[int, int], accepted: list[tuple[int, int]]) -> bool:
    return any(span[0] < other[1] and other[0] < span[1] for other in accepted)


def _excluded_context(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 60): min(len(text), end + 60)]
    token = text[start:end]
    if token.startswith("[") and token.endswith("]"):
        return True
    if _AUTHORITY_CONTEXT.search(window):
        # Do not blanket-exclude ordinary event text merely because another
        # distant year exists; require the matched token to be bracketed or a
        # case-name pattern to be close to it.
        if re.search(rf"(?:v|versus).{{0,50}}\[?{re.escape(token.strip('[]'))}\]?", window, re.I):
            return True
    if _CASE_NUMBER_CONTEXT.search(window) and re.fullmatch(r"\d{4}", token.strip()):
        return True
    return False


def parse_temporal_expressions(text: str) -> tuple[ParsedTemporalExpression, ...]:
    """Parse explicit UK dates/periods without inventing missing precision."""

    source = str(text)
    accepted_spans: list[tuple[int, int]] = []
    values: list[ParsedTemporalExpression] = []

    def add(match: re.Match[str], extent: TemporalExtent) -> None:
        span = match.span()
        if _overlaps(span, accepted_spans) or _excluded_context(source, *span):
            return
        accepted_spans.append(span)
        values.append(ParsedTemporalExpression(span[0], span[1], extent))

    for pattern in _RANGE_PATTERNS:
        for match in pattern.finditer(source):
            try:
                start = _boundary(match.group("start"))
                end = _boundary(match.group("end"))
                add(
                    match,
                    TemporalExtent(
                        kind=TemporalKind.PERIOD,
                        start=start,
                        end=end,
                        original_text=match.group(0),
                    ),
                )
            except ValueError:
                continue

    for pattern in _OPEN_PATTERNS:
        for match in pattern.finditer(source):
            try:
                add(
                    match,
                    TemporalExtent(
                        kind=TemporalKind.PERIOD,
                        start=_boundary(match.group("start")),
                        end=None,
                        original_text=match.group(0),
                    ),
                )
            except ValueError:
                continue

    for match in _EXACT_TEXT.finditer(source):
        try:
            partial = _exact(int(match.group("year")), _month(match.group("month")), int(match.group("day")))
            add(match, TemporalExtent(TemporalKind.POINT, partial, match.group(0)))
        except ValueError:
            continue

    for match in _EXACT_NUMERIC.finditer(source):
        try:
            partial = _exact(int(match.group("year")), int(match.group("month")), int(match.group("day")))
            add(match, TemporalExtent(TemporalKind.POINT, partial, match.group(0)))
        except ValueError:
            continue

    for match in _MONTH_YEAR.finditer(source):
        try:
            partial = PartialDate(
                year=int(match.group("year")),
                month=_month(match.group("month")),
                precision=DatePrecision.MONTH,
            )
            add(match, TemporalExtent(TemporalKind.POINT, partial, match.group(0)))
        except ValueError:
            continue

    for match in _CONTEXT_YEAR.finditer(source):
        try:
            partial = PartialDate(year=int(match.group("year")), precision=DatePrecision.YEAR)
            # "during" identifies a whole year period; "in" remains a
            # year-precision point attribution.
            kind = TemporalKind.PERIOD if match.group(0).casefold().startswith("during") else TemporalKind.POINT
            end = partial if kind is TemporalKind.PERIOD else None
            add(match, TemporalExtent(kind, partial, match.group(0), end=end))
        except ValueError:
            continue

    return tuple(sorted(values, key=lambda item: (item.start_offset, item.end_offset)))


def first_temporal_expression(text: str) -> TemporalExtent | None:
    """Return the first explicit temporal expression, if any."""

    values = parse_temporal_expressions(text)
    return values[0].extent if values else None


__all__ = [
    "ParsedTemporalExpression",
    "first_temporal_expression",
    "parse_temporal_expressions",
]
