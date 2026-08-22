"""Synthetic tests for the governed U3 upload UI."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from document_upload import DocumentUploadError  # noqa: E402
import ui.document_upload as upload_ui  # noqa: E402

CASE_A = "11111111-1111-4111-8111-111111111111"
CASE_B = "22222222-2222-4222-8222-222222222222"
PDF_BYTES = b"%PDF-1.7\nexact-u3-upload-bytes\n"


class Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class Uploaded:
    def __init__(self, name="ET3.pdf", content=PDF_BYTES):
        self.name = name
        self.content = content
        self.reads = 0

    def getvalue(self):
        self.reads += 1
        return self.content


class Sidebar:
    def __init__(self, owner):
        self.owner = owner

    def info(self, text):
        self.owner.rendered.append(("sidebar.info", text))

    def expander(self, label, *, expanded=False):
        self.owner.expanders.append((label, expanded))
        return Context()


class FakeStreamlit:
    def __init__(self):
        self.sidebar = Sidebar(self)
        self.uploaded = None
        self.submitted = False
        self.forms = []
        self.uploaders = []
        self.expanders = []
        self.rendered = []

    def form(self, key, *, clear_on_submit=False):
        self.forms.append((key, clear_on_submit))
        return Context()

    def file_uploader(self, label, *, type, accept_multiple_files, key):
        self.uploaders.append((label, type, accept_multiple_files, key))
        return self.uploaded

    def form_submit_button(self, label, *, use_container_width=False):
        return self.submitted

    def spinner(self, text):
        return Context()

    def info(self, text):
        self.rendered.append(("info", text))

    def success(self, text):
        self.rendered.append(("success", text))

    def error(self, text):
        self.rendered.append(("error", text))

    def text(self, text):
        self.rendered.append(("text", text))


@pytest.fixture
def fake(monkeypatch):
    value = FakeStreamlit()
    monkeypatch.setattr(upload_ui, "st", value)
    return value


def result(*, reused=False):
    return SimpleNamespace(
        filename="ET3.pdf",
        path=Path(r"C:\\SECRET\\docs\\ET3.pdf"),
        chunks_indexed=7,
        reused_existing_file=reused,
    )


def test_no_case_is_informational_and_never_calls_service(fake):
    calls = []
    upload_ui.show_document_upload(None, upload_service=lambda **kw: calls.append(kw))
    assert calls == []
    assert fake.uploaders == []
    assert fake.rendered == [("sidebar.info", "Select or create a matter to add documents.")]


def test_active_case_is_single_pdf_explicit_submit_form(fake):
    upload_ui.show_document_upload(CASE_A, upload_service=lambda **kw: result())
    assert fake.forms == [(f"u3_document_upload_form::{CASE_A}", True)]
    assert fake.uploaders == [
        ("PDF document", ["pdf"], False, f"u3_document_upload_file::{CASE_A}")
    ]


def test_file_selection_without_submit_never_reads_or_calls(fake):
    uploaded = Uploaded()
    fake.uploaded = uploaded
    calls = []
    upload_ui.show_document_upload(CASE_A, upload_service=lambda **kw: calls.append(kw))
    assert uploaded.reads == 0
    assert calls == []


def test_submit_passes_exact_filename_bytes_and_case_once(fake):
    uploaded = Uploaded()
    fake.uploaded = uploaded
    fake.submitted = True
    calls = []

    def service(**kwargs):
        calls.append(kwargs)
        return result()

    upload_ui.show_document_upload(CASE_A, upload_service=service)
    assert uploaded.reads == 1
    assert calls == [{"filename": "ET3.pdf", "content": PDF_BYTES, "case_id": CASE_A}]


def test_success_and_reuse_states_are_controlled(fake):
    fake.uploaded = Uploaded()
    fake.submitted = True
    upload_ui.show_document_upload(CASE_A, upload_service=lambda **kw: result())
    assert ("success", "Document added to the selected matter.") in fake.rendered
    assert ("text", "Document: ET3.pdf") in fake.rendered
    assert "C:\\\\SECRET" not in repr(fake.rendered)

    fake.rendered.clear()
    upload_ui.show_document_upload(CASE_A, upload_service=lambda **kw: result(reused=True))
    assert (
        "success",
        "An identical existing PDF was safely reused for the selected matter.",
    ) in fake.rendered


def test_domain_error_uses_fixed_safe_message_without_raw_exception(fake):
    fake.uploaded = Uploaded()
    fake.submitted = True

    def service(**kwargs):
        raise DocumentUploadError(r"SECRET C:\\Users\\x\\db evidence-key=abc")

    upload_ui.show_document_upload(CASE_A, upload_service=service)
    rendered = repr(fake.rendered)
    assert "SECRET" not in rendered
    assert "evidence-key" not in rendered
    assert "C:\\\\Users" not in rendered
    assert "The document could not be added." in rendered


def test_normal_rerender_does_not_repeat_service(fake):
    fake.uploaded = Uploaded()
    fake.submitted = True
    calls = []

    def service(**kwargs):
        calls.append(kwargs)
        return result()

    upload_ui.show_document_upload(CASE_A, upload_service=service)
    fake.submitted = False
    upload_ui.show_document_upload(CASE_A, upload_service=service)
    assert len(calls) == 1


def test_second_deliberate_submit_is_second_safe_service_call(fake):
    fake.uploaded = Uploaded()
    calls = []

    def service(**kwargs):
        calls.append(kwargs)
        return result()

    fake.submitted = True
    upload_ui.show_document_upload(CASE_A, upload_service=service)
    fake.submitted = True
    upload_ui.show_document_upload(CASE_A, upload_service=service)
    assert len(calls) == 2


def test_case_switch_has_distinct_form_and_uploader_keys(fake):
    upload_ui.show_document_upload(CASE_A, upload_service=lambda **kw: result())
    form_a = fake.forms[-1][0]
    uploader_a = fake.uploaders[-1][3]
    upload_ui.show_document_upload(CASE_B, upload_service=lambda **kw: result())
    form_b = fake.forms[-1][0]
    uploader_b = fake.uploaders[-1][3]
    assert form_a != form_b
    assert uploader_a != uploader_b
