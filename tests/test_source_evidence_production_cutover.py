from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

import source_evidence.production_cutover as cutover
from source_evidence.chroma_lock import (
    ChromaWriterLockError,
)
from source_evidence.offline_cutover import (
    OFFLINE_CUTOVER_PLAN_SCHEMA_VERSION,
    OfflineCutoverPlan,
)
from source_evidence.production_cutover import (
    PRODUCTION_CUTOVER_PERMIT_SCHEMA_VERSION,
    ProductionCutoverBlocker,
    ProductionCutoverError,
    ProductionCutoverPermit,
    ProductionCutoverPermitKind,
    execute_production_cutover,
)
from source_evidence.production_shadow_build import (
    _build_tree_manifest,
)


CASE_ID = (
    "8081166d-9889-40bb-8add-5d0893037ff0"
)

ROW_IDS = (
    "prospective-row-1",
    "prospective-row-2",
)


def sha(
    char: str,
) -> str:
    return "sha256:" + char * 64


def tree_sha(
    path: Path,
) -> str:
    return _build_tree_manifest(
        path,
        require_exists=True,
    ).tree_sha256


def write_old_db(
    root: Path,
) -> None:
    root.mkdir()

    (
        root
        / "chroma.sqlite3"
    ).write_bytes(
        b"old-active"
    )

    (
        root
        / "segment.bin"
    ).write_bytes(
        b"old-segment"
    )


def write_new_db(
    root: Path,
) -> None:
    root.mkdir()

    (
        root
        / "chroma.sqlite3"
    ).write_bytes(
        b"new-shadow"
    )

    (
        root
        / "segment.bin"
    ).write_bytes(
        b"new-segment"
    )


def make_layout(
    tmp_path: Path,
):
    production = (
        tmp_path
        / "production"
    )
    production.mkdir()

    active = (
        production
        / "db"
    )
    write_old_db(
        active
    )

    source_store = (
        production
        / "source_evidence_store"
        / "v1"
    )
    source_store.mkdir(
        parents=True
    )

    (
        source_store
        / "immutable.bin"
    ).write_bytes(
        b"source-store"
    )

    cutover_root = (
        tmp_path
        / "cutover"
    )
    cutover_root.mkdir()

    candidate = (
        cutover_root
        / "candidate"
    )
    write_new_db(
        candidate
    )

    retained = (
        cutover_root
        / "retained"
    )

    quarantine = (
        cutover_root
        / "quarantine"
    )

    control = (
        tmp_path
        / "control"
    )
    control.mkdir()

    sealed_root = (
        tmp_path
        / "sealed"
    )
    sealed_root.mkdir()

    sealed_shadow = (
        sealed_root
        / "shadow"
    )
    write_new_db(
        sealed_shadow
    )

    verified_backup = (
        sealed_root
        / "backup"
    )
    write_old_db(
        verified_backup
    )

    active_sha = tree_sha(
        active
    )

    candidate_sha = tree_sha(
        candidate
    )

    assert (
        tree_sha(
            sealed_shadow
        )
        == candidate_sha
    )

    assert (
        tree_sha(
            verified_backup
        )
        == active_sha
    )

    plan = OfflineCutoverPlan(
        schema_version=(
            OFFLINE_CUTOVER_PLAN_SCHEMA_VERSION
        ),
        case_id=CASE_ID,
        production_shadow_build_report_id=(
            sha("1")
        ),
        active_db_pre_tree_sha256=(
            active_sha
        ),
        active_db_backup_tree_sha256=(
            active_sha
        ),
        source_store_post_tree_sha256=(
            tree_sha(
                source_store
            )
        ),
        shadow_tree_sha256=(
            candidate_sha
        ),
        expected_shadow_row_count=2,
    )

    return {
        "production": production,
        "active": active,
        "source_store": source_store,
        "candidate": candidate,
        "retained": retained,
        "quarantine": quarantine,
        "control": control,
        "sealed_shadow": sealed_shadow,
        "verified_backup": verified_backup,
        "plan": plan,
        "old_sha": active_sha,
        "new_sha": candidate_sha,
    }


