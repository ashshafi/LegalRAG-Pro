from __future__ import annotations

import os
from pathlib import Path

import pytest

import source_evidence.offline_cutover_execution as execution
from source_evidence.offline_cutover import (
    OFFLINE_CUTOVER_PLAN_SCHEMA_VERSION,
    OfflineCutoverPlan,
)
from source_evidence.offline_cutover_execution import (
    DisposableOfflineCutoverBlocker,
    DisposableOfflineCutoverError,
    execute_disposable_offline_cutover,
)
from source_evidence.production_shadow_build import _build_tree_manifest


CASE_ID = "8081166d-9889-40bb-8add-5d0893037ff0"
MARKER = ".legalrag-pfcr3-disposable"
MARKER_BYTES = b"PFCR3-DISPOSABLE-WORKSPACE\n"


def sha(char: str) -> str:
    return "sha256:" + char * 64


def tree_sha(path: Path) -> str:
    return _build_tree_manifest(
        path,
        require_exists=True,
    ).tree_sha256


def make_workspace(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path]:
    workspace = tmp_path / "pfcr3-workspace"
    workspace.mkdir()

    (workspace / MARKER).write_bytes(MARKER_BYTES)

    active = workspace / "active"
    shadow = workspace / "shadow"
    retained = workspace / "retained"

    active.mkdir()
    shadow.mkdir()

    (active / "chroma.sqlite3").write_bytes(b"old-active")
    (active / "segment.bin").write_bytes(b"old-segment")

    (shadow / "chroma.sqlite3").write_bytes(b"new-shadow")
    (shadow / "segment.bin").write_bytes(b"new-segment")

    return workspace, active, shadow, retained


def make_plan(
    *,
    active: Path,
    shadow: Path,
) -> OfflineCutoverPlan:
    active_sha = tree_sha(active)

    return OfflineCutoverPlan(
        schema_version=OFFLINE_CUTOVER_PLAN_SCHEMA_VERSION,
        case_id=CASE_ID,
        production_shadow_build_report_id=sha("1"),
        active_db_pre_tree_sha256=active_sha,
        active_db_backup_tree_sha256=active_sha,
        source_store_post_tree_sha256=sha("2"),
        shadow_tree_sha256=tree_sha(shadow),
        expected_shadow_row_count=393,
    )


def test_disposable_handoff_retains_old_active_tree(
    tmp_path: Path,
) -> None:
    workspace, active, shadow, retained = make_workspace(tmp_path)

    old_sha = tree_sha(active)
    new_sha = tree_sha(shadow)

    result = execute_disposable_offline_cutover(
        plan=make_plan(active=active, shadow=shadow),
        workspace_root=workspace,
        active_db_root=active,
        shadow_db_root=shadow,
        retained_active_root=retained,
    )

    assert active.is_dir()
    assert retained.is_dir()
    assert not shadow.exists()

    assert tree_sha(active) == new_sha
    assert tree_sha(retained) == old_sha

    assert (active / "chroma.sqlite3").read_bytes() == b"new-shadow"
    assert (retained / "chroma.sqlite3").read_bytes() == b"old-active"

    assert result.activated_tree_sha256 == new_sha
    assert result.retained_tree_sha256 == old_sha
    assert result.original_shadow_path_absent is True


def test_stale_active_tree_blocks_before_any_rename(
    tmp_path: Path,
) -> None:
    workspace, active, shadow, retained = make_workspace(tmp_path)
    plan = make_plan(active=active, shadow=shadow)

    (active / "segment.bin").write_bytes(b"changed")

    with pytest.raises(
        DisposableOfflineCutoverError,
        match=DisposableOfflineCutoverBlocker.ACTIVE_TREE_MISMATCH.value,
    ):
        execute_disposable_offline_cutover(
            plan=plan,
            workspace_root=workspace,
            active_db_root=active,
            shadow_db_root=shadow,
            retained_active_root=retained,
        )

    assert active.exists()
    assert shadow.exists()
    assert not retained.exists()


