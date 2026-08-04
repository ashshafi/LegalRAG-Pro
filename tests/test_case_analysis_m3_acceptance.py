from __future__ import annotations

from dataclasses import replace

from case_analysis.m3.chronology import build_case_chronology
from case_analysis.m3.chronology_serialization import dumps_case_chronology, loads_case_chronology
from case_analysis.m3.models import EventStatus, TimingStatus
from legal_analysis.evidence_assessment import PropositionAssessmentStatus

from case_analysis_m3_helpers import evidence, inputs, make_m5_result, proposition


def test_four_doctrine_chronology_acceptance_exercise():
    shared_meeting = evidence(
        key="shared-meeting",
        summary="A return-to-work meeting occurred on 5 July 2005.",
    )
    adjustment = evidence(
        key="adjustment",
        document_name="adjustment.pdf",
        document_id="doc-adjustment",
        summary="Home working was requested in July 2005.",
    )
    treatment = evidence(
        key="treatment",
        document_name="treatment.pdf",
        document_id="doc-treatment",
        summary="CACI commenced a capability review on 17 July 2026.",
    )
    presentation = evidence(
        key="presentation",
        document_name="et1.pdf",
        document_id="doc-et1",
        summary="The ET1 claim was presented on 20 May 2025.",
    )
    je_factors = evidence(
        key="je-factors",
        document_name="delay-evidence.pdf",
        document_id="doc-delay",
        summary="The claimant attended a medical appointment on 29 July 2026 and relies on health factors.",
    )

    results = (
        make_m5_result(
            "EK-001",
            issue_analysis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            evidence_by_element={"EK-TIMING": (shared_meeting,)},
            proposition_overrides={
                "EK-TIMING": (
                    proposition("A return-to-work meeting occurred on 5 July 2005.", ("shared-meeting",)),
                )
            },
        ),
        make_m5_result(
            "RA-001",
            issue_analysis_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            evidence_by_element={"RA-ADJUSTMENT": (adjustment,), "RA-TIMING": (shared_meeting,)},
            proposition_overrides={
                "RA-ADJUSTMENT": (
                    proposition(
                        "Home working was requested in July 2005.",
                        ("adjustment",),
                        status=PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
                    ),
                ),
                "RA-TIMING": (
                    proposition("A return-to-work meeting occurred on 5 July 2005.", ("shared-meeting",)),
                ),
            },
        ),
        make_m5_result(
            "DA-001",
            issue_analysis_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
            evidence_by_element={"DA-UNFAVOURABLE-TREATMENT": (treatment,)},
            proposition_overrides={
                "DA-UNFAVOURABLE-TREATMENT": (
                    proposition(
                        "CACI commenced a capability review on 17 July 2026.",
                        ("treatment",),
                        status=PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
                    ),
                )
            },
        ),
        make_m5_result(
            "LIM-001",
            issue_analysis_id="dddddddd-dddd-4ddd-8ddd-dddddddddddd",
            evidence_by_element={
                "LIM-ACTS": (shared_meeting,),
                "LIM-PRESENTATION": (presentation,),
                "LIM-JE-FACTORS": (je_factors,),
            },
            proposition_overrides={
                "LIM-ACTS": (
                    proposition("A return-to-work meeting occurred on 5 July 2005.", ("shared-meeting",)),
                ),
                "LIM-PRESENTATION": (
                    proposition("The ET1 claim was presented on 20 May 2025.", ("presentation",)),
                ),
                "LIM-JE-FACTORS": (
                    proposition(
                        "The claimant attended a medical appointment on 29 July 2026 and relies on health factors.",
                        ("je-factors",),
                    ),
                ),
            },
        ),
    )

    foundation, matrices, frozen = inputs(*results)
    chronology = build_case_chronology(foundation, matrices, tuple(reversed(frozen)))
    restored = loads_case_chronology(dumps_case_chronology(chronology))

    assert restored == chronology
    assert len(chronology.events) == 4
    shared = next(item for item in chronology.events if item.evidence_keys == ("shared-meeting",))
    assert shared.related_issue_definition_ids == ("EK-001", "LIM-001", "RA-001")
    assert len(shared.assertions) == 3
    supported = {item.evidence_keys[0]: item.event_status for item in chronology.events}
    assert supported["adjustment"] is EventStatus.SUPPORTED
    assert supported["treatment"] is EventStatus.SUPPORTED
    assert supported["presentation"] is EventStatus.ESTABLISHED
    assert all("je-factors" not in item.evidence_keys for item in chronology.events)