def make_permit(
    layout,
    *,
    kind: ProductionCutoverPermitKind = (
        ProductionCutoverPermitKind.DISPOSABLE_TEST
    ),
) -> ProductionCutoverPermit:
    return ProductionCutoverPermit(
        schema_version=(
            PRODUCTION_CUTOVER_PERMIT_SCHEMA_VERSION
        ),
        kind=kind,
        case_id=CASE_ID,
        production_shadow_build_report_id=(
            layout[
                "plan"
            ].production_shadow_build_report_id
        ),
        production_root=str(
            layout[
                "production"
            ].resolve()
        ),
    )


def kwargs_for(
    layout,
    *,
    permit: ProductionCutoverPermit | None = None,
):
    return {
        "plan":
            layout["plan"],

        "permit":
            permit
            or make_permit(
                layout
            ),

        "production_root":
            layout["production"],

        "active_db_root":
            layout["active"],

        "candidate_db_root":
            layout["candidate"],

        "retained_active_root":
            layout["retained"],

        "failed_candidate_quarantine_root":
            layout["quarantine"],

        "external_control_root":
            layout["control"],

        "sealed_shadow_root":
            layout["sealed_shadow"],

        "verified_backup_root":
            layout["verified_backup"],

        "source_store_root":
            layout["source_store"],

        "expected_row_ids":
            ROW_IDS,
    }


def good_inspection():
    return cutover._LogicalInspection(
        collection_count=2,
        ids=ROW_IDS,
        metadata_count=2,
        missing_source_bound_count=0,
    )


def bad_inspection():
    return cutover._LogicalInspection(
        collection_count=1,
        ids=(ROW_IDS[0],),
        metadata_count=1,
        missing_source_bound_count=0,
    )


@pytest.fixture
def offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cutover,
        "_active_runtime_processes",
        lambda: (),
    )


def test_disposable_success_retains_old_active_and_exact_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    offline,
) -> None:
    layout = make_layout(
        tmp_path
    )

    monkeypatch.setattr(
        cutover,
        "_inspect_active_collection",
        lambda db_root: good_inspection(),
    )

    result = execute_production_cutover(
        **kwargs_for(
            layout
        )
    )

    assert (
        layout[
            "active"
        ]
        / "chroma.sqlite3"
    ).read_bytes() == b"new-shadow"

    assert (
        layout[
            "retained"
        ]
        / "chroma.sqlite3"
    ).read_bytes() == b"old-active"

    assert not layout[
        "candidate"
    ].exists()

    assert not layout[
        "quarantine"
    ].exists()

    assert (
        tree_sha(
            layout[
                "retained"
            ]
        )
        == layout[
            "old_sha"
        ]
    )

    assert (
        tree_sha(
            layout[
                "sealed_shadow"
            ]
        )
        == layout[
            "new_sha"
        ]
    )

    assert (
        tree_sha(
            layout[
                "verified_backup"
            ]
        )
        == layout[
            "old_sha"
        ]
    )

    assert result.expected_row_count == 2
    assert result.collection_count == 2
    assert result.unique_id_count == 2
    assert result.metadata_count == 2

    assert (
        result.missing_source_bound_count
        == 0
    )

    assert (
        result.exact_row_set_verified
        is True
    )

    assert (
        result.candidate_path_absent
        is True
    )

    assert (
        result.quarantine_path_absent
        is True
    )

    assert Path(
        result.external_mutex_path
    ).is_file()

    assert Path(
        result.writer_lock_path
    ).is_file()


def test_active_tree_drift_blocks_before_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    offline,
) -> None:
    layout = make_layout(
        tmp_path
    )

    (
        layout["active"]
        / "segment.bin"
    ).write_bytes(
        b"drift"
    )

    monkeypatch.setattr(
        cutover,
        "_inspect_active_collection",
        lambda db_root: good_inspection(),
    )

    with pytest.raises(
        ProductionCutoverError,
        match=(
            ProductionCutoverBlocker
            .ACTIVE_TREE_MISMATCH
            .value
        ),
    ):
        execute_production_cutover(
            **kwargs_for(
                layout
            )
        )

    assert layout[
        "active"
    ].exists()

    assert layout[
        "candidate"
    ].exists()

    assert not layout[
        "retained"
    ].exists()


