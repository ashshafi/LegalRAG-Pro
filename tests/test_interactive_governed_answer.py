from __future__ import annotations

import ast
from pathlib import Path

import interactive_governed_answer as interactive


def _results():
    return {
        "ids": [["e1", "e2"]],
        "documents": [["contemporaneous point one", "qualifying point two"]],
        "metadatas": [[
            {
                "file": "a.pdf",
                "page": 1,
                "u8_evidence_role": "primary_source",
                "source_document_instance_id": "doc-a",
            },
            {
                "file": "b.pdf",
                "page": 2,
                "u8_evidence_role": "adverse",
                "source_document_instance_id": "doc-b",
            },
        ]],
    }


def test_interactive_prompt_is_bounded_projection_not_exhaustive_claim():
    prompt = interactive.build_interactive_governed_answer_prompt(
        question="What happened?",
        enriched_results=_results(),
    )
    assert "bounded semantic answer projection" in prompt
    assert "not an exhaustive whole-corpus report" in prompt
    assert "Do not say or imply that evidence does not exist" in prompt
    normalised_prompt = " ".join(prompt.split())
    assert "explicit exhaustive search is required" in normalised_prompt
    assert "contemporaneous point one" in prompt
    assert "qualifying point two" in prompt


def test_legalrag_routes_normal_and_exhaustive_provider_contexts_separately():
    source = Path("src/legalrag.py").read_text(encoding="utf-8-sig")
    tree = ast.parse(source)

    assert "if governed_evidence.semantic_results is not None:" in source
    assert (
        "results = enrich_evidence_semantics(governed_evidence.semantic_results)"
        in source
    )
    assert "build_interactive_governed_answer_prompt(" in source
    assert (
        "results = enrich_evidence_semantics(governed_evidence.answer_results)"
        in source
    )
    assert "base_prompt = build_governed_answer_prompt(" in source

    asks = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "ask"
    ]
    assert len(asks) == 1
