from __future__ import annotations

from case_analysis.m3.event_extraction import extract_event_assertions
from case_analysis.m3.models import EventType

from case_analysis_m3_helpers import evidence, inputs, make_m5_result, proposition


_GENERIC_PROPOSITION = "The mapped evidence contains factual material relevant to this element."


def _assertions(issue_id: str, element_id: str, summary: str, *, proposition_text: str = _GENERIC_PROPOSITION):
    ev = evidence(key="quality", summary=summary)
    result = make_m5_result(
        issue_id,
        evidence_by_element={element_id: (ev,)},
        proposition_overrides={
            element_id: (proposition(proposition_text, ("quality",)),)
        },
    )
    _, matrices, results = inputs(result)
    return extract_event_assertions(matrices, results)


def test_document_headings_are_suppressed_while_factual_adjustment_event_survives():
    assertions = _assertions(
        "RA-001",
        "RA-ADJUSTMENT",
        "\n".join(
            (
                "MEDICAL BACKGROUND",
                "reasonable Adjustments & Information Requested",
                "Home working was requested on 5 July 2005.",
            )
        ),
    )

    assert len(assertions) == 1
    assert assertions[0].event_type is EventType.ADJUSTMENT_PROPOSAL
    assert "home working was requested" in assertions[0].description.casefold()
    assert "medical background" not in assertions[0].description.casefold()
    assert "information requested" not in assertions[0].description.casefold()


def test_section_titles_policy_labels_and_dramatic_headings_create_no_events():
    assertions = _assertions(
        "DA-001",
        "DA-UNFAVOURABLE-TREATMENT",
        "\n".join(
            (
                "Section 3 – Factual Background (May 2005 RTW Meeting)",
                "Documents Relevant to the Capability Review",
                "Catastrophic Relapse and Permanent Incapacity",
                "The Company's Long-Term Sickness Absence Policy",
            )
        ),
    )

    assert assertions == ()


def test_email_and_acas_footer_boilerplate_is_suppressed():
    assertions = _assertions(
        "LIM-001",
        "LIM-PRESENTATION",
        "\n".join(
            (
                "If you have received this transmission in error, notify Acas immediately.",
                "Acas working for everyone.",
                "The ET1 claim was presented on 20 May 2025.",
            )
        ),
    )

    assert len(assertions) == 1
    assert assertions[0].event_type is EventType.TRIBUNAL_PROCEDURAL
    assert "et1 claim was presented" in assertions[0].description.casefold()


def test_generic_document_request_is_not_misclassified_as_adjustment_proposal():
    assertions = _assertions(
        "RA-001",
        "RA-ADJUSTMENT",
        "Medical records, documents and payslips were requested on 5 July 2005.",
    )

    assert assertions == ()


def test_actual_adjustment_request_remains_event_capable_after_request_hardening():
    assertions = _assertions(
        "RA-001",
        "RA-ADJUSTMENT",
        "A phased return and reduced hours were requested on 5 July 2005.",
    )

    assert len(assertions) == 1
    assert assertions[0].event_type is EventType.ADJUSTMENT_PROPOSAL


def test_noun_only_medical_label_requires_factual_event_predicate():
    assert _assertions(
        "EK-001",
        "EK-INFORMATION",
        "Medical assessment and permanent incapacity.",
    ) == ()

    assertions = _assertions(
        "EK-001",
        "EK-INFORMATION",
        "The claimant was assessed as unfit for work on 7 January 2003.",
    )
    assert len(assertions) == 1
    assert assertions[0].event_type is EventType.MEDICAL


def test_direct_heading_like_proposition_does_not_create_unknown_date_event():
    assertions = _assertions(
        "RA-001",
        "RA-ADJUSTMENT",
        "Reasonable Adjustments & Information Requested",
        proposition_text="Reasonable Adjustments & Information Requested",
    )

    assert assertions == ()


