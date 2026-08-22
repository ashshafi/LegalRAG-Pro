from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

import ui.finance_binding_manager as manager
from finance_workspace_catalog import PublishedFinanceWorkspace


def _entry(workspace_id: str | None = None) -> PublishedFinanceWorkspace:
    workspace_id = workspace_id or str(uuid4())
    return PublishedFinanceWorkspace(
        workspace_id=workspace_id,
        report_projection_id="projection-1",
        as_of=datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc),
        provider_id="provider-1",
        dataset_id="dataset-1",
        dataset_version="v1",
    )


class FakeStreamlit:
    def __init__(self, *, click: bool):
        self.click = click
        self.info_messages = []
        self.caption_messages = []
        self.success_messages = []
        self.rerun_count = 0

    def info(self, value):
        self.info_messages.append(value)

    def caption(self, value):
        self.caption_messages.append(value)

    def selectbox(self, label, *, options, format_func):
        assert label == "Published Finance workspace"
        assert tuple(options)
        format_func(options[0])
        return options[0]

    def button(self, label, *, type):
        assert label == "Bind Finance workspace"
        assert type == "primary"
        return self.click

    def success(self, value):
        self.success_messages.append(value)

    def rerun(self):
        self.rerun_count += 1


def test_empty_catalog_is_read_only_unavailable_state(monkeypatch):
    fake = FakeStreamlit(click=False)
    monkeypatch.setattr(manager, "st", fake)
    monkeypatch.setattr(manager, "load_published_finance_workspace_catalog", lambda: ())

    called = []
    monkeypatch.setattr(
        manager,
        "activate_finance_case_binding",
        lambda **kwargs: called.append(kwargs),
    )

    manager.show_finance_binding_manager(case_id=str(uuid4()))

    assert fake.info_messages == ["No published Finance workspaces are available to bind."]
    assert called == []


def test_selection_without_button_click_does_not_activate(monkeypatch):
    fake = FakeStreamlit(click=False)
    entry = _entry()
    monkeypatch.setattr(manager, "st", fake)
    monkeypatch.setattr(manager, "load_published_finance_workspace_catalog", lambda: (entry,))

    called = []
    monkeypatch.setattr(
        manager,
        "activate_finance_case_binding",
        lambda **kwargs: called.append(kwargs),
    )

    manager.show_finance_binding_manager(case_id=str(uuid4()))

    assert called == []
    assert fake.rerun_count == 0


def test_explicit_button_click_activates_exact_case_workspace_pair(monkeypatch):
    fake = FakeStreamlit(click=True)
    entry = _entry()
    case_id = str(uuid4())
    monkeypatch.setattr(manager, "st", fake)
    monkeypatch.setattr(manager, "load_published_finance_workspace_catalog", lambda: (entry,))

    called = []

    def activate(**kwargs):
        called.append(kwargs)
        return SimpleNamespace(workspace_id=kwargs["workspace_id"])

    monkeypatch.setattr(manager, "activate_finance_case_binding", activate)

    manager.show_finance_binding_manager(case_id=case_id)

    assert called == [{"case_id": case_id, "workspace_id": entry.workspace_id}]
    assert fake.success_messages == [f"Finance workspace bound: {entry.workspace_id}"]
    assert fake.rerun_count == 1


@pytest.mark.parametrize("case_id", ["", "   ", None])
def test_invalid_case_id_fails_before_catalog_or_activation(monkeypatch, case_id):
    monkeypatch.setattr(
        manager,
        "load_published_finance_workspace_catalog",
        lambda: pytest.fail("catalog must not be reached"),
    )
    monkeypatch.setattr(
        manager,
        "activate_finance_case_binding",
        lambda **kwargs: pytest.fail("activation must not be reached"),
    )

    expected = TypeError if case_id is None else ValueError
    with pytest.raises(expected):
        manager.show_finance_binding_manager(case_id=case_id)  # type: ignore[arg-type]
