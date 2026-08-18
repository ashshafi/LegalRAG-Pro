"""Fail-closed private-access authentication for LegalRAG Pro."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping

import streamlit as st

LOGGER = logging.getLogger(__name__)

_ALLOWED_EMAILS_ENV = "LEGALRAG_ALLOWED_EMAILS"
_PROVIDER_ENV = "LEGALRAG_OIDC_PROVIDER"
_SHARED_AUTH_KEYS = ("redirect_uri", "cookie_secret")
_PROVIDER_AUTH_KEYS = ("client_id", "client_secret", "server_metadata_url")


def parse_allowed_emails(raw_value: str | None) -> frozenset[str]:
    """Parse the configured comma-separated email allowlist."""
    if raw_value is None:
        return frozenset()
    return frozenset(
        item.strip().casefold()
        for item in raw_value.split(",")
        if item.strip()
    )


def normalise_email(value: object) -> str | None:
    """Return a canonical email-like identifier, or None if unusable."""
    if not isinstance(value, str):
        return None
    candidate = value.strip().casefold()
    if not candidate or "@" not in candidate:
        return None
    return candidate


def _mapping_value(mapping: object, key: str) -> object | None:
    if isinstance(mapping, Mapping):
        return mapping.get(key)

    getter = getattr(mapping, "get", None)
    if callable(getter):
        try:
            return getter(key)
        except Exception:
            return None

    try:
        return mapping[key]  # type: ignore[index]
    except Exception:
        return None


def _nonempty_config_value(mapping: object, key: str) -> bool:
    value = _mapping_value(mapping, key)
    return isinstance(value, str) and bool(value.strip())


def oidc_configuration_available(provider: str | None) -> bool:
    """Return whether Streamlit has the minimum OIDC configuration."""
    try:
        auth_config = st.secrets["auth"]
    except Exception:
        return False

    if not all(_nonempty_config_value(auth_config, key) for key in _SHARED_AUTH_KEYS):
        return False

    provider_config: object = auth_config
    if provider is not None:
        provider_config = _mapping_value(auth_config, provider)
        if provider_config is None:
            return False

    return all(
        _nonempty_config_value(provider_config, key)
        for key in _PROVIDER_AUTH_KEYS
    )


def extract_user_email(user: object) -> str | None:
    """Extract the best email identity claim exposed by Streamlit."""
    for claim in ("email", "preferred_username"):
        value = _mapping_value(user, claim)
        email = normalise_email(value)
        if email is not None:
            return email

        try:
            value = getattr(user, claim)
        except Exception:
            value = None

        email = normalise_email(value)
        if email is not None:
            return email

    return None


def is_email_authorised(email: str | None, allowed_emails: frozenset[str]) -> bool:
    """Return whether a canonical email is explicitly allowlisted."""
    return email is not None and email in allowed_emails


def _stop_with_error(message: str) -> None:
    st.error(message)
    st.stop()


def require_private_access() -> str:
    """Require authenticated and explicitly authorised private access."""
    allowed_emails = parse_allowed_emails(os.getenv(_ALLOWED_EMAILS_ENV))
    if not allowed_emails:
        _stop_with_error("LegalRAG private access is not configured.")

    provider_value = os.getenv(_PROVIDER_ENV, "").strip()
    provider = provider_value or None

    if not oidc_configuration_available(provider):
        _stop_with_error("LegalRAG sign-in is not configured.")

    try:
        logged_in = bool(st.user.is_logged_in)
    except Exception:
        logged_in = False

    if not logged_in:
        st.title("LegalRAG Pro")
        st.info("Private access. Sign in to continue.")

        if st.button("Log in", key="legalrag_login"):
            try:
                if provider is None:
                    st.login()
                else:
                    st.login(provider)
            except Exception as exc:
                LOGGER.error("OIDC login initiation failed: %s", type(exc).__name__)
                st.error("Sign-in is unavailable. Check the OIDC configuration.")

        st.stop()

    email = extract_user_email(st.user)
    if not is_email_authorised(email, allowed_emails):
        st.error("This account is not authorised to access LegalRAG Pro.")
        st.button("Log out", key="legalrag_unauthorised_logout", on_click=st.logout)
        st.stop()

    st.sidebar.button("Log out", key="legalrag_logout", on_click=st.logout)
    return email
