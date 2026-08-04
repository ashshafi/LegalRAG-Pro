from __future__ import annotations

import copy
from dataclasses import replace

from case_analysis.m3.chronology import build_case_chronology
from case_analysis.m3.models import DatePrecision, EventStatus, TimingStatus
from legal_analysis.evidence_assessment import PropositionAssessmentStatus

from case_analysis_m3_helpers import evidence, inputs, make_m5_result, proposition


def test_same_event_across_issues_merges_and_preserves_all_links():
    shared = evidence(key="meeting", summary="A return-to-work meeting occurred on 5 July 2005.")
    ek = make_m5_result(
        "EK-001",
        issue_analysis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        evidence_by_element={"EK-TIMING": (shared,)},
        proposition_overrides={
            "EK-TIMING": (proposition("A return-to-work meeting occurred on 5 July 2005.", ("meeting",)),)
        },
    )
    lim = make_m5_result(
        "LIM-001",
        issue_analysis_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        evidence_by_element={"LIM-ACTS": (shared,)},
        proposition_overrides={
            "LIM-ACTS": (proposition("A return-to-work meeting occurred on 5 July 2005.", ("meeting",)),)
        },
    )
    foundation, matrices, results = inputs(ek, lim)
    chronology = build_case_chronology(foundation, matrices, results)
    assert len(chronology.events) == 1
    event = chronology.events[0]
    assert len(event.assertions) == 2
    assert event.related_issue_definition_ids == ("EK-001", "LIM-001")
    assert event.related_element_ids == ("EK-TIMING", "LIM-ACTS")
    assert event.evidence_keys == ("meeting",)


def test_one_chunk_with_two_events_remains_separate():
    ev = evidence(
        key="two-events",
        summary="CACI sent a capability review letter on 4 July 2005. CACI sent a capability review letter on 5 July 2005.",
    )
    result = make_m5_result(
        "LIM-001",
        evidence_by_element={"LIM-DATES": (ev,)},
        proposition_overrides={
            "LIM-DATES": (
                proposition("CACI sent a capability review letter on 4 July 2005.", ("two-events",)),
            )
        },
    )
    foundation, matrices, results = inputs(result)
    chronology = build_case_chronology(foundation, matrices, results)
    assert len(chronology.events) == 2
    assert {item.canonical_temporal_extent.display_text for item in chronology.events} == {
        "4 July 2005",
        "5 July 2005",
    }


def test_same_date_different_event_content_remains_separate():
    first = evidence(key="letter", summary="CACI sent a capability letter on 5 July 2005.")
    second = evidence(key="meeting", document_name="meeting.pdf", document_id="doc-2", summary="A return-to-work meeting occurred on 5 July 2005.")
    result = make_m5_result(
        "LIM-001",
        evidence_by_element={"LIM-ACTS": (first, second)},
        proposition_overrides={
            "LIM-ACTS": (
                proposition("CACI sent a capability letter on 5 July 2005.", ("letter",)),
                proposition("A return-to-work meeting occurred on 5 July 2005.", ("meeting",)),
            )
        },
    )
    foundation, matrices, results = inputs(result)
    chronology = build_case_chronology(foundation, matrices, results)
    assert len(chronology.events) == 2
    assert len({item.normalized_event_core for item in chronology.events}) == 2


def test_conflicting_dates_in_different_evidence_records_remain_separate():
    first = evidence(key="date-a", summary="The return-to-work meeting occurred on 4 July 2005.")
    second = evidence(key="date-b", document_name="second.pdf", document_id="doc-2", summary="The return-to-work meeting occurred on 5 July 2005.")
    result = make_m5_result(
        "LIM-001",
        evidence_by_element={"LIM-ACTS": (first, second)},
        proposition_overrides={
            "LIM-ACTS": (
                proposition("The return-to-work meeting occurred on 4 July 2005.", ("date-a",)),
                proposition("The return-to-work meeting occurred on 5 July 2005.", ("date-b",)),
            )
        },
    )
    foundation, matrices, results = inputs(result)
    chronology = build_case_chronology(foundation, matrices, results)
    assert len(chronology.events) == 2
    assert {event.canonical_temporal_extent.display_text for event in chronology.events} == {
        "4 July 2005",
        "5 July 2005",
    }
    assert all(event.timing_status is TimingStatus.ESTABLISHED for event in chronology.events)


