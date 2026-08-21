from __future__ import annotations

from types import SimpleNamespace

import pytest

import ui.finance_workspace_entrypoint as entrypoint


def test_show_finance_workspace_loads_active_projection_and_renders_read_only(monkeypatch) -> None:
    projection = object()
    calls: dict[str, object] = {}

    def fake_load(workspace_id: str):
        calls["load"] = workspace_id
        return projection

    def fake_render(*, workspace_id: str, projection: object, index) -> None:
        calls["render"] = (workspace_id, projection, index)

    monkeypatch.setattr(entrypoint, "load_active_finance_report_projection", fake_load)
    monkeypatch.setattr(entrypoint, "render_finance_workspace", fake_render)
    monkeypatch.setattr(
        entrypoint,
        "st",
        SimpleNamespace(info=lambda message: pytest.fail(f"unexpected info: {message}")),
    )

    result = entrypoint.show_finance_workspace(workspace_id="workspace-1")

    assert result is None
    assert calls == {
        "load": "workspace-1",
        "render": ("workspace-1", projection, None),
    }


def test_show_finance_workspace_missing_projection_is_read_only_unavailable_state(monkeypatch) -> None:
    messages: list[str] = []

    monkeypatch.setattr(
        entrypoint,
        "load_active_finance_report_projection",
        lambda workspace_id: None,
    )
    monkeypatch.setattr(
        entrypoint,
        "render_finance_workspace",
        lambda **kwargs: pytest.fail(f"unexpected render: {kwargs}"),
    )
    monkeypatch.setattr(
        entrypoint,
        "st",
        SimpleNamespace(info=messages.append),
    )

    result = entrypoint.show_finance_workspace(workspace_id="workspace-1")

    assert result is None
    assert messages == ["No active Finance report projection is available for this workspace."]


@pytest.mark.parametrize("workspace_id", [None, 1, object()])
def test_show_finance_workspace_rejects_non_string_workspace_id(workspace_id) -> None:
    with pytest.raises(TypeError, match="workspace_id must be a str"):
        entrypoint.show_finance_workspace(workspace_id=workspace_id)


@pytest.mark.parametrize("workspace_id", ["", " ", "\t\r\n"])
def test_show_finance_workspace_rejects_empty_workspace_id(workspace_id: str) -> None:
    with pytest.raises(ValueError, match="workspace_id must be non-empty"):
        entrypoint.show_finance_workspace(workspace_id=workspace_id)
