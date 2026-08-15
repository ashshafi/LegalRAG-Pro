from __future__ import annotations

import ast
import hashlib
import importlib.util
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHAT = ROOT / "src" / "ui" / "chat.py"

FROZEN_FUNCTION_AST_SHA256 = {
    "_show_reference_findings": "b4d4f25c50ab61cef75f90b8d5e75998ed2a1274c0d575d0e990b0cfb5c6fad7",
    "_show_governed_answer_provenance": "136d4ab3cb224f7daf67e6b6263d0046e896d025529c58208d0cd058d885a02c",
    "_show_evidence_coverage": "9bf705dfd37eb59a0e46d1b8308963ed01211458253bb10a6141ae65bfbad19e",
}


class Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class FakeStreamlit:
    def __init__(self, *, questions=None, buttons=None):
        self.session_state = SessionState()
        self._questions = list(questions or [])
        self._buttons = list(buttons or [])
        self.headers: list[str] = []
        self.subheaders: list[str] = []
        self.captions: list[str] = []
        self.texts: list[str] = []
        self.writes: list[object] = []
        self.expanders: list[tuple[str, bool]] = []
        self.dividers = 0
        self.warnings: list[str] = []
        self.text_input_values: list[str] = []

    def header(self, text):
        self.headers.append(str(text))

    def subheader(self, text):
        self.subheaders.append(str(text))

    def caption(self, text):
        self.captions.append(str(text))

    def text(self, text):
        self.texts.append(str(text))

    def write(self, value):
        self.writes.append(value)

    def divider(self):
        self.dividers += 1

    def expander(self, label, *, expanded=False):
        self.expanders.append((str(label), bool(expanded)))
        return Context()

    def spinner(self, text):
        return Context()

    def warning(self, text):
        self.warnings.append(str(text))

    def info(self, text):
        self.writes.append(str(text))

    def text_input(self, label, *, value="", key=None):
        if key is None:
            current = value
        else:
            if key not in self.session_state:
                self.session_state[key] = value
            current = self.session_state[key]

        self.text_input_values.append(str(current))

        if self._questions:
            submitted = self._questions.pop(0)
            if key is not None:
                self.session_state[key] = submitted
            return submitted

        return current

    def button(self, label):
        if self._buttons:
            return bool(self._buttons.pop(0))
        return False


