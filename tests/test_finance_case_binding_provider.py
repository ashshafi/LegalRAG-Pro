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

# F7C-P15-C6-R3 rollback-target public-query contracts.
from types import SimpleNamespace as _P15SimpleNamespace

import pytest as _p15_pytest

import finance_case_binding.provider as _p15_provider


def test_rollback_workspace_ids_absence_returns_empty_tuple(monkeypatch):
    monkeypatch.setattr(_p15_provider, "_load_active_state", lambda case_id: None)

    assert _p15_provider.load_finance_case_binding_rollback_workspace_ids(
        "11111111-1111-4111-8111-111111111111"
    ) == ()


def test_rollback_workspace_ids_match_prior_chain_membership_and_order(monkeypatch):
    current = _P15SimpleNamespace(new_workspace_id="current")
    older_a = _P15SimpleNamespace(new_workspace_id="older-a")
    older_b = _P15SimpleNamespace(new_workspace_id="older-b")
    older_a_again = _P15SimpleNamespace(new_workspace_id="older-a")
    state = (object(), "payload", (current, older_a, older_b, older_a_again))
    monkeypatch.setattr(_p15_provider, "_load_active_state", lambda case_id: state)

    assert _p15_provider.load_finance_case_binding_rollback_workspace_ids(
        "11111111-1111-4111-8111-111111111111"
    ) == ("older-a", "older-b")


def test_rollback_workspace_ids_propagate_fail_closed_provider_error(monkeypatch):
    def fail(case_id):
        raise _p15_provider.FinanceCaseBindingProviderError("invalid history")

    monkeypatch.setattr(_p15_provider, "_load_active_state", fail)

    with _p15_pytest.raises(_p15_provider.FinanceCaseBindingProviderError):
        _p15_provider.load_finance_case_binding_rollback_workspace_ids(
            "11111111-1111-4111-8111-111111111111"
        )


def test_rollback_workspace_ids_query_is_read_only_surface():
    import inspect

    source = inspect.getsource(
        _p15_provider.load_finance_case_binding_rollback_workspace_ids
    )
    assert "_load_active_state" in source
    assert "chain[1:]" in source
    assert "activate_finance_case_binding" not in source
    assert "write_text" not in source
    assert "os.rename" not in source
    assert "_write_new_file" not in source


def test_package_exports_rollback_workspace_ids_query():
    import finance_case_binding

    assert (
        finance_case_binding.load_finance_case_binding_rollback_workspace_ids
        is _p15_provider.load_finance_case_binding_rollback_workspace_ids
    )
