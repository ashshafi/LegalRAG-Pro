from __future__ import annotations

import ast
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from source_evidence.identity import (
    derive_sha256_id,
    derive_source_document_instance_id,
    sha256_bytes,
)
from source_evidence.models import (
    CHUNKING_PROFILE_ID,
    CHUNKING_PROFILE_SCHEMA_VERSION,
    EVIDENCE_BINDING_SCHEMA_VERSION,
    EXTRACTION_PROFILE_ID,
    EXTRACTION_PROFILE_SCHEMA_VERSION,
    PROJECTION_EVIDENCE_BINDING_SCHEMA_VERSION,
    SOURCE_BOUND_ANALYSIS_RECEIPT_SCHEMA_VERSION,
    SOURCE_BOUND_RETRIEVAL_VERIFIER_VERSION,
    SOURCE_DOCUMENT_MANIFEST_SCHEMA_VERSION,
    BindingClass,
    BoundTextRole,
    ChunkingProfile,
    EvidenceBinding,
    ExtractionMethod,
    ExtractionProfile,
    ProjectionBindingCoverage,
    ProjectionBindingEntry,
    ProjectionEvidenceBindingManifest,
    SourceBoundAnalysisReceipt,
    SourceChunkSnapshot,
    SourceDocumentManifest,
    SourcePageSnapshot,
    VerifiedEvidenceUse,
)
from source_evidence.serialization import (
    dumps_evidence_binding,
    dumps_projection_evidence_binding_manifest,
    dumps_source_bound_analysis_receipt,
    dumps_source_document_manifest,
    evidence_binding_identity_payload_to_dict,
    projection_evidence_binding_manifest_identity_payload_to_dict,
    source_bound_analysis_receipt_identity_payload_to_dict,
    source_document_manifest_identity_payload_to_dict,
)
from source_evidence.store import SourceEvidenceStore, SourceEvidenceStoreError

CASE_ID = "12345678-1234-4234-8234-123456789abc"
OTHER_CASE_ID = "87654321-4321-4321-8321-cba987654321"
REPORT_ID = "11111111-1111-4111-8111-111111111111"
REPORT_MANIFEST_ID = "22222222-2222-4222-8222-222222222222"
ORIGINAL = b"original-pdf"
PAGE_TEXT = b"page text"
CHUNK_TEXT = b"chunk text"
SHA_A = sha256_bytes(ORIGINAL)
SHA_B = sha256_bytes(PAGE_TEXT)
SHA_C = sha256_bytes(CHUNK_TEXT)


def extraction_profile() -> ExtractionProfile:
    return ExtractionProfile(
        profile_id=EXTRACTION_PROFILE_ID,
        profile_schema_version=EXTRACTION_PROFILE_SCHEMA_VERSION,
        pypdf_package_version="6.14.2",
        pdf2image_package_version=None,
        pytesseract_package_version=None,
        tesseract_engine_version=None,
        poppler_version=None,
        ocr_language="eng",
        ocr_config="",
        ocr_dpi=200,
    )


def chunking_profile() -> ChunkingProfile:
    return ChunkingProfile(
        profile_id=CHUNKING_PROFILE_ID,
        profile_schema_version=CHUNKING_PROFILE_SCHEMA_VERSION,
        library="langchain-text-splitters",
        library_version="1.1.2",
        chunk_size=1000,
        chunk_overlap=200,
        separators=("\n\n", "\n", " ", ""),
        length_function="len",
        is_separator_regex=False,
    )


