from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from controlled_agentic_analysis_review import ProfessionalReviewDecision
from ui.professional_review_inbox import _is_duplicate_review_submission


ROOT = Path(__file__).resolve().parents[1]
UI_PATH = ROOT / "src" / "ui" / "professional_review_inbox.py"
APP_PATH = ROOT / "src" / "app.py"


def test_prw2_ui_has_only_prw1_review_write_boundary():
    source = UI_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_names = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_names.add(alias.name)

    assert "review_agent_observation" in imported_names
    assert "publish_professional_review_event" in imported_names
    assert "load_professional_review_inbox" in imported_names

    forbidden = (
        "propose_analytical_change",
        "review_analytical_change",
        "governed_authority_revision",
        "activate_governed_analytical_authority",
        "publish_governed_analytical_authority",
    )
    for value in forbidden:
        assert value not in source


def test_prw2_ui_uses_exact_professional_review_decision_enum():
    source = UI_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    }
    attributes = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
    }

    assert "ProfessionalReviewDecision" in names
    assert "DEFER" in attributes
    assert "ACCEPT_FOR_MAL1_CONSIDERATION" in attributes
    assert "REJECT" in attributes
    assert "RECORD PROFESSIONAL REVIEW" in source
    assert "does not create a MAL1 proposal" in source


def test_app_places_prw2_between_legal_issue_dashboard_and_matter_ledger():
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "ui.professional_review_inbox"
    ]
    assert len(imports) == 1
    assert [alias.name for alias in imports[0].names] == [
        "show_professional_review_inbox"
    ]

    dashboard_call = source.index(
        "show_legal_issue_dashboard(active_case_id)"
    )
    inbox_call = source.index(
        "show_professional_review_inbox(active_case_id)"
    )
    ledger_call = source.index(
        "show_matter_analysis_ledger(active_case_id)"
    )

    assert dashboard_call < inbox_call < ledger_call

def _review_item(*events):
    return SimpleNamespace(review_events=events)


def _review_event(*, decision, reviewer_reference="reviewer", reviewer_note="note"):
    return SimpleNamespace(
        decision=decision,
        reviewer_reference=reviewer_reference,
        reviewer_note=reviewer_note,
    )


def test_duplicate_guard_blocks_exact_repeat_of_latest_review():
    item = _review_item(
        _review_event(
            decision=ProfessionalReviewDecision.DEFER,
            reviewer_reference=" Project Board reviewer ",
            reviewer_note=" Same professional note ",
        )
    )

    assert _is_duplicate_review_submission(
        item=item,
        decision=ProfessionalReviewDecision.DEFER,
        reviewer_reference="Project Board reviewer",
        reviewer_note="Same professional note",
    )


def test_duplicate_guard_allows_different_decision():
    item = _review_item(
        _review_event(
            decision=ProfessionalReviewDecision.DEFER,
        )
    )

    assert not _is_duplicate_review_submission(
        item=item,
        decision=ProfessionalReviewDecision.ACCEPT_FOR_MAL1_CONSIDERATION,
        reviewer_reference="reviewer",
        reviewer_note="note",
    )


def test_duplicate_guard_allows_substantively_different_review_note():
    item = _review_item(
        _review_event(
            decision=ProfessionalReviewDecision.DEFER,
            reviewer_note="Initial reason for deferral.",
        )
    )

    assert not _is_duplicate_review_submission(
        item=item,
        decision=ProfessionalReviewDecision.DEFER,
        reviewer_reference="reviewer",
        reviewer_note="New evidence considered; further review remains required.",
    )


def test_duplicate_guard_allows_first_review():
    assert not _is_duplicate_review_submission(
        item=_review_item(),
        decision=ProfessionalReviewDecision.DEFER,
        reviewer_reference="reviewer",
        reviewer_note="First professional review.",
    )

def test_prw2_review_controls_batch_inputs_in_one_streamlit_form():
    source = UI_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    review_controls = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_review_controls"
    )

    calls = [
        node
        for node in ast.walk(review_controls)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "st"
    ]
    attrs = [node.func.attr for node in calls]

    assert attrs.count("form") == 1
    assert attrs.count("form_submit_button") == 1
    assert "button" not in attrs
    assert attrs.count("text_input") == 1
    assert attrs.count("text_area") == 1
    assert attrs.count("selectbox") == 1


def test_prw2_review_ui_has_no_openai_provider_dependency():
    source = UI_PATH.read_text(encoding="utf-8").casefold()
    assert "openai" not in source
    assert "run_caa1_openai" not in source
    assert "run_caa2_openai" not in source
