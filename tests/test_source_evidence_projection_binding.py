from __future__ import annotations

import ast
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from source_evidence.identity import derive_sha256_id, sha256_bytes
from source_evidence.models import (
    CHUNKING_PROFILE_ID,
    EVIDENCE_BINDING_SCHEMA_VERSION,
    EXTRACTION_PROFILE_ID,
    BindingClass,
    BoundTextRole,
    EvidenceBinding,
    ProjectionBindingCoverage,
)
from source_evidence.projection_binding import (
    ProjectionEvidenceBindingError,
    build_projection_evidence_binding_manifest,
    publish_projection_evidence_binding,
)
from source_evidence.serialization import (
    dumps_projection_evidence_binding_manifest,
    evidence_binding_identity_payload_to_dict,
)
from source_evidence.store import SourceEvidenceStore
from source_evidence.verified_retrieval import build_singleton_analysis_receipt

CASE_ID = "12345678-1234-4234-8234-123456789abc"
OTHER_CASE_ID = "87654321-4321-4321-8321-cba987654321"
REPORT_ID = "11111111-1111-4111-8111-111111111111"
MANIFEST_ID = "22222222-2222-4222-8222-222222222222"
DOC_INSTANCE_ID = "33333333-3333-4333-8333-333333333333"
PROJECTION_SHA = sha256_bytes(b"projection-semantic-payload")
ORIGINAL_SHA = sha256_bytes(b"original")
PAGE_SHA = sha256_bytes(b"page")
CHUNK_SHA = sha256_bytes(b"chunk")
SUMMARY_SHA = sha256_bytes(b"summary")
LEGACY_SHA = sha256_bytes(b"legacy")
SNAPSHOT_ID = "sha256:" + sha256_bytes(b"snapshot")


@dataclass(frozen=True)
class FakeCitation:
    citation_id: str
    evidence_key: str
    document_name: str = "evidence.pdf"
    document_id: str | None = "document-1"
    page: int | None = 2
    chunk_id: str | None = None


@dataclass(frozen=True)
class FakeProjection:
    citations: tuple[FakeCitation, ...]
    report_projection_id: str = REPORT_ID
    projection_payload_sha256: str = PROJECTION_SHA
    case_header: object = field(default_factory=lambda: SimpleNamespace(case_id=CASE_ID))
    manifest: object = field(default_factory=lambda: SimpleNamespace(manifest_id=MANIFEST_ID))


def citation(key: str, *, page: int | None = 2, document_name: str = "evidence.pdf") -> FakeCitation:
    return FakeCitation(
        citation_id=key,
        evidence_key=key,
        document_name=document_name,
        page=page,
        chunk_id=key,
    )


def projection(*citations: FakeCitation) -> FakeProjection:
    return FakeProjection(citations=tuple(citations))


def _binding_id(value: EvidenceBinding) -> EvidenceBinding:
    return replace(
        value,
        evidence_binding_id=derive_sha256_id(evidence_binding_identity_payload_to_dict(value)),
    )


