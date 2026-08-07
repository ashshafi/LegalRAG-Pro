"""PFCR3 M4 production-capable offline cutover execution.

This module is deliberately separate from frozen PFCR3 M1/M2.

It can perform the production handoff only when supplied with an explicit
permit bound to the frozen plan and production root. Tests use a disposable
permit and OS-temporary roots.

The module never deletes the retained old active database, never performs
HM2, and never retires legacy data.

PFCR3 M3.1 established that Chroma 1.5.9 may rewrite internal persistence
bytes during an otherwise read-only open. Therefore the activated tree is
byte-verified against the sealed shadow before the first Chroma open; after
that point acceptance is based on the exact logical row set, source-binding
metadata, preserved immutable source artifacts, and the byte-sealed rollback
generation.
"""

from __future__ import annotations

import errno
import json
import ntpath
import logging
import os
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from source_evidence.chroma_lock import (
    ChromaWriterLock,
    ChromaWriterLockError,
)
from source_evidence.offline_cutover import (
    OFFLINE_CUTOVER_PLAN_SCHEMA_VERSION,
    OfflineCutoverPlan,
)
from source_evidence.production_shadow_build import (
    _build_tree_manifest,
    _is_link_like,
)


LOGGER = logging.getLogger(__name__)

PRODUCTION_CUTOVER_PERMIT_SCHEMA_VERSION = (
    "production-cutover-permit/1.0"
)

_COLLECTION_NAME: Final[str] = "legal_documents"
_TENANT: Final[str] = "default_tenant"
_DATABASE: Final[str] = "default_database"

_EXTERNAL_MUTEX_NAME: Final[str] = (
    "pfcr3-production-cutover.lock"
)
_EXTERNAL_MUTEX_BYTE_COUNT: Final[int] = 1
_EXTERNAL_MUTEX_TIMEOUT_SECONDS: Final[float] = 30.0
_EXTERNAL_MUTEX_POLL_SECONDS: Final[float] = 0.1


class ProductionCutoverPermitKind(StrEnum):
    """Explicit execution scope for one PFCR3 M4 invocation."""

    DISPOSABLE_TEST = "disposable_test"
    PRODUCTION = "production"


@dataclass(frozen=True, slots=True)
class ProductionCutoverPermit:
    """Permit bound to one frozen PFCR3 plan and production root."""

    schema_version: str
    kind: ProductionCutoverPermitKind
    case_id: str
    production_shadow_build_report_id: str
    production_root: str


class ProductionCutoverBlocker(StrEnum):
    """Fail-closed blockers for PFCR3 M4 execution."""

    PLAN_INVALID = "plan_invalid"
    PERMIT_INVALID = "permit_invalid"
    PERMIT_SCOPE_INVALID = "permit_scope_invalid"

    PATH_INVALID = "path_invalid"
    PATH_OVERLAP = "path_overlap"

    ACTIVE_DB_MISSING = "active_db_missing"
    CANDIDATE_DB_MISSING = "candidate_db_missing"
    SEALED_SHADOW_MISSING = "sealed_shadow_missing"
    VERIFIED_BACKUP_MISSING = "verified_backup_missing"
    SOURCE_STORE_MISSING = "source_store_missing"

    RETAINED_SLOT_OCCUPIED = "retained_slot_occupied"
    QUARANTINE_SLOT_OCCUPIED = "quarantine_slot_occupied"

    VOLUME_MISMATCH = "volume_mismatch"

    PROCESS_GATE_UNAVAILABLE = "process_gate_unavailable"
    PROCESS_GATE_FAILED = "process_gate_failed"
    PROCESS_ACTIVE = "process_active"

    EXTERNAL_MUTEX_FAILED = "external_mutex_failed"

    ACTIVE_TREE_MISMATCH = "active_tree_mismatch"
    CANDIDATE_TREE_MISMATCH = "candidate_tree_mismatch"
    SEALED_SHADOW_TREE_MISMATCH = (
        "sealed_shadow_tree_mismatch"
    )
    VERIFIED_BACKUP_TREE_MISMATCH = (
        "verified_backup_tree_mismatch"
    )
    SOURCE_STORE_TREE_MISMATCH = (
        "source_store_tree_mismatch"
    )

    RETAIN_FAILED = "retain_failed"
    RETAINED_VERIFY_FAILED = "retained_verify_failed"
    ACTIVATE_FAILED = "activate_failed"

    PREOPEN_VERIFY_FAILED = "preopen_verify_failed"
    LOGICAL_VERIFY_FAILED = "logical_verify_failed"
    WRITER_LOCK_FAILED = "writer_lock_failed"
    FINAL_VERIFY_FAILED = "final_verify_failed"

    ROLLBACK_FAILED = "rollback_failed"


class ProductionCutoverError(RuntimeError):
    """Raised when PFCR3 M4 cannot complete safely."""

    def __init__(
        self,
        blocker: ProductionCutoverBlocker,
        *,
        detail: str | None = None,
    ) -> None:
        self.blocker = blocker
        self.detail = detail

        message = blocker.value

        if detail:
            message = f"{message}: {detail}"

        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ProductionCutoverResult:
    """Verified result of one completed PFCR3 M4 handoff."""

    active_db_root: str
    retained_active_root: str

    external_mutex_path: str
    writer_lock_path: str

    activated_preopen_tree_sha256: str
    retained_tree_sha256: str

    sealed_shadow_tree_sha256: str
    verified_backup_tree_sha256: str
    source_store_tree_sha256: str

    expected_row_count: int
    collection_count: int
    unique_id_count: int
    metadata_count: int
    missing_source_bound_count: int

    exact_row_set_verified: bool
    candidate_path_absent: bool
    quarantine_path_absent: bool


