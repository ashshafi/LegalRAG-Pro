from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import stat
from typing import Any

from finance_data.immutable_dataset import (
    ValidatedImmutableDataset,
    validate_immutable_dataset_document,
)
from finance_reporting.models import FinanceReportProjection


LOCATOR_SCHEMA_VERSION = "finance-dataset-locator/1.0"
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_LOCATOR_ROOT = _PROJECT_ROOT / "data" / "finance_dataset_locators"
_DEFAULT_DATASET_ROOT = _PROJECT_ROOT
_SAFE_WORKSPACE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

_LOCATOR_FIELDS = frozenset(
    {
        "schema_version",
        "workspace_id",
        "guard_report_projection_id",
        "guard_projection_dataset_identity",
        "dataset_path",
        "expected_provider_id",
        "expected_dataset_id",
        "expected_dataset_version",
        "expected_dataset_identity",
    }
)


class FinanceDatasetLocatorError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FinanceDatasetLocator:
    schema_version: str
    workspace_id: str
    guard_report_projection_id: str
    guard_projection_dataset_identity: str
    dataset_path: str
    expected_provider_id: str
    expected_dataset_id: str
    expected_dataset_version: str
    expected_dataset_identity: str


def _required_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise FinanceDatasetLocatorError(f"locator field {key!r} must be non-empty text")
    return value.strip()


def _canonical_workspace_id(workspace_id: str) -> str:
    if not isinstance(workspace_id, str):
        raise FinanceDatasetLocatorError("workspace_id must be text")
    value = workspace_id.strip()
    if not _SAFE_WORKSPACE.fullmatch(value) or value in {".", ".."}:
        raise FinanceDatasetLocatorError("workspace_id is not a safe locator key")
    return value


def active_finance_dataset_locator_path(
    workspace_id: str,
    *,
    locator_root: Path | None = None,
) -> Path:
    workspace = _canonical_workspace_id(workspace_id)
    root = _DEFAULT_LOCATOR_ROOT if locator_root is None else Path(locator_root)
    if not root.is_absolute():
        raise FinanceDatasetLocatorError("locator_root must be absolute")
    return root / workspace / "active.json"