def test_stale_shadow_tree_blocks_before_any_rename(
    tmp_path: Path,
) -> None:
    workspace, active, shadow, retained = make_workspace(tmp_path)
    plan = make_plan(active=active, shadow=shadow)

    (shadow / "segment.bin").write_bytes(b"changed")

    with pytest.raises(
        DisposableOfflineCutoverError,
        match=DisposableOfflineCutoverBlocker.SHADOW_TREE_MISMATCH.value,
    ):
        execute_disposable_offline_cutover(
            plan=plan,
            workspace_root=workspace,
            active_db_root=active,
            shadow_db_root=shadow,
            retained_active_root=retained,
        )

    assert active.exists()
    assert shadow.exists()
    assert not retained.exists()


def test_existing_retained_slot_blocks_before_mutation(
    tmp_path: Path,
) -> None:
    workspace, active, shadow, retained = make_workspace(tmp_path)
    plan = make_plan(active=active, shadow=shadow)

    retained.mkdir()
    (retained / "do-not-touch").write_bytes(b"x")

    with pytest.raises(
        DisposableOfflineCutoverError,
        match=DisposableOfflineCutoverBlocker.RETAINED_SLOT_OCCUPIED.value,
    ):
        execute_disposable_offline_cutover(
            plan=plan,
            workspace_root=workspace,
            active_db_root=active,
            shadow_db_root=shadow,
            retained_active_root=retained,
        )

    assert (retained / "do-not-touch").read_bytes() == b"x"
    assert active.exists()
    assert shadow.exists()


def test_workspace_requires_explicit_disposable_marker(
    tmp_path: Path,
) -> None:
    workspace, active, shadow, retained = make_workspace(tmp_path)
    plan = make_plan(active=active, shadow=shadow)

    (workspace / MARKER).unlink()

    with pytest.raises(
        DisposableOfflineCutoverError,
        match=DisposableOfflineCutoverBlocker.WORKSPACE_MARKER_INVALID.value,
    ):
        execute_disposable_offline_cutover(
            plan=plan,
            workspace_root=workspace,
            active_db_root=active,
            shadow_db_root=shadow,
            retained_active_root=retained,
        )


def test_workspace_must_be_under_os_temp_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, active, shadow, retained = make_workspace(tmp_path)
    plan = make_plan(active=active, shadow=shadow)

    fake_temp = tmp_path / "different-temp-root"
    fake_temp.mkdir()

    monkeypatch.setattr(
        execution.tempfile,
        "gettempdir",
        lambda: str(fake_temp),
    )

    with pytest.raises(
        DisposableOfflineCutoverError,
        match=DisposableOfflineCutoverBlocker.WORKSPACE_NOT_DISPOSABLE.value,
    ):
        execute_disposable_offline_cutover(
            plan=plan,
            workspace_root=workspace,
            active_db_root=active,
            shadow_db_root=shadow,
            retained_active_root=retained,
        )


def test_protected_tree_overlap_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_project = tmp_path / "fake-project"
    fake_project.mkdir()

    workspace = fake_project / "db" / "workspace"
    workspace.mkdir(parents=True)

    (workspace / MARKER).write_bytes(MARKER_BYTES)

    active = workspace / "active"
    shadow = workspace / "shadow"
    retained = workspace / "retained"

    active.mkdir()
    shadow.mkdir()

    (active / "x").write_bytes(b"old")
    (shadow / "x").write_bytes(b"new")

    monkeypatch.setattr(
        execution,
        "_project_root",
        lambda: fake_project,
    )

    plan = make_plan(active=active, shadow=shadow)

    with pytest.raises(
        DisposableOfflineCutoverError,
        match=DisposableOfflineCutoverBlocker.PROTECTED_PATH.value,
    ):
        execute_disposable_offline_cutover(
            plan=plan,
            workspace_root=workspace,
            active_db_root=active,
            shadow_db_root=shadow,
            retained_active_root=retained,
        )

    assert active.exists()
    assert shadow.exists()
    assert not retained.exists()