@dataclass(frozen=True, slots=True)
class _LogicalInspection:
    """Internal exact logical Chroma inspection."""

    collection_count: int
    ids: tuple[str, ...]
    metadata_count: int
    missing_source_bound_count: int

    @property
    def unique_id_count(self) -> int:
        return len(set(self.ids))


def _is_relative_to(
    path: Path,
    parent: Path,
) -> bool:
    """Return whether path is a strict descendant of parent."""

    try:
        relative = path.relative_to(parent)
    except ValueError:
        return False

    return bool(relative.parts)


def _paths_overlap(
    left: Path,
    right: Path,
) -> bool:
    """Return whether two paths are equal or ancestor-related."""

    if left == right:
        return True

    return (
        _is_relative_to(left, right)
        or _is_relative_to(right, left)
    )


def _tree_sha(
    path: Path,
    *,
    require_exists: bool = True,
) -> str:
    """Return the governed deterministic tree identity."""

    return _build_tree_manifest(
        path,
        require_exists=require_exists,
    ).tree_sha256


def _require_existing_directory(
    raw_path: Path,
    *,
    blocker: ProductionCutoverBlocker,
) -> Path:
    """Resolve one required non-link directory."""

    raw = Path(raw_path).expanduser()

    if (
        not raw.exists()
        or _is_link_like(raw)
        or not raw.is_dir()
    ):
        raise ProductionCutoverError(blocker)

    return raw.resolve(strict=True)


def _require_absent_slot(
    raw_path: Path,
    *,
    blocker: ProductionCutoverBlocker,
) -> Path:
    """Resolve one required-empty destination slot."""

    raw = Path(raw_path).expanduser()

    if raw.exists() or raw.is_symlink():
        raise ProductionCutoverError(blocker)

    parent = raw.parent

    if (
        not parent.exists()
        or _is_link_like(parent)
        or not parent.is_dir()
    ):
        raise ProductionCutoverError(
            ProductionCutoverBlocker.PATH_INVALID,
            detail=f"slot parent unavailable: {parent}",
        )

    return raw.resolve(strict=False)


def _validate_expected_row_ids(
    plan: OfflineCutoverPlan,
    expected_row_ids: tuple[str, ...],
) -> tuple[str, ...]:
    """Validate the sealed prospective row identity set."""

    try:
        values = tuple(expected_row_ids)
    except TypeError as exc:
        raise ProductionCutoverError(
            ProductionCutoverBlocker.PERMIT_INVALID,
            detail="expected_row_ids must be iterable",
        ) from exc

    if any(
        not isinstance(value, str)
        or not value
        for value in values
    ):
        raise ProductionCutoverError(
            ProductionCutoverBlocker.PERMIT_INVALID,
            detail=(
                "expected_row_ids must contain "
                "non-empty strings"
            ),
        )

    if len(values) != len(set(values)):
        raise ProductionCutoverError(
            ProductionCutoverBlocker.PERMIT_INVALID,
            detail="expected_row_ids must be unique",
        )

    if len(values) != plan.expected_shadow_row_count:
        raise ProductionCutoverError(
            ProductionCutoverBlocker.PERMIT_INVALID,
            detail=(
                "expected_row_ids count does not match "
                "the frozen plan"
            ),
        )

    return tuple(sorted(values))


def _validate_permit(
    *,
    plan: OfflineCutoverPlan,
    permit: ProductionCutoverPermit,
    production_root: Path,
) -> None:
    """Validate explicit disposable-test or production scope."""

    if not isinstance(plan, OfflineCutoverPlan):
        raise ProductionCutoverError(
            ProductionCutoverBlocker.PLAN_INVALID
        )

    if (
        plan.schema_version
        != OFFLINE_CUTOVER_PLAN_SCHEMA_VERSION
    ):
        raise ProductionCutoverError(
            ProductionCutoverBlocker.PLAN_INVALID
        )

    if not isinstance(permit, ProductionCutoverPermit):
        raise ProductionCutoverError(
            ProductionCutoverBlocker.PERMIT_INVALID
        )

    if (
        permit.schema_version
        != PRODUCTION_CUTOVER_PERMIT_SCHEMA_VERSION
    ):
        raise ProductionCutoverError(
            ProductionCutoverBlocker.PERMIT_INVALID
        )

    if permit.case_id != plan.case_id:
        raise ProductionCutoverError(
            ProductionCutoverBlocker.PERMIT_INVALID,
            detail="permit case_id does not match plan",
        )

    if (
        permit.production_shadow_build_report_id
        != plan.production_shadow_build_report_id
    ):
        raise ProductionCutoverError(
            ProductionCutoverBlocker.PERMIT_INVALID,
            detail="permit report ID does not match plan",
        )

    try:
        permitted_root = (
            Path(permit.production_root)
            .expanduser()
            .resolve(strict=True)
        )
    except OSError as exc:
        raise ProductionCutoverError(
            ProductionCutoverBlocker.PERMIT_INVALID,
            detail="permit production root cannot be resolved",
        ) from exc

    if permitted_root != production_root:
        raise ProductionCutoverError(
            ProductionCutoverBlocker.PERMIT_INVALID,
            detail=(
                "permit production root does not "
                "match invocation"
            ),
        )

    temp_root = Path(
        tempfile.gettempdir()
    ).resolve(strict=True)

    under_temp = (
        production_root == temp_root
        or _is_relative_to(
            production_root,
            temp_root,
        )
    )

    if (
        permit.kind
        is ProductionCutoverPermitKind.DISPOSABLE_TEST
    ):
        if not under_temp:
            raise ProductionCutoverError(
                ProductionCutoverBlocker.PERMIT_SCOPE_INVALID,
                detail=(
                    "disposable-test permit requires "
                    "an OS-temp production root"
                ),
            )

    elif (
        permit.kind
        is ProductionCutoverPermitKind.PRODUCTION
    ):
        if under_temp:
            raise ProductionCutoverError(
                ProductionCutoverBlocker.PERMIT_SCOPE_INVALID,
                detail=(
                    "production permit may not target "
                    "an OS-temp production root"
                ),
            )

    else:
        raise ProductionCutoverError(
            ProductionCutoverBlocker.PERMIT_INVALID
        )


