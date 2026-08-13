from __future__ import annotations

import ast
import hashlib
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHAT = ROOT / "src" / "ui" / "chat.py"
REFERENCE_FINDINGS_AST_SHA256 = "b4d4f25c50ab61cef75f90b8d5e75998ed2a1274c0d575d0e990b0cfb5c6fad7"


class Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeStreamlit:
    def __init__(self):
        self.dividers: int = 0
        self.subheaders: list[str] = []
        self.captions: list[str] = []
        self.texts: list[str] = []
        self.writes: list[object] = []
        self.expanders: list[tuple[str, bool]] = []

    def divider(self):
        self.dividers += 1

    def subheader(self, text):
        self.subheaders.append(str(text))

    def caption(self, text):
        self.captions.append(str(text))

    def text(self, text):
        self.texts.append(str(text))

    def write(self, value):
        self.writes.append(value)

    def expander(self, label, *, expanded=False):
        self.expanders.append((str(label), bool(expanded)))
        return Context()


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


def _applied_result() -> dict:
    return {
        "analytical_authority_mode": "applied",
        "analytical_authority_reason": "Deterministic issue routing selected RA-001.",
        "analytical_authority_id": "sha256:" + "a" * 64,
        "analytical_activation_id": "sha256:" + "b" * 64,
        "answer_statement_bindings": [
            {
                "statement_id": "S1",
                "text": "First validated statement.",
                "source_proposition_refs": [
                    {
                        "issue_analysis_id": "analysis-1",
                        "element_id": "RA-ADJUSTMENT",
                        "source_proposition_index": 0,
                    }
                ],
                "evidence_keys": ["evidence-1"],
                "source_status": "supported_but_not_established",
            },
            {
                "statement_id": "S2",
                "text": "Second validated statement.",
                "source_proposition_refs": [
                    {
                        "issue_analysis_id": "analysis-1",
                        "element_id": "RA-KNOWLEDGE",
                        "source_proposition_index": 2,
                    },
                    {
                        "issue_analysis_id": "analysis-1",
                        "element_id": "RA-KNOWLEDGE",
                        "source_proposition_index": 3,
                    },
                ],
                "evidence_keys": ["evidence-2", "evidence-3"],
                "source_status": "disputed",
            },
        ],
        "relied_evidence_keys": ["evidence-1", "evidence-2", "evidence-3"],
        "sources": [
            {"text": "Inspected source one."},
            {"text": "Inspected source two."},
            {"text": "Inspected source three."},
            {"text": "Inspected but not relied source."},
        ],
        "evidence_search_receipt": {
            "search_mode": "document_complete",
            "completion": "complete",
            "case_document_count": 43,
            "case_page_count": 120,
            "case_chunk_count": 495,
            "documents_completely_expanded": 4,
            "pages_inspected": 12,
            "chunks_inspected": 48,
            "case_corpus_complete": False,
            "negative_finding_scope": "searched_scope",
            "negative_finding_permitted": True,
        },
    }


def test_applied_mode_renders_validated_statements_status_coordinates_and_exact_relied_keys(
    monkeypatch, chat_module
):
    fake = FakeStreamlit()
    monkeypatch.setattr(chat_module, "st", fake)

    chat_module._show_governed_answer_provenance(_applied_result())

    assert fake.dividers == 1
    assert fake.subheaders == ["🧭 Governed Answer Provenance"]
    assert [label for label, _ in fake.expanders] == [
        "Validated statement 1 — supported_but_not_established",
        "Validated statement 2 — disputed",
    ]
    rendered = "\n".join(fake.texts)
    assert "Frozen source status: supported_but_not_established" in rendered
    assert "Frozen source status: disputed" in rendered
    assert "analysis-1 / RA-ADJUSTMENT / proposition 0" in rendered
    assert "analysis-1 / RA-KNOWLEDGE / proposition 2" in rendered
    assert "analysis-1 / RA-KNOWLEDGE / proposition 3" in rendered
    assert [text for text in fake.texts if text.startswith("Relied evidence: ")] == [
        "Relied evidence: evidence-1",
        "Relied evidence: evidence-2",
        "Relied evidence: evidence-3",
    ]


def test_relied_evidence_is_not_inferred_from_sources(monkeypatch, chat_module):
    fake = FakeStreamlit()
    monkeypatch.setattr(chat_module, "st", fake)
    result = _applied_result()
    result["sources"].append({"text": "A fifth inspected source that is not relied upon."})

    chat_module._show_governed_answer_provenance(result)

    rendered = "\n".join(fake.texts)
    assert "A fifth inspected source" not in rendered
    assert [text for text in fake.texts if text.startswith("Relied evidence: ")] == [
        "Relied evidence: evidence-1",
        "Relied evidence: evidence-2",
        "Relied evidence: evidence-3",
    ]


