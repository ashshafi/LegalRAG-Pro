from __future__ import annotations

from legal_analysis.enums import Confidence
from legal_analysis.evidence_assessment import PropositionAssessmentStatus

from case_analysis.m3.chronology import build_case_chronology
from case_analysis.m3.event_extraction import extract_event_assertions
from case_analysis.m3.models import EventStatus, EventType, TimingStatus

from case_analysis_m3_helpers import (
    evidence,
    inputs,
    make_m5_result,
    proposition,
    source_assertion_evidence,
)


_GENERIC_SOURCE = "The mapped source assertion contains factual material relevant to this element; M4 does not promote the raw excerpt itself into an established proposition."
_GENERIC_EMPLOYER = "The mapped employer evidence contains factual material relevant to this element; M4 does not promote the raw excerpt itself into an established proposition."


def _supported_generic(text: str, key: str):
    return proposition(
        text,
        (key,),
        status=PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
        confidence=Confidence.MEDIUM,
    )


def _unresolved_generic(key: str):
    return proposition(
        _GENERIC_EMPLOYER,
        (key,),
        status=PropositionAssessmentStatus.UNRESOLVED,
        confidence=Confidence.LOW,
    )


def test_live_h4_split_email_envelope_recovers_vf_event_without_inventing_lim():
    key = "h4-live"
    h4 = source_assertion_evidence(
        key=key,
        document_name="Appendix H4.pdf",
        summary=(
            "Appendix H4 – Internal Work and Rehabilitation Correspondence (April–June 2005)\n"
            "Email 1 – Terry Williamson → Phil Lucy & Arshad Shafi (14 June 2005, 20:32)\n"
            "Cc: Mike Fernandes\n"
            "Subject: HB User Documentation\n"
            "I have therefore decided to have a meeting on Thursday morning to bottom out what needs to be done.\n"
            "Phil, can you carry on with the VF specification as discussed, and then update the"
        ),
    )
    results = (
        make_m5_result(
            "DA-001",
            issue_analysis_id="11111111-1111-4111-8111-111111111111",
            evidence_by_element={"DA-KNOWLEDGE": (h4,)},
            proposition_overrides={"DA-KNOWLEDGE": (_supported_generic(_GENERIC_SOURCE, key),)},
        ),
        make_m5_result(
            "EK-001",
            issue_analysis_id="22222222-2222-4222-8222-222222222222",
            evidence_by_element={"EK-RECIPIENT": (h4,)},
            proposition_overrides={"EK-RECIPIENT": (_supported_generic(_GENERIC_SOURCE, key),)},
        ),
        make_m5_result(
            "RA-001",
            issue_analysis_id="33333333-3333-4333-8333-333333333333",
            evidence_by_element={"RA-KNOWLEDGE": (h4,)},
            proposition_overrides={"RA-KNOWLEDGE": (_supported_generic(_GENERIC_SOURCE, key),)},
        ),
    )
    foundation, matrices, frozen = inputs(*results)
    chronology = build_case_chronology(foundation, matrices, frozen)

    vf_events = [item for item in chronology.events if "vf specification" in item.description.casefold()]
    assert len(vf_events) == 1
    event = vf_events[0]
    assert event.event_type is EventType.COMMUNICATION
    assert event.canonical_temporal_extent is not None
    assert event.canonical_temporal_extent.display_text == "14 June 2005"
    assert event.related_issue_definition_ids == ("DA-001", "EK-001", "RA-001")
    assert "LIM-001" not in event.related_issue_definition_ids
    assert "update the" not in event.description.casefold()


def test_live_1_july_relapse_causal_grammar_is_discovered_and_source_qualified():
    key = "relapse-live"
    relapse = source_assertion_evidence(
        key=key,
        document_name="Appendix J - Witness Statement.pdf",
        summary="The events of 1 July 2005 caused a catastrophic relapse of my psychiatric condition.",
    )
    result = make_m5_result(
        "DA-001",
        evidence_by_element={"DA-DISABILITY": (relapse,)},
        proposition_overrides={"DA-DISABILITY": (_supported_generic(_GENERIC_SOURCE, key),)},
    )
    _, matrices, frozen = inputs(result)
    assertions = extract_event_assertions(matrices, frozen)

    assert len(assertions) == 1
    assertion = assertions[0]
    assert assertion.event_type is EventType.MEDICAL
    assert assertion.event_status is EventStatus.SUPPORTED
    assert assertion.temporal_extent is not None
    assert assertion.temporal_extent.display_text == "1 July 2005"
    assert "relapse" in assertion.description.casefold()
    assert (
        "source records an assertion" in assertion.description.casefold()
        or "claimant states" in assertion.description.casefold()
    )


def test_august_payslip_request_is_exceptionally_projected_only_through_existing_ek_unresolved():
    key = "payslip-aug-live"
    payslip = evidence(
        key=key,
        document_name="Appendix D – Payslip Request Letter.pdf",
        summary="In August 2025, the Claimant formally requested copies of payslips and P60s from the Respondent.",
    )
    result = make_m5_result(
        "EK-001",
        evidence_by_element={"EK-UNRESOLVED": (payslip,)},
        proposition_overrides={"EK-UNRESOLVED": (_unresolved_generic(key),)},
    )
    foundation, matrices, frozen = inputs(result)
    chronology = build_case_chronology(foundation, matrices, frozen)

    assert len(chronology.events) == 1
    event = chronology.events[0]
    assert event.event_status is EventStatus.UNRESOLVED
    assert event.related_issue_definition_ids == ("EK-001",)
    assert event.related_element_ids == ("EK-UNRESOLVED",)
    assert event.canonical_temporal_extent is not None
    assert event.canonical_temporal_extent.display_text == "August 2025"
    assert "LIM-001" not in event.related_issue_definition_ids


