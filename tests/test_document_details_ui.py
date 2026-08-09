from __future__ import annotations

from dataclasses import replace

import pytest

from document_catalog import DocumentCatalogEntry, DocumentCatalogError
import ui.document_details as ui


CASE_ID = "11111111-1111-4111-8111-111111111111"


ENTRY = DocumentCatalogEntry(
    source_document_instance_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    original_filename="Role Definition.pdf",
    media_type="application/pdf",
    original_blob_sha256="a" * 64,
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
        self.selectboxes = []
        self.selected = None

    def expander(self, label, *, expanded=False):
        self.expanders.append((label, expanded))
        return Context()

    def info(self, text):
        self.infos.append(text)

    def error(self, text):
        self.errors.append(text)

    def text(self, text):
        self.texts.append(text)

    def selectbox(self, label, *, options, format_func, key):
        options = tuple(options)
        self.selectboxes.append(
            (
                label,
                options,
                tuple(format_func(item) for item in options),
                key,
            )
        )
        return self.selected if self.selected is not None else options[0]


def test_no_active_case_renders_nothing_and_does_not_call_catalog(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(ui, "st", fake)
    calls = []

    def service(case_id):
        calls.append(case_id)
        return (ENTRY,)

    ui.show_document_details(None, catalog_service=service)
    ui.show_document_details("", catalog_service=service)

    assert calls == []
    assert fake.expanders == []
    assert fake.errors == []


def test_empty_case_renders_compact_read_only_state(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(ui, "st", fake)

    ui.show_document_details(CASE_ID, catalog_service=lambda case_id: ())

    assert fake.expanders == [("🔎 Document details", False)]
    assert fake.infos == ["No governed documents are available for this case."]
    assert fake.selectboxes == []


def test_document_details_render_exact_inert_provenance(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(ui, "st", fake)
    calls = []

    def service(case_id):
        calls.append(case_id)
        return (ENTRY,)

    ui.show_document_details(CASE_ID, catalog_service=service)

    assert calls == [CASE_ID]
    assert fake.expanders == [("🔎 Document details", False)]
    assert len(fake.selectboxes) == 1
    assert fake.selectboxes[0][0] == "Document"
    assert fake.selectboxes[0][2] == (
        "Role Definition.pdf · aaaaaaaa",
    )
    rendered = "\n".join(fake.texts)
    assert "Filename: Role Definition.pdf" in rendered
    assert "Media type: application/pdf" in rendered
    assert "Pages: 2" in rendered
    assert "Evidence chunks: 4" in rendered
    assert "Original size: 109,815 bytes" in rendered
    assert ENTRY.source_document_instance_id in rendered
    assert ENTRY.original_blob_sha256 in rendered
    assert ENTRY.source_snapshot_id in rendered
    assert ENTRY.extraction_profile_id in rendered
    assert ENTRY.chunking_profile_id in rendered
    assert "Extraction methods: pypdf_text" in rendered


def test_selector_label_disambiguates_duplicate_filenames(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(ui, "st", fake)
    other = replace(
        ENTRY,
        source_document_instance_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    )

    ui.show_document_details(
        CASE_ID,
        catalog_service=lambda case_id: (ENTRY, other),
    )

    assert fake.selectboxes[0][2] == (
        "Role Definition.pdf · aaaaaaaa",
        "Role Definition.pdf · bbbbbbbb",
    )


def test_catalog_domain_error_is_safe_and_hidden(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(ui, "st", fake)

    def service(case_id):
        raise DocumentCatalogError("SECRET INTERNAL PATH")

    ui.show_document_details(CASE_ID, catalog_service=service)

    assert fake.errors == ["Document details could not be loaded safely."]
    assert "SECRET INTERNAL PATH" not in repr(fake.errors)


def test_non_domain_error_is_not_swallowed(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(ui, "st", fake)

    def service(case_id):
        raise RuntimeError("controlled programming failure")

    with pytest.raises(RuntimeError, match="controlled programming failure"):
        ui.show_document_details(CASE_ID, catalog_service=service)