def make_manifest(*, page_sha: str = SHA_B) -> SourceDocumentManifest:
    document_id = derive_source_document_instance_id(
        case_id=CASE_ID,
        original_filename="evidence.pdf",
        original_blob_sha256=SHA_A,
    )
    chunk = SourceChunkSnapshot(
        page_number=1,
        chunk_ordinal=0,
        chunk_id="chunk-1",
        evidence_key="chunk-1",
        chunk_text_sha256=SHA_C,
        chunk_text_byte_length=len(CHUNK_TEXT),
    )
    page = SourcePageSnapshot(
        page_number=1,
        extraction_method=ExtractionMethod.PYPDF_TEXT,
        page_text_sha256=page_sha,
        page_text_byte_length=len(PAGE_TEXT),
        chunk_snapshots=(chunk,),
    )
    value = SourceDocumentManifest(
        schema_version=SOURCE_DOCUMENT_MANIFEST_SCHEMA_VERSION,
        case_id=CASE_ID,
        source_document_instance_id=document_id,
        original_filename="evidence.pdf",
        media_type="application/pdf",
        original_blob_sha256=SHA_A,
        original_byte_length=len(ORIGINAL),
        extraction_profile=extraction_profile(),
        chunking_profile=chunking_profile(),
        pages=(page,),
        source_snapshot_id="sha256:" + "0" * 64,
    )
    return replace(
        value,
        source_snapshot_id=derive_sha256_id(source_document_manifest_identity_payload_to_dict(value)),
    )


def make_binding(*, document_name: str = "evidence.pdf") -> EvidenceBinding:
    manifest = make_manifest()
    value = EvidenceBinding(
        schema_version=EVIDENCE_BINDING_SCHEMA_VERSION,
        case_id=CASE_ID,
        evidence_key="chunk-1",
        chunk_id="chunk-1",
        binding_class=BindingClass.FULL_CHAIN_BOUND,
        bound_text_role=BoundTextRole.CHUNK_TEXT,
        source_document_instance_id=manifest.source_document_instance_id,
        source_snapshot_id=manifest.source_snapshot_id,
        document_name=document_name,
        document_id=None,
        page=1,
        chunk_ordinal=0,
        original_blob_sha256=SHA_A,
        page_text_sha256=SHA_B,
        chunk_text_sha256=SHA_C,
        bound_text_sha256=SHA_C,
        extraction_profile_id=EXTRACTION_PROFILE_ID,
        chunking_profile_id=CHUNKING_PROFILE_ID,
        evidence_binding_id="sha256:" + "0" * 64,
    )
    return replace(
        value,
        evidence_binding_id=derive_sha256_id(evidence_binding_identity_payload_to_dict(value)),
    )


def make_receipt() -> SourceBoundAnalysisReceipt:
    binding = make_binding()
    value = SourceBoundAnalysisReceipt(
        schema_version=SOURCE_BOUND_ANALYSIS_RECEIPT_SCHEMA_VERSION,
        case_id=CASE_ID,
        verifier_version=SOURCE_BOUND_RETRIEVAL_VERIFIER_VERSION,
        verified_evidence=(
            VerifiedEvidenceUse(
                evidence_key=binding.evidence_key,
                evidence_binding_id=binding.evidence_binding_id,
                chunk_text_sha256=SHA_C,
            ),
        ),
        source_bound_analysis_receipt_id="sha256:" + "0" * 64,
    )
    return replace(
        value,
        source_bound_analysis_receipt_id=derive_sha256_id(
            source_bound_analysis_receipt_identity_payload_to_dict(value)
        ),
    )


def make_projection_binding() -> ProjectionEvidenceBindingManifest:
    binding = make_binding()
    receipt = make_receipt()
    value = ProjectionEvidenceBindingManifest(
        schema_version=PROJECTION_EVIDENCE_BINDING_SCHEMA_VERSION,
        case_id=CASE_ID,
        report_projection_id=REPORT_ID,
        projection_payload_sha256=sha256_bytes(b"projection"),
        manifest_id=REPORT_MANIFEST_ID,
        coverage=ProjectionBindingCoverage.FULLY_SOURCE_BOUND,
        entries=(
            ProjectionBindingEntry(
                citation_id="chunk-1",
                evidence_key="chunk-1",
                binding_class=BindingClass.FULL_CHAIN_BOUND,
                evidence_binding_id=binding.evidence_binding_id,
                source_bound_analysis_receipt_id=receipt.source_bound_analysis_receipt_id,
            ),
        ),
        projection_evidence_binding_manifest_id="sha256:" + "0" * 64,
    )
    return replace(
        value,
        projection_evidence_binding_manifest_id=derive_sha256_id(
            projection_evidence_binding_manifest_identity_payload_to_dict(value)
        ),
    )


