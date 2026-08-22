from __future__ import annotations

from types import SimpleNamespace

import pytest

from finance_case_binding.models import FinanceCaseBindingActivationAction
from ui import finance_binding_lifecycle_manager as lifecycle


CURRENT = "11111111-1111-4111-8111-111111111111"
SWITCH = "22222222-2222-4222-8222-222222222222"
ROLLBACK = "33333333-3333-4333-8333-333333333333"
INVALID_ROLLBACK = "44444444-4444-4444-8444-444444444444"
UNPUBLISHED_ROLLBACK = "55555555-5555-4555-8555-555555555555"


class FakeStreamlit:
    def __init__(self, *, pressed: str | None = None):
        self.pressed = pressed
        self.selectboxes: list[tuple[str, tuple[str, ...]]] = []
        self.buttons: list[str] = []
        self.infos: list[str] = []
        self.successes: list[str] = []
        self.reruns = 0

    def subheader(self, *args, **kwargs):
        return None

    def caption(self, *args, **kwargs):
        return None

    def info(self, message, *args, **kwargs):
        self.infos.append(str(message))

    def warning(self, *args, **kwargs):
        return None

    def write(self, *args, **kwargs):
        return None

    def markdown(self, *args, **kwargs):
        return None

    def selectbox(self, label, *, options, format_func=None, key=None):
        values = tuple(options)
        self.selectboxes.append((str(label), values))
        if not values:
            raise AssertionError("selectbox received empty options")
        return values[0]

    def button(self, label, *args, **kwargs):
        label = str(label)
        self.buttons.append(label)
        return label == self.pressed

    def success(self, message, *args, **kwargs):
        self.successes.append(str(message))

    def rerun(self):
        self.reruns += 1


def _entry(workspace_id: str):
    return SimpleNamespace(workspace_id=workspace_id)


def _install(monkeypatch, fake, *, rollback_ids=(ROLLBACK,)):
    entries = (
        _entry(CURRENT),
        _entry(SWITCH),
        _entry(ROLLBACK),
        _entry(INVALID_ROLLBACK),
    )
    monkeypatch.setattr(lifecycle, "st", fake)
    monkeypatch.setattr(
        lifecycle,
        "load_published_finance_workspace_catalog",
        lambda: entries,
    )
    monkeypatch.setattr(
        lifecycle,
        "load_finance_case_binding_rollback_workspace_ids",
        lambda case_id: tuple(rollback_ids),
    )
    monkeypatch.setattr(
        lifecycle,
        "_workspace_label",
        lambda entry: entry.workspace_id,
    )


def test_switch_and_rollback_use_separate_option_authorities(monkeypatch):
    fake = FakeStreamlit()
    _install(
        monkeypatch,
        fake,
        rollback_ids=(ROLLBACK, UNPUBLISHED_ROLLBACK),
    )

    monkeypatch.setattr(
        lifecycle,
        "activate_finance_case_binding",
        lambda **kwargs: SimpleNamespace(workspace_id=kwargs["workspace_id"]),
    )

    lifecycle.show_finance_binding_lifecycle_manager(
        case_id=CURRENT,
        current_workspace_id=CURRENT,
    )

    assert fake.selectboxes == [
        (
            "Switch target published Finance workspace",
            (SWITCH, ROLLBACK, INVALID_ROLLBACK),
        ),
        (
            "Rollback target published Finance workspace",
            (ROLLBACK,),
        ),
    ]


def test_switch_uses_existing_activate_action(monkeypatch):
    fake = FakeStreamlit(pressed="Switch Finance workspace")
    _install(monkeypatch, fake)
    calls = []

    def activate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(workspace_id=kwargs["workspace_id"])

    monkeypatch.setattr(lifecycle, "activate_finance_case_binding", activate)

    lifecycle.show_finance_binding_lifecycle_manager(
        case_id=CURRENT,
        current_workspace_id=CURRENT,
    )

    assert len(calls) == 1
    assert calls[0]["workspace_id"] == SWITCH
    assert calls[0]["action"] is FinanceCaseBindingActivationAction.ACTIVATE


def test_rollback_uses_only_backend_valid_published_option(monkeypatch):
    fake = FakeStreamlit(pressed="Rollback Finance workspace")
    _install(
        monkeypatch,
        fake,
        rollback_ids=(ROLLBACK, UNPUBLISHED_ROLLBACK),
    )
    calls = []

    def activate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(workspace_id=kwargs["workspace_id"])

    monkeypatch.setattr(lifecycle, "activate_finance_case_binding", activate)

    lifecycle.show_finance_binding_lifecycle_manager(
        case_id=CURRENT,
        current_workspace_id=CURRENT,
    )

    assert len(calls) == 1
    assert calls[0]["workspace_id"] == ROLLBACK
    assert calls[0]["action"] is FinanceCaseBindingActivationAction.ROLLBACK


def test_empty_valid_rollback_set_has_no_rollback_mutation_control(monkeypatch):
    fake = FakeStreamlit()
    _install(monkeypatch, fake, rollback_ids=())

    monkeypatch.setattr(
        lifecycle,
        "activate_finance_case_binding",
        lambda **kwargs: SimpleNamespace(workspace_id=kwargs["workspace_id"]),
    )

    lifecycle.show_finance_binding_lifecycle_manager(
        case_id=CURRENT,
        current_workspace_id=CURRENT,
    )

    assert "Rollback Finance workspace" not in fake.buttons
    assert any("No valid published prior Finance workspace" in x for x in fake.infos)


def test_invalid_identity_fails_before_catalog_or_history_query(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("governed source was accessed before identity validation")

    monkeypatch.setattr(
        lifecycle,
        "load_published_finance_workspace_catalog",
        forbidden,
    )
    monkeypatch.setattr(
        lifecycle,
        "load_finance_case_binding_rollback_workspace_ids",
        forbidden,
    )

    with pytest.raises((TypeError, ValueError)):
        lifecycle.show_finance_binding_lifecycle_manager(
            case_id="",
            current_workspace_id=CURRENT,
        )
