from __future__ import annotations

import hashlib
import multiprocessing as mp
import os
import time
from pathlib import Path

import pytest

from source_evidence.chroma_lock import (
    ChromaWriterLock,
    ChromaWriterLockError,
    ChromaWriterLockTimeout,
)

TENANT = "default_tenant"
DATABASE = "default_database"
COLLECTION = "legal_documents"


def _make_lock(db_path: Path, **kwargs) -> ChromaWriterLock:
    return ChromaWriterLock(
        db_path=db_path,
        tenant=TENANT,
        database=DATABASE,
        collection_name=COLLECTION,
        **kwargs,
    )


def _holding_worker(db_path: str, ready, release) -> None:
    lock = _make_lock(Path(db_path), timeout_seconds=5.0, poll_interval_seconds=0.02)
    with lock:
        ready.set()
        release.wait(10)


def test_constructor_is_side_effect_free_and_key_is_deterministic(tmp_path: Path) -> None:
    db_path = tmp_path / "db"
    first = _make_lock(db_path)
    second = _make_lock(db_path)

    canonical = db_path.resolve(strict=False)
    payload = "\0".join(
        (
            "legalrag-pro/chroma-writer-lock/1.0",
            os.path.normcase(str(canonical)),
            TENANT,
            DATABASE,
            COLLECTION,
        )
    ).encode("utf-8")
    expected = hashlib.sha256(payload).hexdigest()

    assert first.lock_key == second.lock_key == expected
    assert first.lock_path == canonical / ".legalrag-locks" / f"{expected}.lock"
    assert not db_path.exists()


def test_different_resource_components_produce_different_keys(tmp_path: Path) -> None:
    baseline = _make_lock(tmp_path / "db")
    assert baseline.lock_key != ChromaWriterLock(
        db_path=tmp_path / "db-2",
        tenant=TENANT,
        database=DATABASE,
        collection_name=COLLECTION,
    ).lock_key
    assert baseline.lock_key != ChromaWriterLock(
        db_path=tmp_path / "db",
        tenant="other_tenant",
        database=DATABASE,
        collection_name=COLLECTION,
    ).lock_key
    assert baseline.lock_key != ChromaWriterLock(
        db_path=tmp_path / "db",
        tenant=TENANT,
        database="other_database",
        collection_name=COLLECTION,
    ).lock_key
    assert baseline.lock_key != ChromaWriterLock(
        db_path=tmp_path / "db",
        tenant=TENANT,
        database=DATABASE,
        collection_name="other_collection",
    ).lock_key


def test_acquire_creates_one_byte_persistent_file_and_release_allows_reacquire(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "db"
    first = _make_lock(db_path)
    with first:
        assert first.lock_path.is_file()
        assert first.lock_path.stat().st_size >= 1

    assert first.lock_path.is_file()
    with _make_lock(db_path, timeout_seconds=0.5, poll_interval_seconds=0.01):
        pass
    assert first.lock_path.is_file()


def test_lock_object_is_single_use(tmp_path: Path) -> None:
    lock = _make_lock(tmp_path / "db")
    lock.acquire()
    lock.release()
    with pytest.raises(ChromaWriterLockError):
        lock.acquire()
    with pytest.raises(ChromaWriterLockError):
        lock.release()


def test_same_process_second_descriptor_times_out(tmp_path: Path) -> None:
    db_path = tmp_path / "db"
    with _make_lock(db_path):
        started = time.monotonic()
        with pytest.raises(ChromaWriterLockTimeout):
            _make_lock(
                db_path,
                timeout_seconds=0.15,
                poll_interval_seconds=0.02,
            ).acquire()
        elapsed = time.monotonic() - started
        assert elapsed >= 0.12
        assert elapsed < 1.0


def test_context_exception_releases_lock(tmp_path: Path) -> None:
    db_path = tmp_path / "db"
    with pytest.raises(RuntimeError):
        with _make_lock(db_path):
            raise RuntimeError("controlled")

    with _make_lock(db_path, timeout_seconds=0.5, poll_interval_seconds=0.01):
        pass


def test_cross_process_exclusion_and_normal_release(tmp_path: Path) -> None:
    ctx = mp.get_context("spawn")
    ready = ctx.Event()
    release = ctx.Event()
    process = ctx.Process(target=_holding_worker, args=(str(tmp_path / "db"), ready, release))
    process.start()
    try:
        assert ready.wait(10)
        with pytest.raises(ChromaWriterLockTimeout):
            _make_lock(
                tmp_path / "db",
                timeout_seconds=0.2,
                poll_interval_seconds=0.02,
            ).acquire()
        release.set()
        process.join(10)
        assert process.exitcode == 0
        with _make_lock(tmp_path / "db", timeout_seconds=1.0, poll_interval_seconds=0.02):
            pass
    finally:
        release.set()
        if process.is_alive():
            process.terminate()
        process.join(5)


def test_forced_process_death_releases_os_lock_without_deleting_file(tmp_path: Path) -> None:
    ctx = mp.get_context("spawn")
    ready = ctx.Event()
    release = ctx.Event()
    db_path = tmp_path / "db"
    process = ctx.Process(target=_holding_worker, args=(str(db_path), ready, release))
    process.start()
    assert ready.wait(10)
    lock_path = _make_lock(db_path).lock_path
    assert lock_path.exists()

    process.terminate()
    process.join(10)
    assert process.exitcode is not None
    assert lock_path.exists()

    with _make_lock(db_path, timeout_seconds=2.0, poll_interval_seconds=0.02):
        pass
    assert lock_path.exists()


def test_old_lock_file_is_reused_not_deleted(tmp_path: Path) -> None:
    db_path = tmp_path / "db"
    lock = _make_lock(db_path)
    with lock:
        pass
    old_inode = lock.lock_path.stat().st_ino
    old_time = time.time() - 30 * 24 * 60 * 60
    os.utime(lock.lock_path, (old_time, old_time))

    with _make_lock(db_path):
        assert lock.lock_path.stat().st_ino == old_inode


def test_symlink_lock_directory_escape_is_rejected_where_supported(tmp_path: Path) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symbolic links unavailable")
    db_path = tmp_path / "db"
    outside = tmp_path / "outside"
    db_path.mkdir()
    outside.mkdir()
    link = db_path / ".legalrag-locks"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symbolic-link privilege unavailable: {exc}")

    with pytest.raises(ChromaWriterLockError):
        _make_lock(db_path).acquire()
    assert not list(outside.iterdir())


def test_symlink_lock_file_is_rejected_where_supported(tmp_path: Path) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symbolic links unavailable")
    lock = _make_lock(tmp_path / "db")
    lock.lock_path.parent.mkdir(parents=True)
    outside = tmp_path / "outside-file"
    outside.write_bytes(b"x")
    try:
        os.symlink(outside, lock.lock_path)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symbolic-link privilege unavailable: {exc}")

    with pytest.raises(ChromaWriterLockError):
        lock.acquire()
    assert outside.read_bytes() == b"x"


def test_invalid_lock_configuration_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ChromaWriterLock(
            db_path=tmp_path / "db",
            tenant="",
            database=DATABASE,
            collection_name=COLLECTION,
        )
    with pytest.raises(ValueError):
        _make_lock(tmp_path / "db", timeout_seconds=-1)
    with pytest.raises(ValueError):
        _make_lock(tmp_path / "db", poll_interval_seconds=0)
