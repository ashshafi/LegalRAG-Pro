from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
from uuid import UUID

from .models import DerivedTranscriptionRecord
from .serialization import dumps_record, loads_record
from .validation import (
    validate_derived_transcription_record,
    validate_raw_sha256,
    validate_sha256_id,
)


class DerivedTranscriptionStoreError(RuntimeError):
    """Raised when immutable derived-transcription storage fails."""


class DerivedTranscriptionStore:
    """Explicit-root immutable sidecar store.

    C1 intentionally has no default production root.
    """

    def __init__(self, root: str | Path) -> None:
        if root is None:
            raise TypeError(
                "DerivedTranscriptionStore requires an explicit root."
            )

        self._root = Path(root).expanduser().resolve(
            strict=False
        )

    @property
    def root(self) -> Path:
        return self._root

    def put_blob(self, content: bytes) -> str:
        if type(content) is not bytes:
            raise TypeError(
                "content must be exact bytes."
            )

        digest = hashlib.sha256(content).hexdigest()

        final = self._blob_path(digest)

        self._publish_exact_bytes(
            final,
            content,
            expected_sha256=digest,
        )

        return digest

    def read_blob(self, sha256_hex: str) -> bytes:
        digest = validate_raw_sha256(
            sha256_hex,
            field_name="sha256_hex",
        )

        path = self._blob_path(digest)

        data = self._read_final_bytes(
            path,
            optional=False,
        )

        assert data is not None

        if hashlib.sha256(data).hexdigest() != digest:
            raise DerivedTranscriptionStoreError(
                "Stored derived-transcription blob failed SHA-256 verification."
            )

        return data

    def publish_record(
        self,
        record: DerivedTranscriptionRecord,
    ) -> None:
        validate_derived_transcription_record(record)

        canonical = dumps_record(record).encode(
            "utf-8"
        )

        final = self._record_path(
            record.case_id,
            record.source_document_instance_id,
            record.page_number,
            record.record_id,
        )

        self._publish_exact_bytes(
            final,
            canonical,
        )

    def load_record(
        self,
        *,
        case_id: str,
        source_document_instance_id: str,
        page_number: int,
        record_id: str,
    ) -> DerivedTranscriptionRecord:
        case = self._canonical_uuid(
            case_id,
            field_name="case_id",
        )

        document = self._canonical_uuid(
            source_document_instance_id,
            field_name="source_document_instance_id",
        )

        page = self._positive_int(
            page_number,
            field_name="page_number",
        )

        identifier = validate_sha256_id(
            record_id,
            field_name="record_id",
        )

        path = self._record_path(
            case,
            document,
            page,
            identifier,
        )

        raw = self._read_final_bytes(
            path,
            optional=False,
        )

        assert raw is not None

        try:
            text = raw.decode(
                "utf-8",
                errors="strict",
            )
        except UnicodeDecodeError as exc:
            raise DerivedTranscriptionStoreError(
                "Stored transcription record is not strict UTF-8."
            ) from exc

        record = loads_record(text)

        validate_derived_transcription_record(record)

        if (
            record.case_id != case
            or record.source_document_instance_id
            != document
            or record.page_number != page
            or record.record_id != identifier
        ):
            raise DerivedTranscriptionStoreError(
                "Stored transcription record does not match requested coordinates."
            )

        return record

    def list_page_records(
        self,
        *,
        case_id: str,
        source_document_instance_id: str,
        page_number: int,
    ) -> tuple[DerivedTranscriptionRecord, ...]:
        case = self._canonical_uuid(
            case_id,
            field_name="case_id",
        )

        document = self._canonical_uuid(
            source_document_instance_id,
            field_name="source_document_instance_id",
        )

        page = self._positive_int(
            page_number,
            field_name="page_number",
        )

        folder = self._page_records_path(
            case,
            document,
            page,
        )

        if not folder.exists():
            return ()

        if not folder.is_dir():
            raise DerivedTranscriptionStoreError(
                "Derived-transcription page record path is not a directory."
            )

        records: list[DerivedTranscriptionRecord] = []

        for path in sorted(folder.glob("*.json")):
            identifier = f"sha256:{path.stem}"

            records.append(
                self.load_record(
                    case_id=case,
                    source_document_instance_id=document,
                    page_number=page,
                    record_id=identifier,
                )
            )

        return tuple(records)

    def read_transcription(
        self,
        record: DerivedTranscriptionRecord,
    ) -> str:
        validate_derived_transcription_record(record)

        raw = self.read_blob(
            record.transcription_sha256
        )

        if len(raw) != record.transcription_byte_length:
            raise DerivedTranscriptionStoreError(
                "Derived transcription byte length is invalid."
            )

        try:
            return raw.decode(
                "utf-8",
                errors="strict",
            )
        except UnicodeDecodeError as exc:
            raise DerivedTranscriptionStoreError(
                "Derived transcription blob is not strict UTF-8."
            ) from exc

    def read_embedded_image(
        self,
        record: DerivedTranscriptionRecord,
    ) -> bytes:
        validate_derived_transcription_record(record)

        raw = self.read_blob(
            record.embedded_image_sha256
        )

        if len(raw) != record.embedded_image_byte_length:
            raise DerivedTranscriptionStoreError(
                "Embedded-image byte length is invalid."
            )

        return raw

    def _blob_path(
        self,
        digest: str,
    ) -> Path:
        value = validate_raw_sha256(
            digest,
            field_name="sha256_hex",
        )

        return self._contained_path(
            "blobs",
            "sha256",
            value[:2],
            value,
        )

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
        identifier = validate_sha256_id(
            record_id,
            field_name="record_id",
        )

        return (
            self._page_records_path(
                case_id,
                document_id,
                page_number,
            )
            / f"{identifier[7:]}.json"
        )

    def _contained_path(
        self,
        *parts: str,
    ) -> Path:
        candidate = (
            self._root.joinpath(*parts)
            .resolve(strict=False)
        )

        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise DerivedTranscriptionStoreError(
                "Derived-transcription path escaped its configured root."
            ) from exc

        return candidate

    @staticmethod
    def _canonical_uuid(
        value: str,
        *,
        field_name: str,
    ) -> str:
        if not isinstance(value, str):
            raise ValueError(
                f"{field_name} must be canonical UUID text."
            )

        try:
            parsed = UUID(value)
        except ValueError as exc:
            raise ValueError(
                f"{field_name} must be canonical UUID text."
            ) from exc

        canonical = str(parsed)

        if canonical != value:
            raise ValueError(
                f"{field_name} must be lowercase canonical UUID text."
            )

        return canonical

    @staticmethod
    def _positive_int(
        value: int,
        *,
        field_name: str,
    ) -> int:
        if type(value) is not int or value < 1:
            raise ValueError(
                f"{field_name} must be a positive integer."
            )

        return value

    def _read_final_bytes(
        self,
        path: Path,
        *,
        optional: bool,
    ) -> bytes | None:
        try:
            return path.read_bytes()
        except FileNotFoundError:
            if optional:
                return None
            raise DerivedTranscriptionStoreError(
                "Required immutable derived-transcription object is absent."
            )
        except OSError as exc:
            raise DerivedTranscriptionStoreError(
                "Unable to read immutable derived-transcription object."
            ) from exc

    @staticmethod
    def _ensure_directory(
        path: Path,
    ) -> None:
        try:
            path.mkdir(
                parents=True,
                exist_ok=True,
            )
        except OSError as exc:
            raise DerivedTranscriptionStoreError(
                "Unable to create derived-transcription store directory."
            ) from exc

    def _publish_exact_bytes(
        self,
        final: Path,
        intended: bytes,
        *,
        expected_sha256: str | None = None,
    ) -> None:
        self._ensure_directory(
            final.parent
        )

        staging: Path | None = None

        try:
            try:
                fd, raw_stage = tempfile.mkstemp(
                    dir=final.parent,
                    prefix=".dt-stage-",
                )
                staging = Path(raw_stage)
            except OSError as exc:
                raise DerivedTranscriptionStoreError(
                    "Unable to create derived-transcription staging file."
                ) from exc

            try:
                try:
                    os.chmod(
                        staging,
                        0o600,
                    )
                except OSError:
                    pass

                with os.fdopen(
                    fd,
                    "wb",
                    closefd=True,
                ) as handle:
                    handle.write(intended)
                    handle.flush()
                    os.fsync(
                        handle.fileno()
                    )
            except Exception:
                raise

            try:
                os.link(
                    staging,
                    final,
                )
                won = True
            except FileExistsError:
                won = False
            except OSError as exc:
                raise DerivedTranscriptionStoreError(
                    "Immutable derived-transcription publication requires same-filesystem hard-link support."
                ) from exc

            actual = self._read_final_bytes(
                final,
                optional=False,
            )

            assert actual is not None

            if actual != intended:
                raise DerivedTranscriptionStoreError(
                    "Immutable derived-transcription object conflicts with an existing record."
                )

            if (
                expected_sha256 is not None
                and hashlib.sha256(actual).hexdigest()
                != expected_sha256
            ):
                raise DerivedTranscriptionStoreError(
                    "Published derived-transcription blob failed SHA-256 verification."
                )

            if won:
                self._fsync_directory(
                    final.parent
                )

        finally:
            if staging is not None:
                try:
                    staging.unlink(
                        missing_ok=True
                    )
                except OSError as exc:
                    raise DerivedTranscriptionStoreError(
                        "Unable to remove derived-transcription staging file."
                    ) from exc

    @staticmethod
    def _fsync_directory(
        path: Path,
    ) -> None:
        if os.name == "nt":
            return

        descriptor: int | None = None

        try:
            descriptor = os.open(
                path,
                os.O_RDONLY,
            )
            os.fsync(descriptor)
        except OSError:
            return
        finally:
            if descriptor is not None:
                os.close(descriptor)


__all__ = [
    "DerivedTranscriptionStore",
    "DerivedTranscriptionStoreError",
]
