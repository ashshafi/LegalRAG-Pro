from __future__ import annotations

import ast
from pathlib import Path


SOURCE = Path(__file__).parents[1] / "src" / "finance_report_projection_publication.py"


def _tree() -> ast.Module:
    return ast.parse(SOURCE.read_text(encoding="utf-8"))


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _dotted(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""


def test_publication_module_is_additive_finance_only_boundary():
    text = SOURCE.read_text(encoding="utf-8")

    assert "FinanceReportProjection" in text
    assert "dumps_finance_report_projection" in text
    assert '"report_projections"' in text
    assert '"finance"' in text
    assert '"active.json"' in text

    for forbidden in (
        "streamlit",
        "render_finance_workspace",
        "build_finance_workspace_index",
        "openai",
        "langchain",
        "chromadb",
        "src/app.py",
        "src/ui/sidebar.py",
    ):
        assert forbidden not in text


def test_publication_is_create_if_absent_and_never_uses_replace_fallback():
    calls = {_dotted(node.func) for node in ast.walk(_tree()) if isinstance(node, ast.Call)}

    assert "os.link" in calls
    assert "os.fsync" in calls
    assert "os.replace" not in calls
    assert "os.rename" not in calls


def test_publication_has_no_provider_or_ui_activation_dependency():
    imports: set[str] = set()
    for node in _tree().body:
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")

    assert "finance_report_projection_provider" not in imports
    assert all(not item.startswith("ui") and not item.startswith("src.ui") for item in imports)
    assert "app" not in imports


def test_publication_exports_only_publisher_and_error():
    text = SOURCE.read_text(encoding="utf-8")
    assert '"FinanceReportProjectionPublicationError"' in text
    assert '"publish_finance_report_projection"' in text
