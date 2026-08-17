from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def dotted(node):
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def module_scope(tree):
    stack = list(reversed(tree.body))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(node))))


def test_config_has_no_module_scope_chroma_open():
    tree = ast.parse((SRC / "config.py").read_text(encoding="utf-8"))
    calls = [
        dotted(node.func)
        for node in module_scope(tree)
        if isinstance(node, ast.Call)
    ]
    assert not any(name.endswith("PersistentClient") for name in calls)
    assert not any(name.endswith("get_or_create_collection") for name in calls)


def test_config_import_is_chroma_side_effect_free_and_accessors_cache(monkeypatch):
    calls = []
    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda: None
    fake_openai = types.ModuleType("openai")
    fake_openai.OpenAI = type("FakeOpenAI", (), {})
    fake_chromadb = types.ModuleType("chromadb")

    class FakeCollection:
        name = "legal_documents"

    class FakeClient:
        def get_or_create_collection(self, *, name):
            calls.append(("collection", name))
            return FakeCollection()

    def persistent_client(*, path):
        calls.append(("client", path))
        return FakeClient()

    fake_chromadb.PersistentClient = persistent_client
    monkeypatch.setitem(sys.modules, "dotenv", fake_dotenv)
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setitem(sys.modules, "chromadb", fake_chromadb)

    spec = importlib.util.spec_from_file_location("_m4r5_config_probe", SRC / "config.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert calls == []
    assert module.get_chroma_client() is module.get_chroma_client()
    assert module.get_collection() is module.get_collection()
    assert calls == [("client", "db"), ("collection", "legal_documents")]


def test_app_auth_call_remains_before_first_ui_statement():
    tree = ast.parse((SRC / "app.py").read_text(encoding="utf-8"))
    auth_lines = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and dotted(node.func).endswith("require_private_access")
    ]
    assert auth_lines
    assert min(auth_lines) == 44
