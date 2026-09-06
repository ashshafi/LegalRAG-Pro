from pathlib import Path
import ast
from types import SimpleNamespace

import src.bounded_governed_answer as bounded


class _FakeResponses:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(output_text='{"statements":[]}')


class _FakeClient:
    def __init__(self):
        self.responses = _FakeResponses()
        self.timeout = None

    def with_options(self, *, timeout):
        self.timeout = timeout
        return self


def _source() -> str:
    return Path("src/bounded_governed_answer.py").read_text(encoding="utf-8-sig")


def _function_source(name: str) -> str:
    source = _source()
    tree = ast.parse(source)
    node = next(
        n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == name
    )
    return ast.get_source_segment(source, node) or ""


def test_r56_provider_call_accepts_optional_output_schema():
    source = _function_source("_provider_call")
    assert "output_schema" in source


def test_r56_provider_call_emits_strict_json_schema_when_supplied(monkeypatch):
    monkeypatch.setattr(bounded, "_authorise", lambda _model: None)
    client = _FakeClient()
    schema = {
        "type": "object",
        "properties": {"statements": {"type": "array", "items": {"type": "object"}}},
        "required": ["statements"],
        "additionalProperties": False,
    }

    bounded._provider_call(
        client,
        model="test-model",
        prompt="test prompt",
        max_output_tokens=123,
        reasoning_effort=None,
        output_schema=schema,
    )

    text = client.responses.kwargs["text"]
    assert text["format"]["type"] == "json_schema"
    assert text["format"]["name"] == "governed_analytical_answer"
    assert text["format"]["strict"] is True
    assert text["format"]["schema"] == schema


def test_r56_provider_call_omits_structured_format_when_schema_absent(monkeypatch):
    monkeypatch.setattr(bounded, "_authorise", lambda _model: None)
    client = _FakeClient()

    bounded._provider_call(
        client,
        model="test-model",
        prompt="test prompt",
        max_output_tokens=123,
        reasoning_effort=None,
    )

    assert "text" not in client.responses.kwargs


def test_r56_only_final_reduce_receives_output_schema():
    source = _source()
    tree = ast.parse(source)
    fn = next(
        n for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name == "create_bounded_governed_response"
    )

    calls = []
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_provider_call"
        ):
            calls.append(node)

    assert len(calls) == 2

    by_parent_assignment = {}
    for parent in ast.walk(fn):
        if isinstance(parent, ast.Assign) and isinstance(parent.value, ast.Call):
            if parent.value in calls and len(parent.targets) == 1 and isinstance(parent.targets[0], ast.Name):
                by_parent_assignment[parent.targets[0].id] = parent.value

    assert "mapped_answer" in by_parent_assignment
    assert "answer" in by_parent_assignment

    map_keywords = {kw.arg for kw in by_parent_assignment["mapped_answer"].keywords if kw.arg}
    reduce_keywords = {kw.arg for kw in by_parent_assignment["answer"].keywords if kw.arg}

    assert "output_schema" not in map_keywords
    assert "output_schema" in reduce_keywords


def test_r56_existing_timeout_and_r36_boundary_retained():
    source = _source()
    assert "BOUNDED_PROVIDER_TIMEOUT_SECONDS = 90.0" in source
    assert "Intermediate bounded map passes perform source-bound evidence extraction." in source
    assert "final_prompt = _apply_constraint(" in source
