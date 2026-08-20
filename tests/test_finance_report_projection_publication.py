from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from finance_reporting.serialization import dumps_finance_report_projection
from finance_report_projection_publication import (
    FinanceReportProjectionPublicationError,
    publish_finance_report_projection,
)


def _projection():
    fixture_path = Path(__file__).with_name("test_finance_report_projection_provider.py")
    spec = importlib.util.spec_from_file_location(
        "_f7c_p2_provider_fixture",
        fixture_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.projection()


def _finance_root(tmp_path: Path) -> Path:
    report_root = tmp_path / "report_projections"
    report_root.mkdir()
    return report_root / "finance"


def test_publishes_exact_canonical_bytes_to_governed_workspace_slot(tmp_path):
    value = _projection()
    root = _finance_root(tmp_path)

    path = publish_finance_report_projection(value, root=root)

    assert path == root / value.header.workspace_id / "active.json"
    assert path.read_bytes() == dumps_finance_report_projection(value).encode("utf-8")
    assert list(path.parent.glob(".active-*.tmp")) == []


def test_identical_republication_is_idempotent(tmp_path):
    value = _projection()
    root = _finance_root(tmp_path)

    first = publish_finance_report_projection(value, root=root)
    before = first.read_bytes()
    second = publish_finance_report_projection(value, root=root)

    assert second == first
    assert second.read_bytes() == before
    assert list(first.parent.glob(".active-*.tmp")) == []


def test_conflicting_existing_active_fails_closed_without_overwrite(tmp_path):
    value = _projection()
    root = _finance_root(tmp_path)
    workspace = root / value.header.workspace_id
    workspace.mkdir(parents=True)
    active = workspace / "active.json"
    active.write_bytes(b"conflicting-existing-state")
    before = active.read_bytes()

    with pytest.raises(FinanceReportProjectionPublicationError, match="conflicts"):
        publish_finance_report_projection(value, root=root)

    assert active.read_bytes() == before
    assert list(workspace.glob(".active-*.tmp")) == []


def test_nonregular_active_path_fails_closed(tmp_path):
    value = _projection()
    root = _finance_root(tmp_path)
    active = root / value.header.workspace_id / "active.json"
    active.mkdir(parents=True)

    with pytest.raises(FinanceReportProjectionPublicationError, match="plain regular"):
        publish_finance_report_projection(value, root=root)


def test_active_json_symlink_fails_closed(tmp_path):
    value = _projection()
    root = _finance_root(tmp_path)
    workspace = root / value.header.workspace_id
    workspace.mkdir(parents=True)
    target = workspace / "target.json"
    target.write_bytes(dumps_finance_report_projection(value).encode("utf-8"))
    active = workspace / "active.json"
    try:
        active.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink unavailable on this platform: {exc}")

    with pytest.raises(FinanceReportProjectionPublicationError, match="plain regular"):
        publish_finance_report_projection(value, root=root)


def test_workspace_directory_symlink_escape_fails_closed(tmp_path):
    value = _projection()
    root = _finance_root(tmp_path)
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    workspace = root / value.header.workspace_id
    try:
        workspace.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable on this platform: {exc}")

    with pytest.raises(FinanceReportProjectionPublicationError, match="plain directory"):
        publish_finance_report_projection(value, root=root)

    assert list(outside.iterdir()) == []


def test_hard_link_unavailable_fails_closed_and_leaves_no_active(monkeypatch, tmp_path):
    value = _projection()
    root = _finance_root(tmp_path)

    def fail_link(src, dst):
        raise OSError("hard links disabled")

    monkeypatch.setattr(os, "link", fail_link)

    with pytest.raises(
        FinanceReportProjectionPublicationError,
        match="create-if-absent",
    ):
        publish_finance_report_projection(value, root=root)

    workspace = root / value.header.workspace_id
    assert not (workspace / "active.json").exists()
    assert list(workspace.glob(".active-*.tmp")) == []