def _same_volume(
    paths: tuple[Path, ...],
) -> bool:
    """Return whether all handoff paths use one filesystem volume."""

    try:
        devices = {
            os.stat(path).st_dev
            for path in paths
        }
    except OSError as exc:
        raise ProductionCutoverError(
            ProductionCutoverBlocker.VOLUME_MISMATCH,
            detail=(
                "filesystem volume identity could not "
                "be established"
            ),
        ) from exc

    return len(devices) == 1


def _verified_windows_controller_launcher_pid(
    *,
    items: tuple[dict[str, object], ...],
    current_pid: int,
    launcher_executable: str,
    base_executable: str,
) -> int | None:
    """Return the PID of a proven Windows venv launcher parent.

    A Windows virtual-environment launcher can remain alive as the
    direct parent of the actual base interpreter. Only that exact,
    verified controller relationship may be ignored by the offline
    production process gate.
    """

    def path_key(
        value: object,
    ) -> str | None:
        if not isinstance(value, str):
            return None

        value = value.strip()

        if not value:
            return None

        return ntpath.normcase(
            ntpath.normpath(
                value
            )
        )

    def is_python_process(
        item: dict[str, object],
    ) -> bool:
        name = item.get("Name")

        if not isinstance(name, str):
            return False

        return name.casefold() in {
            "python",
            "python.exe",
            "pythonw",
            "pythonw.exe",
            "py",
            "py.exe",
        }

    launcher_key = path_key(
        launcher_executable
    )

    base_key = path_key(
        base_executable
    )

    if (
        launcher_key is None
        or base_key is None
        or launcher_key == base_key
    ):
        return None

    current = next(
        (
            item
            for item in items
            if item.get("ProcessId")
            == current_pid
        ),
        None,
    )

    if (
        current is None
        or not is_python_process(current)
        or path_key(
            current.get("ExecutablePath")
        )
        != base_key
    ):
        return None

    parent_pid = current.get(
        "ParentProcessId"
    )

    if (
        not isinstance(parent_pid, int)
        or parent_pid <= 0
    ):
        return None

    parent = next(
        (
            item
            for item in items
            if item.get("ProcessId")
            == parent_pid
        ),
        None,
    )

    if (
        parent is None
        or not is_python_process(parent)
        or path_key(
            parent.get("ExecutablePath")
        )
        != launcher_key
    ):
        return None

    current_command = current.get(
        "CommandLine"
    )

    parent_command = parent.get(
        "CommandLine"
    )

    if (
        not isinstance(current_command, str)
        or not current_command
        or not isinstance(parent_command, str)
        or not parent_command
        or current_command != parent_command
        or launcher_executable.casefold()
        not in current_command.casefold()
    ):
        return None

    return parent_pid


