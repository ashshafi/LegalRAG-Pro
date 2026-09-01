from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace

import pytest

from controlled_agentic_analysis import (
    CAA1EvidenceInput,
    build_frozen_inspection_universe,
    evidence_ref_from_binding,
    run_controlled_contradiction_adverse_analysis,
)
from controlled_agentic_analysis_gaps import build_caa2_evidence_text


CASE_ID = "compatibility-case"
AUTHORITY_ID = "sha256:" + ("a" * 64)
EVIDENCE_KEY = "E1"
TEXT = "Exact immutable source evidence text."
RAW_SHA256 = sha256(TEXT.encode("utf-8")).hexdigest()
CANONICAL_SHA256 = "sha256:" + RAW_SHA256


def _patch_source_evidence_binding_contract(monkeypatch) -> None:
    import source_evidence.serialization as serialization
    import source_evidence.validation as validation

    monkeypatch.setattr(validation, "validate_evidence_binding", lambda binding: None)
    monkeypatch.setattr(
        serialization,
        "dumps_evidence_binding",
        lambda binding: b'{"compatibility-test":"binding"}',
    )


def _binding(bound_text_sha256: str):
    return SimpleNamespace(
        case_id=CASE_ID,
        evidence_key=EVIDENCE_KEY,
        bound_text_sha256=bound_text_sha256,
    )


def _run_for_binding(binding):
    ref = evidence_ref_from_binding(binding)
    return build_frozen_inspection_universe(
        case_id=CASE_ID,
        active_authority_id=AUTHORITY_ID,
        evidence_bindings=(ref,),
        agent_definition_version="compatibility-test-agent/v1",
        analysis_engine_identity="compatibility-test-engine/v1",
        execution_configuration={"mode": "sha-compatibility-regression"},
    )


@pytest.mark.parametrize(
    "source_bound_text_sha256",
    (RAW_SHA256, CANONICAL_SHA256),
    ids=("source-raw-64", "canonical-sha256-identity"),
)
def test_caa1_normalizes_supported_bound_text_sha_forms(
    monkeypatch,
    source_bound_text_sha256,
):
    _patch_source_evidence_binding_contract(monkeypatch)
    binding = _binding(source_bound_text_sha256)
    run = _run_for_binding(binding)
    seen = {}

    def engine(request):
        assert len(request.evidence) == 1
        seen["bound_text_sha256"] = request.evidence[0].bound_text_sha256
        return ()

    observations = run_controlled_contradiction_adverse_analysis(
        run=run,
        evidence_inputs=(CAA1EvidenceInput(binding=binding, text=TEXT),),
        analysis_engine=engine,
        authority_loader=lambda _: SimpleNamespace(
            manifest=SimpleNamespace(authority_id=AUTHORITY_ID)
        ),
    )

    assert observations == ()
    assert seen["bound_text_sha256"] == CANONICAL_SHA256


@pytest.mark.parametrize(
    "source_bound_text_sha256",
    (RAW_SHA256, CANONICAL_SHA256),
    ids=("source-raw-64", "canonical-sha256-identity"),
)
def test_caa2_normalizes_supported_bound_text_sha_forms(
    monkeypatch,
    source_bound_text_sha256,
):
    _patch_source_evidence_binding_contract(monkeypatch)
    binding = _binding(source_bound_text_sha256)
    run = _run_for_binding(binding)

    evidence = build_caa2_evidence_text(
        run=run,
        binding=binding,
        text=TEXT,
    )

    assert evidence.bound_text_sha256 == CANONICAL_SHA256
    assert evidence.text == TEXT
