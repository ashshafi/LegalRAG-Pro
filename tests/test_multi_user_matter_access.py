from __future__ import annotations

import sqlite3

import pytest

from case_management import (
    Case,
    CaseRepository,
    MatterAccessError,
    MatterRole,
    UserIdentity,
)


def user(email: str) -> UserIdentity:
    return UserIdentity.from_email(email)


def test_user_identity_is_canonical_and_deterministic():
    a = user(" User@Example.COM ")
    b = user("user@example.com")
    assert a == b
    assert a.email == "user@example.com"


def test_unassigned_legacy_case_is_not_visible(tmp_path):
    repo = CaseRepository(tmp_path / "cases.sqlite3")
    case = repo.create(Case.create("Legacy matter"))
    alice = user("alice@example.com")

    assert repo.list_for_user(alice) == []
    with pytest.raises(MatterAccessError):
        repo.require_access(alice, case.case_id)


def test_create_for_user_grants_owner_and_isolated_visibility(tmp_path):
    repo = CaseRepository(tmp_path / "cases.sqlite3")
    alice = user("alice@example.com")
    bob = user("bob@example.com")
    case = Case.create("Alice matter")

    repo.create_for_user(case, alice)

    assert [item.case_id for item in repo.list_for_user(alice)] == [case.case_id]
    assert repo.list_for_user(bob) == []
    assert repo.require_access(alice, case.case_id).role is MatterRole.OWNER


def test_owner_can_grant_and_revoke_membership(tmp_path):
    repo = CaseRepository(tmp_path / "cases.sqlite3")
    owner = user("owner@example.com")
    solicitor = user("solicitor@example.com")
    case = Case.create("Shared matter")
    repo.create_for_user(case, owner)

    repo.grant_membership(
        actor=owner,
        case_id=case.case_id,
        user=solicitor,
        role=MatterRole.SOLICITOR,
    )
    assert repo.require_access(solicitor, case.case_id).role is MatterRole.SOLICITOR

    repo.revoke_membership(actor=owner, case_id=case.case_id, user=solicitor)
    with pytest.raises(MatterAccessError):
        repo.require_access(solicitor, case.case_id)


def test_non_owner_cannot_grant_membership(tmp_path):
    repo = CaseRepository(tmp_path / "cases.sqlite3")
    owner = user("owner@example.com")
    solicitor = user("solicitor@example.com")
    third = user("third@example.com")
    case = Case.create("Shared matter")
    repo.create_for_user(case, owner)
    repo.grant_membership(
        actor=owner,
        case_id=case.case_id,
        user=solicitor,
        role=MatterRole.SOLICITOR,
    )

    with pytest.raises(MatterAccessError):
        repo.grant_membership(
            actor=solicitor,
            case_id=case.case_id,
            user=third,
            role=MatterRole.READ_ONLY,
        )


def test_explicit_legacy_bootstrap_assigns_only_unowned_cases(tmp_path):
    repo = CaseRepository(tmp_path / "cases.sqlite3")
    alice = user("alice@example.com")
    bob = user("bob@example.com")
    owned = Case.create("Already owned")
    legacy = Case.create("Legacy")
    repo.create_for_user(owned, bob)
    repo.create(legacy)

    assigned = repo.assign_unowned_cases_to_user(alice)

    assert assigned == (legacy.case_id,)
    assert {c.case_id for c in repo.list_for_user(alice)} == {legacy.case_id}
    assert {c.case_id for c in repo.list_for_user(bob)} == {owned.case_id}


def test_schema_has_users_and_memberships_without_altering_cases_columns(tmp_path):
    db = tmp_path / "cases.sqlite3"
    CaseRepository(db)
    connection = sqlite3.connect(db)
    try:
        case_columns = [row[1] for row in connection.execute("PRAGMA table_info(cases)")]
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        connection.close()

    assert case_columns == [
        "case_id", "name", "case_number", "claimant", "respondent",
        "status", "created_at", "updated_at",
    ]
    assert {"legalrag_users", "matter_memberships"} <= tables


def test_member_listing_requires_access_and_exposes_only_active_members(tmp_path):
    repo = CaseRepository(tmp_path / "cases.sqlite3")
    owner = user("owner@example.com")
    solicitor = user("solicitor@example.com")
    reviewer = user("reviewer@example.com")
    outsider = user("outsider@example.com")
    case = Case.create("Shared matter")
    repo.create_for_user(case, owner)
    repo.grant_membership(
        actor=owner, case_id=case.case_id, user=solicitor, role=MatterRole.SOLICITOR
    )
    repo.grant_membership(
        actor=owner, case_id=case.case_id, user=reviewer, role=MatterRole.REVIEWER
    )

    members = repo.list_memberships(actor=solicitor, case_id=case.case_id)
    assert [(u.email, m.role) for u, m in members] == [
        ("owner@example.com", MatterRole.OWNER),
        ("solicitor@example.com", MatterRole.SOLICITOR),
        ("reviewer@example.com", MatterRole.REVIEWER),
    ]

    with pytest.raises(MatterAccessError):
        repo.list_memberships(actor=outsider, case_id=case.case_id)

    repo.revoke_membership(actor=owner, case_id=case.case_id, user=reviewer)
    assert [u.email for u, _ in repo.list_memberships(actor=owner, case_id=case.case_id)] == [
        "owner@example.com",
        "solicitor@example.com",
    ]


@pytest.mark.parametrize(
    ("role", "can_manage"),
    [
        (MatterRole.OWNER, True),
        (MatterRole.SOLICITOR, True),
        (MatterRole.REVIEWER, False),
        (MatterRole.READ_ONLY, False),
    ],
)
def test_role_capability_contract(role, can_manage):
    from case_management import MatterMembership

    membership = MatterMembership(
        case_id="case-1",
        user_id="user-1",
        role=role,
    )
    assert membership.can_manage_matter is can_manage