def test_candidate_drift_blocks_before_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    offline,
) -> None:
    layout = make_layout(
        tmp_path
    )

    (
        layout["candidate"]
        / "segment.bin"
    ).write_bytes(
        b"drift"
    )

    monkeypatch.setattr(
        cutover,
        "_inspect_active_collection",
        lambda db_root: good_inspection(),
    )

    with pytest.raises(
        ProductionCutoverError,
        match=(
            ProductionCutoverBlocker
            .CANDIDATE_TREE_MISMATCH
            .value
        ),
    ):
        execute_production_cutover(
            **kwargs_for(
                layout
            )
        )

    assert layout[
        "active"
    ].exists()

    assert layout[
        "candidate"
    ].exists()

    assert not layout[
        "retained"
    ].exists()


def test_sealed_shadow_is_never_consumed_or_modified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    offline,
) -> None:
    layout = make_layout(
        tmp_path
    )

    before = tree_sha(
        layout[
            "sealed_shadow"
        ]
    )

    monkeypatch.setattr(
        cutover,
        "_inspect_active_collection",
        lambda db_root: good_inspection(),
    )

    execute_production_cutover(
        **kwargs_for(
            layout
        )
    )

    assert layout[
        "sealed_shadow"
    ].is_dir()

    assert (
        tree_sha(
            layout[
                "sealed_shadow"
            ]
        )
        == before
    )


def test_verified_backup_is_never_consumed_or_modified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    offline,
) -> None:
    layout = make_layout(
        tmp_path
    )

    before = tree_sha(
        layout[
            "verified_backup"
        ]
    )

    monkeypatch.setattr(
        cutover,
        "_inspect_active_collection",
        lambda db_root: good_inspection(),
    )

    execute_production_cutover(
        **kwargs_for(
            layout
        )
    )

    assert layout[
        "verified_backup"
    ].is_dir()

    assert (
        tree_sha(
            layout[
                "verified_backup"
            ]
        )
        == before
    )


def test_source_store_drift_blocks_before_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    offline,
) -> None:
    layout = make_layout(
        tmp_path
    )

    (
        layout["source_store"]
        / "immutable.bin"
    ).write_bytes(
        b"changed"
    )

    monkeypatch.setattr(
        cutover,
        "_inspect_active_collection",
        lambda db_root: good_inspection(),
    )

    with pytest.raises(
        ProductionCutoverError,
        match=(
            ProductionCutoverBlocker
            .SOURCE_STORE_TREE_MISMATCH
            .value
        ),
    ):
        execute_production_cutover(
            **kwargs_for(
                layout
            )
        )

    assert layout[
        "active"
    ].exists()

    assert layout[
        "candidate"
    ].exists()


def test_active_runtime_blocks_before_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    layout = make_layout(
        tmp_path
    )

    monkeypatch.setattr(
        cutover,
        "_active_runtime_processes",
        lambda: (
            "PID=999 Name=python.exe",
        ),
    )

    with pytest.raises(
        ProductionCutoverError,
        match=(
            ProductionCutoverBlocker
            .PROCESS_ACTIVE
            .value
        ),
    ):
        execute_production_cutover(
            **kwargs_for(
                layout
            )
        )

    assert (
        tree_sha(
            layout["active"]
        )
        == layout["old_sha"]
    )

    assert (
        tree_sha(
            layout["candidate"]
        )
        == layout["new_sha"]
    )

    assert not layout[
        "retained"
    ].exists()


