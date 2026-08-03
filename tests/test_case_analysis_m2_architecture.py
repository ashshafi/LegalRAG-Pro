from __future__ import annotations

import ast
from pathlib import Path


RUNTIME_FILES = {
    "matrices.py",
    "issue_matrix.py",
    "evidence_matrix.py",
    "evidence_identity.py",
    "matrix_validation.py",
    "matrix_serialization.py",
}
FORBIDDEN = {
    "retriever",
    "retrieval_quality",
    "evidence_reranking",
    "query_expander",
    "chromadb",
    "openai",
    "streamlit",
    "features.timeline",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_m2_runtime_surface_is_exactly_six_additive_modules():
    root = Path(__file__).resolve().parents[1] / "src" / "case_analysis" / "m2"
    for name in RUNTIME_FILES:
        assert (root / name).is_file()
    assert not (root / "chronology.py").exists()
    assert not (root / "gaps.py").exists()
    assert not (root / "conflicts.py").exists()


def test_m2_has_no_retrieval_llm_ui_or_timeline_dependency():
    root = Path(__file__).resolve().parents[1] / "src" / "case_analysis" / "m2"
    imports = set()
    for name in RUNTIME_FILES:
        imports.update(_imports(root / name))

    for imported in imports:
        assert not any(
            imported == forbidden or imported.startswith(forbidden + ".")
            for forbidden in FORBIDDEN
        ), imported


def test_legal_analysis_has_no_reverse_case_analysis_dependency():
    root = Path(__file__).resolve().parents[1] / "src" / "legal_analysis"
    for path in root.glob("*.py"):
        assert not any(
            imported == "case_analysis" or imported.startswith("case_analysis.")
            for imported in _imports(path)
        ), path.name
