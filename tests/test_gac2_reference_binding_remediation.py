from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from governed_agentic_investigation_v2 import (
    build_governed_agentic_investigation_v2_plan,
    combine_governed_agentic_investigation_v2_results,
)

ROOT = Path(__file__).resolve().parents[1]
CASE_OPERATOR = ROOT / "src" / "ui" / "case_operator.py"


@dataclass(frozen=True)
class FakeTask:
    case_id: str = "case-reference-audit"
    task_id: str = "task-reference-audit"
    title: str = "Investigate source/page binding"
    issue_name: str = "Reference audit"
    why_it_matters: str = "Professional reliance must be source-bound."


def _plan():
    return build_governed_agentic_investigation_v2_plan(
        FakeTask(),
        objective="Test exact relied source/page binding.",
    )


def _result(*, evidence_key: str = "e1", relied: bool = True, new_ai: bool = False):
    return {
        "answer": "Bound answer.",
        "sources": [
            {
                "file": "Appendix E1 - Phased Return to Work Emails.pdf",
                "page": 1,
                "evidence_key": evidence_key,
            }
        ],
        "relied_evidence_keys": [evidence_key] if relied else [],
        "answer_scope_evidence_keys": [evidence_key],
        "answer_statement_bindings": [],
        "analytical_authority_id": "sha256:authority",
        "analytical_activation_id": "sha256:activation",
        "analytical_authority_mode": "governed",
        "new_ai_finding": new_ai,
    }


def _function_source(name: str) -> str:
    text = CASE_OPERATOR.read_text(encoding="utf-8-sig")
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            segment = ast.get_source_segment(text, node)
            assert segment
            return segment
    raise AssertionError(f"function not found: {name}")


def test_gac2_exact_relied_sources_are_carried_per_step_and_acceptance_is_complete():
    plan = _plan()
    results = [_result(evidence_key=f"e{i}") for i in range(1, 6)]
    combined = combine_governed_agentic_investigation_v2_results(
        plan=plan,
        step_results=results,
    )
    assert combined["gac2_reference_binding_complete"] is True
    assert combined["gac2_reference_binding_blocked_steps"] == []
    assert combined["gac2_reference_binding_schema"] == "gac2-reference-binding-audit/v1"
    assert all(item["reference_binding_status"] == "bound" for item in combined["gac2_step_summaries"])
    assert all(item["relied_source_count"] == 1 for item in combined["gac2_step_summaries"])
    assert combined["gac2_step_summaries"][0]["relied_sources"][0]["file"].startswith("Appendix E1")


def test_gac2_coverage_without_exact_reliance_fails_closed_for_professional_acceptance():
    plan = _plan()
    results = [_result(evidence_key=f"e{i}") for i in range(1, 6)]
    results[2] = _result(evidence_key="coverage-only", relied=False, new_ai=True)
    combined = combine_governed_agentic_investigation_v2_results(
        plan=plan,
        step_results=results,
    )
    assert combined["gac2_reference_binding_complete"] is False
    assert combined["gac2_reference_binding_blocked_steps"] == ["adverse-qualifying-evidence"]
    audit = combined["gac2_step_summaries"][2]
    assert audit["new_ai_finding"] is True
    assert audit["reference_binding_status"] == "coverage_only"
    assert audit["relied_source_count"] == 0
    assert audit["source_count"] == 1


def test_case_operator_separates_coverage_from_reliance_and_disables_acceptance():
    audit = _function_source("_render_gac2_reference_binding_audit")
    assert "exact relied-evidence source/page binding" in audit
    assert "coverage is not proof of reliance" in audit
    assert "Professional acceptance is blocked" in audit
    operator = _function_source("_render_governed_agentic_investigation_v2")
    assert "reference_binding_complete = _render_gac2_reference_binding_audit(result)" in operator
    assert "disabled=not reference_binding_complete" in operator
    renderer = _function_source("_render_result")
    assert "Search coverage references (not relied-source proof)" in renderer
    assert "Do not infer reliance from this list." in renderer
