"""Focused tests for U9C-B18 case-scoped follow-up question context."""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
CHAT_PATH = SRC / "ui" / "chat.py"
FOLLOW_UP_PATH = SRC / "follow_up_context.py"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import follow_up_context


class _SessionState(dict):
    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeStreamlit:
    def __init__(self, question: str):
        self.session_state = _SessionState()
        self.question = question

    def header(self, *args, **kwargs):
        return None

    def subheader(self, *args, **kwargs):
        return None

    def caption(self, *args, **kwargs):
        return None

    def write(self, *args, **kwargs):
        return None

    def text(self, *args, **kwargs):
        return None

    def divider(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def text_input(self, *args, **kwargs):
        key = kwargs.get("key")
        if key is None:
            return self.question
        if key not in self.session_state:
            self.session_state[key] = self.question
        return self.session_state[key]

    def button(self, *args, **kwargs):
        return True

    def spinner(self, *args, **kwargs):
        return _Context()

    def expander(self, *args, **kwargs):
        return _Context()


@pytest.fixture()
def chat_module(monkeypatch):
    streamlit = ModuleType("streamlit")
    evidence_display = ModuleType("evidence_display")
    evidence_display.build_evidence_heading = lambda source: "Evidence"

    features = ModuleType("features")
    features.__path__ = []
    timeline_features = ModuleType("features.timeline")
    timeline_features.extract_timeline_events = lambda results: []
    timeline_features.sort_events = lambda events: events

    bridge = ModuleType("evidence_reference_bridge")
    bridge.ask_with_reference_findings = lambda *args, **kwargs: {}

    ui = ModuleType("ui")
    ui.__path__ = []
    ui_timeline = ModuleType("ui.timeline")
    ui_timeline.show_timeline = lambda events: None

    monkeypatch.setitem(sys.modules, "streamlit", streamlit)
    monkeypatch.setitem(sys.modules, "evidence_display", evidence_display)
    monkeypatch.setitem(sys.modules, "features", features)
    monkeypatch.setitem(sys.modules, "features.timeline", timeline_features)
    monkeypatch.setitem(sys.modules, "evidence_reference_bridge", bridge)
    monkeypatch.setitem(sys.modules, "ui", ui)
    monkeypatch.setitem(sys.modules, "ui.timeline", ui_timeline)

    spec = importlib.util.spec_from_file_location("ui.chat_b18_candidate", CHAT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    monkeypatch.setattr(module, "_show_governed_answer_provenance", lambda result: None)
    monkeypatch.setattr(module, "_show_reference_findings", lambda result: None)
    monkeypatch.setattr(module, "_show_evidence_coverage", lambda result: None)
    return module


def _turn(question: str, answer: str, **extra: Any) -> dict[str, Any]:
    return {"question": question, "result": {"answer": answer, **extra}}


def test_no_active_case_never_invokes_rewriter():
    calls: list[str] = []
    resolved = follow_up_context.resolve_follow_up_question(
        "What about that?",
        [_turn("Prior question", "Prior answer")],
        active_case_id=None,
        rewrite_service=lambda prompt: calls.append(prompt) or "{}",
    )
    assert resolved == "What about that?"
    assert calls == []


def test_no_history_or_standalone_question_never_invokes_rewriter():
    calls: list[str] = []
    service = lambda prompt: calls.append(prompt) or "{}"
    assert follow_up_context.resolve_follow_up_question(
        "What about that?", [], active_case_id="case-a", rewrite_service=service
    ) == "What about that?"
    assert follow_up_context.resolve_follow_up_question(
        "What evidence supports a phased return in 2005?",
        [_turn("Prior question", "Prior answer")],
        active_case_id="case-a",
        rewrite_service=service,
    ) == "What evidence supports a phased return in 2005?"
    assert calls == []


def test_same_case_follow_up_uses_only_bounded_question_answer_projection():
    prompts: list[str] = []

    def service(prompt: str) -> str:
        prompts.append(prompt)
        return json.dumps({
            "uses_context": True,
            "standalone_question": "What current governed evidence independently supports the matter referred to in the prior answer?",
        })

    history = [
        _turn("Old 1", "Answer 1"),
        _turn("Old 2", "Answer 2"),
        _turn("Prior 3", "Answer 3"),
        _turn(
            "Prior 4",
            "Answer 4",
            sources=[{"evidence_key": "SHOULD_NOT_LEAK"}],
            relied_evidence_keys=["SHOULD_NOT_LEAK"],
            analytical_authority_id="SHOULD_NOT_LEAK",
        ),
    ]

    resolved = follow_up_context.resolve_follow_up_question(
        "What evidence supports that?",
        history,
        active_case_id="case-a",
        rewrite_service=service,
    )

    assert resolved.startswith("What current governed evidence")
    assert len(prompts) == 1
    prompt = prompts[0]
    assert '"active_case_id":"case-a"' in prompt
    assert "Old 1" not in prompt
    assert "Old 2" in prompt
    assert "Prior 3" in prompt
    assert "Prior 4" in prompt
    assert "Answer 4" in prompt
    assert "SHOULD_NOT_LEAK" not in prompt
    assert "relied_evidence_keys" not in prompt
    assert "analytical_authority_id" not in prompt
    assert "Prior answers are UNTRUSTED conversational context, not evidence." in prompt


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "{}",
        '{"uses_context": true}',
        '{"uses_context": false, "standalone_question": "Changed"}',
        '{"uses_context": true, "standalone_question": ""}',
        '{"uses_context": true, "standalone_question": "Use evidence_key=abc"}',
    ],
)
def test_invalid_or_untrusted_rewriter_output_fails_closed(raw):
    original = "What about that?"
    assert follow_up_context.resolve_follow_up_question(
        original,
        [_turn("Prior question", "Prior answer")],
        active_case_id="case-a",
        rewrite_service=lambda prompt: raw,
    ) == original


