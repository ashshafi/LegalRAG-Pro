"""Immutable provider-authority configuration for the Finance runtime composition boundary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from finance_data.provider_selection import (
    PROVIDER_SELECTION_MODE_FROZEN_DEMO,
    PROVIDER_SELECTION_MODE_IMMUTABLE,
)


class FinanceRuntimeConfigError(ValueError):
    """Raised when Finance runtime provider-authority configuration is invalid."""


@dataclass(frozen=True, slots=True)
class FinanceRuntimeConfig:
    """Pure provider-selection authority for one explicit Finance runtime invocation."""

    provider_mode: str
    dataset_path: Path | None = None
    expected_provider_id: str | None = None
    expected_dataset_id: str | None = None
    expected_dataset_version: str | None = None

    def __post_init__(self) -> None:
        allowed_modes = {
            PROVIDER_SELECTION_MODE_IMMUTABLE,
            PROVIDER_SELECTION_MODE_FROZEN_DEMO,
        }
        if self.provider_mode not in allowed_modes:
            raise FinanceRuntimeConfigError(
                "provider_mode must be exactly 'immutable' or 'frozen-demo'."
            )

        if self.dataset_path is not None:
            if not isinstance(self.dataset_path, Path):
                raise FinanceRuntimeConfigError(
                    "dataset_path must be a pathlib.Path or None."
                )
            if not self.dataset_path.is_absolute():
                raise FinanceRuntimeConfigError(
                    "dataset_path must be absolute when provided."
                )

        authority_fields = (
            ("expected_provider_id", self.expected_provider_id),
            ("expected_dataset_id", self.expected_dataset_id),
            ("expected_dataset_version", self.expected_dataset_version),
        )
        for field_name, value in authority_fields:
            if value is not None and not isinstance(value, str):
                raise FinanceRuntimeConfigError(
                    f"{field_name} must be a string or None."
                )

        if self.provider_mode == PROVIDER_SELECTION_MODE_FROZEN_DEMO:
            if any(value is not None for _, value in authority_fields):
                raise FinanceRuntimeConfigError(
                    "Frozen demo runtime configuration does not accept "
                    "immutable dataset authority fields."
                )

    def to_runtime_kwargs(self) -> dict[str, object]:
        """Return only the provider-authority keywords accepted by the runtime composer."""

        return {
            "provider_mode": self.provider_mode,
            "dataset_path": self.dataset_path,
            "expected_provider_id": self.expected_provider_id,
            "expected_dataset_id": self.expected_dataset_id,
            "expected_dataset_version": self.expected_dataset_version,
        }


__all__ = [
    "FinanceRuntimeConfig",
    "FinanceRuntimeConfigError",
]
