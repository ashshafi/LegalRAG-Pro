import ast
from pathlib import Path


def test_m4_2_production_surface_preserves_m4_1_and_adds_only_synthesis_module():
    root = Path("src/case_analysis/m4")
    assert {item.name for item in root.glob("*.py")} == {
        "models.py",
        "identity.py",
        "validation.py",
        "serialization.py",
        "synthesis.py",
    }


def test_m4_2_allows_only_the_approved_synthesis_builder_and_no_later_logic_entry_points():
    allowed_builder = {"build_case_synthesis"}
    forbidden_later = {
        "analyse_case_strengths",
        "find_case_risks",
        "generate_priority_questions",
        "synthesise_issue_positions",
        "build_material_conflicts",
        "build_evidence_gaps",
        "build_cross_issue_findings",
    }
    found = set()
    synthesis_found = set()
    for path in Path("src/case_analysis/m4").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        functions = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        found.update(functions)
        if path.name == "synthesis.py":
            synthesis_found.update(functions)
    assert allowed_builder.issubset(synthesis_found)
    assert not (found & forbidden_later)


def test_m4_2_has_no_openai_chroma_retrieval_or_repository_imports():
    forbidden_roots = {
        "openai",
        "chromadb",
        "retriever",
        "search",
        "query_expander",
        "case_management",
    }
    imported = set()
    for path in Path("src/case_analysis/m4").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
    assert not (imported & forbidden_roots)