@pytest.mark.parametrize("mode", ["absent", "unavailable", "invalid_authority", "invalid_analytical_output", None])
def test_non_applied_modes_never_render_governed_provenance(monkeypatch, chat_module, mode):
    fake = FakeStreamlit()
    monkeypatch.setattr(chat_module, "st", fake)
    result = _applied_result()
    result["analytical_authority_mode"] = mode

    chat_module._show_governed_answer_provenance(result)

    assert fake.dividers == 0
    assert fake.subheaders == []
    assert fake.texts == []


def test_applied_mode_with_empty_or_malformed_bindings_fails_closed_in_presentation(
    monkeypatch, chat_module
):
    for bindings, relied in [([], []), (["not-a-binding"], ["e1"]), (None, ["e1"]), ([], None)]:
        fake = FakeStreamlit()
        monkeypatch.setattr(chat_module, "st", fake)
        result = _applied_result()
        result["answer_statement_bindings"] = bindings
        result["relied_evidence_keys"] = relied

        chat_module._show_governed_answer_provenance(result)

        assert fake.subheaders == []
        assert fake.texts == []


def test_coverage_is_separate_from_relied_evidence_and_accepts_mapping_receipt(
    monkeypatch, chat_module
):
    fake = FakeStreamlit()
    monkeypatch.setattr(chat_module, "st", fake)

    chat_module._show_evidence_coverage(_applied_result())

    assert fake.subheaders == ["📊 Coverage"]
    rendered = "\n".join(fake.texts)
    assert "Search mode: document_complete · completion: complete" in rendered
    assert "Inspected: 4 documents · 12 pages · 48 chunks" in rendered
    assert "Case corpus: 43 documents · 120 pages · 495 chunks" in rendered
    assert "Negative-finding scope: searched_scope · permitted: yes" in rendered
    assert "evidence-1" not in rendered


def test_coverage_accepts_immutable_attribute_receipt(monkeypatch, chat_module):
    fake = FakeStreamlit()
    monkeypatch.setattr(chat_module, "st", fake)
    result = _applied_result()
    result["evidence_search_receipt"] = SimpleNamespace(
        search_mode=SimpleNamespace(value="exhaustive_evidence"),
        completion=SimpleNamespace(value="complete"),
        case_document_count=43,
        case_page_count=120,
        case_chunk_count=495,
        documents_completely_expanded=43,
        pages_inspected=120,
        chunks_inspected=495,
        case_corpus_complete=True,
        negative_finding_scope=SimpleNamespace(value="case_corpus"),
        negative_finding_permitted=True,
    )

    chat_module._show_evidence_coverage(result)

    rendered = "\n".join(fake.texts)
    assert "Search mode: exhaustive_evidence · completion: complete · whole case corpus complete: yes" in rendered
    assert "Inspected: 43 documents · 120 pages · 495 chunks" in rendered
    assert "Negative-finding scope: case_corpus · permitted: yes" in rendered


def test_no_coverage_panel_without_u8_receipt(monkeypatch, chat_module):
    fake = FakeStreamlit()
    monkeypatch.setattr(chat_module, "st", fake)
    chat_module._show_evidence_coverage({"evidence_search_receipt": None})
    assert fake.dividers == 0
    assert fake.subheaders == []


def test_reference_findings_renderer_is_ast_identical_to_frozen_baseline():
    tree = ast.parse(CHAT.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_show_reference_findings"
    )
    digest = hashlib.sha256(
        ast.dump(function, annotate_fields=True, include_attributes=False).encode("utf-8")
    ).hexdigest()
    assert digest == REFERENCE_FINDINGS_AST_SHA256


def test_c1_ui_has_no_new_retrieval_chroma_openai_authority_or_source_matching_dependency():
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
    ):
        assert forbidden not in source


def test_existing_answer_bridge_and_reference_panel_contract_remain_present():
    source = CHAT.read_text(encoding="utf-8")
    assert "from evidence_reference_bridge import ask_with_reference_findings" in source
    assert "result = ask_with_reference_findings(" in source
    assert "_show_reference_findings(result)" in source
    assert "📚 Inspected Evidence" in source
    assert "_show_evidence_coverage(result)" in source