def test_signal_matching_uses_word_boundaries_not_substrings():
    assertions = _assertions(
        "LIM-001",
        "LIM-DATES",
        "The factual background was presented on 20 May 2025.",
    )

    # "act" must not match "factual" and "sent" must not match "presented".
    assert assertions == ()


def test_et1_presentation_keeps_tribunal_event_type_after_boundary_hardening():
    assertions = _assertions(
        "LIM-001",
        "LIM-PRESENTATION",
        "The ET1 claim was presented on 20 May 2025.",
    )

    assert len(assertions) == 1
    assert assertions[0].event_type is EventType.TRIBUNAL_PROCEDURAL


def test_all_capital_factual_sentence_with_action_is_not_treated_as_heading():
    assertions = _assertions(
        "LIM-001",
        "LIM-DATES",
        "CACI SENT A CAPABILITY REVIEW LETTER ON 17 JULY 2026.",
    )

    assert len(assertions) == 1
    assert assertions[0].event_type is EventType.CAPABILITY


def test_disclaimer_variant_without_if_is_suppressed():
    assertions = _assertions(
        "LIM-001",
        "LIM-PRESENTATION",
        "You have received this transmission in error; notify Acas immediately.",
    )

    assert assertions == ()


def test_incomplete_numeric_date_phrase_is_rejected():
    assertions = _assertions(
        "LIM-001",
        "LIM-PRESENTATION",
        "The claimant commenced ACAS early conciliation on 10.",
    )

    assert assertions == ()


def test_line_wrapped_complete_date_is_preserved_as_one_event_clause():
    assertions = _assertions(
        "LIM-001",
        "LIM-PRESENTATION",
        "The claimant commenced ACAS early conciliation on 10.\nAugust 2025.",
    )

    assert len(assertions) == 1
    assert assertions[0].temporal_extent is not None
    assert assertions[0].temporal_extent.display_text == "10 August 2025"
    assert "10 august 2025" in assertions[0].description.casefold()


def test_purpose_clause_is_not_treated_as_a_completed_communication_event():
    assertions = _assertions(
        "RA-001",
        "RA-KNOWLEDGE",
        "That informed decisions can be made about the capability review.",
    )

    assert assertions == ()


def test_pleaded_failure_assertion_is_not_treated_as_an_occurrence():
    assertions = _assertions(
        "LIM-001",
        "LIM-ACTS",
        "The Claimant has failed to provide adequate details of the alleged acts on 20 May 2025.",
    )

    assert assertions == ()


def test_dated_specific_clause_replaces_generic_adjustment_fallback():
    assertions = _assertions(
        "RA-001",
        "RA-ADJUSTMENT",
        "On 16 May 2005, CACI proposed a phased return.",
        proposition_text="The direct record documents a proposal or request concerning an adjustment.",
    )

    assert len(assertions) == 1
    assert assertions[0].temporal_extent is not None
    assert assertions[0].temporal_extent.display_text == "16 May 2005"
    assert "caci proposed a phased return" in assertions[0].description.casefold()
    assert "proposal or request concerning an adjustment" not in assertions[0].description.casefold()


def test_unique_sent_header_dates_transactional_adjustment_despite_other_body_date():
    assertions = _assertions(
        "RA-001",
        "RA-ADJUSTMENT",
        "\n".join(
            (
                "From: CACI",
                "Sent: 16 May 2005",
                "Subject: Phased return",
                "A phased return was proposed.",
                "The earlier absence began during 2001.",
            )
        ),
    )

    phased = [item for item in assertions if "phased return was proposed" in item.description.casefold()]
    assert len(phased) == 1
    assert phased[0].temporal_extent is not None
    assert phased[0].temporal_extent.display_text == "16 May 2005"