def test_process_appearing_after_activation_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    layout = make_layout(
        tmp_path
    )

    states = iter(
        (
            (),
            (),
            (
                "PID=999 "
                "Name=python.exe",
            ),
        )
    )

    monkeypatch.setattr(
        cutover,
        "_active_runtime_processes",
        lambda: next(states),
    )

    monkeypatch.setattr(
        cutover,
        "_inspect_active_collection",
        lambda db_root: good_inspection(),
    )

    with pytest.raises(
        ProductionCutoverError,
        match=(
            ProductionCutoverBlocker
            .PROCESS_ACTIVE
            .value
        ),
    ):
        execute_production_cutover(
            **kwargs_for(
                layout
            )
        )

    assert (
        tree_sha(
            layout["active"]
        )
        == layout["old_sha"]
    )

    assert not layout[
        "retained"
    ].exists()

    assert layout[
        "quarantine"
    ].is_dir()

    assert (
        layout[
            "quarantine"
        ]
        / "chroma.sqlite3"
    ).read_bytes() == b"new-shadow"


def test_second_rename_failure_restores_original_layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    offline,
) -> None:
    layout = make_layout(
        tmp_path
    )

    real_replace = os.replace
    calls = 0

    def fail_second_replace(
        source,
        destination,
    ):
        nonlocal calls

        calls += 1

        if calls == 2:
            raise OSError(
                "injected activation failure"
            )

        real_replace(
            source,
            destination,
        )

    monkeypatch.setattr(
        cutover.os,
        "replace",
        fail_second_replace,
    )

    monkeypatch.setattr(
        cutover,
        "_inspect_active_collection",
        lambda db_root: good_inspection(),
    )

    with pytest.raises(
        ProductionCutoverError,
        match=(
            ProductionCutoverBlocker
            .ACTIVATE_FAILED
            .value
        ),
    ):
        execute_production_cutover(
            **kwargs_for(
                layout
            )
        )

    assert (
        tree_sha(
            layout["active"]
        )
        == layout["old_sha"]
    )

    assert (
        tree_sha(
            layout["candidate"]
        )
        == layout["new_sha"]
    )

    assert not layout[
        "retained"
    ].exists()

    assert not layout[
        "quarantine"
    ].exists()


def test_logical_failure_quarantines_candidate_and_restores_old_active(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    offline,
) -> None:
    layout = make_layout(
        tmp_path
    )

    monkeypatch.setattr(
        cutover,
        "_inspect_active_collection",
        lambda db_root: bad_inspection(),
    )

    with pytest.raises(
        ProductionCutoverError,
        match=(
            ProductionCutoverBlocker
            .LOGICAL_VERIFY_FAILED
            .value
        ),
    ):
        execute_production_cutover(
            **kwargs_for(
                layout
            )
        )

    assert (
        tree_sha(
            layout["active"]
        )
        == layout["old_sha"]
    )

    assert not layout[
        "retained"
    ].exists()

    assert not layout[
        "candidate"
    ].exists()

    assert (
        layout[
            "quarantine"
        ]
        / "chroma.sqlite3"
    ).read_bytes() == b"new-shadow"


def test_writer_lock_failure_quarantines_and_restores(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    offline,
) -> None:
    layout = make_layout(
        tmp_path
    )

    monkeypatch.setattr(
        cutover,
        "_inspect_active_collection",
        lambda db_root: good_inspection(),
    )

    class FailingWriterLock:
        def __init__(
            self,
            **kwargs,
        ) -> None:
            pass

        def __enter__(
            self,
        ):
            raise ChromaWriterLockError(
                "injected"
            )

        def __exit__(
            self,
            exc_type,
            exc,
            traceback,
        ) -> None:
            pass

    monkeypatch.setattr(
        cutover,
        "ChromaWriterLock",
        FailingWriterLock,
    )

    with pytest.raises(
        ProductionCutoverError,
        match=(
            ProductionCutoverBlocker
            .WRITER_LOCK_FAILED
            .value
        ),
    ):
        execute_production_cutover(
            **kwargs_for(
                layout
            )
        )

    assert (
        tree_sha(
            layout["active"]
        )
        == layout["old_sha"]
    )

    assert layout[
        "quarantine"
    ].is_dir()


