from __future__ import annotations

from dataclasses import replace

import pytest

from document_catalog import DocumentCatalogEntry, DocumentCatalogError
import ui.document_register as ui


CASE_ID = "11111111-1111-4111-8111-111111111111"

ENTRY = DocumentCatalogEntry(
    source_document_instance_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    original_filename="Role Definition.pdf",
    media_type="application/pdf",
    original_blob_sha256="1" * 64,
    original_byte_length=109815,
    source_snapshot_id="sha256:" + ("b" * 64),
    page_count=2,
    evidence_chunk_count=4,
    extraction_profile_id="pdf-page-extraction/1.0",
    chunking_profile_id="recursive-character-text-splitter/1.0",
    extraction_methods=("pypdf_text",),
)


class Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeStreamlit:
    def __init__(self):
        self.sidebar = self
        self.expanders = []
        self.infos = []
        self.errors = []
        self.texts = []
        self.captions = []
        self.text_inputs = []
        self.query = ""

    def expander(self, label, *, expanded=False):
        self.expanders.append((label, expanded))
        return Context()

    def info(self, text):
        self.infos.append(text)

    def error(self, text):
        self.errors.append(text)

    def text(self, text):
        self.texts.append(text)

    def caption(self, text):
        self.captions.append(text)

    def text_input(self, label, *, key):
        self.text_inputs.append((label, key))
        return self.query


def test_no_active_case_renders_nothing_and_does_not_call_catalog(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(ui, "st", fake)
    calls = []

    def service(case_id):
        calls.append(case_id)
        return (ENTRY,)

    ui.show_document_register(None, catalog_service=service)
    ui.show_document_register("", catalog_service=service)

    assert calls == []
    assert fake.expanders == []
    assert fake.errors == []


def test_empty_case_renders_safe_read_only_state(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(ui, "st", fake)

    ui.show_document_register(CASE_ID, catalog_service=lambda case_id: ())

    assert fake.expanders == [("📋 Governed document register", False)]
    assert fake.infos == ["No governed documents are available for this matter."]
    assert fake.text_inputs == []


def test_register_uses_exact_case_and_renders_catalog_fields(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(ui, "st", fake)
    calls = []

    def service(case_id):
        calls.append(case_id)
        return (ENTRY,)

    ui.show_document_register(CASE_ID, catalog_service=service)

    assert calls == [CASE_ID]
    assert fake.captions == ["1 governed document"]
    assert fake.text_inputs == [
        ("Filter by filename", f"u7_document_register_filter::{CASE_ID}")
    ]
    assert len(fake.texts) == 1
    rendered = fake.texts[0]
    assert "Role Definition.pdf" in rendered
    assert "pages: 2" in rendered
    assert "chunks: 4" in rendered
    assert "methods: pypdf_text" in rendered
    assert "doc: aaaaaaaa" in rendered
    assert "sha256: 111111111111" in rendered


def test_filename_filter_is_literal_case_insensitive_and_preserves_order(monkeypatch):
    fake = FakeStreamlit()
    fake.query = "  ROLE  "
    monkeypatch.setattr(ui, "st", fake)
    second = replace(
        ENTRY,
        source_document_instance_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        original_filename="Other Evidence.pdf",
        original_blob_sha256="2" * 64,
    )
    third = replace(
        ENTRY,
        source_document_instance_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        original_filename="Role Notes.pdf",
        original_blob_sha256="3" * 64,
    )

    ui.show_document_register(
        CASE_ID,
        catalog_service=lambda case_id: (ENTRY, second, third),
    )

    assert fake.captions == ["Showing 2 of 3 governed documents"]
    assert [line.split(" | ", 1)[0] for line in fake.texts] == [
        "Role Definition.pdf",
        "Role Notes.pdf",
    ]


def test_filter_does_not_match_hash_or_document_id(monkeypatch):
    fake = FakeStreamlit()
    fake.query = "aaaaaaaa"
    monkeypatch.setattr(ui, "st", fake)

    ui.show_document_register(CASE_ID, catalog_service=lambda case_id: (ENTRY,))

    assert fake.texts == []
    assert fake.captions == ["Showing 0 of 1 governed document"]
    assert fake.infos == ["No governed documents match that filename filter."]


def test_duplicate_filenames_remain_distinguishable_by_document_identity(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(ui, "st", fake)
    other = replace(
        ENTRY,
        source_document_instance_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        original_blob_sha256="2" * 64,
    )

    ui.show_document_register(
        CASE_ID,
        catalog_service=lambda case_id: (ENTRY, other),
    )

    assert len(fake.texts) == 2
    assert "doc: aaaaaaaa" in fake.texts[0]
    assert "doc: bbbbbbbb" in fake.texts[1]


def test_display_abbreviation_does_not_mutate_source_identity(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(ui, "st", fake)
    document_id = ENTRY.source_document_instance_id
    sha256 = ENTRY.original_blob_sha256

    ui.show_document_register(CASE_ID, catalog_service=lambda case_id: (ENTRY,))

    assert ENTRY.source_document_instance_id == document_id
    assert ENTRY.original_blob_sha256 == sha256
    assert len(ENTRY.source_document_instance_id) == 36
    assert len(ENTRY.original_blob_sha256) == 64


def test_catalog_domain_error_is_safe_and_hidden(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(ui, "st", fake)

    def service(case_id):
        raise DocumentCatalogError("SECRET INTERNAL PATH")

    ui.show_document_register(CASE_ID, catalog_service=service)

    assert fake.errors == [
        "The governed document register could not be loaded safely."
    ]
    assert "SECRET INTERNAL PATH" not in repr(fake.errors)


def test_non_domain_error_is_not_swallowed(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(ui, "st", fake)

    def service(case_id):
        raise RuntimeError("controlled programming failure")

    with pytest.raises(RuntimeError, match="controlled programming failure"):
        ui.show_document_register(CASE_ID, catalog_service=service)
