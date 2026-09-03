from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

import report_projection_provider as provider


CASE_ID = "11111111-1111-4111-8111-111111111111"


@pytest.fixture(autouse=True)
def _clear_cache():
    provider._REPORT_PROJECTION_CACHE.clear()
    yield
    provider._REPORT_PROJECTION_CACHE.clear()


def _install_projection_stubs(monkeypatch, tmp_path):
    active = tmp_path / "active.json"
    active.write_text('{"ok":true}', encoding="utf-8")
    projection = NS(case_header=NS(case_id=CASE_ID))
    calls = {"loads": 0}

    monkeypatch.setattr(provider, "_active_projection_path", lambda _case_id: active)

    def loads(text):
        calls["loads"] += 1
        if text != '{"ok":true}':
            raise ValueError("changed")
        return projection

    monkeypatch.setattr(provider, "loads_case_report_projection", loads)
    monkeypatch.setattr(provider, "validate_case_report_projection", lambda _projection: None)
    monkeypatch.setattr(
        provider,
        "dumps_case_report_projection",
        lambda _projection: '{"ok":true}',
    )
    return active, projection, calls


def test_exact_unchanged_projection_bytes_reuse_validated_object(monkeypatch, tmp_path):
    _active, projection, calls = _install_projection_stubs(monkeypatch, tmp_path)

    first = provider.load_active_case_report_projection(CASE_ID)
    second = provider.load_active_case_report_projection(CASE_ID)

    assert first is projection
    assert second is first
    assert calls["loads"] == 1


def test_changed_projection_bytes_do_not_reuse_cached_object(monkeypatch, tmp_path):
    active, _projection, calls = _install_projection_stubs(monkeypatch, tmp_path)

    assert provider.load_active_case_report_projection(CASE_ID) is not None
    active.write_text('{"changed":true}', encoding="utf-8")

    with pytest.raises(provider.ReportProjectionProviderError):
        provider.load_active_case_report_projection(CASE_ID)

    assert calls["loads"] == 2


def test_absence_after_cache_returns_none_not_stale_projection(monkeypatch, tmp_path):
    active, _projection, _calls = _install_projection_stubs(monkeypatch, tmp_path)

    assert provider.load_active_case_report_projection(CASE_ID) is not None
    active.unlink()

    assert provider.load_active_case_report_projection(CASE_ID) is None