def test_m5_legal_analysis_prose_cannot_create_or_change_events():
    ev = evidence(key="event", summary="CACI sent a letter on 17 July 2026.")
    result = make_m5_result(
        "LIM-001",
        evidence_by_element={"LIM-DATES": (ev,)},
        proposition_overrides={
            "LIM-DATES": (proposition("CACI sent a letter on 17 July 2026.", ("event",)),)
        },
    )
    foundation, matrices, frozen = inputs(result)
    baseline = build_case_chronology(foundation, matrices, frozen)

    altered_elements = tuple(
        replace(
            item,
            legal_significance="A fabricated legal narrative says another event happened on 1 January 1999.",
            provisional_analysis="The statutory test is satisfied on 2 February 2000.",
        )
        for item in result.element_analyses
    )
    altered = replace(result, element_analyses=altered_elements)

    # The foundation lineage is unchanged because legal prose is not source identity.
    changed = build_case_chronology(foundation, matrices, (altered,))
    assert changed == baseline
    assert "1999" not in dumps_case_chronology(changed)
    assert "2000" not in dumps_case_chronology(changed)


def test_dated_shared_communication_remains_one_multi_issue_event_after_rebalancing():
    shared = evidence(
        key="shared-correspondence",
        summary="Sent: 14 June 2005\nCACI sent an email discussing the return-to-work plan.",
    )
    generic = "The mapped evidence contains factual material relevant to this element."
    results = (
        make_m5_result(
            "EK-001",
            issue_analysis_id="11111111-1111-4111-8111-111111111111",
            evidence_by_element={"EK-TIMING": (shared,)},
            proposition_overrides={
                "EK-TIMING": (proposition(generic, ("shared-correspondence",)),)
            },
        ),
        make_m5_result(
            "RA-001",
            issue_analysis_id="22222222-2222-4222-8222-222222222222",
            evidence_by_element={"RA-TIMING": (shared,)},
            proposition_overrides={
                "RA-TIMING": (proposition(generic, ("shared-correspondence",)),)
            },
        ),
        make_m5_result(
            "LIM-001",
            issue_analysis_id="33333333-3333-4333-8333-333333333333",
            evidence_by_element={"LIM-DATES": (shared,)},
            proposition_overrides={
                "LIM-DATES": (proposition(generic, ("shared-correspondence",)),)
            },
        ),
    )

    foundation, matrices, frozen = inputs(*results)
    chronology = build_case_chronology(foundation, matrices, frozen)

    assert len(chronology.events) == 1
    event = chronology.events[0]
    assert event.canonical_temporal_extent is not None
    assert event.canonical_temporal_extent.display_text == "14 June 2005"
    assert event.related_issue_definition_ids == ("EK-001", "LIM-001", "RA-001")
    assert len(event.assertions) == 3


