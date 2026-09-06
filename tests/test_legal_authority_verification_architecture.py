from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "src" / "legal_authority_verification.py"


def _tree():
    return ast.parse(MODULE.read_text(encoding="utf-8"))


def test_c2_has_no_ai_network_or_research_provider_dependency():
    forbidden_roots = {
        "openai",
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "langchain",
    }
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in forbidden_roots
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            assert root not in forbidden_roots


def test_c2_does_not_import_or_mutate_analytical_governance_layers():
    forbidden = {
        "controlled_agentic_analysis",
        "controlled_agentic_analysis_review",
        "analytical_change_proposals",
        "governed_analytical_authority",
        "matter_analysis_ledger",
    }
    for node in ast.walk(_tree()):
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in forbidden
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in forbidden


def test_c2_professional_verification_requires_explicit_reviewer_and_checks():
    tree = _tree()
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    record = functions["record_legal_authority_verification"]
    args = {arg.arg for arg in record.args.kwonlyargs}
    assert {
        "decision",
        "genuine",
        "citation_verifiable",
        "relevant_to_matter",
        "supports_attributed_proposition",
        "verification_source",
        "verification_source_reference",
        "reviewer_reference",
        "review_note",
    } <= args


def test_c2_has_no_automatic_verification_entry_point():
    names = {
        node.name.lower()
        for node in _tree().body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert not any(
        name.startswith(("auto_verify", "ai_verify", "model_verify"))
        for name in names
    )


def test_c2_documented_invariants_keep_classification_and_source_binding_distinct():
    text = MODULE.read_text(encoding="utf-8")
    assert "LEGAL_AUTHORITY classification != legal-authority verification" in text
    assert "Source-bound evidence verification != legal-authority verification" in text
    assert "Retrieval or AI generation != legal-authority verification" in text
    assert "LEGAL_AUTHORITY verified != factual proposition proved" in text
    assert "LEGAL_AUTHORITY verified != governed case assessment changed" in text
    assert "LEGAL_AUTHORITY verified != work product approved or court-ready" in text
    assert "court-readiness decision" in text
