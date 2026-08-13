from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PACKAGE = SRC / "governed_answer_authority"


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def calls(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                result.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                result.add(node.func.attr)
    return result


def test_package_is_exact_five_files():
    assert sorted(path.name for path in PACKAGE.glob("*.py")) == [
        "__init__.py",
        "bindings.py",
        "context.py",
        "models.py",
        "routing.py",
    ]


def test_package_has_no_runtime_retrieval_openai_database_or_mutation_dependency():
    all_imports = set()
    all_calls = set()
    for path in PACKAGE.glob("*.py"):
        all_imports |= imports(path)
        all_calls |= calls(path)

    forbidden_imports = {
        "chromadb",
        "sqlite3",
        "retriever",
        "evidence_search",
        "evidence_retrieval",
        "evidence_answer",
        "openai",
        "config",
        "governed_analytical_authority.activation",
        "governed_analytical_authority.publication",
        "governed_evidential_construction",
        "governed_issue_evidence.binding",
    }
    assert not any(
        name == bad or name.startswith(bad + ".")
        for name in all_imports
        for bad in forbidden_imports
    )
    forbidden_calls = {
        "map_primary_issue",
        "assess",
        "render",
        "build_case_analysis_foundation",
        "build_case_matrices",
        "build_governed_issue_evidence_map",
        "build_governed_evidential_analysis",
        "publish_governed_analytical_authority",
        "activate_governed_analytical_authority",
        "write_text",
        "write_bytes",
        "open",
        "connect",
        "query",
    }
    assert all_calls.isdisjoint(forbidden_calls)


def test_only_routing_module_imports_selector():
    selector_importers = [
        path.name for path in PACKAGE.glob("*.py")
        if "legal_analysis.selector" in imports(path)
    ]
    assert selector_importers == ["routing.py"]


def test_legalrag_is_orchestrator_and_does_not_import_builders():
    source = (SRC / "legalrag.py").read_text(encoding="utf-8")
    assert "load_active_governed_analytical_authority" in source
    assert "prepare_governed_answer_evidence(" in source
    for forbidden in (
        "map_primary_issue",
        "ElementEvidenceAssessor",
        "StructuredLegalAnalysisRenderer",
        "build_case_analysis_foundation",
        "build_case_matrices",
        "build_governed_issue_evidence_map",
        "build_governed_evidential_analysis",
        "publish_governed_analytical_authority",
        "activate_governed_analytical_authority",
    ):
        assert forbidden not in source
