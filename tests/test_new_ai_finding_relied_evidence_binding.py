from __future__ import annotations

import ast
from pathlib import Path

from new_ai_finding import bind_source_comparison_relied_evidence_keys

ROOT = Path(__file__).resolve().parents[1]
LEGALRAG = ROOT / "src" / "legalrag.py"


def _source(file: str, page: int, key: str) -> dict:
    return {"file": file, "page": page, "evidence_key": key}


def test_exact_full_filename_and_page_bind_to_governed_evidence_key():
    result = bind_source_comparison_relied_evidence_keys(
        answer=(
            "The contemporaneous email supports the point. "
            "Appendix E1 - Phased Return to Work Emails (16 May 2005).pdf, p.1."
        ),
        sources=[
            _source(
                "Appendix E1 - Phased Return to Work Emails (16 May 2005).pdf",
                1,
                "ev-e1-p1",
            )
        ],
    )
    assert result["status"] == "bound"
    assert result["relied_evidence_keys"] == ["ev-e1-p1"]


def test_solicitor_style_appendix_short_coordinate_binds_uniquely():
    result = bind_source_comparison_relied_evidence_keys(
        answer="The reply corroborates the point (Appendix E1, p.2).",
        sources=[
            _source(
                "Appendix E1 - Phased Return to Work Emails (16 May 2005).pdf",
                2,
                "ev-e1-p2",
            )
        ],
    )
    assert result["relied_evidence_keys"] == ["ev-e1-p2"]


def test_explicit_page_range_binds_only_governed_pages_in_range():
    result = bind_source_comparison_relied_evidence_keys(
        answer="The record is relevant: Appendix H6, pp.1-2.",
        sources=[
            _source("Appendix H6 - Insurer-Supported Return to Work Plan.pdf", 1, "h6-1"),
            _source("Appendix H6 - Insurer-Supported Return to Work Plan.pdf", 2, "h6-2"),
            _source("Appendix H6 - Insurer-Supported Return to Work Plan.pdf", 3, "h6-3"),
        ],
    )
    assert result["relied_evidence_keys"] == ["h6-1", "h6-2"]


def test_missing_page_is_not_inferred_from_search_coverage():
    result = bind_source_comparison_relied_evidence_keys(
        answer="The answer refers to Appendix E1, p.9.",
        sources=[
            _source(
                "Appendix E1 - Phased Return to Work Emails (16 May 2005).pdf",
                1,
                "ev-e1-p1",
            )
        ],
    )
    assert result["status"] == "unbound"
    assert result["relied_evidence_keys"] == []


def test_ambiguous_same_coordinate_fails_closed():
    result = bind_source_comparison_relied_evidence_keys(
        answer="The material appears at Appendix E1, p.1.",
        sources=[
            _source("Appendix E1 - Version A.pdf", 1, "a-1"),
            _source("Appendix E1 - Version B.pdf", 1, "b-1"),
        ],
    )
    assert result["status"] == "unbound"
    assert result["relied_evidence_keys"] == []
    assert result["ambiguous_citations"]


def test_legalrag_new_ai_path_publishes_only_citation_bound_relied_keys():
    text = LEGALRAG.read_text(encoding="utf-8-sig")
    tree = ast.parse(text)
    ask = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "ask"
    )
    segment = ast.get_source_segment(text, ask)
    assert segment is not None
    assert "bind_source_comparison_relied_evidence_keys" in segment
    assert "answer=response.output_text" in segment
    assert '"relied_evidence_keys": list(' in segment
    assert '"new_ai_finding_reference_binding": new_ai_reference_binding' in segment
