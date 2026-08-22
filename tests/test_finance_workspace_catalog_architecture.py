from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "src" / "finance_workspace_catalog.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _imports() -> set[str]:
    found: set[str] = set()
    for node in ast.walk(TREE):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_catalog_is_read_only_and_consumes_only_published_projection_provider():
    imports = _imports()
    assert "finance_report_projection_provider" in imports
    forbidden = {
        "finance_case_binding.activation",
        "finance_report_projection_publication",
        "finance_runtime_activation",
        "finance_data.provider_selection",
        "streamlit",
    }
    assert imports.isdisjoint(forbidden)
    assert "activate_finance_case_binding" not in SOURCE
    assert "publish_finance_report_projection" not in SOURCE


def test_catalog_does_not_create_or_modify_finance_authority():
    forbidden_fragments = (
        ".write_",
        ".write(",
        ".mkdir(",
        "os.replace",
        "os.rename",
        "unlink(",
        "rmtree(",
    )
    for fragment in forbidden_fragments:
        assert fragment not in SOURCE


def test_catalog_public_contract_is_exact():
    public = [
        node.name
        for node in TREE.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    ]
    assert public == ["load_published_finance_workspace_catalog"]
