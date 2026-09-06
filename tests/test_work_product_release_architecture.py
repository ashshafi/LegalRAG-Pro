from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "src" / "work_product_release.py"


def _tree():
    return ast.parse(MODULE.read_text(encoding="utf-8"))


def test_c3_has_no_ai_network_or_legal_research_dependency():
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


def test_c3_does_not_import_analytical_governance_or_c2_state():
    forbidden = {
        "controlled_agentic_analysis",
        "controlled_agentic_analysis_review",
        "analytical_change_proposals",
        "governed_analytical_authority",
        "matter_analysis_ledger",
        "legal_authority_verification",
    }
    for node in ast.walk(_tree()):
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in forbidden
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in forbidden


def test_c3_professional_release_requires_explicit_review_fields():
    tree = _tree()
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    record = functions["record_work_product_release"]
    args = {arg.arg for arg in record.args.kwonlyargs}
    assert {
        "decision",
        "factual_basis_reviewed",
        "legal_authorities_reviewed",
        "unverified_authorities_remaining",
        "professional_judgment_completed",
        "court_or_tribunal_reliance",
        "reviewer_reference",
        "review_note",
    } <= args


def test_c3_target_binds_projection_and_exact_artifact_identity():
    tree = _tree()
    target_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "WorkProductReleaseTarget"
    )
    fields = {
        node.target.id
        for node in target_class.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
    }
    assert {
        "case_id",
        "report_projection_id",
        "projection_payload_sha256",
        "manifest_id",
        "artifact_format",
        "artifact_id",
        "artifact_sha256",
        "renderer_version",
        "output_profile",
        "target_id",
    } <= fields


def test_c3_has_no_automatic_release_entry_point():
    names = {
        node.name.lower()
        for node in _tree().body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert not any(
        name.startswith(
            (
                "auto_approve",
                "ai_approve",
                "model_approve",
                "auto_release",
                "ai_release",
            )
        )
        for name in names
    )


def test_c3_documented_invariants_keep_release_controls_distinct():
    text = MODULE.read_text(encoding="utf-8")
    assert "CAA professional review != work-product release review" in text
    assert "LEGAL_AUTHORITY verified != work product approved" in text
    assert (
        "Work-product authority checking != work-product release approval"
        in text
    )
    assert "Working export != approved for reliance" in text
    assert (
        "APPROVED_FOR_RELIANCE != court or tribunal reliance"
        in text
    )
    assert "Re-rendered bytes != previously approved artifact" in text
    assert "Changed report projection != previous approval transferred" in text
    assert "Work-product approval != governed case assessment changed" in text
    assert "Missing release history is WORKING, not approved" in text
