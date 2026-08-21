"""Explicit fail-closed Finance data-provider selection boundary."""

from __future__ import annotations

from pathlib import Path

from finance_data.frozen_demo import FrozenDemoProvider
from finance_data.immutable_provider import ImmutableDatasetProvider
from finance_data.provider import FinancialDataProvider


PROVIDER_SELECTION_MODE_IMMUTABLE = "immutable"
PROVIDER_SELECTION_MODE_FROZEN_DEMO = "frozen-demo"


class FinanceDataProviderSelectionError(ValueError):
    """Raised when a Finance provider selection request is not explicit and valid."""


def _absolute_path_or_none(
    value: Path | None,
    *,
    field_name: str,
    required: bool,
) -> Path | None:
    if value is None:
        if required:
            raise FinanceDataProviderSelectionError(f"{field_name} is required.")
        return None
    if not isinstance(value, Path):
        raise FinanceDataProviderSelectionError(f"{field_name} must be a pathlib.Path.")
    if not value.is_absolute():
        raise FinanceDataProviderSelectionError(f"{field_name} must be an absolute explicit path.")
    return value


def _required_identity(value: str | None, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise FinanceDataProviderSelectionError(
            f"{field_name} must be an explicit non-empty canonical string."
        )
    return value


def select_financial_data_provider(
    *,
    mode: str,
    dataset_path: Path | None = None,
    expected_provider_id: str | None = None,
    expected_dataset_id: str | None = None,
    expected_dataset_version: str | None = None,
) -> FinancialDataProvider:
    """Select one explicit Finance provider without discovering authority implicitly."""

    if mode == PROVIDER_SELECTION_MODE_IMMUTABLE:
        selected_path = _absolute_path_or_none(
            dataset_path,
            field_name="dataset_path",
            required=True,
        )
        assert selected_path is not None
        return ImmutableDatasetProvider(
            dataset_path=selected_path,
            expected_provider_id=_required_identity(
                expected_provider_id,
                field_name="expected_provider_id",
            ),
            expected_dataset_id=_required_identity(
                expected_dataset_id,
                field_name="expected_dataset_id",
            ),
            expected_dataset_version=_required_identity(
                expected_dataset_version,
                field_name="expected_dataset_version",
            ),
        )

    if mode == PROVIDER_SELECTION_MODE_FROZEN_DEMO:
        if any(
            value is not None
            for value in (
                expected_provider_id,
                expected_dataset_id,
                expected_dataset_version,
            )
        ):
            raise FinanceDataProviderSelectionError(
                "Frozen demo selection does not accept immutable dataset authority fields."
            )
        return FrozenDemoProvider(
            dataset_path=_absolute_path_or_none(
                dataset_path,
                field_name="dataset_path",
                required=False,
            )
        )

    raise FinanceDataProviderSelectionError(
        "mode must be exactly 'immutable' or 'frozen-demo'."
    )
