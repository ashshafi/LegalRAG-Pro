from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from new_ai_finding import bind_source_comparison_relied_evidence_keys
from governed_agentic_investigation_v2 import (
    combine_governed_agentic_investigation_v2_results,
)

ROOT = Path(__file__).resolve().parents[1]
CASE_OPERATOR = ROOT / "src" / "ui" / "case_operator.py"


def _source(file: str, page: int, key: str) -> dict:
    return {"file": file, "page": page, "evidence_key": key}


def _plan():
    steps = [
        SimpleNamespace(step_id="frame-propositions-and-chronology", title="Frame"),
        SimpleNamespace(step_id="supporting-evidence", title="Support"),
        SimpleNamespace(step_id="adverse-qualifying-evidence", title="Adverse"),
        SimpleNamespace(step_id="contradictions-connections", title="Contradictions"),
        SimpleNamespace(step_id="gaps-professional-actions", title="Gaps"),
    ]
    return SimpleNamespace(
        task_id="task-1",
        objective="Test citation completeness.",
        steps=steps,
        plan_id="sha256:plan",
    )


def _ordinary_result(key: str) -> dict:
    return {
        "answer": "Ordinary governed answer.",
        "sources": [_source("Appendix O1 - Ordinary.pdf", 1, key)],
        "relied_evidence_keys": [key],
        "analytical_authority_id": "sha256:authority",
        "analytical_activation_id": "sha256:activation",
        "analytical_authority_mode": "governed",
        "new_ai_finding": False,
    }


def test_new_ai_binding_counts_every_explicit_coordinate_and_requires_all_bound():
    result = bind_source_comparison_relied_evidence_keys(
        answer=(
            "The first point is supported by Appendix E1, p.1. "
            "The second relies on Appendix E1, p.2. "
            "A third proposition cites Mystery Record.pdf, p.9."
        ),
        sources=[
            _source(
                "Appendix E1 - Phased Return to Work Emails (16 May 2005).pdf",
                1,
                "e1-p1",
            ),
            _source(
                "Appendix E1 - Phased Return to Work Emails (16 May 2005).pdf",
                2,
                "e1-p2",
            ),
        ],
    )

    assert result["explicit_citation_count"] == 3
    assert result["bound_citation_count"] == 2
    assert result["unmatched_citation_count"] == 1
    assert result["ambiguous_citation_count"] == 0
    assert result["citation_binding_complete"] is False
    assert result["status"] == "incomplete"
    assert result["relied_evidence_keys"] == ["e1-p1", "e1-p2"]


def test_full_multi_document_multi_page_answer_is_complete_only_when_all_coordinates_bind():
    result = bind_source_comparison_relied_evidence_keys(
        answer=(
            "Appendix E1 - Phased Return to Work Emails (16 May 2005).pdf, p.1; "
            "Appendix E1, p.2; Appendix H5, pp.1-2; "
            "Rehab Referral Documentation 2004_2005.pdf, pp.11-14."
        ),
        sources=[
            _source(
                "Appendix E1 - Phased Return to Work Emails (16 May 2005).pdf",
                1,
                "e1-p1",
            ),
            _source(
                "Appendix E1 - Phased Return to Work Emails (16 May 2005).pdf",
                2,
                "e1-p2",
            ),
            _source("Appendix H5 - Return to Work.pdf", 1, "h5-p1"),
            _source("Appendix H5 - Return to Work.pdf", 2, "h5-p2"),
            *[
                _source(
                    "Rehab Referral Documentation 2004_2005.pdf",
                    page,
                    f"rehab-{page}",
                )
                for page in range(11, 15)
            ],
        ],
    )

    assert result["explicit_citation_count"] == 8
    assert result["bound_citation_count"] == 8
    assert result["unmatched_citation_count"] == 0
    assert result["ambiguous_citation_count"] == 0
    assert result["citation_binding_complete"] is True
    assert result["status"] == "bound"