def binding(
    key: str,
    binding_class: BindingClass = BindingClass.FULL_CHAIN_BOUND,
    *,
    case_id: str = CASE_ID,
    document_name: str = "evidence.pdf",
    document_id: str | None = "document-1",
    page: int | None = 2,
    chunk_id: str | None = None,
) -> EvidenceBinding:
    if binding_class is BindingClass.FULL_CHAIN_BOUND:
        value = EvidenceBinding(
            schema_version=EVIDENCE_BINDING_SCHEMA_VERSION,
            case_id=case_id,
            evidence_key=key,
            chunk_id=key if chunk_id is None else chunk_id,
            binding_class=binding_class,
            bound_text_role=BoundTextRole.CHUNK_TEXT,
            source_document_instance_id=DOC_INSTANCE_ID,
            source_snapshot_id=SNAPSHOT_ID,
            document_name=document_name,
            document_id=document_id,
            page=page,
            chunk_ordinal=0,
            original_blob_sha256=ORIGINAL_SHA,
            page_text_sha256=PAGE_SHA,
            chunk_text_sha256=CHUNK_SHA,
            bound_text_sha256=CHUNK_SHA,
            extraction_profile_id=EXTRACTION_PROFILE_ID,
            chunking_profile_id=CHUNKING_PROFILE_ID,
            evidence_binding_id="sha256:" + ("0" * 64),
        )
    elif binding_class is BindingClass.ANALYTICAL_TEXT_BOUND:
        value = EvidenceBinding(
            schema_version=EVIDENCE_BINDING_SCHEMA_VERSION,
            case_id=case_id,
            evidence_key=key,
            chunk_id=chunk_id,
            binding_class=binding_class,
            bound_text_role=BoundTextRole.ANALYTICAL_SUMMARY,
            source_document_instance_id=None,
            source_snapshot_id=None,
            document_name=document_name,
            document_id=document_id,
            page=page,
            chunk_ordinal=None,
            original_blob_sha256=None,
            page_text_sha256=None,
            chunk_text_sha256=None,
            bound_text_sha256=SUMMARY_SHA,
            extraction_profile_id=None,
            chunking_profile_id=None,
            evidence_binding_id="sha256:" + ("0" * 64),
        )
    elif binding_class is BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT:
        value = EvidenceBinding(
            schema_version=EVIDENCE_BINDING_SCHEMA_VERSION,
            case_id=case_id,
            evidence_key=key,
            chunk_id=chunk_id,
            binding_class=binding_class,
            bound_text_role=BoundTextRole.LEGACY_CURRENT_INDEX_TEXT,
            source_document_instance_id=None,
            source_snapshot_id=None,
            document_name=document_name,
            document_id=document_id,
            page=page,
            chunk_ordinal=None,
            original_blob_sha256=None,
            page_text_sha256=None,
            chunk_text_sha256=None,
            bound_text_sha256=LEGACY_SHA,
            extraction_profile_id=None,
            chunking_profile_id=None,
            evidence_binding_id="sha256:" + ("0" * 64),
        )
    else:
        raise AssertionError("test helper requires a concrete binding class")
    return _binding_id(value)


def publish_full_chain(store: SourceEvidenceStore, key: str) -> tuple[EvidenceBinding, object]:
    value = binding(key)
    store.publish_evidence_binding(value)
    receipt = build_singleton_analysis_receipt(
        case_id=CASE_ID,
        evidence_key=key,
        evidence_binding_id=value.evidence_binding_id,
        chunk_text_sha256=CHUNK_SHA,
    )
    store.publish_analysis_receipt(receipt)
    return value, receipt


@pytest.fixture(autouse=True)
def valid_projection_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    import source_evidence.projection_binding as module

    monkeypatch.setattr(module, "validate_case_report_projection", lambda value: None)


def test_empty_projection_is_unbound_and_does_not_touch_store() -> None:
    class NoTouchStore:
        def load_evidence_binding(self, *args):
            raise AssertionError("empty projection must not read bindings")

    result = build_projection_evidence_binding_manifest(projection(), store=NoTouchStore())
    assert result.entries == ()
    assert result.coverage is ProjectionBindingCoverage.UNBOUND
    assert result.case_id == CASE_ID
    assert result.report_projection_id == REPORT_ID
    assert result.projection_payload_sha256 == PROJECTION_SHA
    assert result.manifest_id == MANIFEST_ID


def test_missing_binding_creates_unbound_entry() -> None:
    class Store:
        def load_evidence_binding(self, case_id, evidence_key):
            assert (case_id, evidence_key) == (CASE_ID, "e-1")
            return None

    result = build_projection_evidence_binding_manifest(projection(citation("e-1")), store=Store())
    entry = result.entries[0]
    assert entry.citation_id == entry.evidence_key == "e-1"
    assert entry.binding_class is BindingClass.UNBOUND
    assert entry.evidence_binding_id is None
    assert entry.source_bound_analysis_receipt_id is None
    assert result.coverage is ProjectionBindingCoverage.UNBOUND


