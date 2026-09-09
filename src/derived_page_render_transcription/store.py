from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
from uuid import UUID

from .models import PageRenderTranscriptionRecord
from .serialization import dumps_record, loads_record
from .validation import (
    validate_page_render_transcription_record,
    validate_raw_sha256,
    validate_sha256_id,
)


class PageRenderTranscriptionStoreError(RuntimeError):
    """Raised when immutable page-render transcription storage fails."""


class PageRenderTranscriptionStore:
    """Explicit-root immutable sidecar store for page-render derivatives."""

    def __init__(self, root: str | Path) -> None:
        if root is None:
            raise TypeError("PageRenderTranscriptionStore requires an explicit root.")
        self._root = Path(root).expanduser().resolve(strict=False)

    @property
    def root(self) -> Path:
        return self._root

    def put_blob(self, content: bytes) -> str:
        if type(content) is not bytes:
            raise TypeError("content must be exact bytes.")
        digest = hashlib.sha256(content).hexdigest()
        final = self._blob_path(digest)
        self._publish_exact_bytes(final, content, expected_sha256=digest)
        return digest

    def read_blob(self, sha256_hex: str) -> bytes:
        digest = validate_raw_sha256(sha256_hex, field_name="sha256_hex")
        raw = self._read_final_bytes(self._blob_path(digest), optional=False)
        assert raw is not None
        if hashlib.sha256(raw).hexdigest() != digest:
            raise PageRenderTranscriptionStoreError(
                "Stored page-render blob failed SHA-256 verification."
            )
        return raw

    def publish_record(self, record: PageRenderTranscriptionRecord) -> None:
        validate_page_render_transcription_record(record)
        canonical = dumps_record(record).encode("utf-8")
        final = self._record_path(
            record.case_id,
            record.source_document_instance_id,
            record.page_number,
            record.record_id,
        )
        self._publish_exact_bytes(final, canonical)

    def load_record(
        self,
        *,
        case_id: str,
        source_document_instance_id: str,
        page_number: int,
        record_id: str,
    ) -> PageRenderTranscriptionRecord:
        case = self._canonical_uuid(case_id, field_name="case_id")
        document = self._canonical_uuid(
            source_document_instance_id,
            field_name="source_document_instance_id",
        )
        page = self._positive_int(page_number, field_name="page_number")
        identifier = validate_sha256_id(record_id, field_name="record_id")

        raw = self._read_final_bytes(
            self._record_path(case, document, page, identifier),
            optional=False,
        )
        assert raw is not None
        try:
            payload = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise PageRenderTranscriptionStoreError(
                "Stored page-render record is not strict UTF-8."
            ) from exc

        record = loads_record(payload)
        validate_page_render_transcription_record(record)
        if (
            record.case_id != case
            or record.source_document_instance_id != document
            or record.page_number != page
            or record.record_id != identifier
        ):
            raise PageRenderTranscriptionStoreError(
                "Stored page-render record does not match requested coordinates."
            )
        return record

    def list_page_records(
        self,
        *,
        case_id: str,
        source_document_instance_id: str,
        page_number: int,
    ) -> tuple[PageRenderTranscriptionRecord, ...]:
        case = self._canonical_uuid(case_id, field_name="case_id")
        document = self._canonical_uuid(
            source_document_instance_id,
            field_name="source_document_instance_id",
        )
        page = self._positive_int(page_number, field_name="page_number")
        folder = self._page_records_path(case, document, page)

        if not folder.exists():
            return ()
        if not folder.is_dir():
            raise PageRenderTranscriptionStoreError(
                "Page-render record path is not a directory."
            )

        records: list[PageRenderTranscriptionRecord] = []
        for path in sorted(folder.glob("*.json")):
            records.append(
                self.load_record(
                    case_id=case,
                    source_document_instance_id=document,
                    page_number=page,
                    record_id=f"sha256:{path.stem}",
                )
            )
        return tuple(records)

    def read_transcription(self, record: PageRenderTranscriptionRecord) -> str:
        validate_page_render_transcription_record(record)
        raw = self.read_blob(record.transcription_sha256)
        if len(raw) != record.transcription_byte_length:
            raise PageRenderTranscriptionStoreError(
                "Page-render transcription byte length is invalid."
            )
        try:
            return raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise PageRenderTranscriptionStoreError(
                "Page-render transcription is not strict UTF-8."
            ) from exc

    def read_derived_artifact(self, record: PageRenderTranscriptionRecord) -> bytes:
        validate_page_render_transcription_record(record)
        raw = self.read_blob(record.derived_artifact_sha256)
        if len(raw) != record.derived_artifact_byte_length:
            raise PageRenderTranscriptionStoreError(
                "Derived page-render artifact byte length is invalid."
            )
        return raw

    def _blob_path(self, digest: str) -> Path:
        value = validate_raw_sha256(digest, field_name="sha256_hex")
        return self._contained_path("blobs", "sha256", value[:2], value)

    def _page_records_path(
        self,
        case_id: str,
        document_id: str,
        page_number: int,
    ) -> Path:
        return self._contained_path(
            "cases",
            case_id,
            "documents",
            document_id,
            "pages",
            str(page_number),
            "records",
        )

    def _record_path(
        self,
        case_id: str,
        document_id: str,
        page_number: int,
        record_id: str,
    ) -> Path:
        identifier = validate_sha256_id(record_id, field_name="record_id")
        return self._page_records_path(case_id, document_id, page_number) / (
            f"{identifier[7:]}.json"
        )

    def _contained_path(self, *parts: str) -> Path:
        candidate = self._root.joinpath(*parts).resolve(strict=False)
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise PageRenderTranscriptionStoreError(
                "Page-render transcription path escaped its configured root."
            ) from exc
        return candidate

    @staticmethod
    def _canonical_uuid(value: str, *, field_name: str) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{field_name} must be canonical UUID text.")
        try:
            parsed = UUID(value)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be canonical UUID text.") from exc
        canonical = str(parsed)
        if canonical != value:
            raise ValueError(f"{field_name} must be lowercase canonical UUID text.")
        return value

    @staticmethod
    def _positive_int(value: int, *, field_name: str) -> int:
        if type(value) is not int or value < 1:
            raise ValueError(f"{field_name} must be a positive integer.")
        return value

    def _read_final_bytes(self, path: Path, *, optional: bool) -> bytes | None:
        try:
            return path.read_bytes()
        except FileNotFoundError:
            if optional:
                return None
            raise PageRenderTranscriptionStoreError(
                "Required immutable page-render transcription object is absent."
            )
        except OSError as exc:
            raise PageRenderTranscriptionStoreError(
                "Unable to read immutable page-render transcription object."
            ) from exc

    @staticmethod
    def _ensure_directory(path: Path) -> None:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PageRenderTranscriptionStoreError(
                "Unable to create page-render transcription store directory."
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
            fd, raw_stage = tempfile.mkstemp(dir=final.parent, prefix=".dprt-stage-")
            staging = Path(raw_stage)
            try:
                os.chmod(staging, 0o600)
            except OSError:
                pass

            with os.fdopen(fd, "wb", closefd=True) as handle:
                handle.write(intended)
                handle.flush()
                os.fsync(handle.fileno())

            try:
                os.link(staging, final)
            except FileExistsError:
                pass
            except OSError as exc:
                raise PageRenderTranscriptionStoreError(
                    "Immutable page-render publication requires same-filesystem "
                    "hard-link create-if-absent support."
                ) from exc

            actual = self._read_final_bytes(final, optional=False)
            assert actual is not None
            if actual != intended:
                raise PageRenderTranscriptionStoreError(
                    "Immutable page-render object conflicts with an existing record."
                )
            if (
                expected_sha256 is not None
                and hashlib.sha256(actual).hexdigest() != expected_sha256
            ):
                raise PageRenderTranscriptionStoreError(
                    "Published page-render blob failed SHA-256 verification."
                )
        finally:
            if staging is not None:
                try:
                    staging.unlink(missing_ok=True)
                except OSError as exc:
                    raise PageRenderTranscriptionStoreError(
                        "Unable to remove page-render staging file."
                    ) from exc


__all__ = [
    "PageRenderTranscriptionStore",
    "PageRenderTranscriptionStoreError",
]