def test_final_logical_failure_quarantines_and_restores(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    offline,
) -> None:
    layout = make_layout(
        tmp_path
    )

    calls = 0

    def inspect(
        db_root,
    ):
        nonlocal calls
        calls += 1

        if calls == 1:
            return good_inspection()

        return bad_inspection()

    monkeypatch.setattr(
        cutover,
        "_inspect_active_collection",
        inspect,
    )

    with pytest.raises(
        ProductionCutoverError,
        match=(
            ProductionCutoverBlocker
            .FINAL_VERIFY_FAILED
            .value
        ),
    ):
        execute_production_cutover(
            **kwargs_for(
                layout
            )
        )

    assert (
        tree_sha(
            layout["active"]
        )
        == layout["old_sha"]
    )

    assert layout[
        "quarantine"
    ].is_dir()

    assert (
        layout[
            "quarantine"
        ]
        / ".legalrag-locks"
    ).is_dir()


def test_occupied_retained_slot_blocks_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    offline,
) -> None:
    layout = make_layout(
        tmp_path
    )

    layout[
        "retained"
    ].mkdir()

    (
        layout["retained"]
        / "preserve"
    ).write_bytes(
        b"x"
    )

    monkeypatch.setattr(
        cutover,
        "_inspect_active_collection",
        lambda db_root: good_inspection(),
    )

    with pytest.raises(
        ProductionCutoverError,
        match=(
            ProductionCutoverBlocker
            .RETAINED_SLOT_OCCUPIED
            .value
        ),
    ):
        execute_production_cutover(
            **kwargs_for(
                layout
            )
        )

    assert (
        layout["retained"]
        / "preserve"
    ).read_bytes() == b"x"

    assert (
        tree_sha(
            layout["active"]
        )
        == layout["old_sha"]
    )


def test_candidate_cannot_be_the_sealed_shadow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    offline,
) -> None:
    layout = make_layout(
        tmp_path
    )

    monkeypatch.setattr(
        cutover,
        "_inspect_active_collection",
        lambda db_root: good_inspection(),
    )

    args = kwargs_for(
        layout
    )

    args[
        "candidate_db_root"
    ] = layout[
        "sealed_shadow"
    ]

    with pytest.raises(
        ProductionCutoverError,
        match=(
            ProductionCutoverBlocker
            .PATH_OVERLAP
            .value
        ),
    ):
        execute_production_cutover(
            **args
        )

    assert (
        tree_sha(
            layout["active"]
        )
        == layout["old_sha"]
    )

    assert layout[
        "sealed_shadow"
    ].is_dir()


def test_expected_row_ids_must_match_plan_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    offline,
) -> None:
    layout = make_layout(
        tmp_path
    )

    monkeypatch.setattr(
        cutover,
        "_inspect_active_collection",
        lambda db_root: good_inspection(),
    )

    args = kwargs_for(
        layout
    )

    args[
        "expected_row_ids"
    ] = (
        ROW_IDS[0],
    )

    with pytest.raises(
        ProductionCutoverError,
        match=(
            ProductionCutoverBlocker
            .PERMIT_INVALID
            .value
        ),
    ):
        execute_production_cutover(
            **args
        )

    assert (
        tree_sha(
            layout["active"]
        )
        == layout["old_sha"]
    )


def test_production_permit_rejects_os_temp_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    offline,
) -> None:
    layout = make_layout(
        tmp_path
    )

    monkeypatch.setattr(
        cutover,
        "_inspect_active_collection",
        lambda db_root: good_inspection(),
    )

    permit = make_permit(
        layout,
        kind=(
            ProductionCutoverPermitKind.PRODUCTION
        ),
    )

    with pytest.raises(
        ProductionCutoverError,
        match=(
            ProductionCutoverBlocker
            .PERMIT_SCOPE_INVALID
            .value
        ),
    ):
        execute_production_cutover(
            **kwargs_for(
                layout,
                permit=permit,
            )
        )


