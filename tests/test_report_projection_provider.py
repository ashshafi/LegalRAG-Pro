from __future__ import annotations

import json
from pathlib import Path

import pytest

import report_projection_provider as provider
from case_reporting import dumps_case_report_projection
from test_case_reporting_projection import sources_and_projection


def _root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    src = tmp_path / "project" / "src"
    src.mkdir(parents=True)
    monkeypatch.setattr(provider, "__file__", str(src / "report_projection_provider.py"))
    return src.parent


def _write_active(root: Path, case_id: str, payload: bytes) -> Path:
    path = root / "report_projections" / case_id / "active.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _projection():
    return sources_and_projection()[4]


def test_missing_exact_active_slot_is_the_only_none_state(monkeypatch, tmp_path):
    _root(monkeypatch, tmp_path)
    case_id = _projection().case_header.case_id
    assert provider.load_active_case_report_projection(case_id) is None


def test_provider_loads_exact_canonical_projection_without_mutating_source(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    projection = _projection()
    payload = dumps_case_report_projection(projection).encode("utf-8")
    path = _write_active(root, projection.case_header.case_id, payload)
    before = path.read_bytes()

    restored = provider.load_active_case_report_projection(projection.case_header.case_id.upper())

    assert restored == projection
    assert path.read_bytes() == before == payload


def test_provider_ignores_sibling_candidates_and_never_selects_latest(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    projection = _projection()
    case_dir = root / "report_projections" / projection.case_header.case_id
    case_dir.mkdir(parents=True)
    (case_dir / "newer.json").write_text("{}", encoding="utf-8")
    (case_dir / "candidate.json").write_text("{}", encoding="utf-8")

    assert provider.load_active_case_report_projection(projection.case_header.case_id) is None


def test_provider_reads_only_active_json_when_sibling_files_exist(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    projection = _projection()
    case_dir = root / "report_projections" / projection.case_header.case_id
    case_dir.mkdir(parents=True)
    (case_dir / "newer.json").write_text("not-json", encoding="utf-8")
    payload = dumps_case_report_projection(projection).encode("utf-8")
    _write_active(root, projection.case_header.case_id, payload)

    assert provider.load_active_case_report_projection(projection.case_header.case_id) == projection


@pytest.mark.parametrize("case_id", ["", "not-a-uuid", "../escape", None])
def test_invalid_case_id_fails_closed(monkeypatch, tmp_path, case_id):
    _root(monkeypatch, tmp_path)
    with pytest.raises(provider.ReportProjectionProviderError):
        provider.load_active_case_report_projection(case_id)  # type: ignore[arg-type]


def test_noncanonical_json_fails_closed(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    projection = _projection()
    canonical = dumps_case_report_projection(projection)
    pretty = json.dumps(json.loads(canonical), indent=2, sort_keys=True).encode("utf-8")
    _write_active(root, projection.case_header.case_id, pretty)

    with pytest.raises(provider.ReportProjectionProviderError):
        provider.load_active_case_report_projection(projection.case_header.case_id)


def test_extra_trailing_newline_fails_closed(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    projection = _projection()
    payload = dumps_case_report_projection(projection).encode("utf-8") + b"\n"
    _write_active(root, projection.case_header.case_id, payload)

    with pytest.raises(provider.ReportProjectionProviderError):
        provider.load_active_case_report_projection(projection.case_header.case_id)


def test_invalid_utf8_fails_closed(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    projection = _projection()
    _write_active(root, projection.case_header.case_id, b"\xff\xfe")

    with pytest.raises(provider.ReportProjectionProviderError):
        provider.load_active_case_report_projection(projection.case_header.case_id)


def test_malformed_json_fails_closed(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    projection = _projection()
    _write_active(root, projection.case_header.case_id, b"{")

    with pytest.raises(provider.ReportProjectionProviderError):
        provider.load_active_case_report_projection(projection.case_header.case_id)


def test_tampered_projection_identity_fails_closed(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    projection = _projection()
    data = json.loads(dumps_case_report_projection(projection))
    data["report_projection_id"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    payload = json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    _write_active(root, projection.case_header.case_id, payload)

    with pytest.raises(provider.ReportProjectionProviderError):
        provider.load_active_case_report_projection(projection.case_header.case_id)


def test_cross_case_projection_fails_closed(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    projection = _projection()
    requested = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    _write_active(root, requested, dumps_case_report_projection(projection).encode("utf-8"))

    with pytest.raises(provider.ReportProjectionProviderError):
        provider.load_active_case_report_projection(requested)



def test_provider_path_is_independent_of_process_working_directory(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    projection = _projection()
    _write_active(
        root,
        projection.case_header.case_id,
        dumps_case_report_projection(projection).encode("utf-8"),
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert (
        provider.load_active_case_report_projection(projection.case_header.case_id)
        == projection
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data.__setitem__("schema_version", "case-report-projection-schema/999"),
        lambda data: data.__setitem__("projection_payload_sha256", "0" * 64),
        lambda data: data["manifest"].__setitem__(
            "manifest_id", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        ),
    ],
)
def test_schema_hash_and_manifest_tampering_fail_closed(
    monkeypatch, tmp_path, mutation
):
    root = _root(monkeypatch, tmp_path)
    projection = _projection()
    data = json.loads(dumps_case_report_projection(projection))
    mutation(data)
    payload = json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    _write_active(root, projection.case_header.case_id, payload)

    with pytest.raises(provider.ReportProjectionProviderError):
        provider.load_active_case_report_projection(projection.case_header.case_id)

def test_active_json_directory_fails_closed(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    projection = _projection()
    path = root / "report_projections" / projection.case_header.case_id / "active.json"
    path.mkdir(parents=True)

    with pytest.raises(provider.ReportProjectionProviderError):
        provider.load_active_case_report_projection(projection.case_header.case_id)


def test_active_json_symlink_fails_closed(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    projection = _projection()
    payload = dumps_case_report_projection(projection).encode("utf-8")
    case_dir = root / "report_projections" / projection.case_header.case_id
    case_dir.mkdir(parents=True)
    target = case_dir / "projection-target.json"
    target.write_bytes(payload)
    path = case_dir / "active.json"
    try:
        path.symlink_to(target.name)
    except OSError:
        pytest.skip("Symlink creation is not available in this runtime.")

    with pytest.raises(provider.ReportProjectionProviderError):
        provider.load_active_case_report_projection(projection.case_header.case_id)


def test_case_directory_symlink_escape_fails_closed(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    projection = _projection()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "active.json").write_bytes(
        dumps_case_report_projection(projection).encode("utf-8")
    )
    case_link = root / "report_projections" / projection.case_header.case_id
    case_link.parent.mkdir(parents=True)
    try:
        case_link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlink creation is not available in this runtime.")

    with pytest.raises(provider.ReportProjectionProviderError):
        provider.load_active_case_report_projection(projection.case_header.case_id)


def test_filesystem_inspection_error_fails_closed(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    projection = _projection()
    path = _write_active(
        root,
        projection.case_header.case_id,
        dumps_case_report_projection(projection).encode("utf-8"),
    )
    original = Path.lstat

    def fail_lstat(self: Path):
        if self == path:
            raise OSError("synthetic inspection failure")
        return original(self)

    monkeypatch.setattr(Path, "lstat", fail_lstat)
    with pytest.raises(provider.ReportProjectionProviderError):
        provider.load_active_case_report_projection(projection.case_header.case_id)


def test_filesystem_read_error_fails_closed(monkeypatch, tmp_path):
    root = _root(monkeypatch, tmp_path)
    projection = _projection()
    path = _write_active(
        root,
        projection.case_header.case_id,
        dumps_case_report_projection(projection).encode("utf-8"),
    )
    original = Path.read_bytes

    def fail_read(self: Path) -> bytes:
        if self == path:
            raise OSError("synthetic read failure")
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    with pytest.raises(provider.ReportProjectionProviderError):
        provider.load_active_case_report_projection(projection.case_header.case_id)
