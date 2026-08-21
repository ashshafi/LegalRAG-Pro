from uuid import uuid4

import pytest

from finance_case_binding import activation, provider
from finance_case_binding.models import FinanceCaseBindingActivationAction


def _roots(tmp_path, monkeypatch):
    root = tmp_path / "finance_case_bindings"
    monkeypatch.setattr(provider, "_binding_root", lambda: root)
    monkeypatch.setattr(activation, "_binding_root", lambda: root)
    return root


def test_activate_switch_and_rollback(tmp_path, monkeypatch):
    _roots(tmp_path, monkeypatch)
    case_id = str(uuid4())
    first_workspace = str(uuid4())
    second_workspace = str(uuid4())

    first = activation.activate_finance_case_binding(
        case_id=case_id, workspace_id=first_workspace
    )
    assert provider.load_active_finance_case_binding(case_id) == first

    second = activation.activate_finance_case_binding(
        case_id=case_id, workspace_id=second_workspace
    )
    assert provider.load_active_finance_case_binding(case_id) == second

    rolled = activation.activate_finance_case_binding(
        case_id=case_id,
        workspace_id=first_workspace,
        action=FinanceCaseBindingActivationAction.ROLLBACK,
    )
    assert rolled.workspace_id == first_workspace
    assert provider.load_active_finance_case_binding(case_id) == rolled


def test_rollback_target_must_be_prior_workspace(tmp_path, monkeypatch):
    _roots(tmp_path, monkeypatch)
    case_id = str(uuid4())
    activation.activate_finance_case_binding(
        case_id=case_id, workspace_id=str(uuid4())
    )
    with pytest.raises(
        activation.FinanceCaseBindingActivationError,
        match="does not occur in validated prior activation chain",
    ):
        activation.activate_finance_case_binding(
            case_id=case_id,
            workspace_id=str(uuid4()),
            action=FinanceCaseBindingActivationAction.ROLLBACK,
        )


def test_noop_activate_is_rejected(tmp_path, monkeypatch):
    _roots(tmp_path, monkeypatch)
    case_id = str(uuid4()); workspace_id = str(uuid4())
    activation.activate_finance_case_binding(case_id=case_id, workspace_id=workspace_id)
    with pytest.raises(activation.FinanceCaseBindingActivationError, match="no-op"):
        activation.activate_finance_case_binding(case_id=case_id, workspace_id=workspace_id)
