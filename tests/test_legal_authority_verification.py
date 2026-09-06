from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import legal_authority_verification as lav
from evidence_classification import EvidenceSourceType


CASE_ID = "8081166d-9889-40bb-8add-5d0893037ff0"
BINDING_ID = "sha256:" + ("1" * 64)
TEXT_SHA = "2" * 64


def make_binding(**overrides):
    values = dict(
        case_id=CASE_ID,
        evidence_key="authority-evidence-1",
        evidence_binding_id=BINDING_ID,
        bound_text_sha256=TEXT_SHA,
        document_name="Smith v Jones [2024] EAT 1.pdf",
        page=3,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def make_target(**binding_overrides):
    return lav.build_legal_authority_verification_target(
        binding=make_binding(**binding_overrides),
        source_type=EvidenceSourceType.LEGAL_AUTHORITY,
        authority_reference="Smith v Jones [2024] EAT 1",
    )


def verify(target, tmp_path, **overrides):
    values = dict(
        target=target,
        decision=lav.LegalAuthorityVerificationDecision.VERIFIED_FOR_RELIANCE,
        genuine=True,
        citation_verifiable=True,
        relevant_to_matter=True,
        supports_attributed_proposition=True,
        verification_source="The National Archives",
        verification_source_reference="https://example.invalid/authority/1",
        reviewer_reference="solicitor:reviewer-1",
        review_note="Citation, authority identity, relevance and attributed proposition checked.",
        root=tmp_path,
    )
    values.update(overrides)
    return lav.record_legal_authority_verification(**values)


def test_classification_is_not_verification():
    with pytest.raises(
        lav.LegalAuthorityVerificationError,
        match="Only material classified as LEGAL_AUTHORITY",
    ):
        lav.build_legal_authority_verification_target(
            binding=make_binding(),
            source_type=EvidenceSourceType.EMPLOYER_RECORD,
            authority_reference="Not a legal authority",
        )


def test_target_is_bound_to_exact_evidence_binding_and_text():
    first = make_target()
    changed_binding = make_target(
        evidence_binding_id="sha256:" + ("3" * 64),
    )
    changed_text = make_target(
        bound_text_sha256="4" * 64,
    )

    assert first.target_id.startswith("sha256:")
    assert first.target_id != changed_binding.target_id
    assert first.target_id != changed_text.target_id


def test_verified_for_reliance_requires_all_professional_checks(tmp_path, monkeypatch):
    monkeypatch.setattr(lav, "_now", lambda: "2026-09-03T12:00:00+00:00")
    target = make_target()

    with pytest.raises(
        lav.LegalAuthorityVerificationError,
        match="every professional verification check",
    ):
        verify(
            target,
            tmp_path,
            supports_attributed_proposition=False,
        )

    assert lav.load_legal_authority_verification_events(
        CASE_ID,
        root=tmp_path,
    ) == ()


def test_verified_event_is_append_only_and_projects_current_state(tmp_path, monkeypatch):
    times = iter(
        (
            "2026-09-03T12:00:00+00:00",
            "2026-09-03T12:05:00+00:00",
        )
    )
    monkeypatch.setattr(lav, "_now", lambda: next(times))
    target = make_target()

    verified = verify(target, tmp_path)
    rejected = lav.record_legal_authority_verification(
        target=target,
        decision=lav.LegalAuthorityVerificationDecision.REJECTED,
        genuine=True,
        citation_verifiable=True,
        relevant_to_matter=False,
        supports_attributed_proposition=True,
        verification_source="The National Archives",
        verification_source_reference="https://example.invalid/authority/1",
        reviewer_reference="solicitor:reviewer-1",
        review_note="Later review found this authority was not relevant to the issue.",
        root=tmp_path,
    )

    assert rejected.previous_event_id == verified.event_id

    events = lav.load_legal_authority_verification_events(CASE_ID, root=tmp_path)
    assert len(events) == 2
    projection = lav.project_legal_authority_verification(
        target=target,
        events=events,
    )
    assert projection is not None
    assert projection.state is lav.LegalAuthorityVerificationState.REJECTED

    with pytest.raises(
        lav.LegalAuthorityVerificationError,
        match="not currently professionally verified",
    ):
        lav.assert_legal_authority_verified_for_reliance(
            target=target,
            events=events,
        )


def test_exact_verified_target_can_be_asserted_for_reliance(tmp_path, monkeypatch):
    monkeypatch.setattr(lav, "_now", lambda: "2026-09-03T12:00:00+00:00")
    target = make_target()
    verify(target, tmp_path)

    events = lav.load_legal_authority_verification_events(CASE_ID, root=tmp_path)
    projection = lav.assert_legal_authority_verified_for_reliance(
        target=target,
        events=events,
    )

    assert projection.state is lav.LegalAuthorityVerificationState.VERIFIED_FOR_RELIANCE
    assert projection.target.target_id == target.target_id


def test_verification_does_not_transfer_to_changed_authority_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(lav, "_now", lambda: "2026-09-03T12:00:00+00:00")
    original = make_target()
    verify(original, tmp_path)

    changed = lav.build_legal_authority_verification_target(
        binding=make_binding(evidence_binding_id="sha256:" + ("5" * 64)),
        source_type=EvidenceSourceType.LEGAL_AUTHORITY,
        authority_reference=original.authority_reference,
    )
    events = lav.load_legal_authority_verification_events(CASE_ID, root=tmp_path)

    assert lav.project_legal_authority_verification(
        target=changed,
        events=events,
    ) is None

    with pytest.raises(lav.LegalAuthorityVerificationError):
        lav.assert_legal_authority_verified_for_reliance(
            target=changed,
            events=events,
        )


def test_tampered_event_identity_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(lav, "_now", lambda: "2026-09-03T12:00:00+00:00")
    target = make_target()
    verify(target, tmp_path)

    path = lav.verification_event_path(CASE_ID, root=tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["review_note"] = "tampered"
    path.write_text(
        json.dumps(raw, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        lav.LegalAuthorityVerificationError,
        match="event_id does not match",
    ):
        lav.load_legal_authority_verification_events(CASE_ID, root=tmp_path)


def test_parallel_or_broken_event_chain_fails_closed(tmp_path, monkeypatch):
    times = iter(
        (
            "2026-09-03T12:00:00+00:00",
            "2026-09-03T12:05:00+00:00",
        )
    )
    monkeypatch.setattr(lav, "_now", lambda: next(times))
    target = make_target()
    verify(target, tmp_path)
    verify(target, tmp_path)

    path = lav.verification_event_path(CASE_ID, root=tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    second = json.loads(lines[1])
    second["previous_event_id"] = None

    # Recompute the event identity so this tests chain validation, not hash validation.
    provisional = lav._event_from_dict(
        {
            **second,
            "previous_event_id": lines and json.loads(lines[0])["event_id"],
        }
    )
    second["previous_event_id"] = None
    event = lav.LegalAuthorityVerificationEvent(
        **{
            **lav.asdict(provisional),
            "previous_event_id": None,
            "event_id": "sha256:" + ("0" * 64),
        }
    )
    second["event_id"] = lav._derive_id(lav._event_identity_payload(event))
    path.write_text(
        lines[0] + "\n" + json.dumps(second, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        lav.LegalAuthorityVerificationError,
        match="invalid target event chain",
    ):
        lav.load_legal_authority_verification_events(CASE_ID, root=tmp_path)


def test_reviewer_and_external_verification_source_are_mandatory(tmp_path, monkeypatch):
    monkeypatch.setattr(lav, "_now", lambda: "2026-09-03T12:00:00+00:00")
    target = make_target()

    for field, value in (
        ("reviewer_reference", ""),
        ("verification_source", ""),
        ("verification_source_reference", ""),
        ("review_note", ""),
    ):
        with pytest.raises(lav.LegalAuthorityVerificationError):
            verify(target, tmp_path, **{field: value})


def test_case_path_validation_fails_closed(tmp_path):
    with pytest.raises(lav.LegalAuthorityVerificationError, match="case_id is invalid"):
        lav.verification_event_path("../escape", root=tmp_path)


def test_missing_history_is_unverified_not_verified(tmp_path):
    target = make_target()
    events = lav.load_legal_authority_verification_events(CASE_ID, root=tmp_path)

    assert events == ()
    assert lav.project_legal_authority_verification(target=target, events=events) is None
    with pytest.raises(lav.LegalAuthorityVerificationError):
        lav.assert_legal_authority_verified_for_reliance(
            target=target,
            events=events,
        )