@pytest.fixture
def chat_module(monkeypatch):
    streamlit = types.ModuleType("streamlit")
    monkeypatch.setitem(sys.modules, "streamlit", streamlit)

    evidence_display = types.ModuleType("evidence_display")
    evidence_display.build_evidence_heading = lambda source: "Evidence"
    monkeypatch.setitem(sys.modules, "evidence_display", evidence_display)

    features = types.ModuleType("features")
    features.__path__ = []
    timeline_features = types.ModuleType("features.timeline")
    timeline_features.extract_timeline_events = lambda result: []
    timeline_features.sort_events = lambda events: events
    monkeypatch.setitem(sys.modules, "features", features)
    monkeypatch.setitem(sys.modules, "features.timeline", timeline_features)

    bridge = types.ModuleType("evidence_reference_bridge")
    bridge.ask_with_reference_findings = lambda *args, **kwargs: {}
    monkeypatch.setitem(sys.modules, "evidence_reference_bridge", bridge)

    ui = types.ModuleType("ui")
    ui.__path__ = []
    ui_timeline = types.ModuleType("ui.timeline")
    ui_timeline.show_timeline = lambda events: None
    monkeypatch.setitem(sys.modules, "ui", ui)
    monkeypatch.setitem(sys.modules, "ui.timeline", ui_timeline)

    spec = importlib.util.spec_from_file_location("ui.chat", CHAT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["ui.chat"] = module
    spec.loader.exec_module(module)
    return module


def _result(answer: str) -> dict:
    return {
        "answer": answer,
        "sources": [],
        "analytical_authority_mode": "absent",
        "evidence_search_receipt": None,
    }


def test_two_completed_turns_are_case_scoped_and_prior_turn_is_rendered(monkeypatch, chat_module):
    fake = FakeStreamlit(
        questions=["First question?", "Second question?", "Second question?"],
        buttons=[True, True, False],
    )
    calls: list[tuple[str, tuple[str, ...], str | None]] = []

    def answer_service(question, selected_documents, *, case_id=None):
        calls.append((question, tuple(selected_documents), case_id))
        return _result(f"Answer to {question}")

    monkeypatch.setattr(chat_module, "st", fake)
    monkeypatch.setattr(chat_module, "ask_with_reference_findings", answer_service)

    chat_module.show_chat(["doc-a"], False, active_case_id="case-a")
    chat_module.show_chat(["doc-a"], False, active_case_id="case-a")
    chat_module.show_chat(["doc-a"], False, active_case_id="case-a")

    assert calls == [
        ("First question?", ("doc-a",), "case-a"),
        ("Second question?", ("doc-a",), "case-a"),
    ]
    assert fake.session_state["conversation_turn_history"]["case-a"] == [
        {"question": "First question?", "result": _result("Answer to First question?")},
        {"question": "Second question?", "result": _result("Answer to Second question?")},
    ]
    assert "🗂 Conversation History" in fake.subheaders
    assert ("Turn 1 — First question?", False) in fake.expanders
    assert "First question?" in fake.writes
    assert "Answer to First question?" in fake.writes
    assert any("presentation-only" in caption for caption in fake.captions)


def test_case_switch_never_renders_other_case_history_and_clears_question(monkeypatch, chat_module):
    fake = FakeStreamlit()
    monkeypatch.setattr(chat_module, "st", fake)

    first = _result("Case A answer")
    second = _result("Case B answer")
    chat_module._append_history_turn(question="Case A question", result=first, active_case_id="case-a")
    chat_module._append_history_turn(question="Case B question", result=second, active_case_id="case-b")

    fake.session_state.last_question = "Case A question"
    fake.session_state.last_result = first
    fake.session_state.last_result_case_id = "case-a"
    fake.session_state.show_timeline = False

    chat_module.show_chat(["doc-b"], False, active_case_id="case-b")

    assert fake.text_input_values[-1] == ""
    assert fake.session_state.last_question == ""
    assert fake.session_state.last_result is None
    assert ("Turn 1 — Case B question", False) in fake.expanders
    assert all("Case A question" not in label for label, _ in fake.expanders)
    assert "Case A answer" not in fake.writes


def test_malformed_history_fails_closed_and_cannot_influence_answer_call(monkeypatch, chat_module):
    fake = FakeStreamlit(questions=["Fresh question"], buttons=[True])
    fake.session_state["conversation_turn_history"] = {
        "case-a": [{"question": "poison", "result": "not-a-result"}]
    }
    calls = []

    def answer_service(question, selected_documents, *, case_id=None):
        calls.append((question, selected_documents, case_id))
        return _result("Fresh answer")

    monkeypatch.setattr(chat_module, "st", fake)
    monkeypatch.setattr(chat_module, "ask_with_reference_findings", answer_service)

    chat_module.show_chat(["doc-a"], False, active_case_id="case-a")

    assert calls == [("Fresh question", ["doc-a"], "case-a")]
    assert fake.session_state["conversation_turn_history"]["case-a"] == [
        {"question": "Fresh question", "result": _result("Fresh answer")}
    ]
    assert "poison" not in fake.writes


def test_answer_service_call_has_exact_frozen_single_question_contract():
    tree = ast.parse(CHAT.read_text(encoding="utf-8"))
    show_chat = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "show_chat"
    )
    calls = [
        node
        for node in ast.walk(show_chat)
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
    assert "history" not in ast.unparse(call).lower()


def test_history_candidate_preserves_frozen_b16_renderers_exactly():
    tree = ast.parse(CHAT.read_text(encoding="utf-8"))
    for function_name, expected in FROZEN_FUNCTION_AST_SHA256.items():
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == function_name
        )
        digest = hashlib.sha256(
            ast.dump(function, annotate_fields=True, include_attributes=False).encode("utf-8")
        ).hexdigest()
        assert digest == expected, function_name


def test_history_candidate_adds_no_retrieval_openai_chroma_database_or_authority_dependency():
    tree = ast.parse(CHAT.read_text(encoding="utf-8"))
    forbidden_import_roots = {
        "chromadb",
        "sqlite3",
        "openai",
        "retriever",
        "evidence_search",
        "evidence_retrieval",
        "evidence_answer",
        "governed_answer_authority",
        "governed_analytical_authority",
        "source_evidence",
        "legal_analysis",
    }
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
    assert imported_roots.isdisjoint(forbidden_import_roots)

    source = CHAT.read_text(encoding="utf-8")
    for forbidden in (
        "collection.query",
        "PersistentClient",
        "responses.create",
        "load_active_governed_analytical_authority",
        "route_question_to_active_authority",
        "validate_answer_statement_bindings",
        "resolve_evidence_references",
        "search_case_evidence",
        "inspect_document_complete",
        "sqlite3",
    ):
        assert forbidden not in source


def test_history_is_session_only_and_no_persistent_write_api_is_introduced():
    source = CHAT.read_text(encoding="utf-8")
    assert "conversation_turn_history" in source
    for forbidden in (
        "open(",
        "write_text(",
        "write_bytes(",
        "Path(",
        "json.dump",
        "pickle",
        "shelve",
    ):
        assert forbidden not in source
