"""Immutable content-addressed persistence for source-evidence v1 records."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path
from typing import Callable, TypeVar

from .identity import canonical_uuid, sha256_bytes, validate_sha256_hex, validate_sha256_id
from .models import (
    EvidenceBinding,
    ProjectionEvidenceBindingManifest,
    SourceBoundAnalysisReceipt,
    SourceDocumentManifest,
)
from .serialization import (
    dumps_evidence_binding,
    dumps_projection_evidence_binding_manifest,
    dumps_source_bound_analysis_receipt,
    dumps_source_document_manifest,
    loads_evidence_binding,
    loads_projection_evidence_binding_manifest,
    loads_source_bound_analysis_receipt,
    loads_source_document_manifest,
)
from .validation import (
    validate_evidence_binding,
    validate_projection_evidence_binding_manifest,
    validate_source_bound_analysis_receipt,
    validate_source_document_manifest,
)

_T = TypeVar("_T")


class SourceEvidenceStoreError(RuntimeError):
    """Raised when immutable source-evidence persistence cannot be trusted."""


class SourceEvidenceStore:
    """Append-only source-evidence store with exact create-if-absent publication."""

    def __init__(self, root: Path | None = None) -> None:
        """Configure a versioned store root without creating filesystem state."""
        if root is None:
            project_root = Path(__file__).resolve().parents[2]
            configured = project_root / "source_evidence_store" / "v1"
        else:
            configured = Path(root)
        self._root = configured.expanduser().resolve(strict=False)

    @property
    def root(self) -> Path:
        """Return the configured exact versioned store root."""
        return self._root

    def put_blob(self, content: bytes) -> str:
        """Publish exact bytes by SHA-256 and return the raw lowercase digest."""
        if type(content) is not bytes:
            raise TypeError("content must be exact bytes.")
        digest = sha256_bytes(content)
        final = self._blob_path(digest)
        self._publish_exact_bytes(final, content, expected_blob_sha256=digest)
        return digest

    def read_blob(self, sha256_hex: str) -> bytes:
        """Read an immutable blob and re-verify its requested SHA-256."""
        digest = validate_sha256_hex(sha256_hex, field_name="sha256_hex")
        path = self._blob_path(digest)
        data = self._read_final_bytes(path, optional=False)
        assert data is not None
        if sha256_bytes(data) != digest:
            raise SourceEvidenceStoreError(
                "Stored source-evidence blob failed SHA-256 verification."
            )
        return data

    def publish_document_manifest(self, manifest: SourceDocumentManifest) -> None:
        """Publish a validated canonical immutable document manifest."""
        validate_source_document_manifest(manifest)
        canonical = dumps_source_document_manifest(manifest).encode("utf-8")
        final = self._document_manifest_path(
            manifest.case_id,
            manifest.source_document_instance_id,
        )
        self._publish_exact_bytes(final, canonical)

    def load_document_manifest(
        self,
        case_id: str,
        source_document_instance_id: str,
    ) -> SourceDocumentManifest:
        """Load the exact required document manifest for one case/document identity."""
        case = canonical_uuid(case_id, field_name="case_id")
        document = canonical_uuid(
            source_document_instance_id,
            field_name="source_document_instance_id",
        )
        path = self._document_manifest_path(case, document)
        value = self._load_record(path, loads_source_document_manifest, optional=False)
        assert value is not None
        if value.case_id != case or value.source_document_instance_id != document:
            raise SourceEvidenceStoreError(
                "Stored source-evidence document manifest does not match the requested identity."
            )
        return value

    def publish_evidence_binding(self, binding: EvidenceBinding) -> None:
        """Publish a validated immutable case/evidence binding."""
        validate_evidence_binding(binding)
        canonical = dumps_evidence_binding(binding).encode("utf-8")
        final = self._evidence_binding_path(binding.case_id, binding.evidence_key)
        self._publish_exact_bytes(final, canonical)

    def load_evidence_binding(
        self,
        case_id: str,
        evidence_key: str,
    ) -> EvidenceBinding | None:
        """Load an optional exact case/evidence binding."""
        case = canonical_uuid(case_id, field_name="case_id")
        key = self._validate_evidence_key(evidence_key)
        path = self._evidence_binding_path(case, key)
        value = self._load_record(path, loads_evidence_binding, optional=True)
        if value is None:
            return None
        if value.case_id != case or value.evidence_key != key:
            raise SourceEvidenceStoreError(
                "Stored source-evidence binding does not match the requested identity."
            )
        return value

    def publish_analysis_receipt(self, receipt: SourceBoundAnalysisReceipt) -> None:
        """Publish a validated immutable source-bound analysis receipt."""
        validate_source_bound_analysis_receipt(receipt)
        canonical = dumps_source_bound_analysis_receipt(receipt).encode("utf-8")
        final = self._analysis_receipt_path(
            receipt.case_id,
            receipt.source_bound_analysis_receipt_id,
        )
        self._publish_exact_bytes(final, canonical)

    def load_analysis_receipt(
        self,
        case_id: str,
        receipt_id: str,
    ) -> SourceBoundAnalysisReceipt:
        """Load one required source-bound analysis receipt."""
        case = canonical_uuid(case_id, field_name="case_id")
        receipt = validate_sha256_id(receipt_id, field_name="receipt_id")
        path = self._analysis_receipt_path(case, receipt)
        value = self._load_record(path, loads_source_bound_analysis_receipt, optional=False)
        assert value is not None
        if value.case_id != case or value.source_bound_analysis_receipt_id != receipt:
            raise SourceEvidenceStoreError(
                "Stored analysis receipt does not match the requested identity."
            )
        return value

    def publish_projection_binding(
        self,
        manifest: ProjectionEvidenceBindingManifest,
    ) -> None:
        """Publish a validated immutable projection evidence-binding manifest."""
        validate_projection_evidence_binding_manifest(manifest)
        canonical = dumps_projection_evidence_binding_manifest(manifest).encode("utf-8")
        final = self._projection_binding_path(manifest.case_id, manifest.report_projection_id)
        self._publish_exact_bytes(final, canonical)

    def load_projection_binding(
        self,
        case_id: str,
        report_projection_id: str,
    ) -> ProjectionEvidenceBindingManifest | None:
        """Load an optional projection evidence-binding manifest."""
        case = canonical_uuid(case_id, field_name="case_id")
        projection = canonical_uuid(report_projection_id, field_name="report_projection_id")
        path = self._projection_binding_path(case, projection)
        value = self._load_record(
            path,
            loads_projection_evidence_binding_manifest,
            optional=True,
        )
        if value is None:
            return None
        if value.case_id != case or value.report_projection_id != projection:
            raise SourceEvidenceStoreError(
                "Stored projection binding does not match the requested identity."
            )
        return value

    def _blob_path(self, digest: str) -> Path:
        validate_sha256_hex(digest, field_name="sha256_hex")
        return self._contained_path("blobs", "sha256", digest[:2], digest)

    def _document_manifest_path(self, case_id: str, document_id: str) -> Path:
        case = canonical_uuid(case_id, field_name="case_id")
        document = canonical_uuid(document_id, field_name="source_document_instance_id")
        return self._contained_path(
            "cases",
            case,
            "documents",
            document,
            "manifest.json",
        )

    def _evidence_binding_path(self, case_id: str, evidence_key: str) -> Path:
        case = canonical_uuid(case_id, field_name="case_id")
        key = self._validate_evidence_key(evidence_key)
        storage_key = sha256_bytes(case.encode("utf-8") + b"\0" + key.encode("utf-8"))
        return self._contained_path(
            "cases",
            case,
            "evidence-bindings",
            f"{storage_key}.json",
        )

    def _analysis_receipt_path(self, case_id: str, receipt_id: str) -> Path:
        case = canonical_uuid(case_id, field_name="case_id")
        receipt = validate_sha256_id(receipt_id, field_name="receipt_id")
        return self._contained_path(
            "cases",
            case,
            "analysis-receipts",
            f"{receipt[7:]}.json",
        )

    def _projection_binding_path(self, case_id: str, report_projection_id: str) -> Path:
        case = canonical_uuid(case_id, field_name="case_id")
        projection = canonical_uuid(report_projection_id, field_name="report_projection_id")
        return self._contained_path(
            "cases",
            case,
            "projection-bindings",
            f"{projection}.json",
        )

    @staticmethod
    def _validate_evidence_key(value: str) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError("evidence_key must not be empty.")
        return value

    def _contained_path(self, *parts: str) -> Path:
        path = self._root.joinpath(*parts)
        try:
            path.relative_to(self._root)
        except ValueError as exc:
            raise SourceEvidenceStoreError(
                "Unsafe source-evidence store path was rejected."
            ) from exc
        return path

    @staticmethod
    def _is_link_like(path: Path) -> bool:
        try:
            if path.is_symlink():
                return True
            is_junction = getattr(path, "is_junction", None)
            return bool(is_junction and is_junction())
        except OSError as exc:
            raise SourceEvidenceStoreError(
                "Unable to validate source-evidence store path safety."
            ) from exc

    def _verify_existing_directory(self, path: Path) -> None:
        if self._is_link_like(path):
            raise SourceEvidenceStoreError(
                "Unsafe source-evidence store path was rejected."
            )
        try:
            info = os.lstat(path)
        except OSError as exc:
            raise SourceEvidenceStoreError(
                "Unable to inspect source-evidence store directory."
            ) from exc
        if not stat.S_ISDIR(info.st_mode):
            raise SourceEvidenceStoreError(
                "Source-evidence store path component is not a directory."
            )
        try:
            path.resolve(strict=True).relative_to(self._root)
        except (OSError, ValueError) as exc:
            raise SourceEvidenceStoreError(
                "Unsafe source-evidence store path was rejected."
            ) from exc

    def _ensure_directory(self, directory: Path) -> None:
        try:
            relative = directory.relative_to(self._root)
        except ValueError as exc:
            raise SourceEvidenceStoreError(
                "Unsafe source-evidence store path was rejected."
            ) from exc

        current = self._root
        if current.exists() or current.is_symlink():
            self._verify_existing_directory(current)
        else:
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass
            except OSError as exc:
                raise SourceEvidenceStoreError(
                    "Unable to create source-evidence store directory."
                ) from exc
            self._verify_existing_directory(current)

        for part in relative.parts:
            current = current / part
            if current.exists() or current.is_symlink():
                self._verify_existing_directory(current)
                continue
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass
            except OSError as exc:
                raise SourceEvidenceStoreError(
                    "Unable to create source-evidence store directory."
                ) from exc
            self._verify_existing_directory(current)

    def _read_final_bytes(self, path: Path, *, optional: bool) -> bytes | None:
        try:
            relative = path.relative_to(self._root)
        except ValueError as exc:
            raise SourceEvidenceStoreError(
                "Unsafe source-evidence store path was rejected."
            ) from exc

        current = self._root
        if not current.exists() and not current.is_symlink():
            if optional:
                return None
            raise SourceEvidenceStoreError("Required source-evidence record is missing.")
        self._verify_existing_directory(current)

        for part in relative.parts[:-1]:
            current = current / part
            if not current.exists() and not current.is_symlink():
                if optional:
                    return None
                raise SourceEvidenceStoreError("Required source-evidence record is missing.")
            self._verify_existing_directory(current)

        if not path.exists() and not path.is_symlink():
            if optional:
                return None
            raise SourceEvidenceStoreError("Required source-evidence record is missing.")
        if self._is_link_like(path):
            raise SourceEvidenceStoreError(
                "Unsafe source-evidence store path was rejected."
            )
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            if optional:
                return None
            raise SourceEvidenceStoreError("Required source-evidence record is missing.")
        except OSError as exc:
            raise SourceEvidenceStoreError(
                "Unable to inspect source-evidence store object."
            ) from exc
        if not stat.S_ISREG(info.st_mode):
            raise SourceEvidenceStoreError(
                "Source-evidence store object is not a regular file."
            )
        try:
            path.resolve(strict=True).relative_to(self._root)
            return path.read_bytes()
        except (OSError, ValueError) as exc:
            raise SourceEvidenceStoreError(
                "Unable to read source-evidence store object safely."
            ) from exc

    def _load_record(
        self,
        path: Path,
        loader: Callable[[str], _T],
        *,
        optional: bool,
    ) -> _T | None:
        data = self._read_final_bytes(path, optional=optional)
        if data is None:
            return None
        try:
            payload = data.decode("utf-8", errors="strict")
            return loader(payload)
        except (UnicodeDecodeError, ValueError, TypeError) as exc:
            raise SourceEvidenceStoreError(
                "Stored source-evidence record failed canonical validation."
            ) from exc

    def _publish_exact_bytes(
        self,
        final: Path,
        intended: bytes,
        *,
        expected_blob_sha256: str | None = None,
    ) -> None:
        self._ensure_directory(final.parent)
        staging: Path | None = None
        try:
            try:
                fd, raw_stage = tempfile.mkstemp(
                    dir=final.parent,
                    prefix=".ise-stage-",
                )
                staging = Path(raw_stage)
            except OSError as exc:
                raise SourceEvidenceStoreError(
                    "Unable to create source-evidence staging file."
                ) from exc

            try:
                try:
                    os.chmod(staging, 0o600)
                except OSError:
                    pass
                with os.fdopen(fd, "wb", closefd=True) as handle:
                    handle.write(intended)
                    handle.flush()
                    os.fsync(handle.fileno())
            except Exception:
                # fdopen owns the descriptor once entered; cleanup below owns only this stage path.
                raise

            try:
                os.link(staging, final)
                won = True
            except FileExistsError:
                won = False
            except OSError as exc:
                raise SourceEvidenceStoreError(
                    "Immutable publication requires same-filesystem hard-link create-if-absent support."
                ) from exc

            actual = self._read_final_bytes(final, optional=False)
            assert actual is not None
            if actual != intended:
                raise SourceEvidenceStoreError(
                    "Immutable source-evidence object conflicts with an existing record."
                )
            if expected_blob_sha256 is not None and sha256_bytes(actual) != expected_blob_sha256:
                raise SourceEvidenceStoreError(
                    "Stored source-evidence blob failed SHA-256 verification."
                )

            if won:
                self._fsync_directory(final.parent)
        except SourceEvidenceStoreError:
            raise
        except OSError as exc:
            raise SourceEvidenceStoreError(
                "Unable to publish immutable source-evidence object."
            ) from exc
        finally:
            if staging is not None:
                try:
                    staging.unlink(missing_ok=True)
                except OSError as exc:
                    raise SourceEvidenceStoreError(
                        "Unable to remove this invocation's source-evidence staging file."
                    ) from exc

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        if os.name == "nt":
            return
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        try:
            fd = os.open(directory, flags)
        except OSError:
            return
        try:
            os.fsync(fd)
        except OSError:
            return
        finally:
            os.close(fd)


__all__ = ["SourceEvidenceStore", "SourceEvidenceStoreError"]
