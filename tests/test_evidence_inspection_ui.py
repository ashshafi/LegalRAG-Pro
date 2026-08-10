from __future__ import annotations

from dataclasses import replace

import pytest

from evidence_classification import EvidenceSourceType
from evidence_retrieval.models import (
    DocumentEvidenceChunk,
    DocumentEvidenceInspection,
    DocumentEvidencePage,
)
from evidence_roles.models import (
    DocumentEvidenceRoleInspection,
    EvidenceRole,
    EvidenceRoleChunk,
    EvidenceRoleClassification,
    EvidenceRoleCount,
    EvidenceRolePage,
)
from evidence_search import (
    CaseEvidenceSearchResult,
    EvidenceSearchCompletion,
    EvidenceSearchError,
    EvidenceSearchMode,
    EvidenceSearchReceipt,
    EvidenceTextMatchMode,
    NegativeFindingScope,
)
from source_evidence.models import BindingClass, BoundTextRole, ExtractionMethod
import ui.document_register as register_ui
import ui.evidence_inspection as ui


CASE_ID = "11111111-1111-4111-8111-111111111111"
OTHER_CASE_ID = "22222222-2222-4222-8222-222222222222"
DOCUMENT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


CHUNK = DocumentEvidenceChunk(
    page_number=1,
    chunk_ordinal=0,
    chunk_id="chunk-1",
    evidence_key="evidence-key-1",
    evidence_binding_id="binding-1",
    binding_class=BindingClass.FULL_CHAIN_BOUND,
    bound_text_role=BoundTextRole.CHUNK_TEXT,
    chunk_text_sha256="sha256:" + ("c" * 64),
    chunk_text_byte_length=27,
    text="From: HR\nPrimary email text.",
)
PAGE = DocumentEvidencePage(
    page_number=1,
    extraction_method=ExtractionMethod.PYPDF_TEXT,
    page_text_sha256="sha256:" + ("d" * 64),
    page_text_byte_length=27,
    text="From: HR\nPrimary email text.",
    chunks=(CHUNK,),
)
DOCUMENT = DocumentEvidenceInspection(
    case_id=CASE_ID,
    source_document_instance_id=DOCUMENT_ID,
    source_snapshot_id="sha256:" + ("e" * 64),
    original_filename="Appendix H5.pdf",
    original_blob_sha256="f" * 64,
    original_byte_length=12345,
    extraction_profile_id="pdf-page-extraction/1.0",
    chunking_profile_id="recursive-character-text-splitter/1.0",
    page_count=1,
    evidence_chunk_count=1,
    pages=(PAGE,),
)
CLASSIFICATION = EvidenceRoleClassification(
    role=EvidenceRole.PRIMARY_SOURCE,
    rule_id="primary.direct_source_type",
    basis="Existing provenance identifies a direct primary source.",
    source_type=EvidenceSourceType.EMPLOYER_RECORD,
    source_label="Employer record",
    provenance_method="chunk-leading-sender",
    primary_tier=1,
    primary_label="Primary",
)
ROLE_PAGE = EvidenceRolePage(
    page=PAGE,
    chunks=(EvidenceRoleChunk(chunk=CHUNK, classification=CLASSIFICATION),),
)
ROLE_COUNTS = tuple(
    EvidenceRoleCount(role=role, count=1 if role is EvidenceRole.PRIMARY_SOURCE else 0)
    for role in EvidenceRole
)
ROLE_DOCUMENT = DocumentEvidenceRoleInspection(
    document=DOCUMENT,
    document_source_type=EvidenceSourceType.EMPLOYER_RECORD,
    document_source_label="Employer record",
    document_source_method="filename",
    pages=(ROLE_PAGE,),
    role_counts=ROLE_COUNTS,
)
RECEIPT = EvidenceSearchReceipt(
    schema_version="1.0",
    case_id=CASE_ID,
    search_mode=EvidenceSearchMode.DOCUMENT_COMPLETE,
    query_sha256="sha256:" + ("0" * 64),
    case_document_count=2,
    case_page_count=3,
    case_chunk_count=5,
    scope_document_count=1,
    scope_page_count=1,
    scope_chunk_count=1,
    documents_completely_expanded=1,
    pages_inspected=1,
    chunks_inspected=1,
    candidate_document_ids=(DOCUMENT_ID,),
    searched_document_ids=(DOCUMENT_ID,),
    filters_applied=("text=all_evidence",),
    matched_evidence_keys=(CHUNK.evidence_key,),
    completion=EvidenceSearchCompletion.COMPLETE,
    case_corpus_complete=False,
    negative_finding_scope=NegativeFindingScope.SEARCHED_SCOPE,
    negative_finding_permitted=True,
)
RESULT = CaseEvidenceSearchResult(
    case_id=CASE_ID,
    query="",
    search_mode=EvidenceSearchMode.DOCUMENT_COMPLETE,
    documents=(ROLE_DOCUMENT,),
    matches=(),
    receipt=RECEIPT,
)


class Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeStreamlit:
    def __init__(self):
        self.sidebar = self
        self.session_state = {}
        self.titles = []
        self.subheaders = []
        self.texts = []
        self.infos = []
        self.errors = []
        self.codes = []
        self.expanders = []
        self.buttons = []
        self.clicked_key = None

    def title(self, text):
        self.titles.append(text)

    def subheader(self, text):
        self.subheaders.append(text)

    def text(self, text):
        self.texts.append(text)

    def info(self, text):
        self.infos.append(text)

    def error(self, text):
        self.errors.append(text)

    def code(self, text, *, language=None):
        self.codes.append((text, language))

    def expander(self, label, *, expanded=False):
        self.expanders.append((label, expanded))
        return Context()

    def button(self, label, *, key, on_click=None, args=()):
        self.buttons.append((label, key, tuple(args)))
        if key == self.clicked_key and on_click is not None:
            on_click(*args)
            return True
        return False


class RegisterFake(FakeStreamlit):
    def __init__(self):
        super().__init__()
        self.query = ""
        self.captions = []
        self.text_inputs = []

    def text_input(self, label, *, key):
        self.text_inputs.append((label, key))
        return self.query

    def caption(self, text):
        self.captions.append(text)


def test_case_change_resets_only_u8_navigation(monkeypatch):
    fake = FakeStreamlit()
    fake.session_state.update(
        {
            "u8_evidence_inspection_case_id": CASE_ID,
            "u8_evidence_inspection_view": True,
            "u8_evidence_inspection_document_id": DOCUMENT_ID,
            "m7_source_evidence_view": True,
            "unrelated": "keep",
        }
    )
    monkeypatch.setattr(ui, "st", fake)

    changed = ui.synchronise_evidence_inspection_session_state(OTHER_CASE_ID)

    assert changed is True
    assert fake.session_state["u8_evidence_inspection_case_id"] == OTHER_CASE_ID
    assert fake.session_state["u8_evidence_inspection_view"] is False
    assert "u8_evidence_inspection_document_id" not in fake.session_state
    assert fake.session_state["m7_source_evidence_view"] is True
    assert fake.session_state["unrelated"] == "keep"


def test_same_case_does_not_reset_selected_document(monkeypatch):
    fake = FakeStreamlit()
    fake.session_state.update(
        {
            "u8_evidence_inspection_case_id": CASE_ID,
            "u8_evidence_inspection_view": True,
            "u8_evidence_inspection_document_id": DOCUMENT_ID,
        }
    )
    monkeypatch.setattr(ui, "st", fake)

    changed = ui.synchronise_evidence_inspection_session_state(CASE_ID)

    assert changed is False
    assert fake.session_state["u8_evidence_inspection_view"] is True
    assert fake.session_state["u8_evidence_inspection_document_id"] == DOCUMENT_ID


def test_document_register_inspect_action_uses_only_u8_state(monkeypatch):
    fake = RegisterFake()
    fake.clicked_key = f"u8_document_register_inspect::{CASE_ID}::{DOCUMENT_ID}"
    fake.session_state["m7_source_evidence_view"] = True
    monkeypatch.setattr(register_ui, "st", fake)

    entry = type(
        "Entry",
        (),
        {
            "original_filename": "Appendix H5.pdf",
            "page_count": 1,
            "evidence_chunk_count": 1,
            "extraction_methods": ("pypdf_text",),
            "source_document_instance_id": DOCUMENT_ID,
            "original_blob_sha256": "f" * 64,
        },
    )()

    register_ui.show_document_register(CASE_ID, catalog_service=lambda case_id: (entry,))

    assert fake.session_state["u8_evidence_inspection_document_id"] == DOCUMENT_ID
    assert fake.session_state["u8_evidence_inspection_view"] is True
    assert fake.session_state["m7_source_evidence_view"] is True
    assert fake.buttons == [
        (
            "Inspect Evidence",
            f"u8_document_register_inspect::{CASE_ID}::{DOCUMENT_ID}",
            (DOCUMENT_ID,),
        )
    ]