def test_supported_and_unresolved_statuses_are_not_upgraded():
    supported_ev = evidence(key="supported", summary="Home working was requested in July 2005.")
    unresolved_ev = evidence(key="unresolved", document_name="u.pdf", document_id="doc-u", summary="A return-to-work meeting may have occurred during 2005.")
    result = make_m5_result(
        "RA-001",
        evidence_by_element={"RA-ADJUSTMENT": (supported_ev,), "RA-TIMING": (unresolved_ev,)},
        proposition_overrides={
            "RA-ADJUSTMENT": (
                proposition(
                    "Home working was requested in July 2005.",
                    ("supported",),
                    status=PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
                ),
            ),
            "RA-TIMING": (
                proposition(
                    "A return-to-work meeting may have occurred during 2005.",
                    ("unresolved",),
                    status=PropositionAssessmentStatus.UNRESOLVED,
                ),
            ),
        },
    )
    foundation, matrices, results = inputs(result)
    chronology = build_case_chronology(foundation, matrices, results)
    assert {item.event_status for item in chronology.events} == {
        EventStatus.SUPPORTED,
        EventStatus.UNRESOLVED,
    }


def test_input_order_does_not_change_chronology_or_source_objects():
    shared = evidence(key="shared", summary="CACI sent a return-to-work email on 5 July 2005.")
    first = make_m5_result(
        "EK-001",
        issue_analysis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        evidence_by_element={"EK-TIMING": (shared,)},
        proposition_overrides={"EK-TIMING": (proposition("CACI sent a return-to-work email on 5 July 2005.", ("shared",)),)},
    )
    second = make_m5_result(
        "LIM-001",
        issue_analysis_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        evidence_by_element={"LIM-DATES": (shared,)},
        proposition_overrides={"LIM-DATES": (proposition("CACI sent a return-to-work email on 5 July 2005.", ("shared",)),)},
    )
    foundation, matrices, results = inputs(first, second)
    before_results = copy.deepcopy(results)
    before_foundation = copy.deepcopy(foundation)
    before_matrices = copy.deepcopy(matrices)

    normal = build_case_chronology(foundation, matrices, results)
    reversed_value = build_case_chronology(foundation, matrices, tuple(reversed(results)))

    assert normal == reversed_value
    assert results == before_results
    assert foundation == before_foundation
    assert matrices == before_matrices


def test_mixed_precision_ordering_is_deterministic_without_invented_dates():
    ra_month = evidence(key="month", document_name="month.pdf", document_id="doc-month", summary="Home working was requested in July 2005.")
    ek_exact = evidence(key="exact", document_name="exact.pdf", document_id="doc-exact", summary="A return-to-work meeting occurred on 5 July 2005.")
    da_year = evidence(key="year", document_name="year.pdf", document_id="doc-year", summary="The sickness absence continued during 2005.")
    lim_open = evidence(key="open", document_name="open.pdf", document_id="doc-open", summary="PHI benefits were paid from July 2005 onwards.")
    lim_unknown = evidence(key="unknown", document_name="unknown.pdf", document_id="doc-unknown", summary="A capability meeting occurred.")

    results = (
        make_m5_result(
            "RA-001",
            issue_analysis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            evidence_by_element={"RA-ADJUSTMENT": (ra_month,)},
            proposition_overrides={"RA-ADJUSTMENT": (proposition("Home working was requested in July 2005.", ("month",)),)},
        ),
        make_m5_result(
            "EK-001",
            issue_analysis_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            evidence_by_element={"EK-TIMING": (ek_exact,)},
            proposition_overrides={"EK-TIMING": (proposition("A return-to-work meeting occurred on 5 July 2005.", ("exact",)),)},
        ),
        make_m5_result(
            "DA-001",
            issue_analysis_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
            evidence_by_element={"DA-SOMETHING-ARISING": (da_year,)},
            proposition_overrides={"DA-SOMETHING-ARISING": (proposition("The sickness absence continued during 2005.", ("year",)),)},
        ),
        make_m5_result(
            "LIM-001",
            issue_analysis_id="dddddddd-dddd-4ddd-8ddd-dddddddddddd",
            evidence_by_element={"LIM-CONTINUING-CONDUCT": (lim_open,), "LIM-ACTS": (lim_unknown,)},
            proposition_overrides={
                "LIM-CONTINUING-CONDUCT": (proposition("PHI benefits were paid from July 2005 onwards.", ("open",)),),
                "LIM-ACTS": (proposition("A capability meeting occurred.", ("unknown",)),),
            },
        ),
    )
    foundation, matrices, frozen_results = inputs(*results)
    first = build_case_chronology(foundation, matrices, frozen_results)
    second = build_case_chronology(foundation, matrices, tuple(reversed(frozen_results)))
    assert first == second
    displays = [
        item.canonical_temporal_extent.display_text
        if item.canonical_temporal_extent is not None
        else "unknown"
        for item in first.events
    ]
    assert "1 July 2005" not in displays
    assert "July 2005" in displays
    assert "5 July 2005" in displays
    assert "during 2005" in displays
    assert "from July 2005 onwards" in displays
    assert displays[-1] == "unknown"
    month_event = next(item for item in first.events if item.canonical_temporal_extent and item.canonical_temporal_extent.display_text == "July 2005")
    assert month_event.canonical_temporal_extent.start.precision is DatePrecision.MONTH

