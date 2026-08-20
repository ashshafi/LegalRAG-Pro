import ast
from pathlib import Path

MODULE = Path(__file__).parents[1] / "src" / "finance_workspace_index.py"


def imported_roots():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_f7b1_is_projection_only_and_has_no_forbidden_runtime_dependencies():
    roots = imported_roots()
    assert "finance_reporting" in roots
    forbidden = {
        "finance_domain", "finance_data", "finance_calculations", "finance_comps",
        "finance_evidence", "finance_answer_authority", "source_evidence",
        "case_reporting", "workspace_index", "report_projection_provider", "ui",
        "streamlit", "openai", "langchain", "chromadb", "requests", "httpx", "sqlite3",
    }
    assert not (roots & forbidden)


def test_f7b1_source_contains_no_filesystem_network_model_or_arithmetic_authority_calls():
    source = MODULE.read_text(encoding="utf-8")
    forbidden_fragments = (
        "open(", "Path(", "read_text(", "read_bytes(", "write_text(", "write_bytes(",
        "requests.", "httpx.", "openai", "chromadb", "streamlit", "datetime.now",
        "Decimal(", "statistics.", "mean(", "median(",
    )
    assert all(fragment not in source for fragment in forbidden_fragments)


def test_f7b1_candidate_boundary_is_one_production_module():
    src = MODULE.parents[0]
    candidates = sorted(p.name for p in src.glob("finance_workspace_index.py"))
    assert candidates == ["finance_workspace_index.py"]
