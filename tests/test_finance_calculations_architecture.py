import ast
from pathlib import Path

FORBIDDEN_IMPORT_ROOTS = {
    "case_management", "legal_analysis", "case_analysis", "case_reporting",
    "governed_analytical_authority", "governed_answer_authority", "streamlit",
    "chromadb", "openai", "langchain", "requests", "httpx", "sqlite3",
}
FORBIDDEN_RUNTIME_TEXT = (
    "source_evidence_store", "report_projections", "data/cases.sqlite3",
)


def test_f3_package_isolated_from_legal_ui_llm_network_and_persistence_layers():
    root = Path(__file__).resolve().parents[1] / "src" / "finance_calculations"
    for path in sorted(root.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots = {node.module.split(".", 1)[0]}
            else:
                continue
            assert not (roots & FORBIDDEN_IMPORT_ROOTS), (path.name, roots & FORBIDDEN_IMPORT_ROOTS)
        lower = text.lower()
        for token in FORBIDDEN_RUNTIME_TEXT:
            assert token.lower() not in lower


def test_f3_does_not_use_binary_float_or_wall_clock_for_financial_arithmetic():
    root = Path(__file__).resolve().parents[1] / "src" / "finance_calculations"
    texts = "\n".join(p.read_text(encoding="utf-8") for p in sorted(root.glob("*.py")))
    assert "float(" not in texts
    assert "datetime.now" not in texts
    assert "datetime.utcnow" not in texts
