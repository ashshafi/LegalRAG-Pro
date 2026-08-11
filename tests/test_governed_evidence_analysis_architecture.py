from __future__ import annotations

import ast
import inspect
from pathlib import Path

import governed_evidence_analysis.models as models_module
import governed_issue_evidence.models as u9b_models_module


FORBIDDEN_IMPORT_ROOTS = {
    "case_management",
    "chromadb",
    "document_manager",
    "legalrag",
    "openai",
    "query_expander",
    "retriever",
    "source_evidence",
    "streamlit",
}


def _import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def test_u9c_b1_package_is_exactly_five_modules_and_has_no_runtime_dependencies():
    package = Path(inspect.getfile(models_module)).resolve().parent
    observed = {path.name for path in package.glob("*.py") if path.is_file()}
    assert observed == {
        "__init__.py",
        "identity.py",
        "models.py",
        "serialization.py",
        "validation.py",
    }

    for path in package.glob("*.py"):
        assert not (_import_roots(path) & FORBIDDEN_IMPORT_ROOTS), path.name
        source = path.read_text(encoding="utf-8")
        for forbidden_call in (
            "search_case_evidence(",
            "inspect_document_complete(",
            "classify_document_evidence_roles(",
            "build_governed_issue_evidence_map(",
        ):
            assert forbidden_call not in source


def test_u9c_depends_only_downward_on_frozen_u9b_and_u9b_has_no_reverse_dependency():
    u9c_package = Path(inspect.getfile(models_module)).resolve().parent
    u9b_package = Path(inspect.getfile(u9b_models_module)).resolve().parent

    project_roots: set[str] = set()
    for path in u9c_package.glob("*.py"):
        project_roots.update(
            root
            for root in _import_roots(path)
            if root.startswith("governed_")
        )
    assert project_roots <= {"governed_issue_evidence"}

    for path in u9b_package.glob("*.py"):
        assert "governed_evidence_analysis" not in path.read_text(encoding="utf-8")