def _active_runtime_processes() -> tuple[str, ...]:
    """Return other Python/Streamlit processes on Windows."""

    if os.name != "nt":
        raise ProductionCutoverError(
            ProductionCutoverBlocker.PROCESS_GATE_UNAVAILABLE,
            detail=(
                "default production process gate "
                "is Windows-only"
            ),
        )

    current_pid = os.getpid()

    launcher_executable = sys.executable

    base_executable = (
        getattr(
            sys,
            "_base_executable",
            None,
        )
        or launcher_executable
    )

    script = r"""
$ErrorActionPreference = 'Stop'
$ProbePid = $PID

$Items = @(
    Get-CimInstance Win32_Process |
    Where-Object {
        $_.ProcessId -ne $ProbePid -and
        (
            $_.Name -match '^(python|pythonw|py)(\.exe)?$' -or
            (
                $_.CommandLine -and
                $_.CommandLine -match '(?i)streamlit'
            )
        )
    } |
    Select-Object `
        ProcessId, `
        ParentProcessId, `
        Name, `
        ExecutablePath, `
        CommandLine
)

if ($Items.Count -gt 0) {
    $Items | ConvertTo-Json -Compress
}
"""

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        raise ProductionCutoverError(
            ProductionCutoverBlocker.PROCESS_GATE_FAILED,
            detail=(
                completed.stderr.strip()
                or "PowerShell process probe failed"
            ),
        )

    payload = completed.stdout.strip()

    if not payload:
        return ()

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ProductionCutoverError(
            ProductionCutoverBlocker.PROCESS_GATE_FAILED,
            detail=(
                "PowerShell process probe returned "
                "invalid JSON"
            ),
        ) from exc

    raw_items = (
        parsed
        if isinstance(parsed, list)
        else [parsed]
    )

    if not all(
        isinstance(item, dict)
        for item in raw_items
    ):
        raise ProductionCutoverError(
            ProductionCutoverBlocker.PROCESS_GATE_FAILED,
            detail=(
                "PowerShell process probe returned "
                "invalid process records"
            ),
        )

    items: tuple[
        dict[str, object],
        ...,
    ] = tuple(raw_items)

    launcher_pid = (
        _verified_windows_controller_launcher_pid(
            items=items,
            current_pid=current_pid,
            launcher_executable=launcher_executable,
            base_executable=base_executable,
        )
    )

    ignored_pids = {
        current_pid,
    }

    if launcher_pid is not None:
        ignored_pids.add(
            launcher_pid
        )

    return tuple(
        (
            f"PID={item.get('ProcessId')} "
            f"Name={item.get('Name')} "
            f"Command={item.get('CommandLine')}"
        )
        for item in items
        if item.get("ProcessId")
        not in ignored_pids
    )


def _require_offline_process_gate() -> None:
    """Fail closed unless no other governed runtime exists."""

    try:
        active = _active_runtime_processes()
    except ProductionCutoverError:
        raise
    except Exception as exc:
        raise ProductionCutoverError(
            ProductionCutoverBlocker.PROCESS_GATE_FAILED
        ) from exc

    if active:
        raise ProductionCutoverError(
            ProductionCutoverBlocker.PROCESS_ACTIVE,
            detail="; ".join(active),
        )


class _ExternalCutoverMutex:
    """Persistent OS-held cutover mutex outside database trees."""

    def __init__(
        self,
        control_root: Path,
    ) -> None:
        self._control_root = control_root
        self.lock_path = (
            control_root
            / _EXTERNAL_MUTEX_NAME
        )

        self._descriptor: int | None = None
        self._owned = False

    def __enter__(
        self,
    ) -> "_ExternalCutoverMutex":
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ) -> None:
        self.release()

    def acquire(self) -> None:
        """Acquire one persistent OS lock target."""

        if (
            self._owned
            or self._descriptor is not None
        ):
            raise ProductionCutoverError(
                ProductionCutoverBlocker.EXTERNAL_MUTEX_FAILED,
                detail=(
                    "external cutover mutex object "
                    "is already active"
                ),
            )

        if (
            _is_link_like(self._control_root)
            or not self._control_root.is_dir()
        ):
            raise ProductionCutoverError(
                ProductionCutoverBlocker.EXTERNAL_MUTEX_FAILED,
                detail=(
                    "external cutover control root "
                    "is unsafe"
                ),
            )

        if (
            self.lock_path.exists()
            and _is_link_like(self.lock_path)
        ):
            raise ProductionCutoverError(
                ProductionCutoverBlocker.EXTERNAL_MUTEX_FAILED,
                detail=(
                    "external cutover mutex path "
                    "is link-like"
                ),
            )

        flags = os.O_RDWR | os.O_CREAT
        flags |= getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)

        try:
            descriptor = os.open(
                self.lock_path,
                flags,
                0o600,
            )
        except OSError as exc:
            raise ProductionCutoverError(
                ProductionCutoverBlocker.EXTERNAL_MUTEX_FAILED,
                detail=(
                    "external cutover mutex file "
                    "could not be opened"
                ),
            ) from exc

        self._descriptor = descriptor

        try:
            details = os.fstat(descriptor)

            if not stat.S_ISREG(details.st_mode):
                raise ProductionCutoverError(
                    ProductionCutoverBlocker.EXTERNAL_MUTEX_FAILED,
                    detail=(
                        "external cutover mutex target "
                        "is not a regular file"
                    ),
                )

            if (
                details.st_size
                < _EXTERNAL_MUTEX_BYTE_COUNT
            ):
                os.lseek(
                    descriptor,
                    0,
                    os.SEEK_SET,
                )

                written = os.write(
                    descriptor,
                    b"\0",
                )

                if (
                    written
                    != _EXTERNAL_MUTEX_BYTE_COUNT
                ):
                    raise ProductionCutoverError(
                        ProductionCutoverBlocker.EXTERNAL_MUTEX_FAILED,
                        detail=(
                            "external cutover mutex file "
                            "could not be extended"
                        ),
                    )

                os.fsync(descriptor)

            deadline = (
                time.monotonic()
                + _EXTERNAL_MUTEX_TIMEOUT_SECONDS
            )

            while True:
                try:
                    self._try_lock(
                        descriptor
                    )

                except OSError as exc:
                    if not self._is_lock_unavailable(
                        exc
                    ):
                        raise ProductionCutoverError(
                            ProductionCutoverBlocker.EXTERNAL_MUTEX_FAILED,
                            detail=(
                                "external cutover mutex "
                                "could not be acquired"
                            ),
                        ) from exc

                    remaining = (
                        deadline
                        - time.monotonic()
                    )

                    if remaining <= 0:
                        raise ProductionCutoverError(
                            ProductionCutoverBlocker.EXTERNAL_MUTEX_FAILED,
                            detail=(
                                "timed out waiting for "
                                "external cutover mutex"
                            ),
                        ) from exc

                    time.sleep(
                        min(
                            _EXTERNAL_MUTEX_POLL_SECONDS,
                            remaining,
                        )
                    )

                    continue

                self._owned = True
                return

        except Exception:
            os.close(descriptor)
            self._descriptor = None
            raise

    def release(self) -> None:
        """Release the OS lock and close its descriptor."""

        descriptor = self._descriptor

        if descriptor is None:
            return

        try:
            if self._owned:
                try:
                    self._unlock(
                        descriptor
                    )
                except OSError:
                    # Closing the descriptor is the final
                    # OS-level release safeguard.
                    LOGGER.exception(
                        "External PFCR3 cutover mutex "
                        "unlock failed; closing descriptor."
                    )
        finally:
            self._owned = False
            self._descriptor = None
            os.close(descriptor)

    @staticmethod
    def _try_lock(
        descriptor: int,
    ) -> None:
        os.lseek(
            descriptor,
            0,
            os.SEEK_SET,
        )

        if os.name == "nt":
            import msvcrt

            msvcrt.locking(
                descriptor,
                msvcrt.LK_NBLCK,
                _EXTERNAL_MUTEX_BYTE_COUNT,
            )
            return

        import fcntl

        fcntl.flock(
            descriptor,
            fcntl.LOCK_EX | fcntl.LOCK_NB,
        )

    @staticmethod
    def _unlock(
        descriptor: int,
    ) -> None:
        os.lseek(
            descriptor,
            0,
            os.SEEK_SET,
        )

        if os.name == "nt":
            import msvcrt

            msvcrt.locking(
                descriptor,
                msvcrt.LK_UNLCK,
                _EXTERNAL_MUTEX_BYTE_COUNT,
            )
            return

        import fcntl

        fcntl.flock(
            descriptor,
            fcntl.LOCK_UN,
        )

    @staticmethod
    def _is_lock_unavailable(
        exc: OSError,
    ) -> bool:
        if exc.errno in {
            errno.EACCES,
            errno.EAGAIN,
            errno.EDEADLK,
        }:
            return True

        return getattr(
            exc,
            "winerror",
            None,
        ) in {33, 36}


