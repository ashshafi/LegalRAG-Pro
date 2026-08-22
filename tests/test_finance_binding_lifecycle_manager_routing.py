from __future__ import annotations

import ast
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "app.py"
EXPECTED_APP_SHA256 = (
    "132d410ad10f0ba81184455a58cbc3ec14fa76cbd7bb244e06141d563c40c55b"
)


def _dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return (base + "." if base else "") + node.attr
    return ""


def test_app_routes_bound_case_and_workspace_to_lifecycle_manager_exactly_once():
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _dotted(node.func).endswith("show_finance_binding_lifecycle_manager")
    ]

    assert len(calls) == 1
    call = calls[0]
    assert not call.args
    kwargs = {
        keyword.arg: ast.unparse(keyword.value)
        for keyword in call.keywords
        if keyword.arg is not None
    }
    assert kwargs == {
        "case_id": "active_case_id",
        "current_workspace_id": "finance_binding.workspace_id",
    }


def test_app_has_no_direct_activation_or_rollback_query_authority():
    source = APP.read_text(encoding="utf-8")
    assert "activate_finance_case_binding" not in source
    assert "load_finance_case_binding_rollback_workspace_ids" not in source


def test_existing_app_routing_baseline_remains_byte_exact():
    assert hashlib.sha256(APP.read_bytes()).hexdigest() == EXPECTED_APP_SHA256
