from uuid import uuid4

import pytest

from finance_case_binding import provider


def test_absent_root_returns_none(tmp_path, monkeypatch):
    root = tmp_path / "bindings"
    monkeypatch.setattr(provider, "_binding_root", lambda: root)
    assert provider.load_active_finance_case_binding(str(uuid4())) is None


def test_invalid_case_id_fails_closed(tmp_path, monkeypatch):
    root = tmp_path / "bindings"
    monkeypatch.setattr(provider, "_binding_root", lambda: root)
    with pytest.raises(provider.FinanceCaseBindingProviderError, match="Invalid canonical case_id"):
        provider.load_active_finance_case_binding("not-a-uuid")