def _inspect_active_collection(
    db_root: Path,
) -> _LogicalInspection:
    """Inspect Chroma in a child process.

    Using a child process guarantees that Chroma's Windows file
    handles are closed before a possible directory rollback.
    """

    script = r'''
import json
import sys

import chromadb

db_root = sys.argv[1]

client = chromadb.PersistentClient(
    path=db_root
)

collection = client.get_collection(
    name="legal_documents"
)

raw = collection.get(
    include=["metadatas"]
)

ids = list(
    raw.get("ids") or []
)

metadatas = list(
    raw.get("metadatas") or []
)

required = (
    "source_evidence_binding_id",
    "source_snapshot_id",
    "source_document_instance_id",
    "source_chunk_sha256",
    "source_page_text_sha256",
    "source_original_blob_sha256",
    "source_binding_class",
)

missing = 0

for metadata in metadatas:
    value = metadata or {}

    if any(
        not value.get(field)
        for field in required
    ):
        missing += 1

result = {
    "collection_count":
        collection.count(),
    "ids":
        sorted(ids),
    "metadata_count":
        len(metadatas),
    "missing_source_bound_count":
        missing,
}

closer = getattr(
    client,
    "close",
    None,
)

if callable(closer):
    closer()

print(
    "__PFCR3_M4__"
    + json.dumps(
        result,
        sort_keys=True,
    )
)
'''

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(db_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            completed.stderr.strip()
            or completed.stdout.strip()
            or (
                "Chroma verification subprocess "
                "failed"
            )
        )

    marker = "__PFCR3_M4__"

    for line in completed.stdout.splitlines():
        if line.startswith(marker):
            payload = json.loads(
                line[len(marker):]
            )

            return _LogicalInspection(
                collection_count=int(
                    payload[
                        "collection_count"
                    ]
                ),
                ids=tuple(
                    str(value)
                    for value
                    in payload["ids"]
                ),
                metadata_count=int(
                    payload[
                        "metadata_count"
                    ]
                ),
                missing_source_bound_count=int(
                    payload[
                        "missing_source_bound_count"
                    ]
                ),
            )

    raise RuntimeError(
        "Chroma verification subprocess "
        "returned no governed result."
    )


def _verify_logical_state(
    *,
    db_root: Path,
    expected_row_ids: tuple[str, ...],
    expected_row_count: int,
    blocker: ProductionCutoverBlocker,
) -> _LogicalInspection:
    """Require the exact sealed logical Chroma population."""

    try:
        inspection = (
            _inspect_active_collection(
                db_root
            )
        )
    except Exception as exc:
        raise ProductionCutoverError(
            blocker,
            detail=str(exc),
        ) from exc

    if (
        inspection.collection_count
        != expected_row_count
        or len(inspection.ids)
        != expected_row_count
        or inspection.unique_id_count
        != expected_row_count
        or inspection.metadata_count
        != expected_row_count
        or inspection.missing_source_bound_count
        != 0
        or tuple(
            sorted(
                inspection.ids
            )
        )
        != expected_row_ids
    ):
        raise ProductionCutoverError(
            blocker,
            detail=(
                "logical exact-set verification failed "
                f"(collection="
                f"{inspection.collection_count}, "
                f"ids={len(inspection.ids)}, "
                f"unique="
                f"{inspection.unique_id_count}, "
                f"metadata="
                f"{inspection.metadata_count}, "
                f"missing_source_bound="
                f"{inspection.missing_source_bound_count})"
            ),
        )

    return inspection