def test_relapse_and_payslip_signals_remain_event_capable_with_dates():
    relapse = _assertions(
        "EK-001",
        "EK-INFORMATION",
        "The claimant relapsed on 1 July 2005.",
    )
    payslip = _assertions(
        "LIM-001",
        "LIM-DATES",
        "Payslips were provided in August 2025.",
    )

    assert len(relapse) == 1
    assert relapse[0].temporal_extent is not None
    assert relapse[0].temporal_extent.display_text == "1 July 2005"
    assert len(payslip) == 1
    assert payslip[0].temporal_extent is not None
    assert payslip[0].temporal_extent.display_text == "August 2025"


def test_legal_conclusion_is_trimmed_from_a_material_factual_event():
    assertions = _assertions(
        "LIM-001",
        "LIM-ACTS",
        "The source records that CACI failed to provide payslips in breach of s.8.",
    )

    assert len(assertions) == 1
    assert "in breach of" not in assertions[0].description.casefold()
    assert "failed to provide payslips" in assertions[0].description.casefold()


def test_pleaded_race_discrimination_submission_is_not_an_event():
    assertions = _assertions(
        "LIM-001",
        "LIM-RESPONDENT-POSITION",
        "The Respondent submits that the race discrimination allegation is out of time.",
    )

    assert assertions == ()


def test_background_and_comparative_fragments_are_not_events():
    assert _assertions(
        "LIM-001",
        "LIM-ACTS",
        "Of the events underlying this claim and continued access to relevant HR records.",
    ) == ()
    assert _assertions(
        "RA-001",
        "RA-KNOWLEDGE",
        "Rather than relying solely on historical reports, further information was requested.",
    ) == ()


def test_truncated_body_is_rejected_but_meaningful_email_header_preserves_dated_event():
    assertions = _assertions(
        "LIM-001",
        "LIM-DATES",
        "\n".join(
            (
                "From: Phil Jones <phil.jones@caci.co.uk>",
                "Sent: 14 June 2005",
                "Subject: VF specification",
                "Phil, can you carry on with the VF specification as discussed, and then update the.",
            )
        ),
    )

    assert len(assertions) == 1
    event = assertions[0]
    assert event.event_type is EventType.COMMUNICATION
    assert event.temporal_extent is not None
    assert event.temporal_extent.display_text == "14 June 2005"
    assert "vf specification" in event.description.casefold()
    assert "update the" not in event.description.casefold()


def test_generic_phased_return_proposition_does_not_survive_without_specific_source_clause():
    assertions = _assertions(
        "RA-001",
        "RA-ADJUSTMENT",
        "Adjustment information was reviewed.",
        proposition_text="A proposal or request concerning phased return.",
    )

    assert assertions == ()


def test_specific_payroll_email_header_recovers_dated_communication():
    assertions = _assertions(
        "LIM-001",
        "LIM-DATES",
        "\n".join(
            (
                "From: CACI Payroll <payroll@caci.co.uk>",
                "Sent: 4 September 2025",
                "Subject: Payslips",
                "Please see the attached payslips.",
            )
        ),
    )

    assert len(assertions) == 1
    event = assertions[0]
    assert event.event_type is EventType.COMMUNICATION
    assert event.temporal_extent is not None
    assert event.temporal_extent.display_text == "4 September 2025"
    assert "caci payroll" in event.description.casefold()
    assert "payslips" in event.description.casefold()


def test_specific_dated_payslip_request_is_a_communication_not_employment_event():
    assertions = _assertions(
        "LIM-001",
        "LIM-DATES",
        "The claimant requested payslips in August 2025.",
    )

    assert len(assertions) == 1
    event = assertions[0]
    assert event.event_type is EventType.COMMUNICATION
    assert event.temporal_extent is not None
    assert event.temporal_extent.display_text == "August 2025"


def test_long_bundle_document_request_is_not_a_chronology_event_even_when_dated():
    assertions = _assertions(
        "LIM-001",
        "LIM-DATES",
        (
            "On 20 August 2025 the claimant requested copies of medical records, "
            "HR files, policies, correspondence, payslips and all other documents."
        ),
    )

    assert assertions == ()


