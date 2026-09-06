from pathlib import Path
import ast
import hashlib

CHAT = Path("src/ui/chat.py")


def _function_hash(name: str) -> str:
    source = CHAT.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    node = next(
        n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


def test_frozen_audit_helpers_are_unchanged():
    assert _function_hash("_show_reference_findings") == "b4d4f25c50ab61cef75f90b8d5e75998ed2a1274c0d575d0e990b0cfb5c6fad7"
    assert _function_hash("_show_governed_answer_provenance") == "136d4ab3cb224f7daf67e6b6263d0046e896d025529c58208d0cd058d885a02c"
    assert _function_hash("_show_evidence_coverage") == "9bf705dfd37eb59a0e46d1b8308963ed01211458253bb10a6141ae65bfbad19e"


def test_new_ai_finding_uses_compact_provenance_branch():
    source = CHAT.read_text(encoding="utf-8-sig")
    assert 'if result.get("new_ai_finding"):' in source
    assert "_show_new_ai_finding_provenance_summary(result)" in source
    assert "Source documents and page references used in this provisional finding" in source
    assert "Sources & Provenance in the Audit section" in source


def test_heavy_evidence_rendering_is_under_legacy_else_branch():
    source = CHAT.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    show_chat = next(
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "show_chat"
    )

    target_if = None
    for node in ast.walk(show_chat):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if (
            isinstance(test, ast.Call)
            and isinstance(test.func, ast.Attribute)
            and test.func.attr == "get"
            and isinstance(test.func.value, ast.Name)
            and test.func.value.id == "result"
            and len(test.args) == 1
            and isinstance(test.args[0], ast.Constant)
            and test.args[0].value == "new_ai_finding"
        ):
            target_if = node
            break

    assert target_if is not None
    body_module = ast.Module(body=target_if.body, type_ignores=[])
    assert any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "_show_new_ai_finding_provenance_summary"
        for n in ast.walk(body_module)
    )

    legacy_module = ast.Module(body=target_if.orelse, type_ignores=[])
    legacy_text = "\n".join(ast.unparse(n) for n in target_if.orelse)

    assert "_show_governed_answer_provenance(result)" in legacy_text
    assert "_show_reference_findings(result)" in legacy_text
    assert "_show_evidence_coverage(result)" in legacy_text

    source_loop = next(
        (
            n for n in ast.walk(legacy_module)
            if isinstance(n, ast.For)
            and isinstance(n.target, ast.Name)
            and n.target.id == "source"
            and isinstance(n.iter, ast.Subscript)
            and isinstance(n.iter.value, ast.Name)
            and n.iter.value.id == "result"
            and isinstance(n.iter.slice, ast.Constant)
            and n.iter.slice.value == "sources"
        ),
        None,
    )
    assert source_loop is not None


def test_answer_service_call_contract_is_unchanged():
    source = CHAT.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    show_chat = next(
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "show_chat"
    )
    calls = [
        node for node in ast.walk(show_chat)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ask_with_reference_findings"
    ]
    assert len(calls) == 1
    call = calls[0]
    assert [ast.unparse(arg) for arg in call.args] == ["question", "selected_documents"]
    assert [(item.arg, ast.unparse(item.value)) for item in call.keywords] == [
        ("case_id", "active_case_id")
    ]
