from __future__ import annotations

from datetime import date

from case_analysis.m3.event_extraction import (
    CHRONOLOGY_PROFILES,
    KNOWN_ELEMENT_KEYS,
    extract_event_assertions,
    optional_profile_for,
    profile_for,
)
from case_analysis.m3.models import CHRONOLOGY_PROFILE_VERSION, EventStatus, EventType, TimingStatus
from legal_analysis.evidence_assessment import PropositionAssessmentStatus

from case_analysis_m3_helpers import (
    dated_evidence,
    evidence,
    inputs,
    make_m5_result,
    proposition,
    source_assertion_evidence,
)


def test_exact_versioned_profiles_are_valid_controlled_element_subset():
    assert len(KNOWN_ELEMENT_KEYS) == 34
    assert len(CHRONOLOGY_PROFILES) == 33
    assert set(CHRONOLOGY_PROFILES).issubset(KNOWN_ELEMENT_KEYS)
    assert ("LIM-001", "1.0", "LIM-JE-FACTORS") not in CHRONOLOGY_PROFILES
    assert {item.profile_version for item in CHRONOLOGY_PROFILES.values()} == {
        CHRONOLOGY_PROFILE_VERSION
    }


def test_valid_unprofiled_element_has_optional_no_profile_and_strict_lookup_fails():
    assert optional_profile_for("LIM-001", "1.0", "LIM-JE-FACTORS") is None
    try:
        profile_for("LIM-001", "1.0", "LIM-JE-FACTORS")
    except ValueError as exc:
        assert "No chronology extraction profile" in str(exc)
    else:
        raise AssertionError("Strict profile lookup must fail for an unprofiled element.")


def test_unknown_element_still_fails_closed():
    try:
        optional_profile_for("LIM-001", "1.0", "LIM-NOT-A-REAL-ELEMENT")
    except ValueError as exc:
        assert "Unknown controlled legal element" in str(exc)
    else:
        raise AssertionError("Unknown controlled elements must fail closed.")


def test_valid_unprofiled_element_is_skipped_even_when_evidence_contains_date_and_event_words():
    ev = evidence(
        key="je-factors",
        summary="The claimant attended a meeting on 5 July 2005 and relies on illness in support of an extension.",
    )
    result = make_m5_result(
        "LIM-001",
        evidence_by_element={"LIM-JE-FACTORS": (ev,)},
        proposition_overrides={
            "LIM-JE-FACTORS": (
                proposition(
                    "The claimant attended a meeting on 5 July 2005 and relies on illness in support of an extension.",
                    ("je-factors",),
                ),
            )
        },
    )
    _, matrices, results = inputs(result)
    assert extract_event_assertions(matrices, results) == ()


def test_proposition_specific_event_is_primary_source():
    ev = evidence(key="proposal", summary="No additional date metadata.")
    result = make_m5_result(
        "RA-001",
        evidence_by_element={"RA-ADJUSTMENT": (ev,)},
        proposition_overrides={
            "RA-ADJUSTMENT": (
                proposition("The direct record documents a proposal concerning phased return.", ("proposal",)),
            )
        },
    )
    _, matrices, results = inputs(result)
    assertions = extract_event_assertions(matrices, results)
    assert len(assertions) == 1
    assert assertions[0].event_type is EventType.ADJUSTMENT_PROPOSAL
    assert assertions[0].event_status is EventStatus.ESTABLISHED
    assert assertions[0].timing_status is TimingStatus.UNKNOWN


def test_generic_proposition_without_controlled_event_anchor_creates_no_event():
    ev = evidence(key="generic", summary="A date 5 July 2005 appears without an event signal.")
    result = make_m5_result(
        "EK-001",
        evidence_by_element={"EK-INFORMATION": (ev,)},
        proposition_overrides={
            "EK-INFORMATION": (
                proposition("The mapped evidence contains factual material relevant to this element.", ("generic",)),
            )
        },
    )
    _, matrices, results = inputs(result)
    assert extract_event_assertions(matrices, results) == ()


def test_raw_date_does_not_create_event_without_m4_proposition_link():
    ev = evidence(key="no-link", summary="CACI sent a letter on 17 July 2026.")
    result = make_m5_result("RA-001", evidence_by_element={"RA-REASONABLENESS": (ev,)})
    _, matrices, results = inputs(result)
    # RA-REASONABLENESS has no event-capable profile and M3 does not scan raw evidence globally.
    assert extract_event_assertions(matrices, results) == ()


