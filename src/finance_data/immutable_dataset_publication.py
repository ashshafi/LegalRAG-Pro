from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any
from uuid import uuid4

from finance_data.immutable_dataset import (
    IMMUTABLE_DATASET_SCHEMA_VERSION,
    ValidatedImmutableDataset,
    dumps_immutable_dataset_document,
    validate_immutable_dataset_document,
)
from finance_data.immutable_provider import ImmutableDatasetProvider
from finance_domain.serialization import (
    dumps_company,
    dumps_finance_workspace,
    dumps_financial_observation,
    dumps_financial_period,
    dumps_security,
)


class FinanceImmutableDatasetPublicationError(RuntimeError):
    """Raised when governed immutable Finance dataset publication fails closed."""


def _canonical_object(payload: str, *, field_name: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (TypeError, ValueError) as exc:
        raise FinanceImmutableDatasetPublicationError(
            f"{field_name} canonical serialization is invalid."
        ) from exc
    if not isinstance(value, dict):
        raise FinanceImmutableDatasetPublicationError(
            f"{field_name} canonical serialization must be an object."
        )
    return value


def _document_from_validated_dataset(
    dataset: ValidatedImmutableDataset,
) -> dict[str, Any]:
    if not isinstance(dataset, ValidatedImmutableDataset):
        raise FinanceImmutableDatasetPublicationError(
            "Finance immutable dataset publication requires ValidatedImmutableDataset authority."
        )

    document: dict[str, Any] = {
        "schema_version": IMMUTABLE_DATASET_SCHEMA_VERSION,
        "provider_id": dataset.provider_id,
        "dataset_id": dataset.dataset_id,
        "dataset_version": dataset.dataset_version,
        "dataset_identity": dataset.dataset_identity,
        "workspace": _canonical_object(
            dumps_finance_workspace(dataset.workspace),
            field_name="workspace",
        ),
        "companies": [
            _canonical_object(dumps_company(company), field_name="company")
            for company in dataset.companies
        ],
        "securities": [
            _canonical_object(dumps_security(security), field_name="security")
            for security in dataset.securities
        ],
        "periods": [
            _canonical_object(dumps_financial_period(period), field_name="period")
            for period in dataset.periods
        ],
        "observations": [
            _canonical_object(
                dumps_financial_observation(observation),
                field_name="observation",
            )
            for observation in dataset.observations
        ],
    }

    try:
        reconstructed = validate_immutable_dataset_document(
            document,
            expected_provider_id=dataset.provider_id,
            expected_dataset_id=dataset.dataset_id,
            expected_dataset_version=dataset.dataset_version,
        )
    except Exception as exc:
        raise FinanceImmutableDatasetPublicationError(
            "Validated immutable Finance dataset could not be reconstructed canonically."
        ) from exc

    if reconstructed != dataset:
        raise FinanceImmutableDatasetPublicationError(
            "Reconstructed immutable Finance dataset differs from validated authority."
        )
    return document


def _lstat_or_none(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise FinanceImmutableDatasetPublicationError(
            f"Unable to inspect Finance publication path: {path.name}"
        ) from exc


def _is_junction(path: Path) -> bool:
    checker = getattr(path, "is_junction", None)
    if checker is None:
        return False
    try:
        return bool(checker())
    except OSError as exc:
        raise FinanceImmutableDatasetPublicationError(
            f"Unable to inspect Finance publication junction boundary: {path.name}"
        ) from exc


def _require_plain_directory(path: Path) -> None:
    value = _lstat_or_none(path)
    if (
        value is None
        or not stat.S_ISDIR(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
        or _is_junction(path)
    ):
        raise FinanceImmutableDatasetPublicationError(
            f"Finance publication parent must be a plain directory: {path.name}"
        )


def _require_plain_directory_chain(path: Path) -> None:
    chain = tuple(reversed((path, *path.parents)))
    for current in chain:
        _require_plain_directory(current)


def _require_plain_regular_file(path: Path) -> None:
    value = _lstat_or_none(path)
    if (
        value is None
        or not stat.S_ISREG(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
        or _is_junction(path)
    ):
        raise FinanceImmutableDatasetPublicationError(
            f"Finance publication target must be a plain regular file: {path.name}"
        )


def _read_existing_target(path: Path) -> bytes | None:
    value = _lstat_or_none(path)
    if value is None:
        return None
    _require_plain_regular_file(path)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise FinanceImmutableDatasetPublicationError(
            "Unable to read existing immutable Finance dataset publication."
        ) from exc


def _write_staging_file(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise FinanceImmutableDatasetPublicationError(
            "Finance immutable dataset staging path unexpectedly already exists."
        ) from exc
    except OSError as exc:
        raise FinanceImmutableDatasetPublicationError(
            "Unable to write immutable Finance dataset staging file."
        ) from exc
    _require_plain_regular_file(path)


def _verify_provider_handoff(
    dataset: ValidatedImmutableDataset,
    target_path: Path,
) -> None:
    try:
        provider = ImmutableDatasetProvider(
            dataset_path=target_path,
            expected_provider_id=dataset.provider_id,
            expected_dataset_id=dataset.dataset_id,
            expected_dataset_version=dataset.dataset_version,
        )
    except Exception as exc:
        raise FinanceImmutableDatasetPublicationError(
            "Published immutable Finance dataset failed provider validation."
        ) from exc

    if (
        provider.provider_id != dataset.provider_id
        or provider.dataset_id != dataset.dataset_id
        or provider.dataset_version != dataset.dataset_version
        or provider.dataset_identity != dataset.dataset_identity
    ):
        raise FinanceImmutableDatasetPublicationError(
            "Published immutable Finance dataset provider authority differs from input."
        )


def publish_immutable_finance_dataset(
    dataset: ValidatedImmutableDataset,
    *,
    target_path: Path,
) -> Path:
    """Publish one validated immutable Finance dataset to one explicit path.

    Publication is create-if-absent and never overwrites an existing target.
    Identical existing bytes are idempotent; conflicting bytes fail closed.
    """

    if not isinstance(target_path, Path):
        raise FinanceImmutableDatasetPublicationError(
            "target_path must be an explicit pathlib.Path."
        )
    target = target_path
    if not target.is_absolute():
        raise FinanceImmutableDatasetPublicationError(
            "target_path must be absolute."
        )
    if not target.name:
        raise FinanceImmutableDatasetPublicationError(
            "target_path must name a dataset file."
        )

    document = _document_from_validated_dataset(dataset)
    try:
        payload = dumps_immutable_dataset_document(document).encode("utf-8")
    except Exception as exc:
        raise FinanceImmutableDatasetPublicationError(
            "Immutable Finance dataset is not valid canonical publication state."
        ) from exc

    _require_plain_directory_chain(target.parent)

    existing = _read_existing_target(target)
    if existing is not None:
        if existing == payload:
            _verify_provider_handoff(dataset, target)
            return target
        raise FinanceImmutableDatasetPublicationError(
            "Existing immutable Finance dataset conflicts with this publication."
        )

    staging = target.parent / f".{target.name}-{uuid4().hex}.tmp"
    _write_staging_file(staging, payload)

    try:
        try:
            os.link(staging, target)
        except FileExistsError:
            concurrent = _read_existing_target(target)
            if concurrent == payload:
                _verify_provider_handoff(dataset, target)
                return target
            raise FinanceImmutableDatasetPublicationError(
                "Concurrent immutable Finance dataset conflicts with this publication."
            )
        except OSError as exc:
            raise FinanceImmutableDatasetPublicationError(
                "Atomic create-if-absent immutable Finance dataset publication is unavailable."
            ) from exc

        _require_plain_regular_file(target)
        try:
            published = target.read_bytes()
        except OSError as exc:
            raise FinanceImmutableDatasetPublicationError(
                "Unable to verify published immutable Finance dataset."
            ) from exc
        if published != payload:
            raise FinanceImmutableDatasetPublicationError(
                "Published immutable Finance dataset bytes do not match canonical input."
            )

        _verify_provider_handoff(dataset, target)
        return target
    finally:
        try:
            staging.unlink(missing_ok=True)
        except OSError as exc:
            raise FinanceImmutableDatasetPublicationError(
                "Unable to remove this invocation's immutable Finance dataset staging file."
            ) from exc
