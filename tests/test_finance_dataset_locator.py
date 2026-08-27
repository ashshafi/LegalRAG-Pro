from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import finance_dataset_locator as locator


def _projection(
    *,
    workspace_id: str = "workspace-1",
    report_projection_id: str = "sha256:projection",
    dataset_identity: str = "sha256:live-dataset",
):
    return SimpleNamespace(
        report_projection_id=report_projection_id,
        header=SimpleNamespace(
            workspace_id=workspace_id,
            dataset_identity=dataset_identity,
        ),
    )


def _sidecar(**overrides):
    data = {
        "schema_version": locator.LOCATOR_SCHEMA_VERSION,
        "workspace_id": "workspace-1",
        "guard_report_projection_id": "sha256:projection",
        "guard_projection_dataset_identity": "sha256:live-dataset",
        "dataset_path": "datasets/caci.json",
        "expected_provider_id": "caci-accounts-pdf",
        "expected_dataset_id": "CACI-01649776-HISTORICAL-2004-2006",
        "expected_dataset_version": "1",
        "expected_dataset_identity": "sha256:caci-dataset",
    }
    data.update(overrides)
    return data


def _write_locator(root: Path, data: dict) -> Path:
    path = root / "workspace-1" / "active.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_missing_locator_returns_none(tmp_path: Path):
    result = locator.load_validated_immutable_dataset_for_projection(
        workspace_id="workspace-1",
        projection=_projection(),
        locator_root=tmp_path / "locators",
        dataset_root=tmp_path,
    )
    assert result is None


def test_good_locator_uses_public_validator_and_returns_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    locators = tmp_path / "locators"
    _write_locator(locators, _sidecar())
    dataset = tmp_path / "datasets" / "caci.json"
    dataset.parent.mkdir()
    dataset.write_text('{"hello":"world"}', encoding="utf-8")
    sentinel = SimpleNamespace(dataset_identity="sha256:caci-dataset")
    observed = {}

    def fake_validate(document, **kwargs):
        observed["document"] = document
        observed["kwargs"] = kwargs
        return sentinel

    monkeypatch.setattr(locator, "validate_immutable_dataset_document", fake_validate)
    result = locator.load_validated_immutable_dataset_for_projection(
        workspace_id="workspace-1",
        projection=_projection(),
        locator_root=locators,
        dataset_root=tmp_path,
    )
    assert result is sentinel
    assert observed["document"] == {"hello": "world"}
    assert observed["kwargs"] == {
        "expected_provider_id": "caci-accounts-pdf",
        "expected_dataset_id": "CACI-01649776-HISTORICAL-2004-2006",
        "expected_dataset_version": "1",
    }


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("workspace_id", "workspace-2", "workspace_id"),
        ("guard_report_projection_id", "sha256:wrong", "report-projection guard"),
        (
            "guard_projection_dataset_identity",
            "sha256:wrong",
            "projection-dataset guard",
        ),
    ],
)
def test_locator_guards_fail_closed(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
):
    locators = tmp_path / "locators"
    _write_locator(locators, _sidecar(**{field: value}))
    with pytest.raises(locator.FinanceDatasetLocatorError, match=message):
        locator.load_validated_immutable_dataset_for_projection(
            workspace_id="workspace-1",
            projection=_projection(),
            locator_root=locators,
            dataset_root=tmp_path,
        )


def test_live_projection_workspace_guard_fails_closed(tmp_path: Path):
    locators = tmp_path / "locators"
    _write_locator(locators, _sidecar())
    with pytest.raises(locator.FinanceDatasetLocatorError, match="live projection workspace_id"):
        locator.load_validated_immutable_dataset_for_projection(
            workspace_id="workspace-1",
            projection=_projection(workspace_id="workspace-2"),
            locator_root=locators,
            dataset_root=tmp_path,
        )


def test_target_dataset_identity_guard_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    locators = tmp_path / "locators"
    _write_locator(locators, _sidecar())
    dataset = tmp_path / "datasets" / "caci.json"
    dataset.parent.mkdir()
    dataset.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        locator,
        "validate_immutable_dataset_document",
        lambda document, **kwargs: SimpleNamespace(dataset_identity="sha256:wrong"),
    )
    with pytest.raises(locator.FinanceDatasetLocatorError, match="identity"):
        locator.load_validated_immutable_dataset_for_projection(
            workspace_id="workspace-1",
            projection=_projection(),
            locator_root=locators,
            dataset_root=tmp_path,
        )


def test_relative_dataset_path_rejects_parent_traversal(tmp_path: Path):
    locators = tmp_path / "locators"
    _write_locator(locators, _sidecar(dataset_path="../outside.json"))
    with pytest.raises(locator.FinanceDatasetLocatorError, match="parent traversal"):
        locator.load_active_finance_dataset_locator(
            "workspace-1",
            locator_root=locators,
        )


def test_locator_rejects_extra_fields(tmp_path: Path):
    locators = tmp_path / "locators"
    data = _sidecar()
    data["unexpected"] = "x"
    _write_locator(locators, data)
    with pytest.raises(locator.FinanceDatasetLocatorError, match="fields are not exact"):
        locator.load_active_finance_dataset_locator(
            "workspace-1",
            locator_root=locators,
        )


def test_absolute_dataset_path_supported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    locators = tmp_path / "locators"
    dataset = tmp_path / "absolute.json"
    dataset.write_text("{}", encoding="utf-8")
    _write_locator(locators, _sidecar(dataset_path=str(dataset.resolve())))
    sentinel = SimpleNamespace(dataset_identity="sha256:caci-dataset")
    monkeypatch.setattr(
        locator,
        "validate_immutable_dataset_document",
        lambda document, **kwargs: sentinel,
    )
    result = locator.load_validated_immutable_dataset_for_projection(
        workspace_id="workspace-1",
        projection=_projection(),
        locator_root=locators,
        dataset_root=tmp_path,
    )
    assert result is sentinel
