from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "src" / "finance_runtime_config.py"
RUNTIME_PATH = ROOT / "src" / "finance_runtime.py"


def _module() -> ast.Module:
    return ast.parse(CONFIG_PATH.read_text(encoding="utf-8"))


def test_f7c_p9_config_is_exactly_one_frozen_slots_dataclass() -> None:
    tree = _module()
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "FinanceRuntimeConfig"
    ]
    assert len(classes) == 1

    decorators = [ast.unparse(node) for node in classes[0].decorator_list]
    assert decorators == ["dataclass(frozen=True, slots=True)"]

    fields = [
        node.target.id
        for node in classes[0].body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    ]
    assert fields == [
        "provider_mode",
        "dataset_path",
        "expected_provider_id",
        "expected_dataset_id",
        "expected_dataset_version",
    ]


def test_f7c_p9_config_adapter_is_provider_authority_only() -> None:
    tree = _module()
    config_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "FinanceRuntimeConfig"
    )
    adapter = next(
        node
        for node in config_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "to_runtime_kwargs"
    )

    returns = [node for node in ast.walk(adapter) if isinstance(node, ast.Return)]
    assert len(returns) == 1
    assert isinstance(returns[0].value, ast.Dict)

    keys = [
        node.value
        for node in returns[0].value.keys
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    assert keys == [
        "provider_mode",
        "dataset_path",
        "expected_provider_id",
        "expected_dataset_id",
        "expected_dataset_version",
    ]


def test_f7c_p9_config_has_no_runtime_ui_publication_persistence_or_network_activation() -> None:
    text = CONFIG_PATH.read_text(encoding="utf-8")
    forbidden = (
        "build_finance_runtime_projection",
        "publish_finance_report_projection",
        "load_active_finance_report_projection",
        "report_projections",
        "streamlit",
        "session_state",
        "requests.",
        "httpx.",
        "aiohttp.",
        "urlopen(",
        "socket.",
        "yfinance",
        "write_text(",
        "write_bytes(",
        ".mkdir(",
        "os.link",
        "open(",
    )
    for token in forbidden:
        assert token not in text


def test_f7c_p9_config_imports_selector_constants_but_never_calls_selector() -> None:
    tree = _module()

    imported_names = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "finance_data.provider_selection":
            imported_names.extend(alias.name for alias in node.names)

    assert imported_names == [
        "PROVIDER_SELECTION_MODE_FROZEN_DEMO",
        "PROVIDER_SELECTION_MODE_IMMUTABLE",
    ]

    call_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "select_financial_data_provider" not in call_names


def test_f7c_p9_existing_runtime_remains_unmodified_and_unwired_to_config() -> None:
    text = RUNTIME_PATH.read_text(encoding="utf-8")

    assert "finance_runtime_config" not in text
    assert "FinanceRuntimeConfig" not in text


def test_f7c_p9_config_module_does_not_import_ui_or_runtime_modules() -> None:
    tree = _module()
    imported_modules = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)
        elif isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)

    assert "finance_runtime" not in imported_modules
    assert not any(module == "ui" or module.startswith("ui.") for module in imported_modules)
    assert "finance_report_projection_publication" not in imported_modules
    assert "finance_report_projection_provider" not in imported_modules
