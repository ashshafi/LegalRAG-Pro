from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

import work_product_release as wpr


CASE_ID = "8081166d-9889-40bb-8add-5d0893037ff0"
PROJECTION_ID = "11111111-1111-4111-8111-111111111111"
MANIFEST_ID = "22222222-2222-4222-8222-222222222222"


def projection(
    *,
    projection_id: str = PROJECTION_ID,
    payload_sha: str = "1" * 64,
    manifest_id: str = MANIFEST_ID,
):
    return SimpleNamespace(
        case_header=SimpleNamespace(case_id=CASE_ID),
        report_projection_id=projection_id,
        projection_payload_sha256=payload_sha,
        manifest=SimpleNamespace(manifest_id=manifest_id),
    )


def markdown_artifact(
    *,
    projection_id: str = PROJECTION_ID,
    payload_sha: str = "1" * 64,
    manifest_id: str = MANIFEST_ID,
    report_manifest=None,
    text: str = "# Functional report\n",
    artifact_id: str = "33333333-3333-4333-8333-333333333333",
):
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return SimpleNamespace(
        markdown_report_id=artifact_id,
        markdown_sha256=digest,
        markdown=text,
        report_projection_id=projection_id,
        projection_payload_sha256=payload_sha,
        manifest_id=manifest_id,
        report_manifest=report_manifest,
        renderer_version="case-report-markdown/1.0",
        output_profile="full-audit",
    )


def pdf_artifact(
    *,
    projection_id: str = PROJECTION_ID,
    payload_sha: str = "1" * 64,
    manifest_id: str = MANIFEST_ID,
    report_manifest=None,
    payload: bytes = b"%PDF-functional",
    artifact_id: str = "44444444-4444-4444-8444-444444444444",
):
    digest = hashlib.sha256(payload).hexdigest()
    return SimpleNamespace(
        pdf_report_id=artifact_id,
        pdf_sha256=digest,
        pdf=payload,
        report_projection_id=projection_id,
        projection_payload_sha256=payload_sha,
        manifest_id=manifest_id,
        report_manifest=report_manifest,
        renderer_version="case-report-pdf/1.0",
        output_profile="full-audit",
    )


def target(*, artifact=None, artifact_format="markdown", projection_value=None):
    if projection_value is None:
        projection_value = projection()
    if artifact is None:
        artifact = markdown_artifact(
            report_manifest=projection_value.manifest,
        )
    elif getattr(artifact, "report_manifest", None) is None:
        artifact.report_manifest = projection_value.manifest
    return wpr.build_work_product_release_target(
        projection=projection_value,
        artifact=artifact,
        artifact_format=artifact_format,
    )


def approve(t, root, **overrides):
    values = dict(
        target=t,
        decision=wpr.WorkProductReleaseDecision.APPROVED_FOR_RELIANCE,
        factual_basis_reviewed=True,
        legal_authorities_reviewed=True,
        unverified_authorities_remaining=0,
        professional_judgment_completed=True,
        court_or_tribunal_reliance=False,
        reviewer_reference="solicitor:functional-reviewer",
        review_note="Exact work product professionally reviewed.",
        root=root,
    )
    values.update(overrides)
    return wpr.record_work_product_release(**values)


def test_target_binds_exact_projection_and_artifact_bytes():
    t = target()

    assert t.case_id == CASE_ID
    assert t.report_projection_id == PROJECTION_ID
    assert t.projection_payload_sha256 == "1" * 64
    assert t.manifest_id == MANIFEST_ID
    assert t.artifact_format == "markdown"
    assert t.artifact_sha256 == hashlib.sha256(
        b"# Functional report\n"
    ).hexdigest()
    assert t.target_id.startswith("sha256:")


def test_artifact_hash_mismatch_fails_closed():
    artifact = markdown_artifact()
    artifact.markdown_sha256 = "0" * 64

    with pytest.raises(
        wpr.WorkProductReleaseError,
        match="exact rendered bytes",
    ):
        target(artifact=artifact)


def test_artifact_report_manifest_must_match_projection():
    projection_value = projection()
    artifact = markdown_artifact(
        report_manifest=SimpleNamespace(
            manifest_id=MANIFEST_ID,
            extra="different manifest state",
        )
    )

    with pytest.raises(
        wpr.WorkProductReleaseError,
        match="report manifest does not match",
    ):
        target(
            artifact=artifact,
            projection_value=projection_value,
        )


