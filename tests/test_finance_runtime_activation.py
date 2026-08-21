from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

import finance_runtime_activation
from finance_comps import ComparableSetDefinition
from finance_reporting import FinanceReportProjection
from finance_runtime_config import FinanceRuntimeConfig


def _definition() -> ComparableSetDefinition:
    return cast(ComparableSetDefinition, object())


def test_activation_delegates_exact_provider_authority_and_explicit_runtime_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dataset_path = (tmp_path / "dataset.json").resolve()
    config = FinanceRuntimeConfig(
        provider_mode="immutable",
        dataset_path=dataset_path,
        expected_provider_id="provider-1",
        expected_dataset_id="dataset-1",
        expected_dataset_version="v1",
    )
    definition = _definition()
    documents = ("document-1",)
    entries = ("entry-1",)
    sentinel = cast(FinanceReportProjection, object())
    captured: dict[str, object] = {}

    def fake_build_finance_runtime_projection(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(
        finance_runtime_activation,
        "build_finance_runtime_projection",
        fake_build_finance_runtime_projection,
    )

    result = finance_runtime_activation.activate_finance_runtime(
        config=config,
        definition=definition,
        documents=documents,
        entries=entries,
    )

    assert result is sentinel
    assert captured == {
        "definition": definition,
        "documents": documents,
        "entries": entries,
        "provider_mode": "immutable",
        "dataset_path": dataset_path,
        "expected_provider_id": "provider-1",
        "expected_dataset_id": "dataset-1",
        "expected_dataset_version": "v1",
    }


def test_activation_delegates_frozen_demo_without_immutable_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = FinanceRuntimeConfig(provider_mode="frozen-demo")
    definition = _definition()
    sentinel = cast(FinanceReportProjection, object())
    captured: dict[str, object] = {}

    def fake_build_finance_runtime_projection(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(
        finance_runtime_activation,
        "build_finance_runtime_projection",
        fake_build_finance_runtime_projection,
    )

    result = finance_runtime_activation.activate_finance_runtime(
        config=config,
        definition=definition,
        documents=(),
        entries=(),
    )

    assert result is sentinel
    assert captured == {
        "definition": definition,
        "documents": (),
        "entries": (),
        "provider_mode": "frozen-demo",
        "dataset_path": None,
        "expected_provider_id": None,
        "expected_dataset_id": None,
        "expected_dataset_version": None,
    }


def test_activation_rejects_non_config_object_before_runtime_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_build_finance_runtime_projection(**kwargs):
        nonlocal called
        called = True
        return cast(FinanceReportProjection, object())

    monkeypatch.setattr(
        finance_runtime_activation,
        "build_finance_runtime_projection",
        fake_build_finance_runtime_projection,
    )

    with pytest.raises(TypeError, match="FinanceRuntimeConfig"):
        finance_runtime_activation.activate_finance_runtime(
            config=object(),  # type: ignore[arg-type]
            definition=_definition(),
            documents=(),
            entries=(),
        )

    assert called is False


def test_activation_does_not_mutate_config() -> None:
    config = FinanceRuntimeConfig(provider_mode="immutable")

    before = config.to_runtime_kwargs()

    assert config.to_runtime_kwargs() == before