def store(tmp_path: Path) -> SourceEvidenceStore:
    return SourceEvidenceStore(tmp_path / "store-v1")


def test_constructor_is_side_effect_free_and_injected_root_is_exact(tmp_path: Path) -> None:
    root = tmp_path / "store-v1"
    value = SourceEvidenceStore(root)
    assert value.root == root.resolve(strict=False)
    assert not root.exists()
    assert not (root / "v1").exists()


def test_default_root_is_project_relative_without_creation() -> None:
    expected = Path(__file__).resolve().parents[1] / "source_evidence_store" / "v1"
    existed_before = expected.exists()

    value = SourceEvidenceStore()

    assert value.root == expected
    assert expected.exists() is existed_before


def test_put_blob_uses_content_addressed_layout_and_round_trips(tmp_path: Path) -> None:
    value = store(tmp_path)
    digest = value.put_blob(CHUNK_TEXT)
    expected = value.root / "blobs" / "sha256" / digest[:2] / digest
    assert digest == SHA_C
    assert expected.read_bytes() == CHUNK_TEXT
    assert value.read_blob(digest) == CHUNK_TEXT


def test_put_blob_accepts_exact_bytes_only(tmp_path: Path) -> None:
    value = store(tmp_path)
    with pytest.raises(TypeError):
        value.put_blob(bytearray(CHUNK_TEXT))  # type: ignore[arg-type]


def test_blob_idempotence_and_deduplication(tmp_path: Path) -> None:
    value = store(tmp_path)
    first = value.put_blob(CHUNK_TEXT)
    second = value.put_blob(CHUNK_TEXT)
    assert first == second
    files = [p for p in value.root.rglob("*") if p.is_file()]
    assert files == [value.root / "blobs" / "sha256" / first[:2] / first]


def test_read_blob_rehashes_and_rejects_tamper(tmp_path: Path) -> None:
    value = store(tmp_path)
    digest = value.put_blob(CHUNK_TEXT)
    path = value.root / "blobs" / "sha256" / digest[:2] / digest
    path.write_bytes(b"tampered")
    with pytest.raises(SourceEvidenceStoreError, match="SHA-256"):
        value.read_blob(digest)


def test_required_and_optional_absence_semantics(tmp_path: Path) -> None:
    value = store(tmp_path)
    manifest = make_manifest()
    receipt = make_receipt()
    assert value.load_evidence_binding(CASE_ID, "missing") is None
    assert value.load_projection_binding(CASE_ID, REPORT_ID) is None
    with pytest.raises(SourceEvidenceStoreError, match="missing"):
        value.read_blob(SHA_A)
    with pytest.raises(SourceEvidenceStoreError, match="missing"):
        value.load_document_manifest(CASE_ID, manifest.source_document_instance_id)
    with pytest.raises(SourceEvidenceStoreError, match="missing"):
        value.load_analysis_receipt(CASE_ID, receipt.source_bound_analysis_receipt_id)
    assert not value.root.exists()


def test_document_manifest_layout_exact_canonical_bytes_and_load(tmp_path: Path) -> None:
    value = store(tmp_path)
    manifest = make_manifest()
    value.publish_document_manifest(manifest)
    path = (
        value.root
        / "cases"
        / CASE_ID
        / "documents"
        / manifest.source_document_instance_id
        / "manifest.json"
    )
    assert path.read_bytes() == dumps_source_document_manifest(manifest).encode("utf-8")
    assert path.read_bytes().endswith(b"\n")
    assert not path.read_bytes().endswith(b"\r\n")
    assert value.load_document_manifest(CASE_ID, manifest.source_document_instance_id) == manifest