def test_manual_noncanonical_target_fails_closed():
    t = target()
    changed = replace(
        t,
        artifact_id="AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA",
    )

    with pytest.raises(
        wpr.WorkProductReleaseError,
        match="artifact_id is not canonical",
    ):
        wpr.project_work_product_release(
            target=changed,
            events=(),
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "report_projection_id",
            "55555555-5555-4555-8555-555555555555",
            "projection ID",
        ),
        (
            "projection_payload_sha256",
            "2" * 64,
            "payload SHA",
        ),
        (
            "manifest_id",
            "66666666-6666-4666-8666-666666666666",
            "manifest ID",
        ),
    ],
)
def test_artifact_must_match_exact_projection(field, value, message):
    artifact = markdown_artifact()
    setattr(artifact, field, value)

    with pytest.raises(wpr.WorkProductReleaseError, match=message):
        target(artifact=artifact)


def test_target_identity_changes_for_re_render_projection_change_and_format():
    first = target()

    different_bytes = target(
        artifact=markdown_artifact(
            text="# Functional report changed\n",
            artifact_id="77777777-7777-4777-8777-777777777777",
        )
    )

    changed_projection = projection(
        projection_id="88888888-8888-4888-8888-888888888888",
        payload_sha="8" * 64,
        manifest_id="99999999-9999-4999-8999-999999999999",
    )
    changed_projection_artifact = markdown_artifact(
        projection_id=changed_projection.report_projection_id,
        payload_sha=changed_projection.projection_payload_sha256,
        manifest_id=changed_projection.manifest.manifest_id,
        artifact_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    )
    second_projection = target(
        projection_value=changed_projection,
        artifact=changed_projection_artifact,
    )

    pdf = target(
        artifact=pdf_artifact(),
        artifact_format="pdf",
    )

    assert len(
        {
            first.target_id,
            different_bytes.target_id,
            second_projection.target_id,
            pdf.target_id,
        }
    ) == 4


def test_missing_release_history_is_working_and_not_approved(tmp_path):
    t = target()
    events = wpr.load_work_product_release_events(CASE_ID, root=tmp_path)

    projected = wpr.project_work_product_release(target=t, events=events)
    assert projected.state is wpr.WorkProductReleaseState.WORKING
    assert projected.latest_event_id is None
    assert projected.court_or_tribunal_reliance is False

    with pytest.raises(wpr.WorkProductReleaseError):
        wpr.assert_work_product_approved_for_reliance(
            target=t,
            events=events,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("factual_basis_reviewed", False),
        ("legal_authorities_reviewed", False),
        ("unverified_authorities_remaining", 1),
        ("professional_judgment_completed", False),
    ],
)
def test_approval_requires_every_professional_release_gate(
    tmp_path,
    field,
    value,
):
    t = target()

    with pytest.raises(
        wpr.WorkProductReleaseError,
        match="APPROVED_FOR_RELIANCE requires",
    ):
        approve(t, tmp_path, **{field: value})

    assert wpr.load_work_product_release_events(
        CASE_ID,
        root=tmp_path,
    ) == ()


@pytest.mark.parametrize("field", ["reviewer_reference", "review_note"])
def test_approval_requires_professional_provenance(tmp_path, field):
    t = target()

    with pytest.raises(wpr.WorkProductReleaseError):
        approve(t, tmp_path, **{field: ""})

    assert wpr.load_work_product_release_events(
        CASE_ID,
        root=tmp_path,
    ) == ()


def test_general_reliance_approval_does_not_imply_court_or_tribunal(tmp_path):
    t = target()
    approve(t, tmp_path, court_or_tribunal_reliance=False)
    events = wpr.load_work_product_release_events(CASE_ID, root=tmp_path)

    projection_value = wpr.assert_work_product_approved_for_reliance(
        target=t,
        events=events,
    )
    assert (
        projection_value.state
        is wpr.WorkProductReleaseState.APPROVED_FOR_RELIANCE
    )
    assert projection_value.court_or_tribunal_reliance is False

    with pytest.raises(
        wpr.WorkProductReleaseError,
        match="court or tribunal",
    ):
        wpr.assert_work_product_approved_for_court_or_tribunal_reliance(
            target=t,
            events=events,
        )


