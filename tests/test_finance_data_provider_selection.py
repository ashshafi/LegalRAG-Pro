from pathlib import Path

import pytest

from finance_data import provider_selection


def _forbid_constructor(*args, **kwargs):
    raise AssertionError("provider constructor must not be reached")


def test_immutable_selection_forwards_exact_explicit_authority(tmp_path, monkeypatch):
    captured = {}
    sentinel = object()

    def construct(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(provider_selection, "ImmutableDatasetProvider", construct)
    monkeypatch.setattr(provider_selection, "FrozenDemoProvider", _forbid_constructor)

    dataset_path = tmp_path / "immutable-dataset.json"
    selected = provider_selection.select_financial_data_provider(
        mode=provider_selection.PROVIDER_SELECTION_MODE_IMMUTABLE,
        dataset_path=dataset_path,
        expected_provider_id="provider-a",
        expected_dataset_id="dataset-a",
        expected_dataset_version="v1",
    )

    assert selected is sentinel
    assert captured == {
        "dataset_path": dataset_path,
        "expected_provider_id": "provider-a",
        "expected_dataset_id": "dataset-a",
        "expected_dataset_version": "v1",
    }


@pytest.mark.parametrize(
    ("field_name", "kwargs"),
    [
        (
            "dataset_path",
            {
                "dataset_path": None,
                "expected_provider_id": "provider-a",
                "expected_dataset_id": "dataset-a",
                "expected_dataset_version": "v1",
            },
        ),
        (
            "expected_provider_id",
            {
                "dataset_path": Path.cwd().resolve() / "dataset.json",
                "expected_provider_id": None,
                "expected_dataset_id": "dataset-a",
                "expected_dataset_version": "v1",
            },
        ),
        (
            "expected_dataset_id",
            {
                "dataset_path": Path.cwd().resolve() / "dataset.json",
                "expected_provider_id": "provider-a",
                "expected_dataset_id": "",
                "expected_dataset_version": "v1",
            },
        ),
        (
            "expected_dataset_version",
            {
                "dataset_path": Path.cwd().resolve() / "dataset.json",
                "expected_provider_id": "provider-a",
                "expected_dataset_id": "dataset-a",
                "expected_dataset_version": " v1 ",
            },
        ),
    ],
)
def test_immutable_selection_fails_closed_before_provider_construction(
    field_name,
    kwargs,
    monkeypatch,
):
    monkeypatch.setattr(provider_selection, "ImmutableDatasetProvider", _forbid_constructor)
    monkeypatch.setattr(provider_selection, "FrozenDemoProvider", _forbid_constructor)

    with pytest.raises(provider_selection.FinanceDataProviderSelectionError, match=field_name):
        provider_selection.select_financial_data_provider(
            mode=provider_selection.PROVIDER_SELECTION_MODE_IMMUTABLE,
            **kwargs,
        )


def test_immutable_selection_rejects_relative_or_non_path_dataset_path(monkeypatch):
    monkeypatch.setattr(provider_selection, "ImmutableDatasetProvider", _forbid_constructor)
    monkeypatch.setattr(provider_selection, "FrozenDemoProvider", _forbid_constructor)

    with pytest.raises(provider_selection.FinanceDataProviderSelectionError, match="absolute"):
        provider_selection.select_financial_data_provider(
            mode=provider_selection.PROVIDER_SELECTION_MODE_IMMUTABLE,
            dataset_path=Path("relative.json"),
            expected_provider_id="provider-a",
            expected_dataset_id="dataset-a",
            expected_dataset_version="v1",
        )

    with pytest.raises(provider_selection.FinanceDataProviderSelectionError, match="pathlib.Path"):
        provider_selection.select_financial_data_provider(
            mode=provider_selection.PROVIDER_SELECTION_MODE_IMMUTABLE,
            dataset_path="/tmp/dataset.json",
            expected_provider_id="provider-a",
            expected_dataset_id="dataset-a",
            expected_dataset_version="v1",
        )


def test_frozen_demo_selection_is_explicit_and_preserves_optional_path(tmp_path, monkeypatch):
    captured = []
    sentinel_default = object()
    sentinel_explicit = object()

    def construct(**kwargs):
        captured.append(kwargs)
        return sentinel_default if len(captured) == 1 else sentinel_explicit

    monkeypatch.setattr(provider_selection, "FrozenDemoProvider", construct)
    monkeypatch.setattr(provider_selection, "ImmutableDatasetProvider", _forbid_constructor)

    selected_default = provider_selection.select_financial_data_provider(
        mode=provider_selection.PROVIDER_SELECTION_MODE_FROZEN_DEMO,
    )
    explicit_path = tmp_path / "FIN-DEMO-001.json"
    selected_explicit = provider_selection.select_financial_data_provider(
        mode=provider_selection.PROVIDER_SELECTION_MODE_FROZEN_DEMO,
        dataset_path=explicit_path,
    )

    assert selected_default is sentinel_default
    assert selected_explicit is sentinel_explicit
    assert captured == [
        {"dataset_path": None},
        {"dataset_path": explicit_path},
    ]


def test_frozen_demo_rejects_immutable_authority_fields(monkeypatch):
    monkeypatch.setattr(provider_selection, "FrozenDemoProvider", _forbid_constructor)
    monkeypatch.setattr(provider_selection, "ImmutableDatasetProvider", _forbid_constructor)

    with pytest.raises(
        provider_selection.FinanceDataProviderSelectionError,
        match="does not accept immutable",
    ):
        provider_selection.select_financial_data_provider(
            mode=provider_selection.PROVIDER_SELECTION_MODE_FROZEN_DEMO,
            expected_provider_id="provider-a",
        )


def test_frozen_demo_rejects_relative_explicit_path(monkeypatch):
    monkeypatch.setattr(provider_selection, "FrozenDemoProvider", _forbid_constructor)
    monkeypatch.setattr(provider_selection, "ImmutableDatasetProvider", _forbid_constructor)

    with pytest.raises(provider_selection.FinanceDataProviderSelectionError, match="absolute"):
        provider_selection.select_financial_data_provider(
            mode=provider_selection.PROVIDER_SELECTION_MODE_FROZEN_DEMO,
            dataset_path=Path("FIN-DEMO-001.json"),
        )


def test_unknown_or_non_string_mode_fails_without_provider_construction(monkeypatch):
    monkeypatch.setattr(provider_selection, "FrozenDemoProvider", _forbid_constructor)
    monkeypatch.setattr(provider_selection, "ImmutableDatasetProvider", _forbid_constructor)

    for mode in ("auto", "live", "", None):
        with pytest.raises(provider_selection.FinanceDataProviderSelectionError, match="mode"):
            provider_selection.select_financial_data_provider(mode=mode)  # type: ignore[arg-type]
