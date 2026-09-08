from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import work_product_artifact_store as module


CASE_ID = "8081166d-9889-40bb-8add-5d0893037ff0"
PROJECTION_ID = "11111111-1111-4111-8111-111111111111"
MANIFEST_ID = "33333333-3333-4333-8333-333333333333"
ARTIFACT_ID = "44444444-4444-4444-8444-444444444444"
TARGET_ID = "sha256:" + ("5" * 64)
PROJECTION_SHA = "2" * 64
CONTENT = b"# Exact professional review\n\nImmutable bytes.\n"


def target(
    content: bytes = CONTENT,
    *,
    target_id: str = TARGET_ID,
    artifact_id: str = ARTIFACT_ID,
):
    return SimpleNamespace(
        case_id=CASE_ID,
        target_id=target_id,
        report_projection_id=PROJECTION_ID,
        projection_payload_sha256=PROJECTION_SHA,
        manifest_id=MANIFEST_ID,
        artifact_format="markdown",
        artifact_id=artifact_id,
        artifact_sha256=sha256(content).hexdigest(),
        renderer_version="drafting-working-draft-markdown-renderer/1.0",
        output_profile="working-draft-professional-review/1.0",
    )


def expected_paths(root: Path, content: bytes = CONTENT):
    digest = sha256(content).hexdigest()
    blob = (
        root
        / CASE_ID
        / "artifacts"
        / "blobs"
        / "sha256"
        / digest[:2]
        / digest
    )
    binding = (
        root
        / CASE_ID
        / "artifacts"
        / "targets"
        / (TARGET_ID.split(":", 1)[1] + ".json")
    )
    return blob, binding


def test_constructor_is_side_effect_free_and_explicit_root_is_exact(tmp_path):
    root = tmp_path / "release-root"
    store = module.WorkProductArtifactStore(root)
    assert store.root == root
    assert not root.exists()