def test_not_supported_proposition_does_not_create_event():
    ev = evidence(key="not-supported", summary="CACI sent a letter on 17 July 2026.")
    result = make_m5_result(
        "LIM-001",
        evidence_by_element={"LIM-DATES": (ev,)},
        proposition_overrides={
            "LIM-DATES": (
                proposition(
                    "CACI sent a letter on 17 July 2026.",
                    ("not-supported",),
                    status=PropositionAssessmentStatus.NOT_SUPPORTED_BY_CURRENT_EVIDENCE,
                ),
            )
        },
    )
    _, matrices, results = inputs(result)
    assert extract_event_assertions(matrices, results) == ()


def test_source_assertion_caps_event_status_at_supported():
    ev = source_assertion_evidence(
        key="asserted-request",
        summary="The claimant states that home working was requested on 5 July 2005.",
    )
    result = make_m5_result(
        "RA-001",
        evidence_by_element={"RA-ADJUSTMENT": (ev,)},
        proposition_overrides={
            "RA-ADJUSTMENT": (
                proposition("Home working was requested on 5 July 2005.", ("asserted-request",)),
            )
        },
    )
    _, matrices, results = inputs(result)
    assertion = extract_event_assertions(matrices, results)[0]
    assert assertion.event_status is EventStatus.SUPPORTED
    assert assertion.timing_status is TimingStatus.SUPPORTED


def test_document_date_used_only_for_communication_event():
    ev = dated_evidence(
        key="letter",
        summary="CACI sent the capability review letter.",
        source_date=date(2026, 7, 17),
    )
    result = make_m5_result(
        "LIM-001",
        evidence_by_element={"LIM-ACTS": (ev,)},
        proposition_overrides={
            "LIM-ACTS": (
                proposition("The direct record documents a relevant event or communication dated 17 July 2026.", ("letter",)),
            )
        },
    )
    _, matrices, results = inputs(result)
    assertion = extract_event_assertions(matrices, results)[0]
    assert assertion.event_type is EventType.CAPABILITY
    assert assertion.temporal_extent is not None
    assert assertion.temporal_extent.start.year == 2026


def test_historical_event_date_overrides_later_source_date():
    ev = dated_evidence(
        key="statement",
        summary="The witness statement records that a return-to-work meeting occurred on 5 July 2005.",
        source_date=date(2026, 7, 17),
    )
    result = make_m5_result(
        "LIM-001",
        evidence_by_element={"LIM-DATES": (ev,)},
        proposition_overrides={
            "LIM-DATES": (
                proposition("The direct record documents a relevant event or communication dated 5 July 2005.", ("statement",)),
            )
        },
    )
    _, matrices, results = inputs(result)
    assertion = extract_event_assertions(matrices, results)[0]
    assert assertion.temporal_extent is not None
    assert assertion.temporal_extent.start.year == 2005
    assert assertion.temporal_extent.start.day == 5


def test_enriched_detail_cannot_be_upgraded_to_established():
    ev = evidence(
        key="enriched",
        summary="CACI sent a phased-return proposal on 14 June 2005.",
    )
    result = make_m5_result(
        "RA-001",
        evidence_by_element={"RA-ADJUSTMENT": (ev,)},
        proposition_overrides={
            "RA-ADJUSTMENT": (
                proposition("The direct record documents a proposal concerning phased return.", ("enriched",)),
            )
        },
    )
    _, matrices, results = inputs(result)
    assertion = extract_event_assertions(matrices, results)[0]
    assert assertion.event_status is EventStatus.SUPPORTED
    assert assertion.timing_status is TimingStatus.SUPPORTED
    assert assertion.temporal_extent is not None
    assert assertion.temporal_extent.display_text == "14 June 2005"


def test_disputed_proposition_remains_disputed():
    ev = evidence(key="disputed", summary="The parties dispute whether a return-to-work meeting occurred on 4 July 2005.")
    result = make_m5_result(
        "LIM-001",
        evidence_by_element={"LIM-ACTS": (ev,)},
        proposition_overrides={
            "LIM-ACTS": (
                proposition(
                    "A return-to-work meeting occurred on 4 July 2005.",
                    ("disputed",),
                    status=PropositionAssessmentStatus.DISPUTED,
                ),
            )
        },
    )
    _, matrices, results = inputs(result)
    assertion = extract_event_assertions(matrices, results)[0]
    assert assertion.event_status is EventStatus.DISPUTED
    assert assertion.timing_status is TimingStatus.DISPUTED