def test_live_like_dated_events_and_shared_links_survive_final_extraction_policy():
    shared_work_email = evidence(
        key="work-email-14-june",
        document_name="work-email.pdf",
        document_id="doc-work-email",
        summary="\n".join(
            (
                "From: Phil Jones <phil.jones@caci.co.uk>",
                "Sent: 14 June 2005",
                "Subject: VF specification",
                "Phil, can you carry on with the VF specification as discussed, and then update the.",
            )
        ),
    )
    phased_return = evidence(
        key="phased-return-16-may",
        document_name="phased-return.pdf",
        document_id="doc-phased-return",
        summary="\n".join(
            (
                "From: CACI HR <hr@caci.co.uk>",
                "Sent: 16 May 2005",
                "Subject: Phased return",
                "CACI HR proposed a phased return.",
            )
        ),
    )
    communication_28_june = evidence(
        key="communication-28-june",
        document_name="communication.pdf",
        document_id="doc-communication",
        summary="\n".join(
            (
                "From: CACI HR <hr@caci.co.uk>",
                "Sent: 28 June 2005",
                "Subject: Return-to-work discussion",
                "CACI HR emailed about the return-to-work arrangements.",
            )
        ),
    )
    relapse = evidence(
        key="relapse-1-july",
        document_name="relapse.pdf",
        document_id="doc-relapse",
        summary="The claimant states that a relapse followed the 1 July 2005 meeting.",
    )
    payslip_request = evidence(
        key="payslip-request-august",
        document_name="payslip-request.pdf",
        document_id="doc-payslip-request",
        summary="The claimant requested payslips in August 2025.",
    )
    payroll_email = evidence(
        key="payroll-email-4-september",
        document_name="payroll-email.pdf",
        document_id="doc-payroll-email",
        summary="\n".join(
            (
                "From: CACI Payroll <payroll@caci.co.uk>",
                "Sent: 4 September 2025",
                "Subject: Payslips",
                "Please see the attached payslips.",
            )
        ),
    )
    capability = evidence(
        key="capability-17-july",
        document_name="capability.pdf",
        document_id="doc-capability",
        summary="CACI commenced a capability review on 17 July 2026.",
    )

    generic = "The mapped evidence contains factual material relevant to this element."
    results = (
        make_m5_result(
            "EK-001",
            issue_analysis_id="44444444-4444-4444-8444-444444444444",
            evidence_by_element={
                "EK-INFORMATION": (relapse,),
                "EK-TIMING": (shared_work_email, communication_28_june),
            },
            proposition_overrides={
                "EK-INFORMATION": (proposition(generic, ("relapse-1-july",)),),
                "EK-TIMING": (
                    proposition(generic, ("work-email-14-june",)),
                    proposition(generic, ("communication-28-june",)),
                ),
            },
        ),
        make_m5_result(
            "RA-001",
            issue_analysis_id="55555555-5555-4555-8555-555555555555",
            evidence_by_element={
                "RA-ADJUSTMENT": (phased_return,),
                "RA-TIMING": (shared_work_email,),
            },
            proposition_overrides={
                "RA-ADJUSTMENT": (proposition(generic, ("phased-return-16-may",)),),
                "RA-TIMING": (proposition(generic, ("work-email-14-june",)),),
            },
        ),
        make_m5_result(
            "DA-001",
            issue_analysis_id="66666666-6666-4666-8666-666666666666",
            evidence_by_element={"DA-UNFAVOURABLE-TREATMENT": (capability,)},
            proposition_overrides={
                "DA-UNFAVOURABLE-TREATMENT": (
                    proposition(
                        generic,
                        ("capability-17-july",),
                        status=PropositionAssessmentStatus.SUPPORTED_BUT_NOT_ESTABLISHED,
                    ),
                )
            },
        ),
        make_m5_result(
            "LIM-001",
            issue_analysis_id="77777777-7777-4777-8777-777777777777",
            evidence_by_element={
                "LIM-DATES": (
                    shared_work_email,
                    payslip_request,
                    payroll_email,
                ),
            },
            proposition_overrides={
                "LIM-DATES": (
                    proposition(generic, ("work-email-14-june",)),
                    proposition(generic, ("payslip-request-august",)),
                    proposition(generic, ("payroll-email-4-september",)),
                ),
            },
        ),
    )

    foundation, matrices, frozen = inputs(*results)
    chronology = build_case_chronology(foundation, matrices, frozen)

    dated = [event for event in chronology.events if event.canonical_temporal_extent is not None]
    shared = [
        event
        for event in chronology.events
        if len(event.related_issue_definition_ids) > 1
    ]

    assert len(dated) >= 7
    assert shared
    display_dates = {
        event.canonical_temporal_extent.display_text
        for event in dated
        if event.canonical_temporal_extent is not None
    }
    assert {
        "16 May 2005",
        "14 June 2005",
        "28 June 2005",
        "1 July 2005",
        "August 2025",
        "4 September 2025",
        "17 July 2026",
    }.issubset(display_dates)

    shared_email = next(
        event for event in shared
        if "work-email-14-june" in event.evidence_keys
    )
    assert shared_email.related_issue_definition_ids == ("EK-001", "LIM-001", "RA-001")
    assert all("update the" not in event.description.casefold() for event in chronology.events)
    assert all("in breach of" not in event.description.casefold() for event in chronology.events)