@pytest.mark.parametrize(
    "binding_class",
    [BindingClass.ANALYTICAL_TEXT_BOUND, BindingClass.LEGACY_CURRENT_INDEX_SNAPSHOT],
)
def test_weaker_binding_preserves_class_and_never_loads_receipt(binding_class: BindingClass) -> None:
    value = binding("e-1", binding_class)

    class Store:
        def load_evidence_binding(self, case_id, evidence_key):
            return value

        def load_analysis_receipt(self, *args):
            raise AssertionError("weaker classes must not consult M5 receipts")

    result = build_projection_evidence_binding_manifest(projection(citation("e-1")), store=Store())
    entry = result.entries[0]
    assert entry.binding_class is binding_class
    assert entry.evidence_binding_id == value.evidence_binding_id
    assert entry.source_bound_analysis_receipt_id is None
    assert result.coverage is ProjectionBindingCoverage.MIXED_BINDING


def test_full_chain_requires_and_links_exact_m5_singleton_receipt(tmp_path: Path) -> None:
    store = SourceEvidenceStore(tmp_path / "store-v1")
    value, receipt = publish_full_chain(store, "e-1")
    result = build_projection_evidence_binding_manifest(projection(citation("e-1")), store=store)
    entry = result.entries[0]
    assert entry.binding_class is BindingClass.FULL_CHAIN_BOUND
    assert entry.evidence_binding_id == value.evidence_binding_id
    assert entry.source_bound_analysis_receipt_id == receipt.source_bound_analysis_receipt_id
    assert result.coverage is ProjectionBindingCoverage.FULLY_SOURCE_BOUND


def test_full_chain_missing_receipt_fails_closed(tmp_path: Path) -> None:
    store = SourceEvidenceStore(tmp_path / "store-v1")
    store.publish_evidence_binding(binding("e-1"))
    with pytest.raises(ProjectionEvidenceBindingError):
        build_projection_evidence_binding_manifest(projection(citation("e-1")), store=store)


def test_full_chain_wrong_receipt_fails_closed() -> None:
    value = binding("e-1")
    wrong = build_singleton_analysis_receipt(
        case_id=CASE_ID,
        evidence_key="other-evidence",
        evidence_binding_id=value.evidence_binding_id,
        chunk_text_sha256=CHUNK_SHA,
    )

    class Store:
        def load_evidence_binding(self, case_id, evidence_key):
            return value

        def load_analysis_receipt(self, case_id, receipt_id):
            return wrong

    with pytest.raises(ProjectionEvidenceBindingError):
        build_projection_evidence_binding_manifest(projection(citation("e-1")), store=Store())


def test_m5_receipt_absent_from_projection_is_not_promoted(tmp_path: Path) -> None:
    store = SourceEvidenceStore(tmp_path / "store-v1")
    publish_full_chain(store, "unused")
    result = build_projection_evidence_binding_manifest(projection(citation("e-1")), store=store)
    assert tuple(entry.evidence_key for entry in result.entries) == ("e-1",)
    assert result.entries[0].binding_class is BindingClass.UNBOUND


def test_entry_order_is_exact_projection_citation_order(tmp_path: Path) -> None:
    store = SourceEvidenceStore(tmp_path / "store-v1")
    publish_full_chain(store, "e-b")
    publish_full_chain(store, "e-a")
    result = build_projection_evidence_binding_manifest(
        projection(citation("e-b"), citation("e-a")), store=store
    )
    assert tuple(entry.evidence_key for entry in result.entries) == ("e-b", "e-a")


def test_mixed_coverage_is_truthful(tmp_path: Path) -> None:
    store = SourceEvidenceStore(tmp_path / "store-v1")
    publish_full_chain(store, "full")
    store.publish_evidence_binding(binding("analytical", BindingClass.ANALYTICAL_TEXT_BOUND))
    result = build_projection_evidence_binding_manifest(
        projection(citation("full"), citation("analytical"), citation("missing")),
        store=store,
    )
    assert [entry.binding_class for entry in result.entries] == [
        BindingClass.FULL_CHAIN_BOUND,
        BindingClass.ANALYTICAL_TEXT_BOUND,
        BindingClass.UNBOUND,
    ]
    assert result.coverage is ProjectionBindingCoverage.MIXED_BINDING


