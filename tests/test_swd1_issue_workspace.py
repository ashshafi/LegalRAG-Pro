from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace as NS
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ui import swd1_issue_workspace as ui  # noqa: E402

APP = ROOT / "src" / "app.py"
NEW_UI = ROOT / "src" / "ui" / "swd1_issue_workspace.py"


def _issue(*, disputed=0, incomplete=0, unresolved=0, partial=0, well=0,
           high=0, medium=0, low=0):
    return NS(
        synthesis_counts=NS(
            disputed=disputed,
            insufficiently_evidenced=incomplete,
            unresolved=unresolved,
            partially_supported=partial,
            well_supported=well,
        ),
        confidence_counts=NS(high=high, medium=medium, low=low),
    )


def test_unique_renderer_exists():
    assert hasattr(ui, "show_swd1_issue_workspace")
    assert not hasattr(ui, "show_legal_issue_dashboard")


def test_issue_position_precedence():
    assert ui._issue_position(_issue(disputed=1, incomplete=5)) == "DISPUTED"
    assert ui._issue_position(_issue(incomplete=1, unresolved=5)) == "EVIDENCE INCOMPLETE"
    assert ui._issue_position(_issue(unresolved=1, partial=5)) == "UNRESOLVED"
    assert ui._issue_position(_issue(partial=1, well=5)) == "PARTIALLY SUPPORTED"
    assert ui._issue_position(_issue(well=5)) == "WELL SUPPORTED"


def test_confidence_uses_weakest_ceiling():
    assert ui._issue_confidence(_issue(high=5, low=1)) == "LOW"
    assert ui._issue_confidence(_issue(high=5, medium=1)) == "MEDIUM"
    assert ui._issue_confidence(_issue(high=5)) == "HIGH"


def test_repeated_propositions_are_grouped_and_sources_retained():
    s1 = NS(
        text="Same proposition",
        evidence_keys=("e1",),
        citations=("Doc A, p.1",),
    )
    s2 = NS(
        text="Same proposition",
        evidence_keys=("e2",),
        citations=("Doc B, p.2",),
    )
    substantive, technical = ui._group_display_statements((s1, s2))
    assert technical == ()
    assert substantive == (
        ("Same proposition", ("Doc A, p.1", "Doc B, p.2")),
    )


def test_technical_mapping_boilerplate_is_secondary():
    statement = NS(
        text=(
            "The mapped source assertion contains factual material relevant "
            "to this element; M4 does not promote the raw excerpt itself into "
            "an established proposition"
        ),
        evidence_keys=("e1",),
        citations=("Doc A, p.1",),
    )
    substantive, technical = ui._group_display_statements((statement,))
    assert substantive == ()
    assert len(technical) == 1


def test_next_action_is_not_a_copy_of_the_unresolved_question():
    element = NS(
        unresolved_matters=("What contemporaneous evidence records receipt?",),
        limitations=(),
    )
    action = ui._recommended_next_action(element)
    assert action != element.unresolved_matters[0]
    assert "contemporaneous record" in action


def test_new_renderer_has_solicitor_language_and_no_old_counter_cards():
    text = NEW_UI.read_text(encoding="utf-8")

    for value in (
        "Current case assessment",
        "CURRENT POSITION",
        "EVIDENTIAL SUPPORT",
        "Main weakness",
        "Next legal action",
        "Evidence indicating the proposition",
        "Evidence challenging or limiting that conclusion",
        "What remains unclear",
        "Open issue",
        "Audit",
    ):
        assert value in text

    for value in (
        "About this assessment",
        "Disputed elements",
        "Evidence considered",
        "Open issue assessment above",
    ):
        assert value not in text


def test_register_does_not_repeat_weakness_as_next_action():
    text = NEW_UI.read_text(encoding="utf-8")
    assert 'st.write("Investigate: " + open_point)' not in text


def test_app_routes_to_unique_renderer():
    text = APP.read_text(encoding="utf-8")
    assert "from ui.swd1_issue_workspace import show_swd1_issue_workspace" in text
    assert "show_swd1_issue_workspace(active_case_id)" in text
    assert "show_legal_issue_dashboard(active_case_id)" not in text