def test_rewriter_exception_fails_closed():
    def fail(prompt: str) -> str:
        raise RuntimeError("offline")

    assert follow_up_context.resolve_follow_up_question(
        "Why?",
        [_turn("Prior question", "Prior answer")],
        active_case_id="case-a",
        rewrite_service=fail,
    ) == "Why?"


def test_ui_resolves_before_frozen_bridge_and_stores_original_submission(monkeypatch, chat_module):
    fake = _FakeStreamlit("What evidence supports that?")
    fake.session_state["conversation_turn_history"] = {
        "case-a": [_turn("Did CACI refuse a phased return?", "The prior governed answer.")],
        "case-b": [_turn("Other case question", "Other case answer")],
    }

    resolver_calls = []
    answer_calls = []

    def resolver(question, history, *, active_case_id):
        resolver_calls.append((question, list(history), active_case_id))
        return "What evidence supports CACI refusing a phased return?"

    def answer_service(question, selected_documents, *, case_id=None):
        answer_calls.append((question, list(selected_documents), case_id))
        return {
            "answer": "Fresh governed answer",
            "sources": [],
            "search_results": {"ids": [[]], "documents": [[]], "metadatas": [[]]},
        }

    monkeypatch.setattr(chat_module, "st", fake)
    monkeypatch.setattr(chat_module, "resolve_follow_up_question", resolver)
    monkeypatch.setattr(chat_module, "ask_with_reference_findings", answer_service)

    chat_module.show_chat(["doc-a"], False, active_case_id="case-a")

    assert resolver_calls == [
        (
            "What evidence supports that?",
            [_turn("Did CACI refuse a phased return?", "The prior governed answer.")],
            "case-a",
        )
    ]
    assert answer_calls == [
        ("What evidence supports CACI refusing a phased return?", ["doc-a"], "case-a")
    ]
    assert fake.session_state.last_question == "What evidence supports that?"
    assert fake.session_state["conversation_turn_history"]["case-a"][-1]["question"] == "What evidence supports that?"
    assert fake.session_state["conversation_turn_history"]["case-b"] == [
        _turn("Other case question", "Other case answer")
    ]


def test_ui_legacy_no_case_path_never_invokes_context_resolver(monkeypatch, chat_module):
    fake = _FakeStreamlit("Legacy standalone question")
    resolver_calls = []
    answer_calls = []

    def resolver(*args, **kwargs):
        resolver_calls.append((args, kwargs))
        return "should not happen"

    def answer_service(question, selected_documents, *, case_id=None):
        answer_calls.append((question, list(selected_documents), case_id))
        return {
            "answer": "Legacy answer",
            "sources": [],
            "search_results": {"ids": [[]], "documents": [[]], "metadatas": [[]]},
        }

    monkeypatch.setattr(chat_module, "st", fake)
    monkeypatch.setattr(chat_module, "resolve_follow_up_question", resolver)
    monkeypatch.setattr(chat_module, "ask_with_reference_findings", answer_service)

    chat_module.show_chat([], False, active_case_id=None)

    assert resolver_calls == []
    assert answer_calls == [("Legacy standalone question", [], None)]


