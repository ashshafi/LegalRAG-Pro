
from __future__ import annotations
import importlib, inspect
import pytest

authentication = importlib.import_module("authentication")
from case_management.access import (
    MatterAccessContext, MatterMembership, MatterMutationError,
    MatterRole, MembershipStatus, UserIdentity, require_matter_mutation,
)

OWNER_EMAIL = "ashshafi002@gmail.com"

@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.delenv("LEGALRAG_LOCAL_DEV_AUTH", raising=False)
    monkeypatch.delenv("LEGALRAG_LOCAL_DEV_EMAIL", raising=False)
    monkeypatch.setenv("LEGALRAG_ALLOWED_EMAILS", OWNER_EMAIL)

def test_disabled_by_default(monkeypatch):
    monkeypatch.setattr(authentication.st, "get_option", lambda name: "127.0.0.1")
    assert authentication._local_dev_identity_email(frozenset({OWNER_EMAIL})) is None

def test_requires_loopback(monkeypatch):
    monkeypatch.setenv("LEGALRAG_LOCAL_DEV_AUTH", "1")
    monkeypatch.setenv("LEGALRAG_LOCAL_DEV_EMAIL", OWNER_EMAIL)
    monkeypatch.setattr(authentication.st, "get_option", lambda name: "0.0.0.0")
    with pytest.raises(PermissionError, match="loopback-only"):
        authentication._local_dev_identity_email(frozenset({OWNER_EMAIL}))

def test_requires_explicit_email(monkeypatch):
    monkeypatch.setenv("LEGALRAG_LOCAL_DEV_AUTH", "1")
    monkeypatch.setattr(authentication.st, "get_option", lambda name: "127.0.0.1")
    with pytest.raises(PermissionError, match="LEGALRAG_LOCAL_DEV_EMAIL"):
        authentication._local_dev_identity_email(frozenset({OWNER_EMAIL}))

def test_requires_allowlist(monkeypatch):
    monkeypatch.setenv("LEGALRAG_LOCAL_DEV_AUTH", "1")
    monkeypatch.setenv("LEGALRAG_LOCAL_DEV_EMAIL", "other@example.com")
    monkeypatch.setattr(authentication.st, "get_option", lambda name: "127.0.0.1")
    with pytest.raises(PermissionError, match="not authorised"):
        authentication._local_dev_identity_email(frozenset({OWNER_EMAIL}))

def test_canonical_email(monkeypatch):
    monkeypatch.setenv("LEGALRAG_LOCAL_DEV_AUTH", "1")
    monkeypatch.setenv("LEGALRAG_LOCAL_DEV_EMAIL", f"  {OWNER_EMAIL.upper()}  ")
    monkeypatch.setattr(authentication.st, "get_option", lambda name: "localhost")
    assert authentication._local_dev_identity_email(frozenset({OWNER_EMAIL})) == OWNER_EMAIL

def test_current_identity(monkeypatch):
    monkeypatch.setenv("LEGALRAG_LOCAL_DEV_AUTH", "1")
    monkeypatch.setenv("LEGALRAG_LOCAL_DEV_EMAIL", OWNER_EMAIL)
    monkeypatch.setattr(authentication.st, "get_option", lambda name: "::1")
    assert authentication.current_user_identity() == UserIdentity.from_email(OWNER_EMAIL)

def membership(role):
    sig = inspect.signature(MatterMembership)
    user = UserIdentity.from_email(OWNER_EMAIL)
    vals = dict(case_id="case-1", user_id=user.user_id, email=OWNER_EMAIL,
                role=role, status=MembershipStatus.ACTIVE)
    return MatterMembership(**{k: vals[k] for k in sig.parameters if k in vals})

def access(role):
    sig = inspect.signature(MatterAccessContext)
    user = UserIdentity.from_email(OWNER_EMAIL)
    mem = membership(role)
    vals = dict(user=user, identity=user, membership=mem, case_id="case-1")
    return MatterAccessContext(**{k: vals[k] for k in sig.parameters if k in vals})

@pytest.mark.parametrize("role", [MatterRole.REVIEWER, MatterRole.READ_ONLY])
def test_denied_roles(role):
    a = access(role)
    with pytest.raises(MatterMutationError):
        require_matter_mutation(a)

@pytest.mark.parametrize("role", [MatterRole.OWNER, MatterRole.SOLICITOR])
def test_allowed_roles(role):
    a = access(role)
    assert require_matter_mutation(a) is a
