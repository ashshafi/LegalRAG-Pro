from __future__ import annotations

from case_analysis.m3.chronology import build_case_chronology
from case_analysis.m3.event_extraction import (
    CHRONOLOGY_EXTRACTION_POLICY_VERSION,
    extract_event_assertions,
)
from case_analysis.m3.models import (
    CASE_CHRONOLOGY_BUILDER_VERSION,
    CHRONOLOGY_PROFILE_VERSION,
    EventType,
)

from case_analysis_m3_helpers import evidence, inputs, make_m5_result, proposition


_GENERIC = "The mapped evidence contains factual material relevant to this element."


def test_calibrated_versions_are_explicit():
    assert CHRONOLOGY_EXTRACTION_POLICY_VERSION == "chronology-extraction-policy/1.1"
    assert CHRONOLOGY_PROFILE_VERSION == "chronology-profile/1.1"
    assert CASE_CHRONOLOGY_BUILDER_VERSION == "case-chronology-builder/1.1"


def test_source_event_is_discovered_once_before_varied_legal_projection():
    shared = evidence(
        key="vf-live-shape",
        document_name="vf-email.pdf",
        document_id="doc-vf",
        summary=(
            "From: Phil Jones <phil.jones@caci.co.uk> Sent: 14 June 2005 "
            "Subject: VF specification Phil, can you carry on with the VF specification as discussed."
        ),
    )
    results = (
        make_m5_result(
            "EK-001",
            issue_analysis_id="11111111-1111-4111-8111-111111111112",
            evidence_by_element={"EK-DIRECT-KNOWLEDGE": (shared,)},
            proposition_overrides={"EK-DIRECT-KNOWLEDGE": (proposition(_GENERIC, ("vf-live-shape",)),)},
        ),
        make_m5_result(
            "RA-001",
            issue_analysis_id="22222222-2222-4222-8222-222222222222",
            evidence_by_element={"RA-ADJUSTMENT": (shared,)},
            proposition_overrides={"RA-ADJUSTMENT": (proposition(_GENERIC, ("vf-live-shape",)),)},
        ),
        make_m5_result(
            "LIM-001",
            issue_analysis_id="33333333-3333-4333-8333-333333333333",
            evidence_by_element={"LIM-ACTS": (shared,)},
            proposition_overrides={"LIM-ACTS": (proposition(_GENERIC, ("vf-live-shape",)),)},
        ),
    )
    foundation, matrices, frozen = inputs(*results)
    assertions = extract_event_assertions(matrices, frozen)

    assert len(assertions) == 3
    assert {item.extraction_ordinal for item in assertions} == {0}
    assert {item.evidence_key for item in assertions} == {"vf-live-shape"}
    assert {item.event_type for item in assertions} == {EventType.COMMUNICATION}

    chronology = build_case_chronology(foundation, matrices, frozen)
    assert len(chronology.events) == 1
    event = chronology.events[0]
    assert event.related_issue_definition_ids == ("EK-001", "LIM-001", "RA-001")
    assert event.canonical_temporal_extent is not None
    assert event.canonical_temporal_extent.display_text == "14 June 2005"


def test_source_event_ordinals_are_independent_of_result_order():
    shared = evidence(
        key="order-independent-source",
        summary="A return-to-work meeting occurred on 1 July 2005; CACI regraded the claimant to a junior admin role; The claimant relapsed after the meeting.",
    )
    first = make_m5_result(
        "EK-001",
        issue_analysis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        evidence_by_element={"EK-TIMING": (shared,)},
        proposition_overrides={"EK-TIMING": (proposition(_GENERIC, ("order-independent-source",)),)},
    )
    second = make_m5_result(
        "LIM-001",
        issue_analysis_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        evidence_by_element={"LIM-ACTS": (shared,)},
        proposition_overrides={"LIM-ACTS": (proposition(_GENERIC, ("order-independent-source",)),)},
    )
    foundation, matrices, frozen = inputs(first, second)
    normal = extract_event_assertions(matrices, frozen)
    reversed_values = extract_event_assertions(matrices, tuple(reversed(frozen)))
    assert normal == reversed_values
    assert {item.extraction_ordinal for item in normal} == {0, 1, 2}

    chronology = build_case_chronology(foundation, matrices, frozen)
    assert {item.event_type for item in chronology.events} == {
        EventType.RETURN_TO_WORK,
        EventType.EMPLOYMENT,
        EventType.MEDICAL,
    }