def test_evidence_binding_layout_uses_hashed_storage_key(tmp_path: Path) -> None:
    value = store(tmp_path)
    binding = make_binding()
    value.publish_evidence_binding(binding)
    key = sha256_bytes(CASE_ID.encode() + b"\0" + binding.evidence_key.encode())
    path = value.root / "cases" / CASE_ID / "evidence-bindings" / f"{key}.json"
    assert path.read_bytes() == dumps_evidence_binding(binding).encode("utf-8")
    assert value.load_evidence_binding(CASE_ID, binding.evidence_key) == binding
    assert binding.evidence_key not in path.name


def test_analysis_receipt_layout_and_load(tmp_path: Path) -> None:
    value = store(tmp_path)
    receipt = make_receipt()
    value.publish_analysis_receipt(receipt)
    path = (
        value.root
        / "cases"
        / CASE_ID
        / "analysis-receipts"
        / f"{receipt.source_bound_analysis_receipt_id[7:]}.json"
    )
    assert path.read_bytes() == dumps_source_bound_analysis_receipt(receipt).encode("utf-8")
    assert value.load_analysis_receipt(CASE_ID, receipt.source_bound_analysis_receipt_id) == receipt


def test_projection_binding_layout_and_load(tmp_path: Path) -> None:
    value = store(tmp_path)
    manifest = make_projection_binding()
    value.publish_projection_binding(manifest)
    path = value.root / "cases" / CASE_ID / "projection-bindings" / f"{REPORT_ID}.json"
    assert path.read_bytes() == dumps_projection_evidence_binding_manifest(manifest).encode("utf-8")
    assert value.load_projection_binding(CASE_ID, REPORT_ID) == manifest


def test_record_idempotent_publication_uses_exact_canonical_bytes(tmp_path: Path) -> None:
    value = store(tmp_path)
    binding = make_binding()
    value.publish_evidence_binding(binding)
    value.publish_evidence_binding(binding)
    assert value.load_evidence_binding(CASE_ID, binding.evidence_key) == binding


def test_sequential_conflicting_binding_is_rejected_without_overwrite(tmp_path: Path) -> None:
    value = store(tmp_path)
    first = make_binding(document_name="one.pdf")
    second = make_binding(document_name="two.pdf")
    value.publish_evidence_binding(first)
    with pytest.raises(SourceEvidenceStoreError, match="conflicts"):
        value.publish_evidence_binding(second)
    assert value.load_evidence_binding(CASE_ID, first.evidence_key) == first


def test_sequential_conflicting_document_manifest_is_rejected(tmp_path: Path) -> None:
    value = store(tmp_path)
    first = make_manifest(page_sha=SHA_B)
    second = make_manifest(page_sha=sha256_bytes(b"different page text"))
    value.publish_document_manifest(first)
    with pytest.raises(SourceEvidenceStoreError, match="conflicts"):
        value.publish_document_manifest(second)
    assert value.load_document_manifest(CASE_ID, first.source_document_instance_id) == first


def test_real_concurrent_identical_publishers_all_succeed(tmp_path: Path) -> None:
    value = store(tmp_path)
    binding = make_binding()

    def publish() -> None:
        value.publish_evidence_binding(binding)

    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [executor.submit(publish) for _ in range(64)]
        for future in futures:
            future.result()
    assert value.load_evidence_binding(CASE_ID, binding.evidence_key) == binding
    assert not list(value.root.rglob(".ise-stage-*"))


