from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

import finance_workspace_catalog as catalog


def _projection(workspace_id: str, *, suffix: str = "a"):
    header = SimpleNamespace(
        workspace_id=workspace_id,
        as_of=datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc),
        provider_id=f"provider-{suffix}",
        dataset_id=f"dataset-{suffix}",
        dataset_version=f"version-{suffix}",
    )
    return SimpleNamespace(
        header=header,
        report_projection_id=f"projection-{suffix}",
    )


def _workspace_dir(root: Path, workspace_id: str) -> Path:
    path = root / workspace_id
    path.mkdir(parents=True)
    return path


def test_absent_catalog_root_is_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(catalog, "_catalog_root", lambda: tmp_path / "missing")
    assert catalog.load_published_finance_workspace_catalog() == ()


def test_catalog_is_deterministic_and_uses_trusted_projection_loader(monkeypatch, tmp_path):
    first = str(uuid4())
    second = str(uuid4())
    for workspace_id in (second, first):
        _workspace_dir(tmp_path, workspace_id)

    values = {
        first: _projection(first, suffix="first"),
        second: _projection(second, suffix="second"),
    }
    calls = []

    monkeypatch.setattr(catalog, "_catalog_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalog,
        "load_active_finance_report_projection",
        lambda workspace_id: calls.append(workspace_id) or values[workspace_id],
    )

    result = catalog.load_published_finance_workspace_catalog()

    expected_ids = tuple(sorted((first, second)))
    assert tuple(item.workspace_id for item in result) == expected_ids
    assert tuple(calls) == expected_ids
    assert result[0].report_projection_id == values[expected_ids[0]].report_projection_id


def test_workspace_without_active_projection_is_not_catalogued(monkeypatch, tmp_path):
    workspace_id = str(uuid4())
    _workspace_dir(tmp_path, workspace_id)

    monkeypatch.setattr(catalog, "_catalog_root", lambda: tmp_path)
    monkeypatch.setattr(catalog, "load_active_finance_report_projection", lambda _: None)

    assert catalog.load_published_finance_workspace_catalog() == ()


def test_non_directory_catalog_child_fails_closed(monkeypatch, tmp_path):
    (tmp_path / "unexpected.txt").write_text("not a workspace", encoding="utf-8")
    monkeypatch.setattr(catalog, "_catalog_root", lambda: tmp_path)

    with pytest.raises(catalog.FinanceWorkspaceCatalogError):
        catalog.load_published_finance_workspace_catalog()


def test_noncanonical_workspace_directory_fails_closed(monkeypatch, tmp_path):
    canonical = str(uuid4())
    noncanonical = canonical.upper()
    assert noncanonical != canonical
    _workspace_dir(tmp_path, noncanonical)
    monkeypatch.setattr(catalog, "_catalog_root", lambda: tmp_path)

    with pytest.raises(catalog.FinanceWorkspaceCatalogError):
        catalog.load_published_finance_workspace_catalog()


def test_projection_identity_must_match_catalog_directory(monkeypatch, tmp_path):
    workspace_id = str(uuid4())
    _workspace_dir(tmp_path, workspace_id)

    monkeypatch.setattr(catalog, "_catalog_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalog,
        "load_active_finance_report_projection",
        lambda _: _projection(str(uuid4()), suffix="wrong"),
    )

    with pytest.raises(catalog.FinanceWorkspaceCatalogError):
        catalog.load_published_finance_workspace_catalog()


def test_catalog_entries_are_immutable(monkeypatch, tmp_path):
    workspace_id = str(uuid4())
    _workspace_dir(tmp_path, workspace_id)
    monkeypatch.setattr(catalog, "_catalog_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalog,
        "load_active_finance_report_projection",
        lambda _: _projection(workspace_id),
    )

    entry = catalog.load_published_finance_workspace_catalog()[0]
    with pytest.raises(Exception):
        entry.workspace_id = str(UUID(int=0))
