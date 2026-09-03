"""Read-only provider for explicitly activated governed analytical authorities."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import stat
from threading import RLock

from case_analysis.m2.matrix_serialization import dumps_case_matrices, loads_case_matrices
from governed_evidence_analysis.serialization import (
    dumps_governed_evidential_analysis,
    loads_governed_evidential_analysis,
)
from governed_issue_evidence.serialization import (
    dumps_governed_issue_evidence_map,
    loads_governed_issue_evidence_map,
)

from .identity import canonical_sha256, require_canonical_case_id, sha256_storage_name
from .models import (
    GOVERNED_ANALYTICAL_AUTHORITY_POINTER_SCHEMA_VERSION,
    GOVERNED_ANALYTICAL_AUTHORITY_ROOT_NAME,
    GovernedAnalyticalAuthorityActivationAction,
    GovernedAnalyticalAuthorityActivePointer,
    GovernedRuntimeAnalyticalAuthority,
)
from .serialization import (
    dumps_governed_analytical_authority_activation_receipt,
    dumps_governed_analytical_authority_active_pointer,
    dumps_governed_analytical_authority_manifest,
    dumps_structured_legal_analysis_results,
    loads_governed_analytical_authority_activation_receipt,
    loads_governed_analytical_authority_active_pointer,
    loads_governed_analytical_authority_manifest,
    loads_structured_legal_analysis_results,
)
from .validation import (
    validate_governed_analytical_authority_activation_receipt,
    validate_governed_analytical_authority_active_pointer,
    validate_governed_analytical_authority_manifest,
)


_OBJECT_FILENAMES = frozenset(
    {
        "manifest.json",
        "structured_legal_analysis_results.json",
        "case_matrices.json",
        "governed_issue_evidence_map.json",
        "governed_evidential_analysis.json",
    }
)


class GovernedAnalyticalAuthorityProviderError(RuntimeError):
    """Raised when selected persisted authority state is present but invalid."""


@dataclass(frozen=True, slots=True)
class _RuntimeAuthorityCacheEntry:
    authority: GovernedRuntimeAnalyticalAuthority
    directories: tuple[str, ...]
    exact_listing_directories: tuple[str, ...]
    files: tuple[str, ...]
    fingerprint: str


_RUNTIME_AUTHORITY_CACHE_LIMIT = 4
_RUNTIME_AUTHORITY_CACHE: OrderedDict[
    tuple[str, str],
    _RuntimeAuthorityCacheEntry,
] = OrderedDict()
_RUNTIME_AUTHORITY_CACHE_LOCK = RLock()


def _drop_runtime_authority_cache(case_id: str) -> None:
    with _RUNTIME_AUTHORITY_CACHE_LOCK:
        stale = tuple(
            key for key in _RUNTIME_AUTHORITY_CACHE
            if key[0] == case_id
        )
        for key in stale:
            _RUNTIME_AUTHORITY_CACHE.pop(key, None)


def _runtime_authority_cache_get(
    *,
    case_id: str,
    root_identity: str,
) -> _RuntimeAuthorityCacheEntry | None:
    key = (case_id, root_identity)
    with _RUNTIME_AUTHORITY_CACHE_LOCK:
        value = _RUNTIME_AUTHORITY_CACHE.get(key)
        if value is None:
            return None
        _RUNTIME_AUTHORITY_CACHE.move_to_end(key)
        return value


def _runtime_authority_cache_put(
    *,
    case_id: str,
    root_identity: str,
    entry: _RuntimeAuthorityCacheEntry,
) -> None:
    key = (case_id, root_identity)
    with _RUNTIME_AUTHORITY_CACHE_LOCK:
        stale = tuple(
            candidate for candidate in _RUNTIME_AUTHORITY_CACHE
            if candidate[0] == case_id and candidate != key
        )
        for candidate in stale:
            _RUNTIME_AUTHORITY_CACHE.pop(candidate, None)
        _RUNTIME_AUTHORITY_CACHE[key] = entry
        _RUNTIME_AUTHORITY_CACHE.move_to_end(key)
        while len(_RUNTIME_AUTHORITY_CACHE) > _RUNTIME_AUTHORITY_CACHE_LIMIT:
            _RUNTIME_AUTHORITY_CACHE.popitem(last=False)


@dataclass(frozen=True, slots=True)
class _PublishedAuthority:
    manifest: object
    structured_legal_analysis_results: tuple[object, ...]
    case_matrices: object
    governed_issue_evidence_map: object
    governed_evidential_analysis: object
    manifest_payload: str


def _authority_root() -> Path:
    return Path(__file__).resolve().parents[2] / GOVERNED_ANALYTICAL_AUTHORITY_ROOT_NAME


def _is_reparse(path: Path) -> bool:
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError as exc:
        raise GovernedAnalyticalAuthorityProviderError(
            f"Filesystem inspection failed for governed authority path: {path}"
        ) from exc
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & flag)


def _reject_link_or_reparse(path: Path) -> None:
    try:
        if path.is_symlink() or _is_reparse(path):
            raise GovernedAnalyticalAuthorityProviderError(
                f"Governed authority path must not be a symlink/junction/reparse point: {path}"
            )
    except OSError as exc:
        raise GovernedAnalyticalAuthorityProviderError(
            f"Filesystem inspection failed for governed authority path: {path}"
        ) from exc


def _require_safe_directory(path: Path, *, root: Path) -> None:
    if not path.exists():
        raise GovernedAnalyticalAuthorityProviderError(
            f"Required governed authority directory is missing: {path}"
        )
    _reject_link_or_reparse(path)
    try:
        if not path.is_dir():
            raise GovernedAnalyticalAuthorityProviderError(
                f"Governed authority directory path is not a directory: {path}"
            )
        resolved_root = root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        if resolved != resolved_root and resolved_root not in resolved.parents:
            raise GovernedAnalyticalAuthorityProviderError(
                "Governed authority directory escapes the internally derived root."
            )
    except OSError as exc:
        raise GovernedAnalyticalAuthorityProviderError(
            f"Filesystem containment check failed for governed authority path: {path}"
        ) from exc


def _require_safe_file(path: Path, *, root: Path) -> None:
    if not path.exists():
        raise GovernedAnalyticalAuthorityProviderError(
            f"Required governed authority file is missing: {path.name}"
        )
    _reject_link_or_reparse(path)
    try:
        mode = path.stat().st_mode
        if not stat.S_ISREG(mode):
            raise GovernedAnalyticalAuthorityProviderError(
                f"Governed authority path is not a regular file: {path}"
            )
        resolved_root = root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        if resolved_root not in resolved.parents:
            raise GovernedAnalyticalAuthorityProviderError(
                "Governed authority file escapes the internally derived root."
            )
    except OSError as exc:
        raise GovernedAnalyticalAuthorityProviderError(
            f"Filesystem containment check failed for governed authority file: {path}"
        ) from exc


def _read_utf8(path: Path, *, root: Path) -> str:
    _require_safe_file(path, root=root)
    try:
        return path.read_bytes().decode("utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise GovernedAnalyticalAuthorityProviderError(
            f"Governed authority file could not be read as strict UTF-8: {path.name}"
        ) from exc


def _runtime_cache_dependencies(
    *,
    chain: tuple[object, ...],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    authority_ids: list[str] = []
    seen_authorities: set[str] = set()
    receipt_files: list[str] = []

    for receipt in chain:
        authority_id = str(receipt.new_authority_id)
        if authority_id not in seen_authorities:
            seen_authorities.add(authority_id)
            authority_ids.append(authority_id)
        receipt_files.append(
            "activations/"
            + sha256_storage_name(
                str(receipt.activation_id),
                field_name="activation_id",
            )
            + ".json"
        )

    object_directories = tuple(
        "objects/"
        + sha256_storage_name(authority_id, field_name="authority_id")
        for authority_id in authority_ids
    )
    files: list[str] = ["active.json", *receipt_files]
    for directory in object_directories:
        files.extend(
            f"{directory}/{filename}"
            for filename in sorted(_OBJECT_FILENAMES)
        )

    directories = ("objects", "activations", *object_directories)
    return directories, object_directories, tuple(files)


def _runtime_cache_fingerprint(
    case_root: Path,
    *,
    root: Path,
    root_identity: str,
    directories: tuple[str, ...],
    exact_listing_directories: tuple[str, ...],
    files: tuple[str, ...],
) -> str:
    """Hash exactly the filesystem state that the validated provider result depended on."""

    digest = sha256()
    digest.update(b"legalrag-governed-authority-cache-dependencies/1\0")
    digest.update(root_identity.encode("utf-8"))
    digest.update(b"\0")

    for relative in directories:
        directory = case_root / Path(relative)
        _require_safe_directory(directory, root=root)
        digest.update(b"D\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")

    for relative in exact_listing_directories:
        directory = case_root / Path(relative)
        _require_safe_directory(directory, root=root)
        try:
            names = tuple(sorted(item.name for item in directory.iterdir()))
        except OSError as exc:
            raise GovernedAnalyticalAuthorityProviderError(
                "Unable to inspect immutable governed authority object for cache identity."
            ) from exc
        digest.update(b"L\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        for name in names:
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")

    for relative in files:
        path = case_root / Path(relative)
        _require_safe_file(path, root=root)
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise GovernedAnalyticalAuthorityProviderError(
                "Unable to read governed authority dependency for cache identity."
            ) from exc
        digest.update(b"F\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(sha256(payload).digest())

    return digest.hexdigest()


def _load_published_authority(
    *,
    case_id: str,
    authority_id: str,
    root: Path | None = None,
) -> _PublishedAuthority:
    """Load one exact already-published object; never search or select by recency."""

    try:
        canonical_case_id = require_canonical_case_id(case_id)
        authority_storage_name = sha256_storage_name(authority_id, field_name="authority_id")
    except ValueError as exc:
        raise GovernedAnalyticalAuthorityProviderError("Invalid governed authority identity.") from exc

    governed_root = root or _authority_root()
    _require_safe_directory(governed_root, root=governed_root)
    case_root = governed_root / canonical_case_id
    objects_root = case_root / "objects"
    object_root = objects_root / authority_storage_name
    for directory in (case_root, objects_root, object_root):
        _require_safe_directory(directory, root=governed_root)

    try:
        names = frozenset(item.name for item in object_root.iterdir())
    except OSError as exc:
        raise GovernedAnalyticalAuthorityProviderError(
            "Unable to inspect immutable governed authority object."
        ) from exc
    if names != _OBJECT_FILENAMES:
        raise GovernedAnalyticalAuthorityProviderError(
            f"Immutable authority object file set is not exact; observed={sorted(names)}."
        )

    manifest_payload = _read_utf8(object_root / "manifest.json", root=governed_root)
    m5_payload = _read_utf8(
        object_root / "structured_legal_analysis_results.json", root=governed_root
    )
    matrices_payload = _read_utf8(object_root / "case_matrices.json", root=governed_root)
    u9b_payload = _read_utf8(
        object_root / "governed_issue_evidence_map.json", root=governed_root
    )
    u9c_payload = _read_utf8(
        object_root / "governed_evidential_analysis.json", root=governed_root
    )

    try:
        manifest = loads_governed_analytical_authority_manifest(manifest_payload)
        results = loads_structured_legal_analysis_results(m5_payload)
        matrices = loads_case_matrices(matrices_payload)
        if dumps_case_matrices(matrices) != matrices_payload:
            raise ValueError("CaseMatrices stored bytes are not canonical.")
        u9b = loads_governed_issue_evidence_map(u9b_payload)
        if dumps_governed_issue_evidence_map(u9b) != u9b_payload:
            raise ValueError("U9B stored bytes are not canonical.")
        u9c = loads_governed_evidential_analysis(u9c_payload, u9b)
        if dumps_governed_evidential_analysis(u9c, u9b) != u9c_payload:
            raise ValueError("U9C-B1 stored bytes are not canonical.")
        if dumps_structured_legal_analysis_results(results) != m5_payload:
            raise ValueError("M5 stored bytes are not canonical.")
        if dumps_governed_analytical_authority_manifest(manifest) != manifest_payload:
            raise ValueError("Manifest stored bytes are not canonical.")
        validate_governed_analytical_authority_manifest(
            manifest,
            structured_legal_analysis_results=results,
            case_matrices=matrices,
            governed_issue_evidence_map=u9b,
            governed_evidential_analysis=u9c,
        )
    except (TypeError, ValueError) as exc:
        raise GovernedAnalyticalAuthorityProviderError(
            "Published governed analytical authority failed canonical or lineage validation."
        ) from exc

    if manifest.case_id != canonical_case_id or manifest.authority_id != authority_id:
        raise GovernedAnalyticalAuthorityProviderError(
            "Published authority object does not match its requested case/authority identity."
        )
    return _PublishedAuthority(
        manifest=manifest,
        structured_legal_analysis_results=results,
        case_matrices=matrices,
        governed_issue_evidence_map=u9b,
        governed_evidential_analysis=u9c,
        manifest_payload=manifest_payload,
    )



def _load_validated_activation_chain(
    *,
    case_id: str,
    current_activation_id: str,
    root: Path,
) -> tuple[object, ...]:
    """Validate immutable activation history newest-to-oldest without mutating state."""

    activations_root = root / case_id / "activations"
    _require_safe_directory(activations_root, root=root)
    seen: set[str] = set()
    chain: list[object] = []
    next_id: str | None = current_activation_id
    newer = None
    while next_id is not None:
        if next_id in seen:
            raise GovernedAnalyticalAuthorityProviderError("Activation history contains a cycle.")
        seen.add(next_id)
        name = sha256_storage_name(next_id, field_name="activation_id") + ".json"
        payload = _read_utf8(activations_root / name, root=root)
        try:
            receipt = loads_governed_analytical_authority_activation_receipt(payload)
            if dumps_governed_analytical_authority_activation_receipt(receipt) != payload:
                raise ValueError("Activation receipt stored bytes are not canonical.")
            if receipt.case_id != case_id or receipt.activation_id != next_id:
                raise ValueError("Activation receipt is cross-case or misnamed.")
            from .identity import derive_governed_analytical_authority_activation_id

            expected_id = derive_governed_analytical_authority_activation_id(
                case_id=receipt.case_id,
                action=receipt.action,
                previous_activation_id=receipt.previous_activation_id,
                previous_authority_id=receipt.previous_authority_id,
                new_authority_id=receipt.new_authority_id,
                previous_active_pointer_sha256=receipt.previous_active_pointer_sha256,
                schema_version=receipt.schema_version,
            )
            if receipt.activation_id != expected_id:
                raise ValueError("Activation receipt identity mismatch.")
            published = _load_published_authority(
                case_id=case_id,
                authority_id=receipt.new_authority_id,
                root=root,
            )
            historic_pointer = GovernedAnalyticalAuthorityActivePointer(
                schema_version=GOVERNED_ANALYTICAL_AUTHORITY_POINTER_SCHEMA_VERSION,
                case_id=case_id,
                authority_id=receipt.new_authority_id,
                authority_manifest_sha256=canonical_sha256(published.manifest_payload),
                activation_id=receipt.activation_id,
            )
            historic_pointer_payload = dumps_governed_analytical_authority_active_pointer(
                historic_pointer
            )
            if receipt.new_active_pointer_sha256 != canonical_sha256(historic_pointer_payload):
                raise ValueError("Activation receipt new pointer SHA mismatch.")
            if newer is not None:
                if newer.previous_activation_id != receipt.activation_id:
                    raise ValueError("Activation previous_activation_id chain mismatch.")
                if newer.previous_authority_id != receipt.new_authority_id:
                    raise ValueError("Activation previous_authority_id chain mismatch.")
                if newer.previous_active_pointer_sha256 != canonical_sha256(historic_pointer_payload):
                    raise ValueError("Activation previous pointer SHA chain mismatch.")
            if receipt.previous_activation_id is None:
                if receipt.action is not GovernedAnalyticalAuthorityActivationAction.ACTIVATE:
                    raise ValueError("First activation action must be ACTIVATE.")
                if receipt.previous_authority_id is not None or receipt.previous_active_pointer_sha256 is not None:
                    raise ValueError("First activation receipt claims previous pointer state.")
            else:
                if receipt.previous_authority_id is None or receipt.previous_active_pointer_sha256 is None:
                    raise ValueError("Activation receipt omits previous pointer provenance.")
        except (TypeError, ValueError) as exc:
            raise GovernedAnalyticalAuthorityProviderError(
                "Activation history failed deterministic lineage validation."
            ) from exc
        chain.append(receipt)
        newer = receipt
        next_id = receipt.previous_activation_id
    return tuple(chain)

def load_active_governed_analytical_authority(
    case_id: str,
) -> GovernedRuntimeAnalyticalAuthority | None:
    """Load the exact explicitly selected authority or return ``None`` only for ABSENT."""

    try:
        canonical_case_id = require_canonical_case_id(case_id)
    except ValueError as exc:
        raise GovernedAnalyticalAuthorityProviderError("Invalid canonical case_id.") from exc

    governed_root = _authority_root()
    if not governed_root.exists():
        _drop_runtime_authority_cache(canonical_case_id)
        return None
    _require_safe_directory(governed_root, root=governed_root)
    case_root = governed_root / canonical_case_id
    if not case_root.exists():
        _drop_runtime_authority_cache(canonical_case_id)
        return None
    _require_safe_directory(case_root, root=governed_root)
    active_path = case_root / "active.json"
    if not active_path.exists():
        _drop_runtime_authority_cache(canonical_case_id)
        return None

    try:
        root_identity = str(governed_root.resolve(strict=True))
    except OSError as exc:
        raise GovernedAnalyticalAuthorityProviderError(
            "Governed authority root could not be resolved for cache identity."
        ) from exc

    cached = _runtime_authority_cache_get(
        case_id=canonical_case_id,
        root_identity=root_identity,
    )
    if cached is not None:
        current_fingerprint = _runtime_cache_fingerprint(
            case_root,
            root=governed_root,
            root_identity=root_identity,
            directories=cached.directories,
            exact_listing_directories=cached.exact_listing_directories,
            files=cached.files,
        )
        if current_fingerprint == cached.fingerprint:
            return cached.authority

    active_payload = _read_utf8(active_path, root=governed_root)
    try:
        pointer = loads_governed_analytical_authority_active_pointer(active_payload)
        validate_governed_analytical_authority_active_pointer(pointer)
    except (TypeError, ValueError) as exc:
        raise GovernedAnalyticalAuthorityProviderError(
            "Active governed analytical-authority pointer is invalid."
        ) from exc
    if pointer.case_id != canonical_case_id:
        raise GovernedAnalyticalAuthorityProviderError(
            "Active governed analytical-authority pointer is cross-case."
        )

    published = _load_published_authority(
        case_id=canonical_case_id,
        authority_id=pointer.authority_id,
        root=governed_root,
    )
    manifest_sha = canonical_sha256(published.manifest_payload)
    if pointer.authority_manifest_sha256 != manifest_sha:
        raise GovernedAnalyticalAuthorityProviderError(
            "Active pointer authority_manifest_sha256 does not match immutable manifest bytes."
        )

    chain = _load_validated_activation_chain(
        case_id=canonical_case_id,
        current_activation_id=pointer.activation_id,
        root=governed_root,
    )
    if not chain:
        raise GovernedAnalyticalAuthorityProviderError(
            "Active pointer has no immutable activation receipt."
        )
    receipt = chain[0]
    if receipt.new_authority_id != pointer.authority_id:
        raise GovernedAnalyticalAuthorityProviderError(
            "Active pointer authority does not match its activation receipt."
        )
    if receipt.new_active_pointer_sha256 != canonical_sha256(active_payload):
        raise GovernedAnalyticalAuthorityProviderError(
            "Active pointer bytes do not match their activation receipt."
        )

    runtime_authority = GovernedRuntimeAnalyticalAuthority(
        manifest=published.manifest,
        structured_legal_analysis_results=published.structured_legal_analysis_results,
        case_matrices=published.case_matrices,
        governed_issue_evidence_map=published.governed_issue_evidence_map,
        governed_evidential_analysis=published.governed_evidential_analysis,
        active_pointer=pointer,
        activation_receipt=receipt,
    )

    directories, exact_listing_directories, files = _runtime_cache_dependencies(
        chain=chain,
    )
    fingerprint = _runtime_cache_fingerprint(
        case_root,
        root=governed_root,
        root_identity=root_identity,
        directories=directories,
        exact_listing_directories=exact_listing_directories,
        files=files,
    )
    _runtime_authority_cache_put(
        case_id=canonical_case_id,
        root_identity=root_identity,
        entry=_RuntimeAuthorityCacheEntry(
            authority=runtime_authority,
            directories=directories,
            exact_listing_directories=exact_listing_directories,
            files=files,
            fingerprint=fingerprint,
        ),
    )
    return runtime_authority


__all__ = [
    "GovernedAnalyticalAuthorityProviderError",
    "load_active_governed_analytical_authority",
]
