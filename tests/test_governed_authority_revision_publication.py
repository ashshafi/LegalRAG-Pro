from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path

import pytest

from governed_authority_revision import (
    GOVERNED_AUTHORITY_REVISION_RECEIPT_SCHEMA_VERSION,
    GovernedAuthorityRevisionReceipt,
    dumps_governed_authority_revision_receipt,
)
from governed_authority_revision_publication import (
    GOVERNED_AUTHORITY_REVISION_ROOT_NAME,
    GovernedAuthorityRevisionPublicationError,
    publish_governed_authority_revision_receipt,
)


def _receipt() -> GovernedAuthorityRevisionReceipt:
    base = dict(
        schema_version=GOVERNED_AUTHORITY_REVISION_RECEIPT_SCHEMA_VERSION,
        case_id="8081166d-9889-40bb-8add-5d0893037ff0",
        predecessor_authority_id="sha256:" + "1" * 64,
        successor_authority_id="sha256:" + "2" * 64,
        proposal_id="acp:test",
        approval_event_id="ace:test",
        approval_previous_event_id="ace:previous",
        issue_analysis_id="issue-1",
        element_id="element-1",
        previous_status="disputed",
        previous_confidence="medium",
        new_status="disputed",
        new_confidence="high",
        proposal_history_sha256="sha256:" + "3" * 64,
    )
    import json
    from governed_analytical_authority.identity import canonical_sha256

    revision_id = canonical_sha256(
        json.dumps(base, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    return GovernedAuthorityRevisionReceipt(**base, revision_id=revision_id)


def _root(tmp_path: Path) -> Path:
    return tmp_path / GOVERNED_AUTHORITY_REVISION_ROOT_NAME


def _target(root: Path, receipt: GovernedAuthorityRevisionReceipt) -> Path:
    return (
        root
        / receipt.case_id
        / "receipts"
        / (receipt.revision_id.removeprefix("sha256:") + ".json")
    )


def _staging(root: Path, receipt: GovernedAuthorityRevisionReceipt) -> list[Path]:
    target = _target(root, receipt)
    if not target.parent.exists():
        return []
    prefix = "." + receipt.revision_id.removeprefix("sha256:") + "-"
    return [
        item
        for item in target.parent.iterdir()
        if item.name.startswith(prefix) and item.name.endswith(".tmp")
    ]


def test_publishes_exact_canonical_receipt_to_content_addressed_path(tmp_path):
    receipt = _receipt()
    root = _root(tmp_path)

    path = publish_governed_authority_revision_receipt(receipt, root=root)

    assert path == _target(root, receipt)
    assert path.read_bytes() == dumps_governed_authority_revision_receipt(receipt).encode("utf-8")
    assert _staging(root, receipt) == []


def test_identical_republication_is_idempotent(tmp_path):
    receipt = _receipt()
    root = _root(tmp_path)

    first = publish_governed_authority_revision_receipt(receipt, root=root)
    before = first.read_bytes()
    second = publish_governed_authority_revision_receipt(receipt, root=root)

    assert second == first
    assert second.read_bytes() == before
    assert _staging(root, receipt) == []


def test_conflicting_existing_target_fails_closed_without_overwrite(tmp_path):
    receipt = _receipt()
    root = _root(tmp_path)
    target = _target(root, receipt)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"conflict")
    before = target.read_bytes()

    with pytest.raises(GovernedAuthorityRevisionPublicationError, match="conflicts"):
        publish_governed_authority_revision_receipt(receipt, root=root)

    assert target.read_bytes() == before
    assert _staging(root, receipt) == []


def test_invalid_revision_identity_fails_before_publication(tmp_path):
    receipt = replace(_receipt(), revision_id="sha256:" + "f" * 64)
    root = _root(tmp_path)

    with pytest.raises(GovernedAuthorityRevisionPublicationError, match="identity"):
        publish_governed_authority_revision_receipt(receipt, root=root)

    assert not root.exists()


def test_identical_predecessor_successor_is_blocked_before_publication(tmp_path):
    receipt = _receipt()
    base = replace(
        receipt,
        successor_authority_id=receipt.predecessor_authority_id,
    )
    import json
    from governed_analytical_authority.identity import canonical_sha256

    payload = {
        key: value
        for key, value in vars_from_receipt(base).items()
        if key != "revision_id"
    }
    bad = replace(
        base,
        revision_id=canonical_sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        ),
    )

    root = _root(tmp_path)
    with pytest.raises(GovernedAuthorityRevisionPublicationError, match="identical"):
        publish_governed_authority_revision_receipt(bad, root=root)
    assert not root.exists()