def _read_plain_regular_file(path: Path, *, label: str) -> bytes:
    try:
        info = path.lstat()
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise FinanceDatasetLocatorError(f"cannot inspect {label}: {path}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise FinanceDatasetLocatorError(f"{label} must not be a symlink: {path}")
    if not stat.S_ISREG(info.st_mode):
        raise FinanceDatasetLocatorError(f"{label} must be a plain regular file: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise FinanceDatasetLocatorError(f"cannot read {label}: {path}") from exc


def _decode_json_object(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FinanceDatasetLocatorError(f"{label} is not UTF-8") from exc
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FinanceDatasetLocatorError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise FinanceDatasetLocatorError(f"{label} JSON root must be an object")
    return value


def _parse_locator(data: dict[str, Any]) -> FinanceDatasetLocator:
    fields = frozenset(data)
    if fields != _LOCATOR_FIELDS:
        missing = sorted(_LOCATOR_FIELDS - fields)
        extra = sorted(fields - _LOCATOR_FIELDS)
        raise FinanceDatasetLocatorError(
            f"locator fields are not exact; missing={missing!r}; extra={extra!r}"
        )
    schema_version = _required_text(data, "schema_version")
    if schema_version != LOCATOR_SCHEMA_VERSION:
        raise FinanceDatasetLocatorError(
            f"unsupported locator schema_version: {schema_version!r}"
        )
    workspace_id = _canonical_workspace_id(_required_text(data, "workspace_id"))
    dataset_path = _required_text(data, "dataset_path")
    parsed_path = Path(dataset_path)
    if not parsed_path.is_absolute() and ".." in parsed_path.parts:
        raise FinanceDatasetLocatorError("relative dataset_path must not contain parent traversal")
    return FinanceDatasetLocator(
        schema_version=schema_version,
        workspace_id=workspace_id,
        guard_report_projection_id=_required_text(data, "guard_report_projection_id"),
        guard_projection_dataset_identity=_required_text(
            data, "guard_projection_dataset_identity"
        ),
        dataset_path=dataset_path,
        expected_provider_id=_required_text(data, "expected_provider_id"),
        expected_dataset_id=_required_text(data, "expected_dataset_id"),
        expected_dataset_version=_required_text(data, "expected_dataset_version"),
        expected_dataset_identity=_required_text(data, "expected_dataset_identity"),
    )


def load_active_finance_dataset_locator(
    workspace_id: str,
    *,
    locator_root: Path | None = None,
) -> FinanceDatasetLocator | None:
    workspace = _canonical_workspace_id(workspace_id)
    path = active_finance_dataset_locator_path(workspace, locator_root=locator_root)
    if not path.exists():
        return None
    raw = _read_plain_regular_file(path, label="finance dataset locator")
    locator = _parse_locator(_decode_json_object(raw, label="finance dataset locator"))
    if locator.workspace_id != workspace:
        raise FinanceDatasetLocatorError(
            "locator workspace_id does not match requested workspace"
        )
    return locator


def _resolve_dataset_path(
    locator: FinanceDatasetLocator,
    *,
    dataset_root: Path | None = None,
) -> Path:
    raw = Path(locator.dataset_path)
    if raw.is_absolute():
        return raw
    root = _DEFAULT_DATASET_ROOT if dataset_root is None else Path(dataset_root)
    if not root.is_absolute():
        raise FinanceDatasetLocatorError("dataset_root must be absolute")
    candidate = root / raw
    try:
        root_resolved = root.resolve(strict=True)
        candidate_resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise FinanceDatasetLocatorError(
            f"cannot resolve immutable dataset path: {candidate}"
        ) from exc
    try:
        candidate_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise FinanceDatasetLocatorError(
            "relative dataset_path escapes the governed dataset root"
        ) from exc
    return candidate_resolved


def load_validated_immutable_dataset_for_projection(
    *,
    workspace_id: str,
    projection: FinanceReportProjection,
    locator_root: Path | None = None,
    dataset_root: Path | None = None,
) -> ValidatedImmutableDataset | None:
    workspace = _canonical_workspace_id(workspace_id)
    locator = load_active_finance_dataset_locator(
        workspace,
        locator_root=locator_root,
    )
    if locator is None:
        return None
    if projection.header.workspace_id != workspace:
        raise FinanceDatasetLocatorError(
            "live projection workspace_id does not match requested workspace"
        )
    if locator.guard_report_projection_id != projection.report_projection_id:
        raise FinanceDatasetLocatorError(
            "locator report-projection guard does not match the live projection"
        )
    if locator.guard_projection_dataset_identity != projection.header.dataset_identity:
        raise FinanceDatasetLocatorError(
            "locator projection-dataset guard does not match the live projection"
        )
    dataset_path = _resolve_dataset_path(locator, dataset_root=dataset_root)
    try:
        raw = _read_plain_regular_file(
            dataset_path,
            label="immutable finance dataset",
        )
    except FileNotFoundError as exc:
        raise FinanceDatasetLocatorError(
            f"immutable finance dataset is missing: {dataset_path}"
        ) from exc
    document = _decode_json_object(raw, label="immutable finance dataset")
    try:
        validated = validate_immutable_dataset_document(
            document,
            expected_provider_id=locator.expected_provider_id,
            expected_dataset_id=locator.expected_dataset_id,
            expected_dataset_version=locator.expected_dataset_version,
        )
    except Exception as exc:
        raise FinanceDatasetLocatorError(
            "immutable finance dataset failed public validation"
        ) from exc
    if validated.dataset_identity != locator.expected_dataset_identity:
        raise FinanceDatasetLocatorError(
            "immutable finance dataset identity does not match locator authority"
        )
    return validated


__all__ = [
    "FinanceDatasetLocator",
    "FinanceDatasetLocatorError",
    "LOCATOR_SCHEMA_VERSION",
    "active_finance_dataset_locator_path",
    "load_active_finance_dataset_locator",
    "load_validated_immutable_dataset_for_projection",
]
