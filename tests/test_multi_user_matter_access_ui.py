from __future__ import annotations

from pathlib import Path


def test_matter_access_ui_is_owner_managed_and_uses_repository_boundary():
    source = (Path(__file__).parents[1] / "src" / "ui" / "cases.py").read_text(encoding="utf-8")

    assert 'with st.sidebar.expander("👥 Matter access")' in source
    assert "repository.list_memberships(actor=user, case_id=case.case_id)" in source
    assert "access.role is MatterRole.OWNER" in source
    assert "access.role is not MatterRole.OWNER" in source
    assert "repository.grant_membership(" in source
    assert "repository.revoke_membership(" in source
    assert "MatterRole.SOLICITOR" in source
    assert "MatterRole.REVIEWER" in source
    assert "MatterRole.READ_ONLY" in source
    assert "MatterRole.OWNER," not in source.split('options=(', 1)[1].split(')', 1)[0]


def test_second_user_sign_in_remains_separately_allowlisted():
    source = (Path(__file__).parents[1] / "src" / "ui" / "cases.py").read_text(encoding="utf-8")
    assert "must also be authorised by the LegalRAG sign-in allowlist" in source
