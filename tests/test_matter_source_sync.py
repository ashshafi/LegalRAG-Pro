from dataclasses import dataclass
import pytest

from matter_sources.base import MatterSourceUnavailableError
from matter_sources.fake import FakeMatterSourceConnector
from matter_sources.models import ExternalDocument, ExternalMatter, ProviderIdentity, SyncDisposition
from matter_sources.sync import MatterSourceSyncError, apply_pdf_sync_plan, build_sync_plan, observations_after_plan


@dataclass
class Access:
    case_id: str


def _patch_access(monkeypatch):
    import case_management.access as access_module
    monkeypatch.setattr(access_module, "require_matter_mutation", lambda value: value)


def _connector(content=b"%PDF-1.4\none\n", version="v1"):
    matter = ExternalMatter(source_matter_id="matter-1", matter_reference="A1234", title="Smith v Hospital Trust")
    document = ExternalDocument(source_document_id="doc-1", source_matter_id="matter-1",
                                display_name="Medical records.pdf", media_type="application/pdf",
                                source_version_id=version, source_size=len(content))
    return FakeMatterSourceConnector(
        provider=ProviderIdentity(provider="leap", firm_id="firm-1"),
        matters=(matter,), documents=(document,), content={"doc-1": content},
    )


def test_initial_plan_then_identical_resync_is_unchanged():
    connector = _connector()
    first = build_sync_plan(connector, source_matter_id="matter-1")
    assert [e.disposition for e in first.entries] == [SyncDisposition.NEW]
    second = build_sync_plan(connector, source_matter_id="matter-1", previous=observations_after_plan(first))
    assert [e.disposition for e in second.entries] == [SyncDisposition.UNCHANGED]


def test_changed_bytes_create_changed_observation_without_overwriting_prior():
    connector = _connector()
    first = build_sync_plan(connector, source_matter_id="matter-1")
    previous = observations_after_plan(first)
    connector.replace_document_bytes("doc-1", b"%PDF-1.4\ntwo\n", source_version_id="v2")
    second = build_sync_plan(connector, source_matter_id="matter-1", previous=previous)
    entry = second.entries[0]
    assert entry.disposition is SyncDisposition.CHANGED
    assert entry.previous == previous["doc-1"]
    assert entry.current.content_sha256 != entry.previous.content_sha256


def test_external_deletion_is_unavailable_not_destructive():
    connector = _connector()
    first = build_sync_plan(connector, source_matter_id="matter-1")
    previous = observations_after_plan(first)
    connector.remove_document("doc-1")
    second = build_sync_plan(connector, source_matter_id="matter-1", previous=previous)
    entry = second.entries[0]
    assert entry.disposition is SyncDisposition.UNAVAILABLE
    assert entry.previous == previous["doc-1"]
    assert entry.current is None


def test_provider_failure_during_plan_has_no_governed_mutation():
    connector = _connector()
    connector.fail_document_fetch("doc-1")
    with pytest.raises(MatterSourceUnavailableError):
        build_sync_plan(connector, source_matter_id="matter-1")


def test_apply_preflights_all_provider_bytes_before_first_upload(monkeypatch, tmp_path):
    _patch_access(monkeypatch)
    matter = ExternalMatter(source_matter_id="matter-1", matter_reference="A1234", title="Matter")
    docs = (
        ExternalDocument(source_document_id="doc-1", source_matter_id="matter-1", display_name="One.pdf", media_type="application/pdf"),
        ExternalDocument(source_document_id="doc-2", source_matter_id="matter-1", display_name="Two.pdf", media_type="application/pdf"),
    )
    connector = FakeMatterSourceConnector(
        provider=ProviderIdentity(provider="leap", firm_id="firm-1"), matters=(matter,), documents=docs,
        content={"doc-1": b"%PDF-1.4\none\n", "doc-2": b"%PDF-1.4\ntwo\n"},
    )
    plan = build_sync_plan(connector, source_matter_id="matter-1")
    connector.fail_document_fetch("doc-2")
    calls = []
    with pytest.raises(MatterSourceUnavailableError):
        apply_pdf_sync_plan(connector, plan=plan, case_id="case-1", access=Access("case-1"),
                            docs_folder=tmp_path, upload_service=lambda **kwargs: calls.append(kwargs))
    assert calls == []


def test_apply_hands_new_pdf_to_existing_governed_upload_boundary(monkeypatch, tmp_path):
    _patch_access(monkeypatch)
    connector = _connector()
    plan = build_sync_plan(connector, source_matter_id="matter-1")
    calls = []
    def uploader(**kwargs):
        calls.append(kwargs)
        return {"chunks": 3}
    access = Access("case-1")
    applied = apply_pdf_sync_plan(connector, plan=plan, case_id="case-1", access=access,
                                  docs_folder=tmp_path, upload_service=uploader)
    assert len(applied) == 1
    assert calls[0]["case_id"] == "case-1"
    assert calls[0]["access"] is access
    assert calls[0]["content"] == b"%PDF-1.4\none\n"
    assert calls[0]["filename"].startswith("LEAP-")
    assert calls[0]["filename"].endswith("-Medical records.pdf")


def test_apply_rejects_case_access_mismatch_before_upload(monkeypatch, tmp_path):
    _patch_access(monkeypatch)
    connector = _connector()
    plan = build_sync_plan(connector, source_matter_id="matter-1")
    with pytest.raises(MatterSourceSyncError, match="does not match"):
        apply_pdf_sync_plan(connector, plan=plan, case_id="case-1", access=Access("other"),
                            docs_folder=tmp_path, upload_service=lambda **kwargs: object())


def test_apply_fails_closed_if_document_changes_after_plan(monkeypatch, tmp_path):
    _patch_access(monkeypatch)
    connector = _connector()
    plan = build_sync_plan(connector, source_matter_id="matter-1")
    connector.replace_document_bytes("doc-1", b"%PDF-1.4\nlate\n", source_version_id="v2")
    calls = []
    with pytest.raises(MatterSourceSyncError, match="changed after planning"):
        apply_pdf_sync_plan(connector, plan=plan, case_id="case-1", access=Access("case-1"),
                            docs_folder=tmp_path, upload_service=lambda **kwargs: calls.append(kwargs))
    assert calls == []


def test_non_pdf_is_not_sent_to_governed_pdf_upload(monkeypatch, tmp_path):
    _patch_access(monkeypatch)
    matter = ExternalMatter(source_matter_id="matter-1", matter_reference="A1", title="Matter")
    doc = ExternalDocument(source_document_id="doc-1", source_matter_id="matter-1",
                           display_name="note.docx",
                           media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    connector = FakeMatterSourceConnector(
        provider=ProviderIdentity(provider="leap", firm_id="firm-1"), matters=(matter,), documents=(doc,),
        content={"doc-1": b"not a pdf"},
    )
    plan = build_sync_plan(connector, source_matter_id="matter-1")
    with pytest.raises(MatterSourceSyncError, match="PDF"):
        apply_pdf_sync_plan(connector, plan=plan, case_id="case-1", access=Access("case-1"),
                            docs_folder=tmp_path, upload_service=lambda **kwargs: object())
