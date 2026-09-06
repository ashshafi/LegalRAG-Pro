from pathlib import Path
from types import SimpleNamespace

from new_ai_finding import (
    NEW_AI_FINDING_NOTICE,
    is_source_comparison_new_ai_finding,
    wrap_source_comparison_new_ai_finding_prompt,
)


def _evidence(*, complete, semantic):
    return SimpleNamespace(
        search_result=SimpleNamespace() if complete else None,
        semantic_results={"ids": [["e1"]]} if semantic else None,
    )


def test_routes_only_resolved_explicit_complete_source_comparisons():
    assert is_source_comparison_new_ai_finding(
        question="Compare paragraphs 27-30 of the Grounds of Resistance with the Unum evidence.",
        evidence=_evidence(complete=True, semantic=True),
    )
    assert not is_source_comparison_new_ai_finding(
        question="What does the evidence say about return to work?",
        evidence=_evidence(complete=True, semantic=True),
    )
    assert not is_source_comparison_new_ai_finding(
        question="Compare the evidence.",
        evidence=_evidence(complete=False, semantic=True),
    )
    assert not is_source_comparison_new_ai_finding(
        question="Compare all evidence exhaustively.",
        evidence=_evidence(complete=True, semantic=False),
    )


def test_prompt_marks_finding_non_authoritative_and_requires_source_page_comparison():
    prompt = wrap_source_comparison_new_ai_finding_prompt(
        base_prompt="GOVERNED COMPLETE EVIDENCE",
        question="Compare paragraphs 27-30.",
    )
    assert "NOT the Current Assessment" in prompt
    assert "requires professional review" in prompt
    assert "name the source document and page" in prompt
    assert "Do not say the Current Assessment has changed" in prompt
    assert "GOVERNED COMPLETE EVIDENCE" in prompt


def test_legalrag_uses_complete_answer_results_and_bypasses_frozen_constraint_only_for_new_finding():
    source = Path("src/legalrag.py").read_text(encoding="utf-8-sig")
    assert "if new_ai_finding_mode:" in source
    assert "results = enrich_evidence_semantics(governed_evidence.answer_results)" in source
    assert "wrap_source_comparison_new_ai_finding_prompt(" in source
    assert "analytical_reason = NEW_AI_FINDING_NOTICE" in source
    assert '"new_ai_finding": True' in source
    assert '"current_assessment_changed": False' in source
    assert "validate_answer_statement_bindings(" in source
    assert 'reasoning={"effort": INTERACTIVE_REASONING_EFFORT}' in source
    assert "store=False" in source


def test_notice_is_solictor_facing():
    assert "not yet part of Current Assessment" in NEW_AI_FINDING_NOTICE
    assert "requires professional review" in NEW_AI_FINDING_NOTICE