def test_real_concurrent_conflicting_publishers_never_overwrite_winner(tmp_path: Path) -> None:
    value = store(tmp_path)
    first = make_binding(document_name="one.pdf")
    second = make_binding(document_name="two.pdf")

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(value.publish_evidence_binding, first),
            executor.submit(value.publish_evidence_binding, second),
        ]
    outcomes: list[str] = []
    for future in futures:
        try:
            future.result()
            outcomes.append("success")
        except SourceEvidenceStoreError:
            outcomes.append("conflict")
    assert sorted(outcomes) == ["conflict", "success"]
    winner = value.load_evidence_binding(CASE_ID, "chunk-1")
    assert winner in (first, second)
    final_bytes = dumps_evidence_binding(winner).encode("utf-8")  # type: ignore[arg-type]
    key = sha256_bytes(CASE_ID.encode() + b"\0chunk-1")
    path = value.root / "cases" / CASE_ID / "evidence-bindings" / f"{key}.json"
    assert path.read_bytes() == final_bytes


def test_publication_final_is_absent_until_complete_staging_is_linked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import source_evidence.store as store_module

    value = store(tmp_path)
    binding = make_binding()
    expected = dumps_evidence_binding(binding).encode("utf-8")
    real_link = store_module.os.link
    observed = {"called": False}

    def checking_link(src: os.PathLike[str] | str, dst: os.PathLike[str] | str, *args, **kwargs) -> None:
        source = Path(src)
        final = Path(dst)
        assert not final.exists()
        assert source.read_bytes() == expected
        observed["called"] = True
        real_link(src, dst, *args, **kwargs)

    monkeypatch.setattr(store_module.os, "link", checking_link)
    value.publish_evidence_binding(binding)
    assert observed["called"]


def test_unsupported_hard_link_fails_closed_and_cleans_own_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import source_evidence.store as store_module

    value = store(tmp_path)

    def unsupported(*args, **kwargs):
        raise OSError("hard links unsupported")

    monkeypatch.setattr(store_module.os, "link", unsupported)
    with pytest.raises(SourceEvidenceStoreError, match="hard-link"):
        value.put_blob(CHUNK_TEXT)
    assert not list(value.root.rglob(".ise-stage-*"))
    assert not list((value.root / "blobs" / "sha256").rglob(SHA_C))


def test_real_same_directory_hard_link_capability(tmp_path: Path) -> None:
    parent = tmp_path / "links"
    parent.mkdir()
    source = parent / "source"
    final = parent / "final"
    source.write_bytes(b"complete")
    try:
        os.link(source, final)
    except OSError as exc:  # pragma: no cover - governed environment gate
        pytest.fail(f"same-directory hard-link create-if-absent is unavailable: {exc}")
    assert final.read_bytes() == b"complete"


def test_symlink_final_is_rejected(tmp_path: Path) -> None:
    value = store(tmp_path)
    binding = make_binding()
    key = sha256_bytes(CASE_ID.encode() + b"\0" + binding.evidence_key.encode())
    final = value.root / "cases" / CASE_ID / "evidence-bindings" / f"{key}.json"
    final.parent.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_bytes(dumps_evidence_binding(binding).encode("utf-8"))
    try:
        final.symlink_to(outside)
    except OSError as exc:  # pragma: no cover - permission dependent on Windows
        pytest.skip(f"symlink unavailable: {exc}")
    with pytest.raises(SourceEvidenceStoreError, match="Unsafe"):
        value.publish_evidence_binding(binding)


def test_symlink_directory_escape_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "store-v1"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "cases").symlink_to(outside, target_is_directory=True)
    except OSError as exc:  # pragma: no cover - permission dependent on Windows
        pytest.skip(f"directory symlink unavailable: {exc}")
    value = SourceEvidenceStore(root)
    with pytest.raises(SourceEvidenceStoreError, match="Unsafe"):
        value.publish_evidence_binding(make_binding())
    assert not list(outside.rglob("*.json"))


def test_case_isolation_returns_no_other_case_binding(tmp_path: Path) -> None:
    value = store(tmp_path)
    binding = make_binding()
    value.publish_evidence_binding(binding)
    assert value.load_evidence_binding(OTHER_CASE_ID, binding.evidence_key) is None


