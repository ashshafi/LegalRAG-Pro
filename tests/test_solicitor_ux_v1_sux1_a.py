from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

APP = ROOT / "src" / "app.py"
DASHBOARD = ROOT / "src" / "ui" / "legal_issue_dashboard.py"
LEDGER = ROOT / "src" / "ui" / "matter_analysis_ledger.py"
INBOX = ROOT / "src" / "ui" / "professional_review_inbox.py"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_workflow_is_split_into_three_focused_solicitor_views():
    text = source(APP)
    assert '"Legal issues", "AI findings", "Issue assessment"' in text
    assert 'key="solicitor_ux_v1_working_view"' in text

    dashboard = text.index("show_legal_issue_dashboard(active_case_id)")
    inbox = text.index("show_professional_review_inbox(active_case_id)")
    ledger = text.index("show_matter_analysis_ledger(active_case_id)")

    assert dashboard < inbox < ledger
    assert 'if _solicitor_view == "Legal issues":' in text
    assert 'elif _solicitor_view == "AI findings":' in text


def test_legal_issue_dashboard_starts_with_solicitor_orientation():
    text = source(DASHBOARD)
    assert (
        "Choose a legal issue to see the current assessment, evidence "
        "and any action that needs your attention."
        in text
    )
    assert "Evidence considered" in text
    assert "Evidence against / qualifying" in text
    assert "Audit trail" in text


def test_ai_review_is_presented_as_ai_findings_not_governance_machinery():
    text = source(INBOX)
    assert "AI findings" in text
    assert "Review new AI findings that may affect the case assessment." in text
    assert "AI confidence:" in text
    assert "AI recommendation:" in text

    assert "Controlled Agent Professional Review Inbox" not in text
    assert "PRW2 surfaces immutable CAA observations" not in text
    assert "Professional MAL1 consideration" not in text

    authority = text.index("Current governed authority:")
    audit = text.rfind('with st.expander("Audit trail"', 0, authority)
    assert audit != -1


def test_issue_assessment_uses_plain_solicitor_language():
    text = source(LEDGER)

    for value in (
        "Issue assessment",
        "Current assessment",
        "Current case assessment:",
        "Why this is the current assessment",
        "Evidence against / qualifying",
        "Check draft against case assessment",
        "SUGGEST CHANGE",
    ):
        assert value in text

    for value in (
        "Issue Review & Decisions",
        "Technical system: Matter Analysis Ledger",
        "Work-product authority checker",
    ):
        assert value not in text

    authority = text.index(
        "Relationship review is bound to analytical authority"
    )
    audit = text.rfind('with st.expander("Audit trail"', 0, authority)
    assert audit != -1


def test_modified_python_files_parse():
    for path in (APP, DASHBOARD, LEDGER, INBOX):
        ast.parse(source(path))


def test_backend_governance_modules_do_not_contain_sux1_a_projection():
    for rel in (
        "src/analytical_change_proposals.py",
        "src/governed_authority_revision.py",
        "src/governed_authority_revision_publication.py",
        "src/controlled_agentic_analysis.py",
        "src/controlled_agentic_analysis_review.py",
    ):
        path = ROOT / rel
        if not path.exists():
            continue
        text = source(path)
        assert "solicitor_ux_v1_working_view" not in text
        assert "SUGGESTED CHANGE - DECISION REQUIRED" not in text
