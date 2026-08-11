from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PACKAGE = SRC / "governed_analytical_capture"
FILES = tuple(sorted(PACKAGE.glob("*.py")))

PROHIBITED_IMPORT_ROOTS = {
    "chromadb",
    "openai",
    "retriever",
    "query_expander",
    "legalrag",
    "streamlit",
    "case_management",
    "governed_analytical_authority",
}
PROHIBITED_CALLS = {
    "search_case_evidence",
    "retrieve_for_legal_analysis",
    "publish_governed_analytical_authority",
    "activate_governed_analytical_authority",
    "rollback_governed_analytical_authority",
    "open",
    "write",
    "write_text",
    "write_bytes",
    "mkdir",
    "unlink",
    "remove",
    "replace",
    "rename",
}


def _roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _calls(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    calls: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            calls.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            calls.add(node.func.attr)
    return calls


def test_b8c2_package_surface_is_exactly_two_additive_production_files() -> None:
    assert [path.name for path in FILES] == ["__init__.py", "u8_mapper_input.py"]


def test_b8c2_has_no_retrieval_llm_runtime_authority_or_writer_dependency() -> None:
    for path in FILES:
        assert _roots(path).isdisjoint(PROHIBITED_IMPORT_ROOTS), (path, _roots(path))
        assert _calls(path).isdisjoint(PROHIBITED_CALLS), (path, _calls(path))


def test_b8c2_uses_only_frozen_u8_projection_and_semantic_enrichment_boundaries() -> None:
    source = (PACKAGE / "u8_mapper_input.py").read_text(encoding="utf-8")
    assert "CaseEvidenceSearchResult" in source
    assert "EvidenceSearchMode.EXHAUSTIVE_EVIDENCE" in source
    assert "EvidenceSearchCompletion.COMPLETE" in source
    assert "NegativeFindingScope.CASE_CORPUS" in source
    assert "text_match=all_evidence" in source
    assert "enrich_evidence_semantics" in source
    assert "GOVERNED_DISCOVERY_RANK_KEY: None" in source
    assert "search_case_evidence(" not in source
    assert "retrieve_for_legal_analysis(" not in source


def test_b8c2_does_not_create_reverse_dependency_from_existing_source() -> None:
    hits = []
    for path in sorted(SRC.rglob("*.py")):
        if PACKAGE in path.parents:
            continue
        if "governed_analytical_capture" in path.read_text(encoding="utf-8"):
            hits.append(path.relative_to(ROOT).as_posix())
    assert hits == []
