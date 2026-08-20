from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROVIDER = ROOT / "src" / "finance_report_projection_provider.py"


def _tree() -> ast.Module:
    return ast.parse(PROVIDER.read_text(encoding="utf-8"))


def test_f7c_p1_is_one_additive_read_only_production_module():
    assert PROVIDER.is_file()
    for forbidden in (
        ROOT / "src" / "finance_app.py",
        ROOT / "src" / "finance_runtime.py",
        ROOT / "src" / "finance_projection_provider.py",
        ROOT / "src" / "ui" / "finance_navigation.py",
    ):
        assert not forbidden.exists()


def test_provider_consumes_only_f7a_projection_authority():
    tree = _tree()
    imported = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert "finance_reporting" in imported
    assert not any(
        name.startswith(prefix)
        for name in imported
        for prefix in (
            "streamlit",
            "finance_comps",
            "finance_evidence",
            "finance_calculations",
            "finance_answer_authority",
            "finance_data",
            "ui.",
        )
    )


def test_provider_has_no_write_or_activation_calls():
    tree = _tree()
    forbidden_attributes = {
        "write_text",
        "write_bytes",
        "mkdir",
        "unlink",
        "rename",
        "replace",
        "touch",
        "open",
    }
    forbidden_names = {
        "open",
        "render_finance_workspace",
        "build_finance_report_projection",
        "build_finance_workspace_index",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_attributes
            elif isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_names


def test_provider_uses_namespaced_protected_projection_slot():
    text = PROVIDER.read_text(encoding="utf-8")
    assert '"report_projections" / "finance"' in text
    assert '"active.json"' in text
    assert "FinanceReportProjectionProviderError" in text
    assert "load_active_finance_report_projection" in text
