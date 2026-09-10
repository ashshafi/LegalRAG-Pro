from __future__ import annotations

import ast
from pathlib import Path


def _timeline_route_assignments():
    source = Path("src/ui/sidebar.py").read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    show_sidebar = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "show_sidebar"
    )
    timeline_if = next(
        node for node in ast.walk(show_sidebar)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "timeline_clicked"
    )

    values = {}
    for stmt in timeline_if.body:
        if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
            continue
        target = stmt.targets[0]
        if not isinstance(target, ast.Subscript):
            continue
        value = target.value
        if not (
            isinstance(value, ast.Attribute)
            and value.attr == "session_state"
            and isinstance(value.value, ast.Name)
            and value.value.id == "st"
        ):
            continue
        key = target.slice
        if not (
            isinstance(key, ast.Constant)
            and isinstance(key.value, str)
        ):
            continue
        if isinstance(stmt.value, ast.Constant):
            values[key.value] = stmt.value.value
    return values


def test_i2_r2_sidebar_chronology_routes_to_workspace_chronology():
    values = _timeline_route_assignments()
    assert values["m6_workspace_view"] == "chronology"
    assert values["m7_source_evidence_view"] is False


def test_i2_r2_sidebar_chronology_no_longer_routes_to_none():
    values = _timeline_route_assignments()
    assert values["m6_workspace_view"] is not None


def test_i2_r2_app_workspace_route_still_accepts_chronology():
    source = Path("src/app.py").read_text(encoding="utf-8-sig")
    tree = ast.parse(source)

    route = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test_source = ast.get_source_segment(source, node.test) or ""
        if (
            "m6_workspace_view" in test_source
            and "chronology" in test_source
        ):
            route = node
            break

    assert route is not None

    calls = {
        call.func.id
        for call in ast.walk(route)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
    }
    assert "show_workspace" in calls


def test_i2_r2_released_chronology_renderer_remains_present():
    source = Path("src/ui/workspace.py").read_text(encoding="utf-8-sig")
    assert 'st.header("Chronology")' in source
    assert "Technical / audit details" in source
    assert "Open source" in source
    assert "_render_chronology_task_creator(" in source