def test_production_permit_code_path_is_testable_only_on_disposable_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    offline,
) -> None:
    layout = make_layout(
        tmp_path
    )

    #
    # Pretend a different directory is the OS temp root so this
    # fixture exercises the PRODUCTION permit branch while all
    # actual filesystem activity remains under pytest tmp_path.
    #
    declared_temp = (
        tmp_path
        / "declared-os-temp"
    )
    declared_temp.mkdir()

    monkeypatch.setattr(
        cutover.tempfile,
        "gettempdir",
        lambda: str(
            declared_temp
        ),
    )

    monkeypatch.setattr(
        cutover,
        "_inspect_active_collection",
        lambda db_root: good_inspection(),
    )

    permit = make_permit(
        layout,
        kind=(
            ProductionCutoverPermitKind.PRODUCTION
        ),
    )

    result = execute_production_cutover(
        **kwargs_for(
            layout,
            permit=permit,
        )
    )

    assert (
        result.exact_row_set_verified
        is True
    )

    assert (
        tree_sha(
            layout["retained"]
        )
        == layout["old_sha"]
    )


def test_volume_mismatch_blocks_before_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    offline,
) -> None:
    layout = make_layout(
        tmp_path
    )

    monkeypatch.setattr(
        cutover,
        "_same_volume",
        lambda paths: False,
    )

    monkeypatch.setattr(
        cutover,
        "_inspect_active_collection",
        lambda db_root: good_inspection(),
    )

    with pytest.raises(
        ProductionCutoverError,
        match=(
            ProductionCutoverBlocker
            .VOLUME_MISMATCH
            .value
        ),
    ):
        execute_production_cutover(
            **kwargs_for(
                layout
            )
        )

    assert (
        tree_sha(
            layout["active"]
        )
        == layout["old_sha"]
    )

    assert layout[
        "candidate"
    ].exists()


def test_module_contains_no_retirement_or_destructive_cleanup_api() -> None:
    path = (
        Path(__file__)
        .resolve()
        .parents[1]
        / "src"
        / "source_evidence"
        / "production_cutover.py"
    )

    text = path.read_text(
        encoding="utf-8"
    )

    tree = ast.parse(
        text
    )

    destructive = set()

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.Call,
        ):
            if isinstance(
                node.func,
                ast.Attribute,
            ):
                if node.func.attr in {
                    "unlink",
                    "rmdir",
                    "remove",
                    "removedirs",
                    "rmtree",
                }:
                    destructive.add(
                        node.func.attr
                    )

    assert not destructive

    for forbidden in (
        "collection.delete(",
        "collection.update(",
        "collection.upsert(",
        "collection.add(",
        "retire_legacy(",
        "execute_hm2(",
    ):
        assert forbidden not in text


def test_public_api_is_exact() -> None:
    assert cutover.__all__ == [
        "PRODUCTION_CUTOVER_PERMIT_SCHEMA_VERSION",
        "ProductionCutoverPermitKind",
        "ProductionCutoverPermit",
        "ProductionCutoverBlocker",
        "ProductionCutoverError",
        "ProductionCutoverResult",
        "execute_production_cutover",
    ]


