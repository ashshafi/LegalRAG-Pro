import ast
from pathlib import Path


def test_m4_1_production_surface_is_exactly_the_four_authorised_modules():
    root = Path("src/case_analysis/m4")
    assert {item.name for item in root.glob("*.py")} == {
        "models.py",
        "identity.py",
        "validation.py",
        "serialization.py",
    }


def test_m4_1_contains_no_builder_renderer_or_synthesis_logic_entry_points():
    forbidden = {
        "build_case_synthesis",
        "analyse_case_strengths",
        "find_case_risks",
        "generate_priority_questions",
        "synthesise_issue_positions",
    }
    found = set()
    for path in Path("src/case_analysis/m4").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found.update(node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))
    assert not (found & forbidden)


def test_m4_1_has_no_openai_chroma_retrieval_or_repository_imports():
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