def vars_from_receipt(receipt: GovernedAuthorityRevisionReceipt) -> dict[str, object]:
    return {
        field: getattr(receipt, field)
        for field in (
            "schema_version",
            "case_id",
            "predecessor_authority_id",
            "successor_authority_id",
            "proposal_id",
            "approval_event_id",
            "approval_previous_event_id",
            "issue_analysis_id",
            "element_id",
            "previous_status",
            "previous_confidence",
            "new_status",
            "new_confidence",
            "proposal_history_sha256",
            "revision_id",
        )
    }


def test_nonregular_target_fails_closed(tmp_path):
    receipt = _receipt()
    root = _root(tmp_path)
    target = _target(root, receipt)
    target.mkdir(parents=True)

    with pytest.raises(GovernedAuthorityRevisionPublicationError, match="plain regular"):
        publish_governed_authority_revision_receipt(receipt, root=root)


def test_target_symlink_fails_closed_when_supported(tmp_path):
    receipt = _receipt()
    root = _root(tmp_path)
    target = _target(root, receipt)
    target.parent.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside")
    try:
        target.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink unavailable on this platform: {exc}")

    with pytest.raises(GovernedAuthorityRevisionPublicationError, match="plain regular"):
        publish_governed_authority_revision_receipt(receipt, root=root)

    assert outside.read_bytes() == b"outside"


def test_root_ancestor_symlink_escape_fails_closed_when_supported(tmp_path):
    receipt = _receipt()
    outside = tmp_path / "outside-root"
    outside.mkdir()
    linked = tmp_path / "linked-root"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable on this platform: {exc}")

    root = linked / GOVERNED_AUTHORITY_REVISION_ROOT_NAME
    with pytest.raises(GovernedAuthorityRevisionPublicationError, match="plain directory"):
        publish_governed_authority_revision_receipt(receipt, root=root)

    assert list(outside.iterdir()) == []


def test_parent_symlink_escape_fails_closed_when_supported(tmp_path):
    receipt = _receipt()
    root = _root(tmp_path)
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    case_root = root / receipt.case_id
    try:
        case_root.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable on this platform: {exc}")

    with pytest.raises(GovernedAuthorityRevisionPublicationError, match="plain directory"):
        publish_governed_authority_revision_receipt(receipt, root=root)

    assert list(outside.iterdir()) == []


def test_relative_or_non_path_root_is_blocked_before_publication(tmp_path, monkeypatch):
    receipt = _receipt()
    with pytest.raises(GovernedAuthorityRevisionPublicationError, match="pathlib.Path"):
        publish_governed_authority_revision_receipt(receipt, root=str(tmp_path))  # type: ignore[arg-type]

    monkeypatch.chdir(tmp_path)
    with pytest.raises(GovernedAuthorityRevisionPublicationError, match="absolute"):
        publish_governed_authority_revision_receipt(
            receipt,
            root=Path(GOVERNED_AUTHORITY_REVISION_ROOT_NAME),
        )


def test_hardlink_unavailable_fails_closed_and_cleans_staging(tmp_path, monkeypatch):
    receipt = _receipt()
    root = _root(tmp_path)

    def fail_link(*args, **kwargs):
        raise OSError("hard links unavailable")

    monkeypatch.setattr(os, "link", fail_link)

    with pytest.raises(
        GovernedAuthorityRevisionPublicationError,
        match="create-if-absent",
    ):
        publish_governed_authority_revision_receipt(receipt, root=root)

    assert not _target(root, receipt).exists()
    assert _staging(root, receipt) == []


def test_concurrent_identical_publication_is_idempotent(tmp_path, monkeypatch):
    receipt = _receipt()
    root = _root(tmp_path)
    real_link = os.link

    def concurrent_identical(staging, destination):
        real_link(staging, destination)
        raise FileExistsError("simulated concurrent winner")

    monkeypatch.setattr(os, "link", concurrent_identical)

    path = publish_governed_authority_revision_receipt(receipt, root=root)
    assert path == _target(root, receipt)
    assert path.read_bytes() == dumps_governed_authority_revision_receipt(receipt).encode("utf-8")
    assert _staging(root, receipt) == []


def test_module_lives_outside_frozen_authority_package():
    import governed_authority_revision_publication as publication

    source_path = Path(publication.__file__).resolve()
    frozen_package = source_path.parent / "governed_analytical_authority"
    assert source_path.name == "governed_authority_revision_publication.py"
    assert source_path.parent.name == "src"
    assert not (frozen_package / "revision_publication.py").exists()
