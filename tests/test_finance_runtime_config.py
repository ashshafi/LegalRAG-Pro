from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from finance_runtime_config import FinanceRuntimeConfig, FinanceRuntimeConfigError


def test_immutable_config_preserves_provider_authority_exactly(tmp_path: Path) -> None:
    dataset_path = (tmp_path / "dataset.json").resolve()
    config = FinanceRuntimeConfig(
        provider_mode="immutable",
        dataset_path=dataset_path,
        expected_provider_id="provider-1",
        expected_dataset_id="dataset-1",
        expected_dataset_version="v1",
    )

    assert config.to_runtime_kwargs() == {
        "provider_mode": "immutable",
        "dataset_path": dataset_path,
        "expected_provider_id": "provider-1",
        "expected_dataset_id": "dataset-1",
        "expected_dataset_version": "v1",
    }


def test_frozen_demo_config_accepts_no_immutable_authority_fields() -> None:
    config = FinanceRuntimeConfig(provider_mode="frozen-demo")

    assert config.to_runtime_kwargs() == {
        "provider_mode": "frozen-demo",
        "dataset_path": None,
        "expected_provider_id": None,
        "expected_dataset_id": None,
        "expected_dataset_version": None,
    }


def test_frozen_demo_config_accepts_absolute_dataset_path(tmp_path: Path) -> None:
    dataset_path = (tmp_path / "frozen-demo.json").resolve()

    config = FinanceRuntimeConfig(
        provider_mode="frozen-demo",
        dataset_path=dataset_path,
    )

    assert config.dataset_path == dataset_path


@pytest.mark.parametrize("mode", ["", "IMMUTABLE", "Frozen-Demo", "demo", "live"])
def test_provider_mode_is_exact(mode: str) -> None:
    with pytest.raises(FinanceRuntimeConfigError, match="provider_mode"):
        FinanceRuntimeConfig(provider_mode=mode)


def test_relative_dataset_path_fails_closed() -> None:
    with pytest.raises(FinanceRuntimeConfigError, match="absolute"):
        FinanceRuntimeConfig(
            provider_mode="immutable",
            dataset_path=Path("relative/dataset.json"),
        )


def test_non_path_dataset_path_fails_closed() -> None:
    with pytest.raises(FinanceRuntimeConfigError, match="pathlib.Path"):
        FinanceRuntimeConfig(  # type: ignore[arg-type]
            provider_mode="immutable",
            dataset_path="C:/dataset.json",
        )


@pytest.mark.parametrize(
    ("field_name", "kwargs"),
    [
        ("expected_provider_id", {"expected_provider_id": "provider-1"}),
        ("expected_dataset_id", {"expected_dataset_id": "dataset-1"}),
        ("expected_dataset_version", {"expected_dataset_version": "v1"}),
    ],
)
def test_frozen_demo_rejects_immutable_authority_fields(
    field_name: str,
    kwargs: dict[str, str],
) -> None:
    with pytest.raises(FinanceRuntimeConfigError, match="does not accept"):
        FinanceRuntimeConfig(provider_mode="frozen-demo", **kwargs)

    assert field_name in {
        "expected_provider_id",
        "expected_dataset_id",
        "expected_dataset_version",
    }


@pytest.mark.parametrize(
    ("field_name", "kwargs"),
    [
        ("expected_provider_id", {"expected_provider_id": 1}),
        ("expected_dataset_id", {"expected_dataset_id": object()}),
        ("expected_dataset_version", {"expected_dataset_version": []}),
    ],
)
def test_authority_fields_must_be_strings_or_none(
    field_name: str,
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(FinanceRuntimeConfigError, match=field_name):
        FinanceRuntimeConfig(provider_mode="immutable", **kwargs)  # type: ignore[arg-type]


def test_config_is_frozen() -> None:
    config = FinanceRuntimeConfig(provider_mode="immutable")

    with pytest.raises(FrozenInstanceError):
        config.provider_mode = "frozen-demo"  # type: ignore[misc]


def test_adapter_has_exact_runtime_provider_authority_key_set() -> None:
    config = FinanceRuntimeConfig(provider_mode="immutable")

    assert tuple(config.to_runtime_kwargs()) == (
        "provider_mode",
        "dataset_path",
        "expected_provider_id",
        "expected_dataset_id",
        "expected_dataset_version",
    )
