from __future__ import annotations

import json
from pathlib import Path

import pytest

import finance_report_projection_provider as provider
from finance_reporting import dumps_finance_report_projection
from test_finance_reporting_models import projection


def _root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    src = tmp_path / "project" / "src"
    src.mkdir(parents=True)
    monkeypatch.setattr(
        provider,
        "__file__",
        str(src / "finance_report_projection_provider.py"),
    )
    return tmp_path / "project"


def _write_active(root: Path, workspace_id: str, payload: bytes) -> Path:
    path = (
        root
        / "report_projections"
        / "finance"
        / workspace_id
        / "active.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_missing_exact_active_slot_is_the_only_none_state(monkeypatch, tmp_path):
    _root(monkeypatch, tmp_path)
    workspace_id = projection().header.workspace_id
    assert provider.load_active_finance_report_projection(workspace_id) is None


def test_provider_loads_exact_canonical_projection_without_mutating_source(
    monkeypatch, tmp_path
):
    root = _root(monkeypatch, tmp_path)
    value = projection()
    payload = dumps_finance_report_projection(value).encode("utf-8")
    path = _write_active(root, value.header.workspace_id, payload)

    before = path.read_bytes()
    restored = provider.load_active_finance_report_projection(
        value.header.workspace_id.upper()
    )

    assert restored == value
    assert path.read_bytes() == before


def test_provider_ignores_sibling_candidates_and_reads_only_active_json(
    monkeypatch, tmp_path
):
    root = _root(monkeypatch, tmp_path)
    value = projection()
    workspace_dir = (
        root / "report_projections" / "finance" / value.header.workspace_id
    )
    workspace_dir.mkdir(parents=True)
    (workspace_dir / "newer.json").write_text("{}", encoding="utf-8")

    assert provider.load_active_finance_report_projection(
        value.header.workspace_id
    ) is None

    _write_active(
        root,
        value.header.workspace_id,
        dumps_finance_report_projection(value).encode("utf-8"),
    )
    assert provider.load_active_finance_report_projection(
        value.header.workspace_id
    ) == value


@pytest.mark.parametrize("workspace_id", ["", "not-a-uuid", "../escape", None])
def test_invalid_workspace_id_fails_closed(monkeypatch, tmp_path, workspace_id):
    _root(monkeypatch, tmp_path)
    with pytest.raises(provider.FinanceReportProjectionProviderError):
        provider.load_active_finance_report_projection(workspace_id)  # type: ignore[arg-type]


def test_noncanonical_json_fails_closed(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    value = projection()
    canonical = dumps_finance_report_projection(value)
    pretty = json.dumps(json.loads(canonical), indent=2).encode("utf-8")
    _write_active(root, value.header.workspace_id, pretty)

    with pytest.raises(provider.FinanceReportProjectionProviderError):
        provider.load_active_finance_report_projection(value.header.workspace_id)


def test_extra_trailing_newline_fails_closed(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    value = projection()
    payload = dumps_finance_report_projection(value).encode("utf-8") + b"\n"
    _write_active(root, value.header.workspace_id, payload)

    with pytest.raises(provider.FinanceReportProjectionProviderError):
        provider.load_active_finance_report_projection(value.header.workspace_id)


def test_invalid_utf8_fails_closed(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    value = projection()
    _write_active(root, value.header.workspace_id, b"\xff\xfe")

    with pytest.raises(provider.FinanceReportProjectionProviderError):
        provider.load_active_finance_report_projection(value.header.workspace_id)


def test_malformed_json_fails_closed(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    value = projection()
    _write_active(root, value.header.workspace_id, b"{")

    with pytest.raises(provider.FinanceReportProjectionProviderError):
        provider.load_active_finance_report_projection(value.header.workspace_id)


def test_tampered_projection_identity_fails_closed(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    value = projection()
    data = json.loads(dumps_finance_report_projection(value))
    data["report_projection_id"] = "sha256:" + "f" * 64
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    _write_active(root, value.header.workspace_id, payload)

    with pytest.raises(provider.FinanceReportProjectionProviderError):
        provider.load_active_finance_report_projection(value.header.workspace_id)


def test_cross_workspace_projection_fails_closed(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    value = projection()
    requested = "00000000-0000-4000-8000-000000000001"
    if requested == value.header.workspace_id:
        requested = "00000000-0000-4000-8000-000000000002"

    _write_active(
        root,
        requested,
        dumps_finance_report_projection(value).encode("utf-8"),
    )

    with pytest.raises(provider.FinanceReportProjectionProviderError):
        provider.load_active_finance_report_projection(requested)


def test_provider_path_is_independent_of_process_working_directory(
    monkeypatch, tmp_path
):
    root = _root(monkeypatch, tmp_path)
    value = projection()
    _write_active(
        root,
        value.header.workspace_id,
        dumps_finance_report_projection(value).encode("utf-8"),
    )

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert provider.load_active_finance_report_projection(
        value.header.workspace_id
    ) == value


def test_active_json_directory_fails_closed(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    value = projection()
    path = (
        root
        / "report_projections"
        / "finance"
        / value.header.workspace_id
        / "active.json"
    )
    path.mkdir(parents=True)

    with pytest.raises(provider.FinanceReportProjectionProviderError):
        provider.load_active_finance_report_projection(value.header.workspace_id)


def test_active_json_symlink_fails_closed(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    value = projection()
    workspace_dir = (
        root / "report_projections" / "finance" / value.header.workspace_id
    )
    workspace_dir.mkdir(parents=True)
    target = workspace_dir / "projection-target.json"
    target.write_bytes(dumps_finance_report_projection(value).encode("utf-8"))
    active = workspace_dir / "active.json"

    try:
        active.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink unavailable on this platform: {exc}")

    with pytest.raises(provider.FinanceReportProjectionProviderError):
        provider.load_active_finance_report_projection(value.header.workspace_id)


def test_workspace_directory_symlink_escape_fails_closed(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    value = projection()
    governed = root / "report_projections" / "finance"
    governed.mkdir(parents=True)

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "active.json").write_bytes(
        dumps_finance_report_projection(value).encode("utf-8")
    )

    workspace_link = governed / value.header.workspace_id
    try:
        workspace_link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable on this platform: {exc}")

    with pytest.raises(provider.FinanceReportProjectionProviderError):
        provider.load_active_finance_report_projection(value.header.workspace_id)


def test_filesystem_inspection_error_fails_closed(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    value = projection()
    _write_active(
        root,
        value.header.workspace_id,
        dumps_finance_report_projection(value).encode("utf-8"),
    )

    original = Path.lstat

    def fail_lstat(self):
        if self.name == "active.json":
            raise OSError("inspection failed")
        return original(self)

    monkeypatch.setattr(Path, "lstat", fail_lstat)

    with pytest.raises(provider.FinanceReportProjectionProviderError):
        provider.load_active_finance_report_projection(value.header.workspace_id)


def test_filesystem_read_error_fails_closed(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    value = projection()
    _write_active(
        root,
        value.header.workspace_id,
        dumps_finance_report_projection(value).encode("utf-8"),
    )

    original = Path.read_bytes

    def fail_read(self):
        if self.name == "active.json":
            raise OSError("read failed")
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", fail_read)

    with pytest.raises(provider.FinanceReportProjectionProviderError):
        provider.load_active_finance_report_projection(value.header.workspace_id)