def test_projection_validation_runs_before_store_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    import source_evidence.projection_binding as module

    called = False

    class Store:
        def load_evidence_binding(self, *args):
            nonlocal called
            called = True
            return None

    def invalid(value):
        raise ValueError("projection tamper")

    monkeypatch.setattr(module, "validate_case_report_projection", invalid)
    with pytest.raises(ProjectionEvidenceBindingError):
        build_projection_evidence_binding_manifest(projection(citation("e-1")), store=Store())
    assert called is False


@pytest.mark.parametrize(
    ("change", "citation_change"),
    [
        ({"case_id": OTHER_CASE_ID}, {}),
        ({"document_name": "other.pdf"}, {}),
        ({"document_id": "other-doc"}, {}),
        ({"page": 3}, {}),
        ({"chunk_id": "other-chunk"}, {}),
    ],
)
def test_concrete_binding_coordinate_mismatches_fail_closed(change, citation_change) -> None:
    value = binding("e-1", **change)

    class Store:
        def load_evidence_binding(self, case_id, evidence_key):
            return value

        def load_analysis_receipt(self, *args):
            raise AssertionError("coordinate mismatch must fail before receipt lookup")

    item = replace(citation("e-1"), **citation_change)
    with pytest.raises(ProjectionEvidenceBindingError):
        build_projection_evidence_binding_manifest(projection(item), store=Store())


def test_citation_chunk_mismatch_fails_full_chain_before_receipt() -> None:
    value = binding("e-1")

    class Store:
        def load_evidence_binding(self, case_id, evidence_key):
            return value

        def load_analysis_receipt(self, *args):
            raise AssertionError("chunk mismatch must fail before receipt lookup")

    item = replace(citation("e-1"), chunk_id="different")
    with pytest.raises(ProjectionEvidenceBindingError):
        build_projection_evidence_binding_manifest(projection(item), store=Store())


def test_builder_does_not_publish() -> None:
    class Store:
        def load_evidence_binding(self, case_id, evidence_key):
            return None

        def publish_projection_binding(self, manifest):
            raise AssertionError("pure builder must not publish")

    build_projection_evidence_binding_manifest(projection(citation("e-1")), store=Store())


def test_publication_round_trip_and_idempotence(tmp_path: Path) -> None:
    store = SourceEvidenceStore(tmp_path / "store-v1")
    publish_full_chain(store, "e-1")
    value = projection(citation("e-1"))
    first = publish_projection_evidence_binding(value, store=store)
    second = publish_projection_evidence_binding(value, store=store)
    assert first == second
    assert store.load_projection_binding(CASE_ID, REPORT_ID) == first


def test_conflicting_publication_for_same_projection_id_fails(tmp_path: Path) -> None:
    store = SourceEvidenceStore(tmp_path / "store-v1")
    value = projection(citation("e-1"))
    first = publish_projection_evidence_binding(value, store=store)
    assert first.coverage is ProjectionBindingCoverage.UNBOUND
    publish_full_chain(store, "e-1")
    with pytest.raises(ProjectionEvidenceBindingError):
        publish_projection_evidence_binding(value, store=store)
    assert store.load_projection_binding(CASE_ID, REPORT_ID) == first


def test_manifest_identity_and_canonical_bytes_are_deterministic(tmp_path: Path) -> None:
    store = SourceEvidenceStore(tmp_path / "store-v1")
    _, receipt = publish_full_chain(store, "e-1")
    value = projection(citation("e-1"))
    first = build_projection_evidence_binding_manifest(value, store=store)
    second = build_projection_evidence_binding_manifest(value, store=store)
    assert first == second
    assert dumps_projection_evidence_binding_manifest(first) == dumps_projection_evidence_binding_manifest(second)
    assert first.entries[0].source_bound_analysis_receipt_id == receipt.source_bound_analysis_receipt_id


def test_manifest_top_level_identity_is_copied_from_projection() -> None:
    result = build_projection_evidence_binding_manifest(
        projection(),
        store=SimpleNamespace(load_evidence_binding=lambda *args: None),
    )
    assert result.case_id == CASE_ID
    assert result.report_projection_id == REPORT_ID
    assert result.projection_payload_sha256 == PROJECTION_SHA
    assert result.manifest_id == MANIFEST_ID