def test_mutable_slots_must_be_direct_workspace_children(
    tmp_path: Path,
) -> None:
    workspace, active, shadow, retained = make_workspace(tmp_path)
    plan = make_plan(active=active, shadow=shadow)

    nested = workspace / "nested"
    nested.mkdir()

    bad_retained = nested / "retained"

    with pytest.raises(
        DisposableOfflineCutoverError,
        match=DisposableOfflineCutoverBlocker.PATH_RELATION_INVALID.value,
    ):
        execute_disposable_offline_cutover(
            plan=plan,
            workspace_root=workspace,
            active_db_root=active,
            shadow_db_root=shadow,
            retained_active_root=bad_retained,
        )

    assert not retained.exists()


def test_link_like_workspace_is_rejected(
    tmp_path: Path,
) -> None:
    real_workspace, active, shadow, retained = make_workspace(tmp_path)

    link = tmp_path / "workspace-link"

    try:
        link.symlink_to(
            real_workspace,
            target_is_directory=True,
        )
    except OSError as exc:
        pytest.skip(f"symbolic-link privilege unavailable: {exc}")

    plan = make_plan(active=active, shadow=shadow)

    with pytest.raises(
        DisposableOfflineCutoverError,
        match=DisposableOfflineCutoverBlocker.WORKSPACE_UNSAFE.value,
    ):
        execute_disposable_offline_cutover(
            plan=plan,
            workspace_root=link,
            active_db_root=link / "active",
            shadow_db_root=link / "shadow",
            retained_active_root=link / "retained",
        )


def test_second_rename_failure_restores_original_layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, active, shadow, retained = make_workspace(tmp_path)
    plan = make_plan(active=active, shadow=shadow)

    old_sha = tree_sha(active)
    new_sha = tree_sha(shadow)

    real_replace = os.replace
    calls = 0

    def fail_second_replace(
        source: str | bytes | Path,
        destination: str | bytes | Path,
    ) -> None:
        nonlocal calls
        calls += 1

        if calls == 2:
            raise OSError("injected activation failure")

        real_replace(source, destination)

    monkeypatch.setattr(
        execution.os,
        "replace",
        fail_second_replace,
    )

    with pytest.raises(
        DisposableOfflineCutoverError,
        match=DisposableOfflineCutoverBlocker.ACTIVATE_FAILED.value,
    ):
        execute_disposable_offline_cutover(
            plan=plan,
            workspace_root=workspace,
            active_db_root=active,
            shadow_db_root=shadow,
            retained_active_root=retained,
        )

    assert tree_sha(active) == old_sha
    assert tree_sha(shadow) == new_sha
    assert not retained.exists()


def test_invalid_plan_type_fails_closed(
    tmp_path: Path,
) -> None:
    workspace, active, shadow, retained = make_workspace(tmp_path)

    with pytest.raises(
        DisposableOfflineCutoverError,
        match=DisposableOfflineCutoverBlocker.PLAN_INVALID.value,
    ):
        execute_disposable_offline_cutover(
            plan=object(),  # type: ignore[arg-type]
            workspace_root=workspace,
            active_db_root=active,
            shadow_db_root=shadow,
            retained_active_root=retained,
        )


def test_m2_has_no_chroma_or_production_lock_capability() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "source_evidence"
        / "offline_cutover_execution.py"
    )

    text = path.read_text(encoding="utf-8")

    for token in (
        "import chromadb",
        "PersistentClient",
        "ChromaWriterLock",
        "get_collection(",
        "get_or_create_collection(",
    ):
        assert token not in text


def test_public_api_is_explicitly_disposable_only() -> None:
    assert execution.__all__ == [
        "DisposableOfflineCutoverBlocker",
        "DisposableOfflineCutoverError",
        "DisposableOfflineCutoverResult",
        "execute_disposable_offline_cutover",
    ]

    assert not hasattr(execution, "execute_offline_cutover")
    assert not hasattr(execution, "activate_production")
    assert not hasattr(execution, "retire_legacy")