def test_4_september_payroll_email_is_separate_exceptional_projection_without_borrowing_lim():
    key = "payroll-4-sep-live"
    payroll = evidence(
        key=key,
        document_name="Appendix D – Payslip Request Letter.pdf",
        summary=(
            "Email from Joanna Eaton, Payroll Manager – 4 September 2025. "
            "I understand from our HR director that you have requested copies of your last 12 payslips."
        ),
    )
    result = make_m5_result(
        "EK-001",
        evidence_by_element={"EK-UNRESOLVED": (payroll,)},
        proposition_overrides={"EK-UNRESOLVED": (_unresolved_generic(key),)},
    )
    foundation, matrices, frozen = inputs(result)
    chronology = build_case_chronology(foundation, matrices, frozen)

    assert len(chronology.events) == 1
    event = chronology.events[0]
    assert event.event_status is EventStatus.UNRESOLVED
    assert event.canonical_temporal_extent is not None
    assert event.canonical_temporal_extent.display_text == "4 September 2025"
    assert event.related_issue_definition_ids == ("EK-001",)
    assert "LIM-001" not in event.related_issue_definition_ids


def test_6_september_payroll_response_can_have_supported_content_and_established_timing():
    key = "payroll-6-sep-live"
    payroll = evidence(
        key=key,
        document_name="Appendix D – Payslip Request Letter.pdf",
        summary=(
            "Response from Joanna Eaton – 6 September 2025. "
            "I will ensure your payslips are forwarded to this email account each month going forward."
        ),
    )
    result = make_m5_result(
        "LIM-001",
        evidence_by_element={"LIM-DATES": (payroll,)},
        proposition_overrides={
            "LIM-DATES": (
                proposition(
                    "The direct record documents a relevant event or communication dated 6 September 2025.",
                    (key,),
                    status=PropositionAssessmentStatus.ESTABLISHED_BY_CURRENT_EVIDENCE,
                    confidence=Confidence.HIGH,
                ),
            )
        },
    )
    _, matrices, frozen = inputs(result)
    assertions = extract_event_assertions(matrices, frozen)

    assert len(assertions) == 1
    assertion = assertions[0]
    assert assertion.event_status is EventStatus.SUPPORTED
    assert assertion.timing_status is TimingStatus.ESTABLISHED
    assert assertion.temporal_extent is not None
    assert assertion.temporal_extent.display_text == "6 September 2025"
    assert "payslip" in assertion.description.casefold()


def test_generic_non_event_capable_projection_does_not_whitelist_unrelated_multi_event_chunk():
    key = "mixed-unresolved-live"
    mixed = evidence(
        key=key,
        summary=(
            "In August 2025, the Claimant requested copies of payslips. "
            "The events of 1 July 2005 caused a relapse of his psychiatric condition."
        ),
    )
    result = make_m5_result(
        "EK-001",
        evidence_by_element={"EK-UNRESOLVED": (mixed,)},
        proposition_overrides={"EK-UNRESOLVED": (_unresolved_generic(key),)},
    )
    _, matrices, frozen = inputs(result)

    assert extract_event_assertions(matrices, frozen) == ()


def test_not_supported_non_event_capable_use_cannot_project_discovered_event():
    key = "not-supported-unresolved-live"
    payslip = evidence(
        key=key,
        summary="In August 2025, the Claimant requested copies of payslips and P60s.",
    )
    result = make_m5_result(
        "EK-001",
        evidence_by_element={"EK-UNRESOLVED": (payslip,)},
        proposition_overrides={
            "EK-UNRESOLVED": (
                proposition(
                    _GENERIC_EMPLOYER,
                    (key,),
                    status=PropositionAssessmentStatus.NOT_SUPPORTED_BY_CURRENT_EVIDENCE,
                    confidence=Confidence.LOW,
                ),
            )
        },
    )
    _, matrices, frozen = inputs(result)

    assert extract_event_assertions(matrices, frozen) == ()


def test_automatic_reply_header_is_rejected_before_body_topic_can_rescue_it():
    key = "c2-auto-reply-live"
    c2 = evidence(
        key=key,
        document_name="Appendix C2.pdf",
        summary=(
            "Please find attached a copy of the letter provided by my GP.\n"
            "I have been referred to the Coventry and Warwickshire WorkWell service to support my health "
            "and facilitate a supported return to work.\n"
            "From: Alison M Brooks (Head of HR) <ambrooks@caci.co.uk>\n"
            "Sent: 24 July 2026 08:13\n"
            "To: ARSHAD Shafi <ashshafi@hotmail.com>\n"
            "Subject: Automatic reply: CACI Employment"
        ),
    )
    result = make_m5_result(
        "EK-001",
        evidence_by_element={"EK-RECIPIENT": (c2,)},
        proposition_overrides={
            "EK-RECIPIENT": (
                proposition(
                    "The direct correspondence records communication or receipt of health/return-to-work information involving identifiable CACI personnel.",
                    (key,),
                    status=PropositionAssessmentStatus.ESTABLISHED_BY_CURRENT_EVIDENCE,
                    confidence=Confidence.HIGH,
                ),
            )
        },
    )
    foundation, matrices, frozen = inputs(result)
    chronology = build_case_chronology(foundation, matrices, frozen)

    assert all("alison" not in event.description.casefold() for event in chronology.events)
    assert all("automatic reply" not in event.description.casefold() for event in chronology.events)
