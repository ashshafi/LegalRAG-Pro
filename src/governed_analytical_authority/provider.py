"""Read-only provider for explicitly activated governed analytical authorities."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat

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
        return None
    _require_safe_directory(governed_root, root=governed_root)
    case_root = governed_root / canonical_case_id
    if not case_root.exists():
        return None
    _require_safe_directory(case_root, root=governed_root)
    active_path = case_root / "active.json"
    if not active_path.exists():
        return None

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

    return GovernedRuntimeAnalyticalAuthority(
        manifest=published.manifest,
        structured_legal_analysis_results=published.structured_legal_analysis_results,
        case_matrices=published.case_matrices,
        governed_issue_evidence_map=published.governed_issue_evidence_map,
        governed_evidential_analysis=published.governed_evidential_analysis,
        active_pointer=pointer,
        activation_receipt=receipt,
    )


__all__ = [
    "GovernedAnalyticalAuthorityProviderError",
    "load_active_governed_analytical_authority",
]