def test_inspection_calls_exact_document_complete_boundary_and_renders_full_chain(monkeypatch):
    fake = FakeStreamlit()
    fake.session_state["u8_evidence_inspection_document_id"] = DOCUMENT_ID
    monkeypatch.setattr(ui, "st", fake)
    calls = []

    def service(**kwargs):
        calls.append(kwargs)
        return RESULT

    ui.show_evidence_inspection(CASE_ID, search_service=service)

    assert calls == [
        {
            "case_id": CASE_ID,
            "query": "",
            "mode": EvidenceSearchMode.DOCUMENT_COMPLETE,
            "candidate_document_ids": (DOCUMENT_ID,),
            "text_match_mode": EvidenceTextMatchMode.ALL_EVIDENCE,
        }
    ]
    assert fake.errors == []
    assert fake.titles == ["🔬 Document Evidence Inspection"]
    rendered = "\n".join(fake.texts)
    assert "Filename: Appendix H5.pdf" in rendered
    assert f"Source document ID: {DOCUMENT_ID}" in rendered
    assert "Pages: 1" in rendered
    assert "Evidence chunks: 1" in rendered
    assert "Source-bound status: FULL_CHAIN_BOUND" in rendered
    assert "Primary source: 1" in rendered
    assert "Commentary: 0" in rendered
    assert "Search mode: document_complete" in rendered
    assert "Completion: complete" in rendered
    assert "Pages inspected: 1/1" in rendered
    assert "Chunks inspected: 1/1" in rendered
    assert "Evidence role: primary_source" in rendered
    assert "Binding class: full_chain_bound" in rendered
    assert f"Evidence key: {CHUNK.evidence_key}" in rendered
    assert PAGE.text in {item[0] for item in fake.codes}
    assert CHUNK.text in {item[0] for item in fake.codes}
    assert any("People and dates are not asserted" in text for text in fake.infos)


def test_back_button_callback_closes_only_u8_view(monkeypatch):
    fake = FakeStreamlit()
    fake.session_state.update(
        {
            "u8_evidence_inspection_document_id": DOCUMENT_ID,
            "u8_evidence_inspection_view": True,
            "m7_source_evidence_view": True,
        }
    )
    fake.clicked_key = f"u8_evidence_inspection_back::{CASE_ID}"
    monkeypatch.setattr(ui, "st", fake)

    ui.show_evidence_inspection(CASE_ID, search_service=lambda **kwargs: RESULT)

    assert fake.session_state["u8_evidence_inspection_view"] is False
    assert fake.session_state["m7_source_evidence_view"] is True


def test_no_selected_document_is_safe_and_does_not_call_service(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(ui, "st", fake)
    calls = []

    def service(**kwargs):
        calls.append(kwargs)
        return RESULT

    ui.show_evidence_inspection(CASE_ID, search_service=service)

    assert calls == []
    assert fake.infos == ["No governed document is selected for evidence inspection."]


def test_search_domain_error_is_hidden_and_no_text_is_displayed(monkeypatch):
    fake = FakeStreamlit()
    fake.session_state["u8_evidence_inspection_document_id"] = DOCUMENT_ID
    monkeypatch.setattr(ui, "st", fake)

    def service(**kwargs):
        raise EvidenceSearchError("SECRET SOURCE PATH")

    ui.show_evidence_inspection(CASE_ID, search_service=service)

    assert fake.errors == [
        "Document-complete evidence could not be verified. No evidence text has been displayed."
    ]
    assert "SECRET SOURCE PATH" not in repr(fake.errors)
    assert fake.codes == []


def test_mismatched_complete_result_fails_closed(monkeypatch):
    fake = FakeStreamlit()
    fake.session_state["u8_evidence_inspection_document_id"] = DOCUMENT_ID
    monkeypatch.setattr(ui, "st", fake)
    bad = replace(RESULT, case_id=OTHER_CASE_ID)

    ui.show_evidence_inspection(CASE_ID, search_service=lambda **kwargs: bad)

    assert fake.errors == [
        "Document-complete evidence could not be verified. No evidence text has been displayed."
    ]
    assert fake.codes == []


def test_non_domain_error_is_not_swallowed(monkeypatch):
    fake = FakeStreamlit()
    fake.session_state["u8_evidence_inspection_document_id"] = DOCUMENT_ID
    monkeypatch.setattr(ui, "st", fake)

    def service(**kwargs):
        raise RuntimeError("controlled programming failure")

    with pytest.raises(RuntimeError, match="controlled programming failure"):
        ui.show_evidence_inspection(CASE_ID, search_service=service)
