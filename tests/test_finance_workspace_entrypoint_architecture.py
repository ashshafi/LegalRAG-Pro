from __future__ import annotations

import ast
from pathlib import Path


_SOURCE = Path(__file__).resolve().parents[1] / "src" / "ui" / "finance_workspace_entrypoint.py"


def _tree() -> ast.Module:
    return ast.parse(_SOURCE.read_text(encoding="utf-8"), filename=str(_SOURCE))


def test_entrypoint_has_only_permitted_finance_dependencies() -> None:
    imports: set[tuple[str, str]] = set()
    for node in ast.walk(_tree()):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imports.add((node.module, alias.name))

    assert (
        "finance_report_projection_provider",
        "load_active_finance_report_projection",
    ) in imports
    assert ("ui.finance_workspace", "render_finance_workspace") in imports

    forbidden_modules = {
        "finance_runtime_activation",
        "finance_report_projection_publication",
        "finance_runtime",
        "finance_runtime_config",
        "finance_data",
        "finance_calculations",
    }
    assert not any(module in forbidden_modules for module, _ in imports)


def test_entrypoint_calls_load_and_render_but_not_activation_or_publication() -> None:
    calls: set[str] = set()
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                calls.add(func.id)
            elif isinstance(func, ast.Attribute):
                calls.add(func.attr)

    assert "load_active_finance_report_projection" in calls
    assert "render_finance_workspace" in calls
    assert "info" in calls

    assert "activate_finance_runtime" not in calls
    assert "publish_finance_report_projection" not in calls
    assert "build_finance_runtime_projection" not in calls
    assert "build_comparable_company_analysis" not in calls


def test_entrypoint_contains_no_session_state_or_persistence_authority() -> None:
    text = _SOURCE.read_text(encoding="utf-8")

    assert "session_state" not in text
    assert "finance_runtime_activation" not in text
    assert "finance_report_projection_publication" not in text
    assert "PersistentClient" not in text
    assert "chromadb" not in text
    assert "requests." not in text
    assert "httpx." not in text
    assert "urllib." not in text


def test_entrypoint_public_contract_is_exact() -> None:
    tree = _tree()
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "show_finance_workspace"
    ]
    assert len(functions) == 1

    function = functions[0]
    assert not function.args.args
    assert [arg.arg for arg in function.args.kwonlyargs] == ["workspace_id"]
    assert ast.unparse(function.args.kwonlyargs[0].annotation) == "str"
    assert ast.unparse(function.returns) == "None"

    exports = [
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets)
    ]
    assert len(exports) == 1
    assert ast.literal_eval(exports[0].value) == ["show_finance_workspace"]