def _restore_retained_active(
    *,
    active: Path,
    retained: Path,
) -> None:
    """Restore retained old active before candidate activation."""

    try:
        if active.exists():
            raise OSError(
                "active slot unexpectedly occupied "
                "during restore"
            )

        if not retained.exists():
            raise OSError(
                "retained old-active slot missing "
                "during restore"
            )

        os.replace(
            retained,
            active,
        )

    except OSError as exc:
        raise ProductionCutoverError(
            ProductionCutoverBlocker.ROLLBACK_FAILED,
            detail=(
                "retained old active could not "
                "be restored"
            ),
        ) from exc


def _quarantine_and_restore(
    *,
    active: Path,
    retained: Path,
    quarantine: Path,
) -> None:
    """Preserve failed candidate and restore old active."""

    try:
        if (
            quarantine.exists()
            or quarantine.is_symlink()
        ):
            raise OSError(
                "quarantine slot became occupied"
            )

        if active.exists():
            os.replace(
                active,
                quarantine,
            )

        if not retained.exists():
            raise OSError(
                "retained old-active slot missing"
            )

        os.replace(
            retained,
            active,
        )

    except OSError as exc:
        raise ProductionCutoverError(
            ProductionCutoverBlocker.ROLLBACK_FAILED,
            detail=(
                "activated candidate could not be "
                "quarantined and old active restored"
            ),
        ) from exc