def test_requested_path_identity_mismatch_is_detected(tmp_path: Path) -> None:
    value = store(tmp_path)
    binding = make_binding()
    wrong_key = sha256_bytes(OTHER_CASE_ID.encode() + b"\0" + binding.evidence_key.encode())
    path = value.root / "cases" / OTHER_CASE_ID / "evidence-bindings" / f"{wrong_key}.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(dumps_evidence_binding(binding).encode("utf-8"))
    with pytest.raises(SourceEvidenceStoreError, match="requested identity"):
        value.load_evidence_binding(OTHER_CASE_ID, binding.evidence_key)


def test_noncanonical_or_tampered_record_fails_closed(tmp_path: Path) -> None:
    value = store(tmp_path)
    binding = make_binding()
    value.publish_evidence_binding(binding)
    key = sha256_bytes(CASE_ID.encode() + b"\0" + binding.evidence_key.encode())
    path = value.root / "cases" / CASE_ID / "evidence-bindings" / f"{key}.json"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(SourceEvidenceStoreError, match="canonical"):
        value.load_evidence_binding(CASE_ID, binding.evidence_key)


def test_store_location_does_not_change_semantic_bytes(tmp_path: Path) -> None:
    binding = make_binding()
    left = SourceEvidenceStore(tmp_path / "left")
    right = SourceEvidenceStore(tmp_path / "right")
    left.publish_evidence_binding(binding)
    right.publish_evidence_binding(binding)
    key = sha256_bytes(CASE_ID.encode() + b"\0" + binding.evidence_key.encode())
    left_bytes = (left.root / "cases" / CASE_ID / "evidence-bindings" / f"{key}.json").read_bytes()
    right_bytes = (right.root / "cases" / CASE_ID / "evidence-bindings" / f"{key}.json").read_bytes()
    assert left_bytes == right_bytes == dumps_evidence_binding(binding).encode("utf-8")


def test_store_source_uses_link_not_overwrite_capable_publication() -> None:
    source_path = Path(__file__).resolve().parents[1] / "src" / "source_evidence" / "store.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = {
        ast.unparse(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert "os.link" in calls
    assert "os.replace" not in calls
    assert "os.rename" not in calls
    assert "Path.replace" not in calls
    assert "Path.rename" not in calls


def test_store_has_no_disallowed_layer_imports() -> None:
    source_path = Path(__file__).resolve().parents[1] / "src" / "source_evidence" / "store.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    forbidden = (
        "pypdf",
        "pdf2image",
        "pytesseract",
        "langchain",
        "chromadb",
        "openai",
        "legal_analysis",
        "case_analysis",
        "case_reporting",
        "document_upload",
        "index_documents",
        "streamlit",
    )
    assert not any(name.startswith(forbidden) for name in imports)


def test_frozen_m1_core_hashes_are_unchanged() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "source_evidence"
    expected = {
        "__init__.py": "227a93c7a53c66f842dcdfeb7b0957ce6568236375c2e5f0b94d6b11994718bc",
        "models.py": "c955c3ddb718dea34baddd53f0a51b2f2b3b3b874845fb0a18be199de3b735e2",
        "identity.py": "20cc4d96e08bbb239f41be9e6da147c50f16c7cbcb346bff6cc357bb14c29bf9",
        "serialization.py": "b6326c57a4c78a7ed086998dcf6b028032b57126ad18781514be5c8e711ef428",
        "validation.py": "63e04c87230bc4fba61c453ef356024d1517d9b43d18271431e1df7d8eabce2f",
    }
    actual = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in expected
    }
    assert actual == expected


def test_gitignore_contains_only_approved_source_store_rule_at_end() -> None:
    gitignore = (Path(__file__).resolve().parents[1] / ".gitignore").read_text(encoding="utf-8")
    assert gitignore.endswith(
        "docs/*.pdf\n# Immutable source evidence store\nsource_evidence_store/\n"
    )
