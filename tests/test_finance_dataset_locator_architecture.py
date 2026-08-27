from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _tree(rel: str) -> ast.Module:
    return ast.parse((ROOT / rel).read_text(encoding="utf-8"), filename=rel)


def _calls(tree: ast.AST) -> set[str]:
    result = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            result.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            result.add(node.func.attr)
    return result


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    matches = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(matches) == 1
    return matches[0]


def test_locator_uses_public_validator_not_private_provider_state():
    source = (ROOT / "src/finance_dataset_locator.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = _calls(tree)
    assert "validate_immutable_dataset_document" in calls
    assert "ImmutableDatasetProvider" not in source
    assert "._dataset" not in source
    assert "self._dataset" not in source


def test_entrypoint_orchestrates_optional_historical_dataset_and_report():
    tree = _tree("src/ui/finance_workspace_entrypoint.py")
    calls = _calls(tree)
    assert "load_validated_immutable_dataset_for_projection" in calls
    assert "build_historical_finance_report" in calls
    render_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "render_finance_workspace")
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "render_finance_workspace")
        )
    ]
    assert len(render_calls) == 2
    keyword_sets = [
        {kw.arg for kw in call.keywords}
        for call in render_calls
    ]
    historical_calls = [
        keywords
        for keywords in keyword_sets
        if "historical_report" in keywords
        and "historical_report_error" in keywords
    ]
    legacy_calls = [
        keywords
        for keywords in keyword_sets
        if "historical_report" not in keywords
        and "historical_report_error" not in keywords
    ]
    assert len(historical_calls) == 1
    assert len(legacy_calls) == 1


def test_workspace_renders_published_historical_markdown():
    tree = _tree("src/ui/finance_workspace.py")
    calls = _calls(tree)
    render = _function(tree, "render_finance_workspace")
    args = [arg.arg for arg in render.args.args] + [arg.arg for arg in render.args.kwonlyargs]
    assert "historical_report" in args
    assert "historical_report_error" in args
    assert "render_historical_finance_markdown" in calls


def test_persisted_binding_and_projection_schemas_are_not_modified_by_locator_module():
    locator_source = (ROOT / "src/finance_dataset_locator.py").read_text(encoding="utf-8")
    assert "finance_case_binding" not in locator_source
    assert "FinanceReportHeader(" not in locator_source
    assert "FinanceReportProjection(" not in locator_source