def execute_production_cutover(
    *,
    plan: OfflineCutoverPlan,
    permit: ProductionCutoverPermit,

    production_root: Path,
    active_db_root: Path,

    candidate_db_root: Path,
    retained_active_root: Path,
    failed_candidate_quarantine_root: Path,
    external_control_root: Path,

    sealed_shadow_root: Path,
    verified_backup_root: Path,
    source_store_root: Path,

    expected_row_ids: tuple[str, ...],
) -> ProductionCutoverResult:
    """Execute one fail-closed PFCR3 production-capable handoff.

    Args:
        plan: Frozen PFCR3 M1 eligibility plan.
        permit: Explicit disposable-test or production permit.
        production_root: LegalRAG runtime root.
        active_db_root: Current ``production_root / "db"``.
        candidate_db_root: Separate exact copy of the sealed shadow.
        retained_active_root: Empty slot that will retain old active.
        failed_candidate_quarantine_root: Empty rollback quarantine.
        external_control_root: Existing directory for the external mutex.
        sealed_shadow_root: Preserved immutable Retry3 shadow.
        verified_backup_root: Preserved verified old-active backup.
        source_store_root: Frozen production source-evidence store.
        expected_row_ids: Exact sealed prospective row identity set.

    Returns:
        Verified production-cutover result.

    Raises:
        ProductionCutoverError: If any prerequisite, handoff, acceptance,
            or rollback invariant fails.

    Notes:
        This function never removes the retained old active database.
        It does not perform HM2 or legacy retirement.
    """

    production = _require_existing_directory(
        Path(production_root),
        blocker=(
            ProductionCutoverBlocker.PATH_INVALID
        ),
    )

    _validate_permit(
        plan=plan,
        permit=permit,
        production_root=production,
    )

    expected_ids = (
        _validate_expected_row_ids(
            plan,
            expected_row_ids,
        )
    )

    active = _require_existing_directory(
        Path(active_db_root),
        blocker=(
            ProductionCutoverBlocker.ACTIVE_DB_MISSING
        ),
    )

    expected_active = (
        production
        / "db"
    ).resolve(strict=False)

    if active != expected_active:
        raise ProductionCutoverError(
            ProductionCutoverBlocker.PATH_INVALID,
            detail=(
                "active DB must be "
                "production_root/db"
            ),
        )

    source_store = _require_existing_directory(
        Path(source_store_root),
        blocker=(
            ProductionCutoverBlocker.SOURCE_STORE_MISSING
        ),
    )

    expected_source_store = (
        production
        / "source_evidence_store"
        / "v1"
    ).resolve(strict=False)

    if source_store != expected_source_store:
        raise ProductionCutoverError(
            ProductionCutoverBlocker.PATH_INVALID,
            detail=(
                "source store must be "
                "production_root/"
                "source_evidence_store/v1"
            ),
        )

    candidate = _require_existing_directory(
        Path(candidate_db_root),
        blocker=(
            ProductionCutoverBlocker.CANDIDATE_DB_MISSING
        ),
    )

    sealed_shadow = (
        _require_existing_directory(
            Path(sealed_shadow_root),
            blocker=(
                ProductionCutoverBlocker.SEALED_SHADOW_MISSING
            ),
        )
    )

    verified_backup = (
        _require_existing_directory(
            Path(verified_backup_root),
            blocker=(
                ProductionCutoverBlocker.VERIFIED_BACKUP_MISSING
            ),
        )
    )

    retained = _require_absent_slot(
        Path(retained_active_root),
        blocker=(
            ProductionCutoverBlocker.RETAINED_SLOT_OCCUPIED
        ),
    )

    quarantine = _require_absent_slot(
        Path(
            failed_candidate_quarantine_root
        ),
        blocker=(
            ProductionCutoverBlocker.QUARANTINE_SLOT_OCCUPIED
        ),
    )

    control = _require_existing_directory(
        Path(external_control_root),
        blocker=(
            ProductionCutoverBlocker.PATH_INVALID
        ),
    )

    mutable_paths = (
        active,
        candidate,
        retained,
        quarantine,
    )

    for index, left in enumerate(
        mutable_paths
    ):
        for right in mutable_paths[
            index + 1:
        ]:
            if _paths_overlap(
                left,
                right,
            ):
                raise ProductionCutoverError(
                    ProductionCutoverBlocker.PATH_OVERLAP
                )

    #
    # Candidate / rollback / control paths are all external to
    # the application production root.
    #
    for external in (
        candidate,
        retained,
        quarantine,
        control,
        sealed_shadow,
        verified_backup,
    ):
        if _paths_overlap(
            external,
            production,
        ):
            raise ProductionCutoverError(
                ProductionCutoverBlocker.PATH_OVERLAP,
                detail=(
                    "candidate/rollback/control/"
                    "sealed evidence roots must be external"
                ),
            )

    #
    # The exact sealed source trees may never overlap a mutable slot.
    #
    immutable_paths = (
        sealed_shadow,
        verified_backup,
        source_store,
    )

    for immutable in immutable_paths:
        for mutable in mutable_paths:
            if _paths_overlap(
                immutable,
                mutable,
            ):
                raise ProductionCutoverError(
                    ProductionCutoverBlocker.PATH_OVERLAP
                )

    for mutable in mutable_paths:
        if _paths_overlap(
            control,
            mutable,
        ):
            raise ProductionCutoverError(
                ProductionCutoverBlocker.PATH_OVERLAP
            )

    for immutable in immutable_paths:
        if _paths_overlap(
            control,
            immutable,
        ):
            raise ProductionCutoverError(
                ProductionCutoverBlocker.PATH_OVERLAP
            )

    #
    # os.replace directory handoff must remain on one volume.
    #
    if not _same_volume(
        (
            active,
            candidate,
            retained.parent,
            quarantine.parent,
        )
    ):
        raise ProductionCutoverError(
            ProductionCutoverBlocker.VOLUME_MISMATCH
        )

    mutex = _ExternalCutoverMutex(
        control
    )

    with mutex:
        #
        # No other Python / Streamlit runtime may be active.
        #
        _require_offline_process_gate()

        #
        # Authoritative physical pre-cutover seals.
        #
        if (
            _tree_sha(active)
            != plan.active_db_pre_tree_sha256
        ):
            raise ProductionCutoverError(
                ProductionCutoverBlocker.ACTIVE_TREE_MISMATCH
            )

        if (
            _tree_sha(candidate)
            != plan.shadow_tree_sha256
        ):
            raise ProductionCutoverError(
                ProductionCutoverBlocker.CANDIDATE_TREE_MISMATCH
            )

        if (
            _tree_sha(sealed_shadow)
            != plan.shadow_tree_sha256
        ):
            raise ProductionCutoverError(
                ProductionCutoverBlocker.SEALED_SHADOW_TREE_MISMATCH
            )

        if (
            _tree_sha(verified_backup)
            != plan.active_db_backup_tree_sha256
        ):
            raise ProductionCutoverError(
                ProductionCutoverBlocker.VERIFIED_BACKUP_TREE_MISMATCH
            )

        if (
            _tree_sha(source_store)
            != plan.source_store_post_tree_sha256
        ):
            raise ProductionCutoverError(
                ProductionCutoverBlocker.SOURCE_STORE_TREE_MISMATCH
            )

        if retained.exists():
            raise ProductionCutoverError(
                ProductionCutoverBlocker.RETAINED_SLOT_OCCUPIED
            )

        if quarantine.exists():
            raise ProductionCutoverError(
                ProductionCutoverBlocker.QUARANTINE_SLOT_OCCUPIED
            )

        #
        # Immediate second process gate before the first rename.
        #
        _require_offline_process_gate()

        LOGGER.warning(
            "PFCR3 M4 retaining current active DB at %s",
            retained,
        )

        try:
            os.replace(
                active,
                retained,
            )
        except OSError as exc:
            raise ProductionCutoverError(
                ProductionCutoverBlocker.RETAIN_FAILED
            ) from exc

        #
        # Verify rollback generation before candidate activation.
        #
        try:
            if (
                _tree_sha(retained)
                != plan.active_db_pre_tree_sha256
            ):
                raise ProductionCutoverError(
                    ProductionCutoverBlocker.RETAINED_VERIFY_FAILED
                )

        except Exception:
            _restore_retained_active(
                active=active,
                retained=retained,
            )
            raise

        LOGGER.warning(
            "PFCR3 M4 activating sealed candidate at %s",
            active,
        )

        try:
            os.replace(
                candidate,
                active,
            )

        except OSError as exc:
            _restore_retained_active(
                active=active,
                retained=retained,
            )

            raise ProductionCutoverError(
                ProductionCutoverBlocker.ACTIVATE_FAILED
            ) from exc

        #
        # Any failure from this point quarantines the activated
        # candidate and restores the byte-sealed old active.
        #
        try:
            activated_preopen = (
                _tree_sha(active)
            )

            retained_tree = (
                _tree_sha(retained)
            )

            if (
                activated_preopen
                != plan.shadow_tree_sha256
                or retained_tree
                != plan.active_db_pre_tree_sha256
            ):
                raise ProductionCutoverError(
                    ProductionCutoverBlocker.PREOPEN_VERIFY_FAILED
                )

            #
            # No other runtime may have appeared during handoff.
            #
            _require_offline_process_gate()

            #
            # First Chroma open. From here physical active-tree SHA
            # is deliberately NOT an acceptance invariant.
            #
            _verify_logical_state(
                db_root=active,
                expected_row_ids=expected_ids,
                expected_row_count=(
                    plan.expected_shadow_row_count
                ),
                blocker=(
                    ProductionCutoverBlocker.LOGICAL_VERIFY_FAILED
                ),
            )

            #
            # Production-path governed writer-lock lifecycle.
            #
            try:
                writer_lock = (
                    ChromaWriterLock(
                        db_path=active,
                        tenant=_TENANT,
                        database=_DATABASE,
                        collection_name=(
                            _COLLECTION_NAME
                        ),
                        timeout_seconds=5.0,
                        poll_interval_seconds=0.02,
                    )
                )

                with writer_lock:
                    pass

            except ChromaWriterLockError as exc:
                raise ProductionCutoverError(
                    ProductionCutoverBlocker.WRITER_LOCK_FAILED
                ) from exc

            #
            # Final exact logical verification after writer lock.
            #
            final = _verify_logical_state(
                db_root=active,
                expected_row_ids=expected_ids,
                expected_row_count=(
                    plan.expected_shadow_row_count
                ),
                blocker=(
                    ProductionCutoverBlocker.FINAL_VERIFY_FAILED
                ),
            )

            #
            # Final offline process gate.
            #
            _require_offline_process_gate()

            #
            # Immutable / rollback generations must still be exact.
            #
            if (
                _tree_sha(retained)
                != plan.active_db_pre_tree_sha256
            ):
                raise ProductionCutoverError(
                    ProductionCutoverBlocker.FINAL_VERIFY_FAILED,
                    detail=(
                        "byte-sealed rollback "
                        "generation changed"
                    ),
                )

            if (
                _tree_sha(sealed_shadow)
                != plan.shadow_tree_sha256
            ):
                raise ProductionCutoverError(
                    ProductionCutoverBlocker.FINAL_VERIFY_FAILED,
                    detail=(
                        "sealed Retry3 shadow changed"
                    ),
                )

            if (
                _tree_sha(verified_backup)
                != plan.active_db_backup_tree_sha256
            ):
                raise ProductionCutoverError(
                    ProductionCutoverBlocker.FINAL_VERIFY_FAILED,
                    detail=(
                        "verified Retry3 backup changed"
                    ),
                )

            if (
                _tree_sha(source_store)
                != plan.source_store_post_tree_sha256
            ):
                raise ProductionCutoverError(
                    ProductionCutoverBlocker.FINAL_VERIFY_FAILED,
                    detail=(
                        "source store changed "
                        "during cutover"
                    ),
                )

        except Exception as exc:
            try:
                _quarantine_and_restore(
                    active=active,
                    retained=retained,
                    quarantine=quarantine,
                )
            except ProductionCutoverError as rollback_exc:
                raise rollback_exc from exc

            if isinstance(
                exc,
                ProductionCutoverError,
            ):
                raise

            raise ProductionCutoverError(
                ProductionCutoverBlocker.FINAL_VERIFY_FAILED,
                detail=str(exc),
            ) from exc

        return ProductionCutoverResult(
            active_db_root=str(active),
            retained_active_root=str(retained),

            external_mutex_path=str(
                mutex.lock_path
            ),
            writer_lock_path=str(
                writer_lock.lock_path
            ),

            activated_preopen_tree_sha256=(
                activated_preopen
            ),
            retained_tree_sha256=(
                retained_tree
            ),

            sealed_shadow_tree_sha256=(
                plan.shadow_tree_sha256
            ),
            verified_backup_tree_sha256=(
                plan.active_db_backup_tree_sha256
            ),
            source_store_tree_sha256=(
                plan.source_store_post_tree_sha256
            ),

            expected_row_count=(
                plan.expected_shadow_row_count
            ),
            collection_count=(
                final.collection_count
            ),
            unique_id_count=(
                final.unique_id_count
            ),
            metadata_count=(
                final.metadata_count
            ),
            missing_source_bound_count=(
                final.missing_source_bound_count
            ),

            exact_row_set_verified=(
                tuple(
                    sorted(
                        final.ids
                    )
                )
                == expected_ids
            ),
            candidate_path_absent=(
                not candidate.exists()
            ),
            quarantine_path_absent=(
                not quarantine.exists()
            ),
        )


__all__ = [
    "PRODUCTION_CUTOVER_PERMIT_SCHEMA_VERSION",
    "ProductionCutoverPermitKind",
    "ProductionCutoverPermit",
    "ProductionCutoverBlocker",
    "ProductionCutoverError",
    "ProductionCutoverResult",
    "execute_production_cutover",
]