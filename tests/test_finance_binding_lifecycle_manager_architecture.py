from __future__ import annotations

import ast
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "src" / "ui" / "finance_binding_lifecycle_manager.py"
PROVIDER = ROOT / "src" / "finance_case_binding" / "provider.py"
ACTIVATION = ROOT / "src" / "finance_case_binding" / "activation.py"
PACKAGE_INIT = ROOT / "src" / "finance_case_binding" / "__init__.py"

EXPECTED_ACTIVATION_SHA256 = (
    "b547fe4615256d4b70ebb1da86baff7a45a00180b70efbbb4fa01df4d67d75a8"
)


def test_activation_module_remains_byte_exact():
    assert hashlib.sha256(ACTIVATION.read_bytes()).hexdigest() == EXPECTED_ACTIVATION_SHA256


def test_manager_uses_public_rollback_query_and_no_private_provider_state():
    source = MANAGER.read_text(encoding="utf-8")
    assert "load_finance_case_binding_rollback_workspace_ids" in source
    assert "_load_active_state" not in source
    assert "_load_receipt" not in source


def test_provider_exposes_least_authority_target_id_query_only():
    source_text = PROVIDER.read_text(encoding="utf-8")
    tree = ast.parse(source_text)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "load_finance_case_binding_rollback_workspace_ids"
    )

    assert ast.unparse(function.returns) == "tuple[str, ...]"
    source = ast.get_source_segment(source_text, function)
    assert source is not None
    assert "_load_active_state" in source
    assert "chain[1:]" in source
    assert "return tuple(workspace_ids)" in source
    assert "activate_finance_case_binding" not in source


def test_package_exports_public_rollback_target_query():
    source = PACKAGE_INIT.read_text(encoding="utf-8")
    assert source.count("load_finance_case_binding_rollback_workspace_ids") == 2


def test_manager_has_separate_switch_and_rollback_selectors():
    source = MANAGER.read_text(encoding="utf-8")
    assert "switch_target_ids" in source
    assert "rollback_target_ids" in source
    assert "selected_switch_workspace_id" in source
    assert "selected_rollback_workspace_id" in source
    assert "for workspace_id in rollback_authority_ids" in source
    assert "if workspace_id in by_id" in source
