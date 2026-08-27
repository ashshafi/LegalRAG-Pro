from __future__ import annotations

import ast
from pathlib import Path

import finance_historical_report


def test_historical_report_candidate_has_no_comparable_network_runtime_or_persistence_dependency():
    path = Path(finance_historical_report.__file__)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = (
        "finance_comps",
        "finance_evidence",
        "finance_reporting",
        "finance_runtime",
        "finance_case_binding",
        "streamlit",
        "chromadb",
        "openai",
        "langchain",
        "requests",
        "httpx",
        "sqlite3",
        "subprocess",
        "pathlib",
    )
    lowered = source.lower()
    for token in forbidden:
        assert token not in lowered
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "build_comparable_company_analysis" not in calls
    assert "publish_immutable_finance_dataset" not in calls
    assert "activate_finance_case_binding" not in calls
    public = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    }
    assert public == {
        "build_historical_finance_report",
        "render_historical_finance_markdown",
        "render_historical_finance_html",
    }
