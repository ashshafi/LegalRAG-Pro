import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "src" / "ui" / "finance_workspace.py"
REPORTS = ROOT / "src" / "ui" / "finance_reports.py"


def imported_roots(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_f7b2_approved_presentation_modules_exist_and_activation_modules_are_absent():
    assert WORKSPACE.is_file()
    assert REPORTS.is_file()

    forbidden_activation_paths = (
        ROOT / "src" / "finance_app.py",
        ROOT / "src" / "finance_projection_provider.py",
    )
    for path in forbidden_activation_paths:
        assert not path.exists()


def test_workspace_imports_only_f7a_f7b1_streamlit_and_standard_library():
    roots = imported_roots(WORKSPACE)
    assert {"finance_reporting", "finance_workspace_index", "streamlit", "ui"} <= roots
    forbidden = {
        "finance_domain", "finance_data", "finance_calculations", "finance_comps",
        "finance_evidence", "finance_answer_authority", "source_evidence",
        "case_reporting", "workspace_index", "report_projection_provider",
        "openai", "langchain", "chromadb", "requests", "httpx", "sqlite3",
    }
    assert roots.isdisjoint(forbidden)


def test_reports_module_delegates_only_to_f7a_renderers_and_streamlit():
    roots = imported_roots(REPORTS)
    assert roots == {"__future__", "streamlit", "finance_reporting"}
    text = REPORTS.read_text(encoding="utf-8")
    assert "render_finance_markdown_report" in text
    assert "render_finance_html_report" in text
    assert "open(" not in text
    assert "write_text" not in text
    assert "write_bytes" not in text


def test_no_model_network_database_source_resolution_or_finance_math_implementation():
    combined = WORKSPACE.read_text(encoding="utf-8") + REPORTS.read_text(encoding="utf-8")
    forbidden_fragments = (
        "OpenAI", "chat.completions", "responses.create", "Chroma", "chromadb",
        "requests.", "httpx.", "sqlite3", "resolve_finance", "BlobReader", "page_text",
        "premium", "discount", "target_price", "implied_value", "rank(", "mean(", "median(",
    )
    for fragment in forbidden_fragments:
        assert fragment not in combined