def test_no_invented_priority():
    text = NEW_UI.read_text(encoding="utf-8")
    for value in ("URGENT", "HIGH PRIORITY", "NORMAL PRIORITY", "LOW PRIORITY"):
        assert value not in text


def test_new_renderer_read_only():
    text = NEW_UI.read_text(encoding="utf-8").lower()
    assert "publish_governed_analytical_authority" not in text
    assert "activate_governed_analytical_authority" not in text
    assert "openai" not in text
    assert "chromadb" not in text


def test_sources_parse():
    ast.parse(APP.read_text(encoding="utf-8"))
    ast.parse(NEW_UI.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# SWD1-I3 focused solicitor evidence tests
# ---------------------------------------------------------------------------

def test_i3_evidence_surface_uses_frozen_significance_not_counts_or_ranking():
    text = NEW_UI.read_text(encoding="utf-8")

    for value in (
        "Why it matters",
        "What the current evidence establishes",
        "What it may support",
        "Limitation",
        "Source: ",
        "Additional evidence",
        "Other relevant context",
        "build_swd1_evidence_items",
    ):
        assert value in text

    for value in (
        "strongest evidence",
        "evidence priority",
        "priority score",
        "rank evidence",
    ):
        assert value.lower() not in text.lower()


def test_i3_source_assertion_is_not_presented_as_established_fact():
    from types import SimpleNamespace as NS

    item = NS(
        evidence_status="source_assertion",
        assessment_rationale=(
            "The source makes a relevant assertion, but the underlying "
            "proposition is not independently established by that assertion alone."
        ),
    )

    why, limitation = ui._i3_rationale_parts(item)

    assert "relevant assertion" in why.lower()
    assert "does not by itself establish" in limitation.lower()


def test_i3_respondent_position_remains_a_party_position():
    from types import SimpleNamespace as NS

    item = NS(
        evidence_status="respondent_evidence",
        assessment_rationale=(
            "The mapped source expressly records a denial or contrary position "
            "relevant to this element."
        ),
    )

    why, limitation = ui._i3_rationale_parts(item)

    assert "denial or contrary position" in why.lower()
    assert "party position" in limitation.lower()
    assert "established fact" in limitation.lower()


def test_i3_low_signal_email_footer_is_secondary():
    assert ui._i3_is_low_signal_summary(
        "This electronic message contains information from CACI "
        "and is intended to be used solely by the recipient."
    )
    assert not ui._i3_is_low_signal_summary(
        "A graduated return to work is recommended."
    )


def test_i3_procedural_forms_are_secondary_not_primary_merits_evidence():
    from types import SimpleNamespace as NS

    procedural = NS(
        evidence_status="source_assertion",
        provenance_type="tribunal_record",
        source_type="tribunal_record",
        document_name="ET hearing (1).pdf",
        summary="13.4 Are you interested in attending a judicial mediation?",
    )
    substantive = NS(
        evidence_status="source_assertion",
        provenance_type="mixed_correspondence",
        source_type="mixed_correspondence",
        document_name="Appendix H6.pdf",
        summary="A graduated return to work is recommended.",
    )

    assert ui._i3_is_procedural_material(procedural)
    assert not ui._i3_is_procedural_material(substantive)


def test_i3_groups_repeated_pages_from_same_document_preserving_first_order():
    from types import SimpleNamespace as NS

    items = (
        NS(document_name="Grounds.pdf", citation="Grounds.pdf, p.1", evidence_key="e1"),
        NS(document_name="Grounds.pdf", citation="Grounds.pdf, p.2", evidence_key="e2"),
        NS(document_name="Plan.pdf", citation="Plan.pdf, p.1", evidence_key="e3"),
        NS(document_name="Grounds.pdf", citation="Grounds.pdf, p.3", evidence_key="e4"),
    )

    groups = ui._i3_group_by_document(items)

    assert tuple(item.evidence_key for item in groups[0]) == ("e1", "e2", "e4")
    assert tuple(item.evidence_key for item in groups[1]) == ("e3",)


def test_i3_claimant_account_separates_relevance_from_party_evidence_limitation():
    from types import SimpleNamespace as NS

    item = NS(
        assessment_rationale=(
            "Claimant-authored evidence is relevant to the factual proposition "
            "but remains party evidence rather than independent confirmation."
        )
    )

    why, limitation = ui._i3_rationale_parts(item)

    assert "claimant's account" in why.lower()
    assert "party evidence" in limitation.lower()
    assert "independent confirmation" in limitation.lower()


# ---------------------------------------------------------------------------
# SWD1 post-validation solicitor refinement tests
# ---------------------------------------------------------------------------

def test_solicitor_working_text_removes_residual_internal_m4_wording():
    rendered = ui._solicitor_working_text(
        "M4 does not determine credibility; a factual conflict remains."
    )

    assert "M4" not in rendered
    assert "current material does not determine credibility" in rendered


def test_solicitor_working_text_replaces_mapped_evidence_language():
    assert (
        ui._solicitor_working_text(
            "Mapped evidence remains incomplete."
        )
        == "Current evidence remains incomplete."
    )
    assert (
        ui._solicitor_working_text(
            "The mapped evidence remains incomplete."
        )
        == "The current evidence remains incomplete."
    )


def test_attention_issues_preserve_input_order_without_priority_ranking():
    from types import SimpleNamespace as NS

    clear = NS(
        provisional_status="well_supported",
        unresolved_matters=(),
        evidential_gaps=(),
    )
    open_one = NS(
        provisional_status="materially_disputed",
        unresolved_matters=("Question one",),
        evidential_gaps=(),
    )
    open_two = NS(
        provisional_status="well_supported",
        unresolved_matters=("Question two",),
        evidential_gaps=(),
    )

    first = NS(
        issue_name="First",
        elements=(open_one,),
        overall_limitations=(),
    )
    second = NS(
        issue_name="Second",
        elements=(clear,),
        overall_limitations=(),
    )
    third = NS(
        issue_name="Third",
        elements=(open_two,),
        overall_limitations=(),
    )

    dashboard = NS(issues=(first, second, third))

    assert tuple(
        item.issue_name
        for item in ui._attention_issues(dashboard)
    ) == ("First", "Third")


def test_attention_orientation_explicitly_disclaims_ranking():
    text = NEW_UI.read_text(encoding="utf-8")

    assert "Issues requiring attention" in text
    assert "shown in case order, not ranked by importance" in text

    for forbidden in (
        "highest priority",
        "top priority",
        "most important issue",
        "deal with this first",
        "urgent issue",
        "strongest evidence",
    ):
        assert forbidden.lower() not in text.lower()


def test_overall_support_label_is_explicitly_issue_level():
    text = NEW_UI.read_text(encoding="utf-8")

    assert "Overall issue evidential support:" in text
    assert 'st.write("Overall evidential support: "' not in text


def test_solicitor_working_text_removes_residual_m4_resolve_wording():
    rendered = ui._solicitor_working_text(
        "The source takes a materially incompatible position; "
        "M4 does not resolve credibility."
    )

    assert "M4" not in rendered
    assert "current material does not resolve credibility" in rendered


def test_working_view_uses_additional_evidence_not_mapped_material():
    text = NEW_UI.read_text(encoding="utf-8")

    assert "Additional mapped material" not in text
    assert "Additional evidence" in text


def test_mw1_issue_workspace_exposes_task_creation_from_both_origins():
    text = NEW_UI.read_text(encoding="utf-8")
    assert "show_issue_task_creator" in text
    assert '"next_legal_action"' in text
    assert '"what_remains_unclear"' in text


def test_mw1_issue_workspace_exposes_matter_task_workspace_without_nav_rewrite():
    text = NEW_UI.read_text(encoding="utf-8")
    assert "show_solicitor_tasks" in text
    assert "mw1_task_workspace_case_id" in text
    assert '"Tasks"' in text

def test_mw1_issue_workspace_has_direct_view_tasks_control():
    text = NEW_UI.read_text(encoding="utf-8")

    assert '"View tasks"' in text
    assert '"mw1_view_tasks::"' in text


def test_mw1_task_why_reuses_issue_explanation_not_generic_placeholder():
    text = NEW_UI.read_text(encoding="utf-8")

    assert "Resolving this work point is necessary because it remains unresolved" not in text
    assert text.count("why_it_matters=str(") == 2
