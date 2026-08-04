from __future__ import annotations

import pytest

from case_analysis.m3.date_parsing import parse_temporal_expressions
from case_analysis.m3.models import DatePrecision, PartialDate, TemporalKind


def one(text: str):
    values = parse_temporal_expressions(text)
    assert len(values) == 1
    return values[0].extent


def test_exact_textual_date():
    value = one("The meeting occurred on 5 July 2005.")
    assert value.kind is TemporalKind.POINT
    assert value.start == PartialDate(2005, 7, 5, DatePrecision.EXACT)
    assert value.display_text == "5 July 2005"


def test_exact_uk_numeric_date():
    value = one("The email was sent 17/07/2026.")
    assert value.start == PartialDate(2026, 7, 17, DatePrecision.EXACT)


def test_abbreviated_month_and_month_precision():
    value = one("The review occurred in Jul 2026.")
    assert value.start == PartialDate(2026, 7, None, DatePrecision.MONTH)
    assert value.display_text == "Jul 2026"


def test_contextual_year_is_not_fabricated_to_month_or_day():
    value = one("The absence began in 2005.")
    assert value.start == PartialDate(2005, None, None, DatePrecision.YEAR)
    assert value.display_text == "in 2005"


def test_during_year_is_period_with_year_precision():
    value = one("The review continued during 2005.")
    assert value.kind is TemporalKind.PERIOD
    assert value.start.precision is DatePrecision.YEAR
    assert value.end == value.start


def test_closed_range_preserves_boundary_precision():
    value = one("The arrangement operated from July 2005 to 5 September 2005.")
    assert value.kind is TemporalKind.PERIOD
    assert value.start.precision is DatePrecision.MONTH
    assert value.end is not None
    assert value.end.precision is DatePrecision.EXACT


def test_open_period_preserves_unknown_end():
    value = one("The payments continued from July 2005 onwards.")
    assert value.kind is TemporalKind.PERIOD
    assert value.start.precision is DatePrecision.MONTH
    assert value.end is None


def test_invalid_date_is_not_normalised():
    assert parse_temporal_expressions("A meeting occurred on 31/02/2005.") == ()


def test_bare_year_and_case_number_are_not_dates():
    assert parse_temporal_expressions("Case 2207441/2025 was allocated.") == ()
    assert parse_temporal_expressions("The number 2005 appears in the identifier.") == ()


def test_legal_authority_year_is_not_case_event_timing():
    assert parse_temporal_expressions("Smith v Jones [2018] was cited.") == ()


def test_partial_date_display_never_invents_components():
    assert PartialDate(2005, precision=DatePrecision.YEAR).display_text == "2005"
    assert PartialDate(2005, 7, precision=DatePrecision.MONTH).display_text == "July 2005"


def test_invalid_partial_date_combinations_fail():
    with pytest.raises(ValueError):
        PartialDate(2005, 7, 1, DatePrecision.MONTH)
    with pytest.raises(ValueError):
        PartialDate(2005, 2, 31, DatePrecision.EXACT)
