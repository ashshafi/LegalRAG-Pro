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