def test_multiple_events_in_one_evidence_item_remain_distinct():
    ev = evidence(
        key="multi-event",
        summary=(
            "A return-to-work meeting occurred on 1 July 2005; "
            "CACI regraded the claimant to a junior admin role; "
            "The claimant relapsed after the meeting."
        ),
    )
    result = make_m5_result(
        "LIM-001",
        evidence_by_element={"LIM-ACTS": (ev,)},
        proposition_overrides={"LIM-ACTS": (proposition(_GENERIC, ("multi-event",)),)},
    )
    foundation, matrices, frozen = inputs(result)
    chronology = build_case_chronology(foundation, matrices, frozen)
    assert len(chronology.events) == 3
    assert {event.event_type for event in chronology.events} == {
        EventType.RETURN_TO_WORK,
        EventType.EMPLOYMENT,
        EventType.MEDICAL,
    }
    assert {assertion.extraction_ordinal for event in chronology.events for assertion in event.assertions} == {0, 1, 2}


def test_later_email_header_does_not_redate_historical_body_event():
    ev = evidence(
        key="later-wrapper",
        summary=(
            "From: Witness <witness@example.com>\n"
            "Sent: 17 July 2026\n"
            "Subject: Return to work\n"
            "The return-to-work meeting occurred on 5 July 2005."
        ),
    )
    result = make_m5_result(
        "LIM-001",
        evidence_by_element={"LIM-DATES": (ev,)},
        proposition_overrides={"LIM-DATES": (proposition(_GENERIC, ("later-wrapper",)),)},
    )
    foundation, matrices, frozen = inputs(result)
    chronology = build_case_chronology(foundation, matrices, frozen)
    assert len(chronology.events) == 1
    event = chronology.events[0]
    assert event.canonical_temporal_extent is not None
    assert event.canonical_temporal_extent.display_text == "5 July 2005"
    assert event.event_type is EventType.RETURN_TO_WORK


def test_canonical_summary_choice_is_independent_of_caller_order():
    primary = evidence(
        key="canonical-summary",
        summary=(
            "From: Phil Jones <phil.jones@caci.co.uk>\n"
            "Sent: 14 June 2005\n"
            "Subject: VF specification\n"
            "Phil emailed about the VF specification."
        ),
    )
    compatible_variant = evidence(
        key="canonical-summary",
        summary="Automatic reply. You have received this transmission in error.",
    )
    ek = make_m5_result(
        "EK-001",
        issue_analysis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        evidence_by_element={"EK-TIMING": (primary,)},
        proposition_overrides={"EK-TIMING": (proposition(_GENERIC, ("canonical-summary",)),)},
    )
    lim = make_m5_result(
        "LIM-001",
        issue_analysis_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        evidence_by_element={"LIM-DATES": (compatible_variant,)},
        proposition_overrides={"LIM-DATES": (proposition(_GENERIC, ("canonical-summary",)),)},
    )
    foundation, matrices, frozen = inputs(ek, lim)
    first = build_case_chronology(foundation, matrices, frozen)
    second = build_case_chronology(foundation, matrices, tuple(reversed(frozen)))
    assert first == second
    assert len(first.events) == 1
    assert first.events[0].canonical_temporal_extent.display_text == "14 June 2005"


def test_same_core_different_evidence_with_same_date_may_group_conservatively():
    first = evidence(
        key="meeting-a",
        summary="The return-to-work meeting occurred on 5 July 2005.",
    )
    second = evidence(
        key="meeting-b",
        document_name="other.pdf",
        document_id="doc-other",
        summary="The return-to-work meeting occurred on 5 July 2005.",
    )
    result = make_m5_result(
        "LIM-001",
        evidence_by_element={"LIM-ACTS": (first, second)},
        proposition_overrides={
            "LIM-ACTS": (
                proposition("The return-to-work meeting occurred on 5 July 2005.", ("meeting-a",)),
                proposition("The return-to-work meeting occurred on 5 July 2005.", ("meeting-b",)),
            )
        },
    )
    foundation, matrices, frozen = inputs(result)
    chronology = build_case_chronology(foundation, matrices, frozen)
    assert len(chronology.events) == 1
    assert chronology.events[0].evidence_keys == ("meeting-a", "meeting-b")