def test_one_successful_binding_cannot_make_multi_citation_new_ai_step_pass():
    plan = _plan()
    results = [_ordinary_result(f"o{i}") for i in range(1, 6)]
    results[2] = {
        "answer": "Appendix E1, p.1 and Missing Record.pdf, p.4.",
        "sources": [
            _source(
                "Appendix E1 - Phased Return to Work Emails (16 May 2005).pdf",
                1,
                "e1-p1",
            )
        ],
        "relied_evidence_keys": ["e1-p1"],
        "analytical_authority_id": "sha256:authority",
        "analytical_activation_id": "sha256:activation",
        "analytical_authority_mode": "governed",
        "new_ai_finding": True,
        "new_ai_finding_reference_binding": {
            "schema": "new-ai-finding-citation-completeness/v2",
            "status": "incomplete",
            "citation_binding_complete": False,
            "explicit_citation_count": 2,
            "bound_citation_count": 1,
            "unmatched_citation_count": 1,
            "ambiguous_citation_count": 0,
            "relied_evidence_keys": ["e1-p1"],
            "matched_citations": [
                {
                    "file": "Appendix E1 - Phased Return to Work Emails (16 May 2005).pdf",
                    "page": 1,
                    "evidence_key": "e1-p1",
                }
            ],
            "unmatched_citations": [{"label": "missing record", "page": 4}],
            "ambiguous_citations": [],
        },
    }

    combined = combine_governed_agentic_investigation_v2_results(
        plan=plan,
        step_results=results,
    )

    assert combined["gac2_reference_binding_complete"] is False
    assert combined["gac2_reference_binding_blocked_steps"] == [
        "adverse-qualifying-evidence"
    ]
    audit = combined["gac2_step_summaries"][2]
    assert audit["reference_binding_status"] == "citation_binding_incomplete"
    assert audit["citation_binding_complete"] is False
    assert audit["explicit_citation_count"] == 2
    assert audit["bound_citation_count"] == 1
    assert audit["unmatched_citation_count"] == 1


def test_complete_new_ai_citation_set_can_pass_gac2_reference_gate():
    plan = _plan()
    results = [_ordinary_result(f"o{i}") for i in range(1, 6)]
    results[2] = {
        "answer": "Appendix E1, p.1.",
        "sources": [
            _source(
                "Appendix E1 - Phased Return to Work Emails (16 May 2005).pdf",
                1,
                "e1-p1",
            )
        ],
        "relied_evidence_keys": ["e1-p1"],
        "analytical_authority_id": "sha256:authority",
        "analytical_activation_id": "sha256:activation",
        "analytical_authority_mode": "governed",
        "new_ai_finding": True,
        "new_ai_finding_reference_binding": {
            "schema": "new-ai-finding-citation-completeness/v2",
            "status": "bound",
            "citation_binding_complete": True,
            "explicit_citation_count": 1,
            "bound_citation_count": 1,
            "unmatched_citation_count": 0,
            "ambiguous_citation_count": 0,
            "relied_evidence_keys": ["e1-p1"],
            "matched_citations": [
                {
                    "file": "Appendix E1 - Phased Return to Work Emails (16 May 2005).pdf",
                    "page": 1,
                    "evidence_key": "e1-p1",
                }
            ],
            "unmatched_citations": [],
            "ambiguous_citations": [],
        },
    }

    combined = combine_governed_agentic_investigation_v2_results(
        plan=plan,
        step_results=results,
    )
    assert combined["gac2_reference_binding_complete"] is True
    audit = combined["gac2_step_summaries"][2]
    assert audit["reference_binding_status"] == "bound"
    assert audit["citation_binding_complete"] is True


def test_case_operator_exposes_citation_completeness_and_retains_fail_closed_acceptance():
    text = CASE_OPERATOR.read_text(encoding="utf-8-sig")
    tree = ast.parse(text)
    fn = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_render_gac2_reference_binding_audit"
    )
    source = ast.get_source_segment(text, fn)
    assert source is not None
    assert "Citation completeness:" in source
    assert "Unmatched citation coordinates" in source
    assert "Ambiguous citation coordinates" in source
    assert "every New AI Finding citation is completely resolved" in source

    operator = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_render_governed_agentic_investigation_v2"
    )
    operator_source = ast.get_source_segment(text, operator)
    assert operator_source is not None
    assert "disabled=not reference_binding_complete" in operator_source