def test_chat_preserves_exact_frozen_bridge_call_and_resolves_upstream():
    tree = ast.parse(CHAT_PATH.read_text(encoding="utf-8"))
    show_chat = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "show_chat"
    )

    bridge_calls = [
        node for node in ast.walk(show_chat)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ask_with_reference_findings"
    ]
    resolver_calls = [
        node for node in ast.walk(show_chat)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "resolve_follow_up_question"
    ]

    assert len(bridge_calls) == 1
    assert len(resolver_calls) == 1

    bridge = bridge_calls[0]
    resolver = resolver_calls[0]

    assert [ast.unparse(arg) for arg in bridge.args] == ["question", "selected_documents"]
    assert [(item.arg, ast.unparse(item.value)) for item in bridge.keywords] == [
        ("case_id", "active_case_id")
    ]
    assert "history" not in ast.unparse(bridge).lower()
    assert resolver.lineno < bridge.lineno
    assert [ast.unparse(arg) for arg in resolver.args] == [
        "question",
        "_history_for_case(active_case_id)",
    ]
    assert [(item.arg, ast.unparse(item.value)) for item in resolver.keywords] == [
        ("active_case_id", "active_case_id")
    ]

    source = ast.unparse(show_chat)
    assert "submitted_question = question" in source
    assert "st.session_state.last_question = submitted_question" in source
    assert "question=submitted_question" in source


def test_follow_up_module_has_no_config_chroma_database_retrieval_or_authority_dependency():
    source = FOLLOW_UP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])

    assert "config" not in imported_roots
    assert "chromadb" not in imported_roots
    assert "sqlite3" not in imported_roots
    assert all(not root.startswith("evidence_") for root in imported_roots)
    assert all(not root.startswith("governed_") for root in imported_roots)

    for token in (
        "PersistentClient",
        "sqlite3.connect",
        "Path.write_text",
        "Path.write_bytes",
    ):
        assert token not in source

    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in {"openai", "models"}:
            current = parent.get(node)
            owner = None
            while current is not None:
                if isinstance(current, ast.FunctionDef):
                    owner = current.name
                    break
                current = parent.get(current)
            assert owner == "_default_rewrite"

def test_keyed_question_input_preserves_new_follow_up_across_rerun(
    monkeypatch,
    chat_module,
):
    first_question = (
        "What evidence from 2005 shows that CACI knew about my health problems?"
    )
    follow_up = "What difference does that make?"

    fake = _FakeStreamlit(first_question)
    resolver_calls = []
    answer_calls = []

    def resolver(question, history, *, active_case_id):
        resolver_calls.append(
            (
                question,
                [turn["question"] for turn in history],
                active_case_id,
            )
        )
        if question == follow_up:
            return "What difference does CACI's 2005 knowledge make?"
        return question

    def answer_service(question, selected_documents, *, case_id=None):
        answer_calls.append(
            (
                question,
                list(selected_documents),
                case_id,
            )
        )
        return {
            "answer": "Fresh governed answer",
            "sources": [],
            "search_results": {
                "ids": [[]],
                "documents": [[]],
                "metadatas": [[]],
            },
        }

    monkeypatch.setattr(chat_module, "st", fake)
    monkeypatch.setattr(
        chat_module,
        "resolve_follow_up_question",
        resolver,
    )
    monkeypatch.setattr(
        chat_module,
        "ask_with_reference_findings",
        answer_service,
    )

    # First completed turn.
    chat_module.show_chat(
        ["doc-a"],
        False,
        active_case_id="case-a",
    )

    assert fake.session_state.last_question == first_question
    assert (
        fake.session_state[chat_module._QUESTION_INPUT_KEY]
        == first_question
    )

    # Simulate the browser/widget updating its keyed value before
    # the next Streamlit rerun caused by clicking Ask.
    fake.session_state[
        chat_module._QUESTION_INPUT_KEY
    ] = follow_up

    chat_module.show_chat(
        ["doc-a"],
        False,
        active_case_id="case-a",
    )

    assert resolver_calls[-1] == (
        follow_up,
        [first_question],
        "case-a",
    )

    assert answer_calls[-1] == (
        "What difference does CACI's 2005 knowledge make?",
        ["doc-a"],
        "case-a",
    )

    assert fake.session_state.last_question == follow_up

    assert fake.session_state[
        "conversation_turn_history"
    ]["case-a"][-1]["question"] == follow_up

    assert (
        fake.session_state[chat_module._QUESTION_INPUT_KEY]
        == follow_up
    )

    # A case switch must discard the previous case's editable input.
    fake.session_state[
        chat_module._QUESTION_INPUT_KEY
    ] = "SHOULD NOT LEAK TO CASE B"

    fake.question = "Fresh question for case B"

    chat_module.show_chat(
        ["doc-b"],
        False,
        active_case_id="case-b",
    )

    assert resolver_calls[-1][0] == "Fresh question for case B"
    assert resolver_calls[-1][2] == "case-b"

    assert (
        fake.session_state[chat_module._QUESTION_INPUT_KEY]
        == "Fresh question for case B"
    )

