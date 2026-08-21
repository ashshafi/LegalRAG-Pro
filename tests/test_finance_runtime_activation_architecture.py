from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVATION_PATH = ROOT / "src" / "finance_runtime_activation.py"
RUNTIME_PATH = ROOT / "src" / "finance_runtime.py"
CONFIG_PATH = ROOT / "src" / "finance_runtime_config.py"


def _module() -> ast.Module:
    return ast.parse(ACTIVATION_PATH.read_text(encoding="utf-8"))


def test_f7c_p10_activation_has_exact_public_service_signature() -> None:
    tree = _module()
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "activate_finance_runtime"
    ]
    assert len(functions) == 1
    function = functions[0]

    assert [arg.arg for arg in function.args.args] == []
    assert [arg.arg for arg in function.args.kwonlyargs] == [
        "config",
        "definition",
        "documents",
        "entries",
    ]
    assert [ast.unparse(arg.annotation) if arg.annotation is not None else None for arg in function.args.kwonlyargs] == [
        "FinanceRuntimeConfig",
        "ComparableSetDefinition",
        None,
        None,
    ]
    assert ast.unparse(function.returns) == "FinanceReportProjection"


def test_f7c_p10_activation_imports_only_runtime_config_and_model_contracts() -> None:
    tree = _module()
    imports: list[tuple[str, tuple[str, ...]]] = []

    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module != "__future__":
            imports.append(
                (node.module or "", tuple(alias.name for alias in node.names))
            )

    assert imports == [
        ("finance_comps", ("ComparableSetDefinition",)),
        ("finance_reporting", ("FinanceReportProjection",)),
        ("finance_runtime", ("build_finance_runtime_projection",)),
        ("finance_runtime_config", ("FinanceRuntimeConfig",)),
    ]


def test_f7c_p10_activation_calls_runtime_composer_exactly_once() -> None:
    tree = _module()
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "build_finance_runtime_projection"
    ]
    assert len(calls) == 1

    call = calls[0]
    assert [kw.arg for kw in call.keywords[:3]] == [
        "definition",
        "documents",
        "entries",
    ]
    assert call.keywords[3].arg is None
    assert ast.unparse(call.keywords[3].value) == "config.to_runtime_kwargs()"


def test_f7c_p10_activation_has_no_ui_publication_load_persistence_or_network_boundary() -> None:
    text = ACTIVATION_PATH.read_text(encoding="utf-8")
    forbidden = (
        "streamlit",
        "session_state",
        "ui.",
        "publish_finance_report_projection",
        "load_active_finance_report_projection",
        "report_projections",
        "write_text(",
        "write_bytes(",
        ".mkdir(",
        "os.link",
        "requests.",
        "httpx.",
        "aiohttp.",
        "urlopen(",
        "socket.",
        "yfinance",
    )

    for token in forbidden:
        assert token not in text


def test_f7c_p10_activation_does_not_modify_or_redefine_runtime_or_config_contracts() -> None:
    activation_text = ACTIVATION_PATH.read_text(encoding="utf-8")
    runtime_text = RUNTIME_PATH.read_text(encoding="utf-8")
    config_text = CONFIG_PATH.read_text(encoding="utf-8")

    assert "def build_finance_runtime_projection" not in activation_text
    assert "class FinanceRuntimeConfig" not in activation_text
    assert "finance_runtime_activation" not in runtime_text
    assert "finance_runtime_activation" not in config_text


def test_f7c_p10_activation_exports_only_the_service() -> None:
    tree = _module()
    assignments = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets)
    ]

    assert len(assignments) == 1
    assert ast.literal_eval(assignments[0].value) == ["activate_finance_runtime"]