def test_explicit_court_or_tribunal_approval_is_separate(tmp_path):
    t = target()
    approve(t, tmp_path, court_or_tribunal_reliance=True)
    events = wpr.load_work_product_release_events(CASE_ID, root=tmp_path)

    projection_value = (
        wpr.assert_work_product_approved_for_court_or_tribunal_reliance(
            target=t,
            events=events,
        )
    )
    assert projection_value.court_or_tribunal_reliance is True


def test_rejected_event_cannot_approve_court_or_tribunal_reliance(tmp_path):
    t = target()

    with pytest.raises(
        wpr.WorkProductReleaseError,
        match="rejected event",
    ):
        wpr.record_work_product_release(
            target=t,
            decision=wpr.WorkProductReleaseDecision.REJECTED,
            factual_basis_reviewed=False,
            legal_authorities_reviewed=False,
            unverified_authorities_remaining=3,
            professional_judgment_completed=False,
            court_or_tribunal_reliance=True,
            reviewer_reference="solicitor:reviewer",
            review_note="Rejected.",
            root=tmp_path,
        )


def test_append_only_approval_rejection_reapproval_lifecycle(tmp_path, monkeypatch):
    t = target()
    times = iter(
        (
            "2026-09-03T16:00:00+00:00",
            "2026-09-03T16:05:00+00:00",
            "2026-09-03T16:10:00+00:00",
        )
    )
    monkeypatch.setattr(wpr, "_now", lambda: next(times))

    first = approve(t, tmp_path)
    second = wpr.record_work_product_release(
        target=t,
        decision=wpr.WorkProductReleaseDecision.REJECTED,
        factual_basis_reviewed=True,
        legal_authorities_reviewed=True,
        unverified_authorities_remaining=1,
        professional_judgment_completed=True,
        court_or_tribunal_reliance=False,
        reviewer_reference="solicitor:functional-reviewer",
        review_note="Later review found one unverified authority.",
        root=tmp_path,
    )
    third = approve(
        t,
        tmp_path,
        court_or_tribunal_reliance=True,
        review_note="Re-review completed; approved for tribunal reliance.",
    )

    assert second.previous_event_id == first.event_id
    assert third.previous_event_id == second.event_id

    events = wpr.load_work_product_release_events(CASE_ID, root=tmp_path)
    assert len(events) == 3
    projected = (
        wpr.assert_work_product_approved_for_court_or_tribunal_reliance(
            target=t,
            events=events,
        )
    )
    assert projected.latest_event_id == third.event_id


def test_approval_does_not_transfer_to_changed_artifact_identity(tmp_path):
    original = target()
    approve(original, tmp_path)
    events = wpr.load_work_product_release_events(CASE_ID, root=tmp_path)

    changed = target(
        artifact=markdown_artifact(
            text="# Changed bytes\n",
            artifact_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        )
    )

    projected = wpr.project_work_product_release(
        target=changed,
        events=events,
    )
    assert projected.state is wpr.WorkProductReleaseState.WORKING


def test_tampered_history_fails_closed(tmp_path):
    t = target()
    approve(t, tmp_path)

    path = wpr.release_event_path(CASE_ID, root=tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["review_note"] = "tampered"
    path.write_text(
        json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        wpr.WorkProductReleaseError,
        match="event_id does not match",
    ):
        wpr.load_work_product_release_events(CASE_ID, root=tmp_path)


def test_duplicate_history_fails_closed(tmp_path):
    t = target()
    approve(t, tmp_path)

    path = wpr.release_event_path(CASE_ID, root=tmp_path)
    line = path.read_text(encoding="utf-8")
    path.write_text(line + line, encoding="utf-8")

    with pytest.raises(wpr.WorkProductReleaseError):
        wpr.load_work_product_release_events(CASE_ID, root=tmp_path)


def test_case_path_traversal_fails_closed(tmp_path):
    with pytest.raises(
        wpr.WorkProductReleaseError,
        match="case_id is invalid",
    ):
        wpr.release_event_path("../escape", root=tmp_path)
