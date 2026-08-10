from __future__ import annotations

import importlib
import sys
import types
from types import SimpleNamespace

import pytest


class Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeStreamlit:
    def __init__(self):
        self.dividers = 0
        self.subheaders = []
        self.captions = []
        self.texts = []
        self.expanders = []

    def divider(self):
        self.dividers += 1

    def subheader(self, text):
        self.subheaders.append(text)

    def caption(self, text):
        self.captions.append(text)

    def text(self, text):
        self.texts.append(text)

    def expander(self, label, *, expanded=False):
        self.expanders.append((label, expanded))
        return Context()


@pytest.fixture
def chat_module(monkeypatch):
    config = types.ModuleType("config")
    config.openai_client = SimpleNamespace()
    config.collection = SimpleNamespace()
    monkeypatch.setitem(sys.modules, "config", config)
    sys.modules.pop("legalrag", None)
    sys.modules.pop("ui.chat", None)
    return importlib.import_module("ui.chat")


def test_chat_reference_panel_renders_structured_deterministic_finding(monkeypatch, chat_module):
    fake = FakeStreamlit()
    monkeypatch.setattr(chat_module, "st", fake)
    payload = {
        "evidence_reference_resolution": {
            "receipt": {
                "documents_completely_expanded": 43,
                "searched_document_ids": [f"doc-{i}" for i in range(43)],
                "case_corpus_complete": True,
            },
            "findings": [{
                "status": "POSSIBLE_REFERENCED_BUT_NOT_LOCATED",
                "reference_text": "email from Emma Shakespeare dated 6 July 2005",
                "matched_document_ids": [],
                "matched_evidence_keys": [],
                "basis": "No governed match after complete case-corpus inspection.",
            }],
        }
    }

    chat_module._show_reference_findings(payload)

    assert fake.dividers == 1
    assert "🔗 Referenced Evidence" in fake.subheaders
    assert any("43/43 governed documents" in value for value in fake.captions)
    rendered = "\n".join(fake.texts)
    assert "email from Emma Shakespeare dated 6 July 2005" in rendered
    assert "POSSIBLE_REFERENCED_BUT_NOT_LOCATED" in rendered
    assert "Matched governed document IDs: none" in rendered
    assert any("does not prove" in value for value in fake.captions)


def test_chat_reference_panel_is_absent_when_no_explicit_findings(monkeypatch, chat_module):
    fake = FakeStreamlit()
    monkeypatch.setattr(chat_module, "st", fake)

    chat_module._show_reference_findings({
        "evidence_reference_resolution": {
            "receipt": {"searched_document_ids": []},
            "findings": [],
        }
    })

    assert fake.dividers == 0
    assert fake.subheaders == []
