"""Tests for the fail-closed LegalRAG authentication boundary."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

import authentication


class StopCalled(RuntimeError):
    """Raised by the fake Streamlit stop boundary."""


class FakeUser(dict[str, object]):
    """Minimal dict-like Streamlit user object."""

    def __init__(self, *, is_logged_in: bool, **claims: object) -> None:
        super().__init__(claims)
        self.is_logged_in = is_logged_in

    def __getattr__(self, name: str) -> object:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


@dataclass
class FakeSidebar:
    buttons: list[str] = field(default_factory=list)

    def button(self, label: str, **_: object) -> bool:
        self.buttons.append(label)
        return False


@dataclass
class FakeStreamlit:
    secrets: dict[str, object]
    user: FakeUser
    login_clicked: bool = False
    sidebar: FakeSidebar = field(default_factory=FakeSidebar)
    errors: list[str] = field(default_factory=list)
    infos: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)
    login_calls: list[object] = field(default_factory=list)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def info(self, message: str) -> None:
        self.infos.append(message)

    def title(self, message: str) -> None:
        self.titles.append(message)

    def stop(self) -> None:
        raise StopCalled()

    def button(self, _: str, **kwargs: object) -> bool:
        if "on_click" in kwargs:
            return False
        return self.login_clicked

    def login(self, provider: object = None) -> None:
        self.login_calls.append(provider)

    def logout(self) -> None:
        return None


def configured_secrets(provider: str | None = None) -> dict[str, object]:
    shared: dict[str, object] = {
        "redirect_uri": "https://legalrag.example/oauth2callback",
        "cookie_secret": "not-a-real-secret",
    }
    provider_values = {
        "client_id": "client",
        "client_secret": "secret",
        "server_metadata_url": "https://idp.example/.well-known/openid-configuration",
    }
    if provider is None:
        shared.update(provider_values)
    else:
        shared[provider] = provider_values
    return {"auth": shared}


def test_parse_allowed_emails_normalises_and_deduplicates() -> None:
    assert authentication.parse_allowed_emails(
        " Person@Example.COM,other@example.com, person@example.com "
    ) == frozenset({"person@example.com", "other@example.com"})


@pytest.mark.parametrize("value", [None, "", " ", "not-an-email", 123])
def test_normalise_email_rejects_unusable_values(value: object) -> None:
    assert authentication.normalise_email(value) is None


def test_extract_user_email_falls_back_to_preferred_username() -> None:
    user = FakeUser(
        is_logged_in=True,
        email="",
        preferred_username="USER@Example.COM",
    )
    assert authentication.extract_user_email(user) == "user@example.com"


def test_oidc_configuration_requires_named_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeStreamlit(
        secrets=configured_secrets("microsoft"),
        user=FakeUser(is_logged_in=False),
    )
    monkeypatch.setattr(authentication, "st", fake)
    assert authentication.oidc_configuration_available("microsoft") is True
    assert authentication.oidc_configuration_available("missing") is False


def test_require_private_access_fails_closed_without_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeStreamlit(
        secrets=configured_secrets(),
        user=FakeUser(is_logged_in=False),
    )
    monkeypatch.setattr(authentication, "st", fake)
    monkeypatch.delenv("LEGALRAG_ALLOWED_EMAILS", raising=False)
    monkeypatch.delenv("LEGALRAG_OIDC_PROVIDER", raising=False)

    with pytest.raises(StopCalled):
        authentication.require_private_access()

    assert fake.errors == ["LegalRAG private access is not configured."]


def test_require_private_access_fails_closed_without_oidc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeStreamlit(
        secrets={},
        user=FakeUser(is_logged_in=False),
    )
    monkeypatch.setattr(authentication, "st", fake)
    monkeypatch.setenv("LEGALRAG_ALLOWED_EMAILS", "user@example.com")
    monkeypatch.delenv("LEGALRAG_OIDC_PROVIDER", raising=False)

    with pytest.raises(StopCalled):
        authentication.require_private_access()

    assert fake.errors == ["LegalRAG sign-in is not configured."]


def test_require_private_access_stops_before_app_when_logged_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeStreamlit(
        secrets=configured_secrets(),
        user=FakeUser(is_logged_in=False),
        login_clicked=False,
    )
    monkeypatch.setattr(authentication, "st", fake)
    monkeypatch.setenv("LEGALRAG_ALLOWED_EMAILS", "user@example.com")
    monkeypatch.delenv("LEGALRAG_OIDC_PROVIDER", raising=False)

    with pytest.raises(StopCalled):
        authentication.require_private_access()

    assert fake.titles == ["LegalRAG Pro"]
    assert fake.infos == ["Private access. Sign in to continue."]
    assert fake.login_calls == []


def test_require_private_access_initiates_named_login_then_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeStreamlit(
        secrets=configured_secrets("microsoft"),
        user=FakeUser(is_logged_in=False),
        login_clicked=True,
    )
    monkeypatch.setattr(authentication, "st", fake)
    monkeypatch.setenv("LEGALRAG_ALLOWED_EMAILS", "user@example.com")
    monkeypatch.setenv("LEGALRAG_OIDC_PROVIDER", "microsoft")

    with pytest.raises(StopCalled):
        authentication.require_private_access()

    assert fake.login_calls == ["microsoft"]


def test_require_private_access_rejects_non_allowlisted_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeStreamlit(
        secrets=configured_secrets(),
        user=FakeUser(is_logged_in=True, email="other@example.com"),
    )
    monkeypatch.setattr(authentication, "st", fake)
    monkeypatch.setenv("LEGALRAG_ALLOWED_EMAILS", "user@example.com")
    monkeypatch.delenv("LEGALRAG_OIDC_PROVIDER", raising=False)

    with pytest.raises(StopCalled):
        authentication.require_private_access()

    assert fake.errors == ["This account is not authorised to access LegalRAG Pro."]


def test_require_private_access_returns_canonical_allowlisted_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeStreamlit(
        secrets=configured_secrets(),
        user=FakeUser(is_logged_in=True, email="USER@Example.COM"),
    )
    monkeypatch.setattr(authentication, "st", fake)
    monkeypatch.setenv("LEGALRAG_ALLOWED_EMAILS", "user@example.com")
    monkeypatch.delenv("LEGALRAG_OIDC_PROVIDER", raising=False)

    assert authentication.require_private_access() == "user@example.com"
    assert fake.sidebar.buttons == ["Log out"]