def test_dated_relapse_assertion_with_followed_wording_remains_event_capable():
    assertions = _assertions(
        "EK-001",
        "EK-INFORMATION",
        "The claimant states that a relapse followed the 1 July 2005 meeting.",
    )

    assert len(assertions) == 1
    assert assertions[0].temporal_extent is not None
    assert assertions[0].temporal_extent.display_text == "1 July 2005"
    assert "relapse followed" in assertions[0].description.casefold()


def test_28_june_2005_email_header_recovers_complete_dated_communication():
    assertions = _assertions(
        "EK-001",
        "EK-TIMING",
        "\n".join(
            (
                "From: CACI HR <hr@caci.co.uk>",
                "Sent: 28 June 2005",
                "Subject: Return-to-work discussion",
                "The return-to-work arrangements were discussed.",
            )
        ),
    )

    assert len(assertions) == 1
    assert assertions[0].event_type is EventType.COMMUNICATION
    assert assertions[0].temporal_extent is not None
    assert assertions[0].temporal_extent.display_text == "28 June 2005"


def test_acas_procedural_event_trims_trailing_limitation_argument():
    assertions = _assertions(
        "LIM-001",
        "LIM-PRESENTATION",
        (
            "The Claimant commenced ACAS early conciliation on 10 September 2025, "
            "as such any acts occurring prior to 9 June 2025 are prima facie out of time."
        ),
    )

    assert len(assertions) == 1
    event = assertions[0]
    assert event.temporal_extent is not None
    assert event.temporal_extent.display_text == "10 September 2025"
    assert "prima facie" not in event.description.casefold()
    assert "out of time" not in event.description.casefold()
    assert "9 june 2025" not in event.description.casefold()


def test_long_adjustment_related_document_request_is_suppressed():
    assertions = _assertions(
        "RA-001",
        "RA-ADJUSTMENT",
        (
            "I requested any records relating to consideration of reasonable adjustments, "
            "copies of any Occupational Health reports, copies of any documents, "
            "records and information held by the Company on 4 September 2025."
        ),
    )

    assert assertions == ()


def test_conditional_adjustment_commentary_does_not_create_event():
    assert _assertions(
        "RA-001",
        "RA-ADJUSTMENT",
        (
            "If Occupational Health concludes that a return to work is medically appropriate, "
            "I believe the following measures should be considered: phased return and home working."
        ),
    ) == ()

    assert _assertions(
        "RA-001",
        "RA-FAILURE",
        (
            "If the Company considers that any recommended adjustment cannot be implemented, "
            "I ask that its reasons be explained."
        ),
    ) == ()


def test_flattened_outlook_headers_recover_specific_vf_email_event():
    assertions = _assertions(
        "EK-001",
        "EK-TIMING",
        (
            "From: Phil Jones <phil.jones@caci.co.uk> Sent: 14 June 2005 "
            "Subject: VF specification Phil, can you carry on with the VF specification "
            "as discussed, and then update the."
        ),
    )

    assert len(assertions) == 1
    event = assertions[0]
    assert event.temporal_extent is not None
    assert event.temporal_extent.display_text == "14 June 2005"
    assert "vf specification" in event.description.casefold()
    assert "update the" not in event.description.casefold()


def test_unique_body_date_can_date_linked_relapse_and_demotion_assertions():
    relapse = _assertions(
        "EK-001",
        "EK-INFORMATION",
        (
            "A return-to-work meeting took place on 1 July 2005. "
            "The claimant states that a relapse followed the meeting."
        ),
    )
    demotion = _assertions(
        "DA-001",
        "DA-UNFAVOURABLE-TREATMENT",
        (
            "A meeting took place on 1 July 2005. "
            "The claimant states that he was demoted to a junior administrative role."
        ),
    )

    assert len(relapse) == 1
    assert relapse[0].temporal_extent is not None
    assert relapse[0].temporal_extent.display_text == "1 July 2005"
    assert len(demotion) == 1
    assert demotion[0].temporal_extent is not None
    assert demotion[0].temporal_extent.display_text == "1 July 2005"
