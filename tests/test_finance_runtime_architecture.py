from __future__ import annotations

import ast
from pathlib import Path


SOURCE = Path(__file__).parents[1] / "src" / "finance_runtime.py"


def _tree() -> ast.Module:
    return ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
            return ".".join(reversed(parts))
    return None


def test_runtime_import_boundary_is_small_and_explicit():
    tree = _tree()
    imports = []

    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            imports.append((node.module, tuple(alias.name for alias in node.names)))
        elif isinstance(node, ast.Import):
            imports.append(
                (
                    None,
                    tuple(alias.name for alias in node.names),
                )
            )

    assert imports == [
        ("__future__", ("annotations",)),
        ("pathlib", ("Path",)),
        (
            "finance_comps",
            ("ComparableSetDefinition", "build_comparable_company_analysis"),
        ),
        (
            "finance_data.provider_selection",
            ("select_financial_data_provider",),
        ),
        (
            "finance_evidence",
            ("build_finance_observation_evidence_manifest",),
        ),
        (
            "finance_reporting",
            ("FinanceReportProjection", "build_finance_report_projection"),
        ),
    ]


def test_runtime_body_is_exact_four_stage_composition():
    tree = _tree()
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "build_finance_runtime_projection"
    )

    calls = []
    for node in ast.walk(function):
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in {
                "select_financial_data_provider",
                "build_comparable_company_analysis",
                "build_finance_observation_evidence_manifest",
                "build_finance_report_projection",
            }:
                calls.append(name)

    assert calls == [
        "select_financial_data_provider",
        "build_comparable_company_analysis",
        "build_finance_observation_evidence_manifest",
        "build_finance_report_projection",
    ]


def test_runtime_has_no_publication_network_environment_or_ui_surface():
    source = SOURCE.read_text(encoding="utf-8").lower()

    forbidden = (
        "publish_",
        "streamlit",
        "session_state",
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "urlopen",
        "socket",
        "yfinance",
        "os.environ",
        "getenv",
        "dotenv",
        "chromadb",
        "sqlite",
        "source_evidence_store",
        "report_projections",
        "governed_analytical_authorities",
        "data/cases.sqlite3",
    )

    assert not [token for token in forbidden if token in source]


def test_runtime_has_no_file_or_process_mutation_calls():
    tree = _tree()
    forbidden_calls = {
        "open",
        "write",
        "write_text",
        "write_bytes",
        "mkdir",
        "unlink",
        "remove",
        "replace",
        "rename",
        "system",
        "run",
        "Popen",
    }
    observed = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name is not None and name.split(".")[-1] in forbidden_calls:
                observed.append(name)

    assert observed == []


def test_runtime_does_not_construct_concrete_provider_types():
    tree = _tree()
    observed = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name is not None and name.split(".")[-1] in {
                "ImmutableDatasetProvider",
                "FrozenDemoProvider",
            }:
                observed.append(name)

    assert observed == []