def test_flattened_shared_work_email_remains_cross_issue_event():
    shared = evidence(
        key="flattened-work-email",
        document_name="work-email.pdf",
        document_id="doc-flattened-work-email",
        summary=(
            "From: Phil Jones <phil.jones@caci.co.uk> Sent: 14 June 2005 "
            "Subject: VF specification Phil, can you carry on with the VF specification "
            "as discussed, and then update the."
        ),
    )
    generic = "The mapped evidence contains factual material relevant to this element."
    results = (
        make_m5_result(
            "EK-001",
            issue_analysis_id="81818181-8181-4181-8181-818181818181",
            evidence_by_element={"EK-TIMING": (shared,)},
            proposition_overrides={
                "EK-TIMING": (proposition(generic, ("flattened-work-email",)),)
            },
        ),
        make_m5_result(
            "RA-001",
            issue_analysis_id="82828282-8282-4282-8282-828282828282",
            evidence_by_element={"RA-TIMING": (shared,)},
            proposition_overrides={
                "RA-TIMING": (proposition(generic, ("flattened-work-email",)),)
            },
        ),
        make_m5_result(
            "LIM-001",
            issue_analysis_id="83838383-8383-4383-8383-838383838383",
            evidence_by_element={"LIM-DATES": (shared,)},
            proposition_overrides={
                "LIM-DATES": (proposition(generic, ("flattened-work-email",)),)
            },
        ),
    )

    foundation, matrices, frozen = inputs(*results)
    chronology = build_case_chronology(foundation, matrices, frozen)

    assert len(chronology.events) == 1
    event = chronology.events[0]
    assert event.canonical_temporal_extent is not None
    assert event.canonical_temporal_extent.display_text == "14 June 2005"
    assert event.related_issue_definition_ids == ("EK-001", "LIM-001", "RA-001")
    assert len(event.assertions) == 3
    assert "update the" not in event.description.casefold()


def test_competing_payroll_dates_are_preserved_as_disputed_timing():
    payroll_4 = evidence(
        key="payroll-4-september",
        document_name="payroll-4.pdf",
        document_id="doc-payroll-4",
        summary=(
            "From: Joanna Eaton <joanna.eaton@caci.co.uk>\n"
            "Sent: 4 September 2025\n"
            "Subject: Payslips\n"
            "Joanna Eaton emailed the claimant regarding payslips."
        ),
    )
    payroll_6 = evidence(
        key="payroll-6-september",
        document_name="payroll-6.pdf",
        document_id="doc-payroll-6",
        summary=(
            "From: Joanna Eaton <joanna.eaton@caci.co.uk>\n"
            "Sent: 6 September 2025\n"
            "Subject: Payslips\n"
            "Joanna Eaton emailed the claimant regarding payslips."
        ),
    )
    generic = "The mapped evidence contains factual material relevant to this element."
    result = make_m5_result(
        "LIM-001",
        issue_analysis_id="84848484-8484-4484-8484-848484848484",
        evidence_by_element={"LIM-DATES": (payroll_4, payroll_6)},
        proposition_overrides={
            "LIM-DATES": (
                proposition(generic, ("payroll-4-september",)),
                proposition(generic, ("payroll-6-september",)),
            )
        },
    )

    foundation, matrices, frozen = inputs(result)
    chronology = build_case_chronology(foundation, matrices, frozen)

    assert len(chronology.events) == 2
    assert {event.canonical_temporal_extent.display_text for event in chronology.events} == {
        "4 September 2025",
        "6 September 2025",
    }
    assert {event.evidence_keys for event in chronology.events} == {
        ("payroll-4-september",),
        ("payroll-6-september",),
    }
    assert all(event.timing_status is not TimingStatus.DISPUTED for event in chronology.events)
