"""Immutable exact-artifact persistence for governed work-product release."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from uuid import UUID


WORK_PRODUCT_ARTIFACT_BINDING_SCHEMA_VERSION = (
    "work-product-artifact-binding/1.0"
)

_DEFAULT_ROOT = Path("work_product_release")
_ROOT_ENV = "LEGALRAG_WORK_PRODUCT_RELEASE_ROOT"
_RAW_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class WorkProductArtifactStoreError(RuntimeError):
    """Raised when immutable work-product artifact storage cannot be trusted."""


@dataclass(frozen=True, slots=True)
class WorkProductArtifactBinding:
    """Immutable binding from one exact release target to published bytes."""

    schema_version: str
    binding_id: str
    case_id: str
    target_id: str
    report_projection_id: str
    projection_payload_sha256: str
    manifest_id: str
    artifact_format: str
    artifact_id: str
    artifact_sha256: str
    artifact_byte_length: int
    renderer_version: str
    output_profile: str


def _required(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(field_name + " must be text.")
    text = value.strip()
    if not text or text != value:
        raise ValueError(field_name + " must be non-empty trimmed text.")
    return text


def _uuid(value: object, field_name: str) -> str:
    text = _required(value, field_name)
    try:
        parsed = UUID(text)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(field_name + " must be a UUID.") from exc
    canonical = str(parsed)
    if text != canonical:
        raise ValueError(field_name + " must use canonical UUID text.")
    return canonical


def _sha256_hex(value: object, field_name: str) -> str:
    text = _required(value, field_name)
    if _RAW_SHA256_RE.fullmatch(text) is None:
        raise ValueError(field_name + " must be raw lowercase SHA-256.")
    return text


def _sha256_id(value: object, field_name: str) -> str:
    text = _required(value, field_name)
    prefix = "sha256:"
    if not text.startswith(prefix):
        raise ValueError(field_name + " must be a sha256: identity.")
    _sha256_hex(text[len(prefix):], field_name)
    return text


def _root(root: object = None) -> Path:
    if root is not None:
        return Path(root)
    configured = os.getenv(_ROOT_ENV, "").strip()
    return Path(configured) if configured else _DEFAULT_ROOT


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _binding_identity_payload(
    binding: WorkProductArtifactBinding,
) -> dict[str, object]:
    return {
        key: value
        for key, value in asdict(binding).items()
        if key != "binding_id"
    }


def _derive_binding_id(
    binding: WorkProductArtifactBinding,
) -> str:
    digest = sha256(
        _canonical_json_bytes(
            _binding_identity_payload(binding)
        )
    ).hexdigest()
    return "sha256:" + digest


def _validate_binding(
    binding: WorkProductArtifactBinding,
) -> WorkProductArtifactBinding:
    try:
        if (
            binding.schema_version
            != WORK_PRODUCT_ARTIFACT_BINDING_SCHEMA_VERSION
        ):
            raise ValueError(
                "Artifact binding schema version is invalid."
            )

        _sha256_id(binding.binding_id, "binding_id")
        _uuid(binding.case_id, "case_id")
        _sha256_id(binding.target_id, "target_id")
        _uuid(
            binding.report_projection_id,
            "report_projection_id",
        )
        _sha256_hex(
            binding.projection_payload_sha256,
            "projection_payload_sha256",
        )
        _uuid(binding.manifest_id, "manifest_id")
        _required(binding.artifact_format, "artifact_format")
        _uuid(binding.artifact_id, "artifact_id")
        _sha256_hex(
            binding.artifact_sha256,
            "artifact_sha256",
        )
        if (
            type(binding.artifact_byte_length) is not int
            or binding.artifact_byte_length < 0
        ):
            raise ValueError(
                "artifact_byte_length must be a non-negative integer."
            )
        _required(binding.renderer_version, "renderer_version")
        _required(binding.output_profile, "output_profile")
    except (TypeError, ValueError) as exc:
        raise WorkProductArtifactStoreError(str(exc)) from exc

    if binding.binding_id != _derive_binding_id(binding):
        raise WorkProductArtifactStoreError(
            "Artifact binding identity does not match its canonical payload."
        )

    return binding


def _binding_from_dict(
    raw: object,
) -> WorkProductArtifactBinding:
    if not isinstance(raw, dict):
        raise WorkProductArtifactStoreError(
            "Artifact binding is not a JSON object."
        )

    expected = {
        field.name
        for field in fields(
            WorkProductArtifactBinding
        )
    }

    if set(raw) != expected:
        raise WorkProductArtifactStoreError(
            "Artifact binding fields are not exact."
        )

    try:
        value = WorkProductArtifactBinding(**raw)
    except TypeError as exc:
        raise WorkProductArtifactStoreError(
            "Artifact binding could not be constructed."
        ) from exc

    return _validate_binding(value)


def _binding_bytes(
    binding: WorkProductArtifactBinding,
) -> bytes:
    _validate_binding(binding)
    return _canonical_json_bytes(asdict(binding))


def _build_binding(
    *,
    target: object,
    content: bytes,
) -> WorkProductArtifactBinding:
    try:
        case_id = _uuid(
            getattr(target, "case_id"),
            "case_id",
        )
        target_id = _sha256_id(
            getattr(target, "target_id"),
            "target_id",
        )
        report_projection_id = _uuid(
            getattr(target, "report_projection_id"),
            "report_projection_id",
        )
        projection_payload_sha256 = _sha256_hex(
            getattr(target, "projection_payload_sha256"),
            "projection_payload_sha256",
        )
        manifest_id = _uuid(
            getattr(target, "manifest_id"),
            "manifest_id",
        )
        artifact_format = _required(
            getattr(target, "artifact_format"),
            "artifact_format",
        )
        artifact_id = _uuid(
            getattr(target, "artifact_id"),
            "artifact_id",
        )
        artifact_sha256 = _sha256_hex(
            getattr(target, "artifact_sha256"),
            "artifact_sha256",
        )
        renderer_version = _required(
            getattr(target, "renderer_version"),
            "renderer_version",
        )
        output_profile = _required(
            getattr(target, "output_profile"),
            "output_profile",
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise WorkProductArtifactStoreError(
            "Release target does not provide a valid exact artifact identity."
        ) from exc

    actual_sha256 = sha256(content).hexdigest()

    if actual_sha256 != artifact_sha256:
        raise WorkProductArtifactStoreError(
            "Artifact bytes do not match target artifact_sha256."
        )

    provisional = WorkProductArtifactBinding(
        schema_version=(
            WORK_PRODUCT_ARTIFACT_BINDING_SCHEMA_VERSION
        ),
        binding_id="sha256:" + ("0" * 64),
        case_id=case_id,
        target_id=target_id,
        report_projection_id=report_projection_id,
        projection_payload_sha256=(
            projection_payload_sha256
        ),
        manifest_id=manifest_id,
        artifact_format=artifact_format,
        artifact_id=artifact_id,
        artifact_sha256=artifact_sha256,
        artifact_byte_length=len(content),
        renderer_version=renderer_version,
        output_profile=output_profile,
    )

    value = WorkProductArtifactBinding(
        **{
            **asdict(provisional),
            "binding_id": _derive_binding_id(provisional),
        }
    )

    return _validate_binding(value)


class WorkProductArtifactStore:
    """Immutable exact-byte store colocated with work-product release state."""

    def __init__(
        self,
        root: str | Path | None = None,
    ) -> None:
        self._root = _root(root)

    @property
    def root(self) -> Path:
        """Return the configured work-product root without creating it."""

        return self._root

    def publish_artifact(
        self,
        *,
        target: object,
        content: bytes,
    ) -> WorkProductArtifactBinding:
        """Publish exact bytes and immutable target binding, then verify."""

        if type(content) is not bytes:
            raise TypeError(
                "content must be exact bytes."
            )

        binding = _build_binding(
            target=target,
            content=content,
        )

        blob_path = self._blob_path(
            binding.case_id,
            binding.artifact_sha256,
        )

        binding_path = self._binding_path(
            binding.case_id,
            binding.target_id,
        )

        self._publish_exact_bytes(
            blob_path,
            content,
            expected_sha256=binding.artifact_sha256,
        )

        self._publish_exact_bytes(
            binding_path,
            _binding_bytes(binding),
        )

        loaded = self.load_binding(
            binding.case_id,
            binding.target_id,
        )

        if loaded != binding:
            raise WorkProductArtifactStoreError(
                "Published artifact binding failed exact read-back verification."
            )

        actual = self.read_artifact(
            binding.case_id,
            binding.target_id,
        )

        if actual != content:
            raise WorkProductArtifactStoreError(
                "Published artifact bytes failed exact read-back verification."
            )

        return binding

    def load_binding(
        self,
        case_id: str,
        target_id: str,
    ) -> WorkProductArtifactBinding:
        """Load one exact immutable target-to-artifact binding."""

        try:
            case = _uuid(case_id, "case_id")
            target = _sha256_id(target_id, "target_id")
        except (TypeError, ValueError) as exc:
            raise WorkProductArtifactStoreError(
                "Requested artifact coordinates are invalid."
            ) from exc

        path = self._binding_path(case, target)
        raw = self._read_final_bytes(path)

        try:
            text = raw.decode(
                "utf-8",
                errors="strict",
            )
        except UnicodeDecodeError as exc:
            raise WorkProductArtifactStoreError(
                "Artifact binding is not strict UTF-8."
            ) from exc

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise WorkProductArtifactStoreError(
                "Artifact binding is not valid JSON."
            ) from exc

        binding = _binding_from_dict(parsed)

        if (
            binding.case_id != case
            or binding.target_id != target
        ):
            raise WorkProductArtifactStoreError(
                "Artifact binding does not match requested coordinates."
            )

        if raw != _binding_bytes(binding):
            raise WorkProductArtifactStoreError(
                "Artifact binding is not canonical JSON."
            )

        return binding

    def read_artifact(
        self,
        case_id: str,
        target_id: str,
    ) -> bytes:
        """Read exact bytes without rebuilding current analytical authority."""

        binding = self.load_binding(
            case_id,
            target_id,
        )

        path = self._blob_path(
            binding.case_id,
            binding.artifact_sha256,
        )

        data = self._read_final_bytes(path)

        if sha256(data).hexdigest() != binding.artifact_sha256:
            raise WorkProductArtifactStoreError(
                "Stored work-product artifact failed SHA-256 verification."
            )

        if len(data) != binding.artifact_byte_length:
            raise WorkProductArtifactStoreError(
                "Stored work-product artifact byte length is invalid."
            )

        return data

    def _blob_path(
        self,
        case_id: str,
        digest: str,
    ) -> Path:
        try:
            case = _uuid(case_id, "case_id")
            sha = _sha256_hex(
                digest,
                "artifact_sha256",
            )
        except (TypeError, ValueError) as exc:
            raise WorkProductArtifactStoreError(
                "Artifact blob coordinates are invalid."
            ) from exc

        return self._contained_path(
            case,
            "artifacts",
            "blobs",
            "sha256",
            sha[:2],
            sha,
        )

    def _binding_path(
        self,
        case_id: str,
        target_id: str,
    ) -> Path:
        try:
            case = _uuid(case_id, "case_id")
            target = _sha256_id(
                target_id,
                "target_id",
            )
        except (TypeError, ValueError) as exc:
            raise WorkProductArtifactStoreError(
                "Artifact binding coordinates are invalid."
            ) from exc

        digest = target.split(":", 1)[1]

        return self._contained_path(
            case,
            "artifacts",
            "targets",
            digest + ".json",
        )

    @staticmethod
    def _normalise_resolved_path_for_containment(
        path: Path,
    ) -> Path:
        """Normalise equivalent resolved Windows path spellings for comparison."""

        if os.name != "nt":
            return path

        value = str(path)

        if value.startswith("\\\\?\\UNC\\"):
            value = "\\\\" + value[8:]
        elif value.startswith("\\\\?\\"):
            value = value[4:]

        return Path(
            os.path.normcase(
                os.path.normpath(
                    value
                )
            )
        )

    def _contained_path(
        self,
        *parts: str,
    ) -> Path:
        candidate = self._root.joinpath(*parts)
        root_resolved = self._normalise_resolved_path_for_containment(
            self._root.resolve(strict=False)
        )
        candidate_resolved = self._normalise_resolved_path_for_containment(
            candidate.resolve(strict=False)
        )

        try:
            candidate_resolved.relative_to(root_resolved)
        except ValueError as exc:
            raise WorkProductArtifactStoreError(
                "Unsafe work-product artifact path was rejected."
            ) from exc

        return candidate

    @staticmethod
    def _is_link_like(
        path: Path,
    ) -> bool:
        try:
            if path.is_symlink():
                return True
            isjunction = getattr(
                os.path,
                "isjunction",
                None,
            )
            return bool(
                isjunction
                and isjunction(path)
            )
        except OSError as exc:
            raise WorkProductArtifactStoreError(
                "Unable to inspect work-product artifact path."
            ) from exc

    def _verify_existing_directory(
        self,
        path: Path,
    ) -> None:
        if self._is_link_like(path):
            raise WorkProductArtifactStoreError(
                "Work-product artifact directory must not be a link."
            )

        if not path.is_dir():
            raise WorkProductArtifactStoreError(
                "Work-product artifact path component is not a directory."
            )

    def _ensure_directory(
        self,
        directory: Path,
    ) -> None:
        root_resolved = self._normalise_resolved_path_for_containment(
            self._root.resolve(strict=False)
        )
        directory_resolved = self._normalise_resolved_path_for_containment(
            directory.resolve(strict=False)
        )

        try:
            relative_parts = directory_resolved.relative_to(
                root_resolved
            ).parts
        except ValueError as exc:
            raise WorkProductArtifactStoreError(
                "Unsafe work-product artifact directory was rejected."
            ) from exc

        if self._root.exists() or self._is_link_like(self._root):
            self._verify_existing_directory(self._root)
        else:
            try:
                self._root.mkdir(
                    parents=True,
                    exist_ok=False,
                )
            except FileExistsError:
                self._verify_existing_directory(self._root)
            except OSError as exc:
                raise WorkProductArtifactStoreError(
                    "Unable to create work-product release root."
                ) from exc

        current = self._root

        for part in relative_parts:
            current = current / part

            if current.exists() or self._is_link_like(current):
                self._verify_existing_directory(current)
                continue

            try:
                current.mkdir(exist_ok=False)
            except FileExistsError:
                self._verify_existing_directory(current)
            except OSError as exc:
                raise WorkProductArtifactStoreError(
                    "Unable to create work-product artifact directory."
                ) from exc

    def _read_final_bytes(
        self,
        path: Path,
    ) -> bytes:
        if not path.exists() and not self._is_link_like(path):
            raise WorkProductArtifactStoreError(
                "Required immutable work-product artifact object is absent."
            )

        if self._is_link_like(path) or not path.is_file():
            raise WorkProductArtifactStoreError(
                "Immutable work-product artifact object is not a plain file."
            )

        try:
            path_resolved = self._normalise_resolved_path_for_containment(
                path.resolve(strict=True)
            )
            root_resolved = self._normalise_resolved_path_for_containment(
                self._root.resolve(strict=True)
            )
            path_resolved.relative_to(
                root_resolved
            )
        except (OSError, ValueError) as exc:
            raise WorkProductArtifactStoreError(
                "Unsafe work-product artifact object path was rejected."
            ) from exc

        try:
            return path.read_bytes()
        except OSError as exc:
            raise WorkProductArtifactStoreError(
                "Unable to read immutable work-product artifact object."
            ) from exc

    def _publish_exact_bytes(
        self,
        final: Path,
        intended: bytes,
        *,
        expected_sha256: str | None = None,
    ) -> None:
        self._ensure_directory(final.parent)
        staging: Path | None = None

        try:
            try:
                fd, raw_stage = tempfile.mkstemp(
                    dir=final.parent,
                    prefix=".wpa-stage-",
                )
                staging = Path(raw_stage)
            except OSError as exc:
                raise WorkProductArtifactStoreError(
                    "Unable to create work-product artifact staging file."
                ) from exc

            try:
                try:
                    os.chmod(staging, 0o600)
                except OSError:
                    pass

                with os.fdopen(
                    fd,
                    "wb",
                    closefd=True,
                ) as handle:
                    handle.write(intended)
                    handle.flush()
                    os.fsync(handle.fileno())
            except Exception:
                raise

            try:
                os.link(staging, final)
                won = True
            except FileExistsError:
                won = False
            except OSError as exc:
                raise WorkProductArtifactStoreError(
                    "Immutable work-product artifact publication requires "
                    "same-filesystem hard-link create-if-absent support."
                ) from exc

            actual = self._read_final_bytes(final)

            if actual != intended:
                raise WorkProductArtifactStoreError(
                    "Immutable work-product artifact object conflicts "
                    "with an existing object."
                )

            if (
                expected_sha256 is not None
                and sha256(actual).hexdigest() != expected_sha256
            ):
                raise WorkProductArtifactStoreError(
                    "Published work-product artifact failed SHA-256 verification."
                )

            if won:
                self._fsync_directory(final.parent)
        finally:
            if staging is not None:
                try:
                    staging.unlink(missing_ok=True)
                except OSError as exc:
                    raise WorkProductArtifactStoreError(
                        "Unable to remove work-product artifact staging file."
                    ) from exc

    @staticmethod
    def _fsync_directory(
        path: Path,
    ) -> None:
        if os.name == "nt":
            return

        try:
            descriptor = os.open(
                path,
                os.O_RDONLY,
            )
        except OSError as exc:
            raise WorkProductArtifactStoreError(
                "Unable to open work-product artifact directory for fsync."
            ) from exc

        try:
            os.fsync(descriptor)
        except OSError as exc:
            raise WorkProductArtifactStoreError(
                "Unable to fsync work-product artifact directory."
            ) from exc
        finally:
            os.close(descriptor)