def test_default_and_environment_root_match_release_contract(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LEGALRAG_WORK_PRODUCT_RELEASE_ROOT", raising=False)
    default = module.WorkProductArtifactStore()
    assert default.root == Path("work_product_release")
    assert not (tmp_path / "work_product_release").exists()

    configured = tmp_path / "configured-release"
    monkeypatch.setenv(
        "LEGALRAG_WORK_PRODUCT_RELEASE_ROOT",
        str(configured),
    )
    from_environment = module.WorkProductArtifactStore()
    assert from_environment.root == configured
    assert not configured.exists()


def test_publish_round_trips_exact_bytes_and_binding(tmp_path):
    root = tmp_path / "release"
    store = module.WorkProductArtifactStore(root)
    value = store.publish_artifact(
        target=target(),
        content=CONTENT,
    )

    assert value.case_id == CASE_ID
    assert value.target_id == TARGET_ID
    assert value.artifact_id == ARTIFACT_ID
    assert value.artifact_sha256 == sha256(CONTENT).hexdigest()
    assert value.artifact_byte_length == len(CONTENT)
    assert value.binding_id.startswith("sha256:")

    blob, binding_path = expected_paths(root)
    assert blob.read_bytes() == CONTENT
    assert store.load_binding(CASE_ID, TARGET_ID) == value
    assert store.read_artifact(CASE_ID, TARGET_ID) == CONTENT
    assert binding_path.is_file()

    raw = binding_path.read_bytes()
    parsed = json.loads(raw.decode("utf-8"))
    assert parsed["binding_id"] == value.binding_id
    assert raw == json.dumps(
        parsed,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    assert not (root / CASE_ID / "events.jsonl").exists()


def test_publish_accepts_exact_bytes_only(tmp_path):
    root = tmp_path / "release"
    store = module.WorkProductArtifactStore(root)

    with pytest.raises(TypeError, match="exact bytes"):
        store.publish_artifact(
            target=target(),
            content=bytearray(CONTENT),  # type: ignore[arg-type]
        )

    assert not root.exists()


def test_target_hash_mismatch_fails_before_any_publication(tmp_path):
    root = tmp_path / "release"
    store = module.WorkProductArtifactStore(root)
    value = target()
    value.artifact_sha256 = "0" * 64

    with pytest.raises(
        module.WorkProductArtifactStoreError,
        match="artifact_sha256",
    ):
        store.publish_artifact(
            target=value,
            content=CONTENT,
        )

    assert not root.exists()


def test_identical_publication_is_idempotent_and_deduplicated(tmp_path):
    root = tmp_path / "release"
    store = module.WorkProductArtifactStore(root)

    first = store.publish_artifact(
        target=target(),
        content=CONTENT,
    )
    second = store.publish_artifact(
        target=target(),
        content=CONTENT,
    )

    assert first == second
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
    )
    assert len(files) == 2
    assert not list(root.rglob(".wpa-stage-*"))


def test_blob_tamper_is_detected_on_read(tmp_path):
    root = tmp_path / "release"
    store = module.WorkProductArtifactStore(root)
    store.publish_artifact(
        target=target(),
        content=CONTENT,
    )

    blob, _ = expected_paths(root)
    blob.write_bytes(b"tampered")

    with pytest.raises(
        module.WorkProductArtifactStoreError,
        match="SHA-256",
    ):
        store.read_artifact(CASE_ID, TARGET_ID)


def test_binding_tamper_is_detected_by_identity(tmp_path):
    root = tmp_path / "release"
    store = module.WorkProductArtifactStore(root)
    store.publish_artifact(
        target=target(),
        content=CONTENT,
    )

    _, binding_path = expected_paths(root)
    raw = json.loads(binding_path.read_text(encoding="utf-8"))
    raw["artifact_byte_length"] += 1
    binding_path.write_text(
        json.dumps(
            raw,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        module.WorkProductArtifactStoreError,
        match="identity",
    ):
        store.load_binding(CASE_ID, TARGET_ID)


def test_invalid_coordinates_fail_closed_without_creating_root(tmp_path):
    root = tmp_path / "release"
    store = module.WorkProductArtifactStore(root)
    value = target()
    value.case_id = "../escape"

    with pytest.raises(module.WorkProductArtifactStoreError):
        store.publish_artifact(
            target=value,
            content=CONTENT,
        )

    assert not root.exists()


def test_containment_rejects_escape_without_creating_root(tmp_path):
    root = tmp_path / "release"
    store = module.WorkProductArtifactStore(root)

    with pytest.raises(
        module.WorkProductArtifactStoreError,
        match="Unsafe",
    ):
        store._contained_path("..", "escape")

    assert not root.exists()


def test_publication_order_is_blob_then_binding(tmp_path, monkeypatch):
    root = tmp_path / "release"
    store = module.WorkProductArtifactStore(root)
    calls = []
    original = store._publish_exact_bytes

    def recording(final, intended, **kwargs):
        calls.append(final)
        return original(final, intended, **kwargs)

    monkeypatch.setattr(
        store,
        "_publish_exact_bytes",
        recording,
    )

    store.publish_artifact(
        target=target(),
        content=CONTENT,
    )

    assert len(calls) == 2
    assert "blobs" in calls[0].parts
    assert "targets" in calls[1].parts


def test_real_concurrent_identical_publishers_all_succeed(tmp_path):
    root = tmp_path / "release"
    store = module.WorkProductArtifactStore(root)

    def publish():
        return store.publish_artifact(
            target=target(),
            content=CONTENT,
        )

    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [
            executor.submit(publish)
            for _ in range(64)
        ]
        results = [
            future.result()
            for future in futures
        ]

    assert all(result == results[0] for result in results)
    assert store.read_artifact(CASE_ID, TARGET_ID) == CONTENT
    assert not list(root.rglob(".wpa-stage-*"))


def test_concurrent_conflicting_target_bindings_never_overwrite_winner(tmp_path):
    root = tmp_path / "release"
    store = module.WorkProductArtifactStore(root)
    first_content = b"first exact artifact"
    second_content = b"second exact artifact"

    first_target = target(
        first_content,
        artifact_id="66666666-6666-4666-8666-666666666666",
    )
    second_target = target(
        second_content,
        artifact_id="77777777-7777-4777-8777-777777777777",
    )

    def publish(value, content):
        try:
            result = store.publish_artifact(
                target=value,
                content=content,
            )
            return ("success", result)
        except module.WorkProductArtifactStoreError as exc:
            return ("conflict", str(exc))

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (
            executor.submit(publish, first_target, first_content),
            executor.submit(publish, second_target, second_content),
        )
        outcomes = [future.result() for future in futures]

    assert sorted(value[0] for value in outcomes) == [
        "conflict",
        "success",
    ]

    binding = store.load_binding(CASE_ID, TARGET_ID)
    actual = store.read_artifact(CASE_ID, TARGET_ID)

    if binding.artifact_sha256 == sha256(first_content).hexdigest():
        assert actual == first_content
    else:
        assert binding.artifact_sha256 == sha256(second_content).hexdigest()
        assert actual == second_content

    assert not list(root.rglob(".wpa-stage-*"))


def test_missing_artifact_fails_closed_without_creating_state(tmp_path):
    root = tmp_path / "release"
    store = module.WorkProductArtifactStore(root)

    with pytest.raises(
        module.WorkProductArtifactStoreError,
        match="absent",
    ):
        store.read_artifact(CASE_ID, TARGET_ID)

    assert not root.exists()


def test_store_has_no_release_state_or_ui_provider_dependencies():
    source = Path(module.__file__).read_text(encoding="utf-8")

    for forbidden in (
        "record_work_product_release",
        "WorkProductReleaseState",
        "streamlit",
        "openai",
        "chromadb",
        "drafting_working_draft",
        "source_evidence",
        "derived_transcription",
    ):
        assert forbidden not in source

    assert 'Path("work_product_release")' in source
    assert "LEGALRAG_WORK_PRODUCT_RELEASE_ROOT" in source
    assert "os.link(staging, final)" in source
    assert 'prefix=".wpa-stage-"' in source
