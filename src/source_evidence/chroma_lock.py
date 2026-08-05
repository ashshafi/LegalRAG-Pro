"""Cross-process writer lock for the governed embedded Chroma collection.

The persistent lock file is only the operating-system lock target. Its
existence, age, or contents never represent ownership.
"""

from __future__ import annotations

import errno
import os
import stat
import time
from pathlib import Path
from typing import Final

from .identity import sha256_bytes

_LOCK_NAMESPACE: Final[str] = "legalrag-pro/chroma-writer-lock/1.0"
_LOCK_DIRECTORY_NAME: Final[str] = ".legalrag-locks"
_LOCK_SUFFIX: Final[str] = ".lock"
_DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
_DEFAULT_POLL_INTERVAL_SECONDS: Final[float] = 0.1
_LOCK_BYTE_COUNT: Final[int] = 1


class ChromaWriterLockError(RuntimeError):
    """Raised when the governed Chroma writer lock cannot be trusted."""


class ChromaWriterLockTimeout(ChromaWriterLockError):
    """Raised when the governed writer lock is not acquired before its deadline."""


class ChromaWriterLock:
    """One-lifecycle OS-held lock for one Chroma database/collection resource."""

    def __init__(
        self,
        *,
        db_path: str | Path,
        tenant: str,
        database: str,
        collection_name: str,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        self._db_path = Path(db_path).expanduser().resolve(strict=False)
        self._tenant = self._required_text(tenant, field_name="tenant")
        self._database = self._required_text(database, field_name="database")
        self._collection_name = self._required_text(
            collection_name,
            field_name="collection_name",
        )
        self._timeout_seconds = self._nonnegative_float(
            timeout_seconds,
            field_name="timeout_seconds",
        )
        self._poll_interval_seconds = self._positive_float(
            poll_interval_seconds,
            field_name="poll_interval_seconds",
        )
        payload = "\0".join(
            (
                _LOCK_NAMESPACE,
                os.path.normcase(str(self._db_path)),
                self._tenant,
                self._database,
                self._collection_name,
            )
        ).encode("utf-8")
        self._lock_key = sha256_bytes(payload)
        self._lock_path = (
            self._db_path / _LOCK_DIRECTORY_NAME / f"{self._lock_key}{_LOCK_SUFFIX}"
        )
        self._file_descriptor: int | None = None
        self._started = False
        self._owned = False
        self._released = False

    @property
    def lock_key(self) -> str:
        """Return the deterministic lowercase lock-resource SHA-256."""

        return self._lock_key

    @property
    def lock_path(self) -> Path:
        """Return the persistent lock-file path without creating it."""

        return self._lock_path

    def acquire(self) -> None:
        """Acquire the OS-held lock before the bounded monotonic deadline."""

        if self._started:
            raise ChromaWriterLockError("A ChromaWriterLock object is single-use.")
        self._started = True
        try:
            descriptor = self._open_lock_file()
            self._file_descriptor = descriptor
            deadline = time.monotonic() + self._timeout_seconds
            while True:
                try:
                    self._try_lock(descriptor)
                except OSError as exc:
                    if not self._is_lock_unavailable(exc):
                        raise ChromaWriterLockError(
                            "The governed Chroma writer lock could not be acquired."
                        ) from exc
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ChromaWriterLockTimeout(
                            "Timed out waiting for the governed Chroma writer lock."
                        ) from exc
                    time.sleep(min(self._poll_interval_seconds, remaining))
                    continue
                self._owned = True
                return
        except Exception:
            self._close_descriptor()
            raise

    def release(self) -> None:
        """Release the exact OS-held lock and close its owning descriptor."""

        if not self._owned or self._file_descriptor is None:
            raise ChromaWriterLockError("The Chroma writer lock is not owned.")
        descriptor = self._file_descriptor
        unlock_error: Exception | None = None
        try:
            self._unlock(descriptor)
        except Exception as exc:  # pragma: no cover - exceptional OS failure
            unlock_error = exc
        finally:
            self._owned = False
            self._released = True
            self._close_descriptor()
        if unlock_error is not None:
            raise ChromaWriterLockError(
                "The governed Chroma writer lock could not be released cleanly."
            ) from unlock_error

    def __enter__(self) -> ChromaWriterLock:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.release()

    @staticmethod
    def _required_text(value: str, *, field_name: str) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field_name} must not be empty.")
        return value

    @staticmethod
    def _nonnegative_float(value: float, *, field_name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field_name} must be a non-negative number.")
        result = float(value)
        if result < 0:
            raise ValueError(f"{field_name} must be a non-negative number.")
        return result

    @staticmethod
    def _positive_float(value: float, *, field_name: str) -> float:
        result = ChromaWriterLock._nonnegative_float(value, field_name=field_name)
        if result <= 0:
            raise ValueError(f"{field_name} must be greater than zero.")
        return result

    @staticmethod
    def _is_link_like(path: Path) -> bool:
        try:
            details = path.lstat()
        except FileNotFoundError:
            return False
        if stat.S_ISLNK(details.st_mode):
            return True
        attributes = getattr(details, "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        return bool(reparse_flag and attributes & reparse_flag)

    def _assert_contained(self, path: Path) -> None:
        try:
            path.resolve(strict=False).relative_to(self._db_path)
        except ValueError as exc:
            raise ChromaWriterLockError(
                "Unsafe governed Chroma writer lock path was rejected."
            ) from exc

    def _verify_directory(self, path: Path) -> None:
        self._assert_contained(path)
        if self._is_link_like(path):
            raise ChromaWriterLockError(
                "A governed Chroma writer lock directory must not be a link or junction."
            )
        try:
            details = path.stat()
        except OSError as exc:
            raise ChromaWriterLockError(
                "A governed Chroma writer lock directory could not be inspected."
            ) from exc
        if not stat.S_ISDIR(details.st_mode):
            raise ChromaWriterLockError(
                "A governed Chroma writer lock directory path is not a directory."
            )

    def _ensure_lock_directory(self) -> Path:
        try:
            self._db_path.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise ChromaWriterLockError(
                "The governed Chroma persistence directory could not be prepared."
            ) from exc
        self._verify_directory(self._db_path)

        lock_directory = self._lock_path.parent
        self._assert_contained(lock_directory)
        if lock_directory.exists() or self._is_link_like(lock_directory):
            self._verify_directory(lock_directory)
            return lock_directory
        try:
            lock_directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
        except OSError as exc:
            raise ChromaWriterLockError(
                "The governed Chroma writer lock directory could not be prepared."
            ) from exc
        self._verify_directory(lock_directory)
        return lock_directory

    def _open_lock_file(self) -> int:
        self._ensure_lock_directory()
        self._assert_contained(self._lock_path)
        if self._is_link_like(self._lock_path):
            raise ChromaWriterLockError(
                "The governed Chroma writer lock file must not be a link or junction."
            )

        flags = os.O_RDWR | os.O_CREAT
        flags |= getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self._lock_path, flags, 0o600)
        except OSError as exc:
            raise ChromaWriterLockError(
                "The governed Chroma writer lock file could not be opened."
            ) from exc

        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode):
                raise ChromaWriterLockError(
                    "The governed Chroma writer lock target is not a regular file."
                )
            if self._is_link_like(self._lock_path):
                raise ChromaWriterLockError(
                    "The governed Chroma writer lock file must not be a link or junction."
                )
            if details.st_size < _LOCK_BYTE_COUNT:
                os.lseek(descriptor, 0, os.SEEK_SET)
                if os.write(descriptor, b"\0") != _LOCK_BYTE_COUNT:
                    raise ChromaWriterLockError(
                        "The governed Chroma writer lock file could not be extended."
                    )
                os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            return descriptor
        except Exception:
            os.close(descriptor)
            raise

    @staticmethod
    def _try_lock(descriptor: int) -> None:
        if os.name == "nt":
            import msvcrt

            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, _LOCK_BYTE_COUNT)
            return

        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _unlock(descriptor: int) -> None:
        if os.name == "nt":
            import msvcrt

            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, _LOCK_BYTE_COUNT)
            return

        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_UN)

    @staticmethod
    def _is_lock_unavailable(exc: OSError) -> bool:
        return exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}

    def _close_descriptor(self) -> None:
        descriptor = self._file_descriptor
        self._file_descriptor = None
        if descriptor is None:
            return
        try:
            os.close(descriptor)
        except OSError as exc:  # pragma: no cover - exceptional OS failure
            raise ChromaWriterLockError(
                "The governed Chroma writer lock descriptor could not be closed."
            ) from exc


__all__ = [
    "ChromaWriterLock",
    "ChromaWriterLockError",
    "ChromaWriterLockTimeout",
]