def test_production_module_has_only_approved_layer_imports() -> None:
    source_path = Path(__file__).resolve().parents[1] / "src" / "source_evidence" / "projection_binding.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    forbidden = (
        "chromadb",
        "config",
        "retriever",
        "legal_analysis",
        "case_analysis",
        "report_projection_provider",
        "streamlit",
        "pypdf",
        "pdf2image",
        "pytesseract",
    )
    assert not any(name.startswith(forbidden) for name in imports)
    assert "case_reporting.models" in imports
    assert "case_reporting.validation" in imports
    assert "source_evidence.verified_retrieval" not in imports  # relative import is recorded without package prefix


def test_production_module_does_not_import_reporting_builders_or_renderers() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "src" / "source_evidence" / "projection_binding.py"
    ).read_text(encoding="utf-8")
    assert "case_reporting.projection" not in source
    assert "case_reporting.markdown" not in source
    assert "case_reporting.html" not in source
    assert "case_reporting.pdf" not in source
    assert "report_projection_provider" not in source


def test_public_api_is_exact() -> None:
    import source_evidence.projection_binding as module

    assert module.__all__ == [
        "ProjectionEvidenceBindingError",
        "build_projection_evidence_binding_manifest",
        "publish_projection_evidence_binding",
    ]


def test_cross_platform_manifest_and_m5_receipt_golden(tmp_path: Path) -> None:
    store = SourceEvidenceStore(tmp_path / "store-v1")
    _, receipt = publish_full_chain(store, "e-1")
    manifest = build_projection_evidence_binding_manifest(
        projection(citation("e-1")),
        store=store,
    )
    assert receipt.source_bound_analysis_receipt_id == (
        "sha256:d5c10d7aec149e9cc19dff10c194af62e8388ba15f67552366fdd1c95d5983f4"
    )
    assert manifest.projection_evidence_binding_manifest_id == (
        "sha256:24e8d50f9c32429f0e0e445f91ec5caf44e3c21f343d32086627dbb795ae88cb"
    )
    assert dumps_projection_evidence_binding_manifest(manifest) == (
        '{"case_id":"12345678-1234-4234-8234-123456789abc",'
        '"coverage":"fully_source_bound","entries":[{"binding_class":"full_chain_bound",'
        '"citation_id":"e-1","evidence_binding_id":'
        '"sha256:207385055f1b22d29bf6580d03fa70cb3c51f8842970a4a3869bb3038869e4d6",'
        '"evidence_key":"e-1","source_bound_analysis_receipt_id":'
        '"sha256:d5c10d7aec149e9cc19dff10c194af62e8388ba15f67552366fdd1c95d5983f4"}],'
        '"manifest_id":"22222222-2222-4222-8222-222222222222",'
        '"projection_evidence_binding_manifest_id":'
        '"sha256:24e8d50f9c32429f0e0e445f91ec5caf44e3c21f343d32086627dbb795ae88cb",'
        '"projection_payload_sha256":"df9e89d1b1973379976984ee2b91c7d9dc780baa3c0d94f45fcf637ba609e82c",'
        '"report_projection_id":"11111111-1111-4111-8111-111111111111",'
        '"schema_version":"projection-evidence-binding/1.0"}\n'
    )


def test_citation_id_must_equal_evidence_key_even_if_projection_validator_is_stubbed() -> None:
    item = replace(citation("e-1"), citation_id="different")
    with pytest.raises(ProjectionEvidenceBindingError):
        build_projection_evidence_binding_manifest(
            projection(item),
            store=SimpleNamespace(load_evidence_binding=lambda *args: None),
        )


def test_publisher_does_not_publish_when_build_fails() -> None:
    value = binding("e-1")
    published = False

    class Store:
        def load_evidence_binding(self, case_id, evidence_key):
            return value

        def load_analysis_receipt(self, case_id, receipt_id):
            raise RuntimeError("missing receipt")

        def publish_projection_binding(self, manifest):
            nonlocal published
            published = True

    with pytest.raises(ProjectionEvidenceBindingError):
        publish_projection_evidence_binding(projection(citation("e-1")), store=Store())
    assert published is False