def test_import_does_not_initialize_chromadb() -> None:
    src = (
        Path(__file__)
        .resolve()
        .parents[1]
        / "src"
    )

    code = (
        "import sys; "
        "import source_evidence.production_cutover; "
        "assert 'chromadb' not in sys.modules"
    )

    env = dict(
        os.environ
    )

    current = env.get(
        "PYTHONPATH"
    )

    env["PYTHONPATH"] = (
        str(src)
        if not current
        else (
            str(src)
            + os.pathsep
            + current
        )
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert (
        completed.returncode
        == 0
    ), completed.stderr
def test_verified_windows_controller_launcher_pid_accepts_exact_chain() -> None:
    launcher = (
        r"C:\repo\.venv\Scripts\python.exe"
    )
    base = (
        r"C:\Python\python.exe"
    )
    command = (
        f'"{launcher}" -'
    )

    items = (
        {
            "ProcessId": 200,
            "ParentProcessId": 100,
            "Name": "python.exe",
            "ExecutablePath": base,
            "CommandLine": command,
        },
        {
            "ProcessId": 100,
            "ParentProcessId": 50,
            "Name": "python.exe",
            "ExecutablePath": launcher,
            "CommandLine": command,
        },
    )

    assert (
        cutover
        ._verified_windows_controller_launcher_pid(
            items=items,
            current_pid=200,
            launcher_executable=launcher,
            base_executable=base,
        )
        == 100
    )


@pytest.mark.parametrize(
    (
        "current_executable",
        "parent_executable",
        "parent_command",
        "base_executable",
    ),
    (
        (
            r"C:\Python\other.exe",
            r"C:\repo\.venv\Scripts\python.exe",
            r'"C:\repo\.venv\Scripts\python.exe" -',
            r"C:\Python\python.exe",
        ),
        (
            r"C:\Python\python.exe",
            r"C:\other\python.exe",
            r'"C:\repo\.venv\Scripts\python.exe" -',
            r"C:\Python\python.exe",
        ),
        (
            r"C:\Python\python.exe",
            r"C:\repo\.venv\Scripts\python.exe",
            r'"C:\repo\.venv\Scripts\python.exe" other.py',
            r"C:\Python\python.exe",
        ),
        (
            r"C:\Python\python.exe",
            r"C:\repo\.venv\Scripts\python.exe",
            r'"C:\repo\.venv\Scripts\python.exe" -',
            r"C:\repo\.venv\Scripts\python.exe",
        ),
    ),
)
def test_verified_windows_controller_launcher_pid_rejects_unproven_parent(
    current_executable: str,
    parent_executable: str,
    parent_command: str,
    base_executable: str,
) -> None:
    launcher = (
        r"C:\repo\.venv\Scripts\python.exe"
    )
    command = (
        f'"{launcher}" -'
    )

    items = (
        {
            "ProcessId": 200,
            "ParentProcessId": 100,
            "Name": "python.exe",
            "ExecutablePath": current_executable,
            "CommandLine": command,
        },
        {
            "ProcessId": 100,
            "ParentProcessId": 50,
            "Name": "python.exe",
            "ExecutablePath": parent_executable,
            "CommandLine": parent_command,
        },
    )

    assert (
        cutover
        ._verified_windows_controller_launcher_pid(
            items=items,
            current_pid=200,
            launcher_executable=launcher,
            base_executable=base_executable,
        )
        is None
    )


def test_active_runtime_processes_filters_only_verified_controller_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launcher = (
        r"C:\repo\.venv\Scripts\python.exe"
    )
    base = (
        r"C:\Python\python.exe"
    )
    command = (
        f'"{launcher}" -'
    )

    payload = cutover.json.dumps(
        [
            {
                "ProcessId": 200,
                "ParentProcessId": 100,
                "Name": "python.exe",
                "ExecutablePath": base,
                "CommandLine": command,
            },
            {
                "ProcessId": 100,
                "ParentProcessId": 50,
                "Name": "python.exe",
                "ExecutablePath": launcher,
                "CommandLine": command,
            },
            {
                "ProcessId": 999,
                "ParentProcessId": 50,
                "Name": "python.exe",
                "ExecutablePath": (
                    r"C:\other\python.exe"
                ),
                "CommandLine": "external.py",
            },
        ]
    )

    monkeypatch.setattr(
        cutover.os,
        "name",
        "nt",
    )

    monkeypatch.setattr(
        cutover.os,
        "getpid",
        lambda: 200,
    )

    monkeypatch.setattr(
        cutover.sys,
        "executable",
        launcher,
    )

    monkeypatch.setattr(
        cutover.sys,
        "_base_executable",
        base,
    )

    monkeypatch.setattr(
        cutover.subprocess,
        "run",
        lambda *args, **kwargs: (
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=payload,
                stderr="",
            )
        ),
    )

    assert (
        cutover
        ._active_runtime_processes()
        == (
            (
                "PID=999 "
                "Name=python.exe "
                "Command=external.py"
            ),
        )
    )
