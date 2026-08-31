from __future__ import annotations

from types import SimpleNamespace

import pytest

from controlled_agentic_analysis import (
    CAA1_EVIDENCE_REF_SCHEMA_VERSION,
    CAA1EvidenceRef,
    Materiality,
    ObservationConfidence,
    ObservationType,
    build_agent_observation,
    build_frozen_inspection_universe,
)
from controlled_agentic_analysis_publication import (
    CAA1PublicationError,
    publish_caa1_run,
)


CASE = "8081166d-9889-40bb-8add-5d0893037ff0"
AUTH = "sha256:" + "a" * 64


def ref(key, ch):
    return CAA1EvidenceRef(
        schema_version=CAA1_EVIDENCE_REF_SCHEMA_VERSION,
        case_id=CASE,
        evidence_key=key,
        evidence_binding_sha256="sha256:" + ch * 64,
    )


def run():
    return build_frozen_inspection_universe(
        case_id=CASE,
        active_authority_id=AUTH,
        evidence_bindings=(ref("E1", "1"), ref("E2", "2")),
        agent_definition_version="caa1/v1",
        analysis_engine_identity="test-engine/v1",
        execution_configuration={"mode": "bounded"},
    )


def obs(value):
    return build_agent_observation(
        run=value,
        observation_type=ObservationType.CONTRADICTION,
        title="Conflict",
        summary="Two records conflict.",
        supporting_evidence_keys=("E1",),
        contrary_evidence_keys=("E2",),
        reasoning_summary="The propositions are materially incompatible.",
        materiality=Materiality.HIGH,
        observation_confidence=ObservationConfidence.MEDIUM,
        uncertainty="Context may distinguish the records.",
        limitations=("Frozen scope only.",),
    )


def loader(authority=AUTH):
    return lambda case_id: SimpleNamespace(manifest=SimpleNamespace(authority_id=authority))


def test_publish_run_and_observation_is_append_only(tmp_path):
    value = run()
    result = publish_caa1_run(
        run=value,
        observations=(obs(value),),
        root=tmp_path,
        active_authority_loader=loader(),
    )
    assert result.run_path.is_file()
    assert len(result.observation_paths) == 1
    assert result.observation_paths[0].is_file()


def test_identical_republication_is_idempotent(tmp_path):
    value = run()
    first = publish_caa1_run(
        run=value,
        observations=(obs(value),),
        root=tmp_path,
        active_authority_loader=loader(),
    )
    before = first.run_path.read_bytes(), first.observation_paths[0].read_bytes()
    second = publish_caa1_run(
        run=value,
        observations=(obs(value),),
        root=tmp_path,
        active_authority_loader=loader(),
    )
    after = second.run_path.read_bytes(), second.observation_paths[0].read_bytes()
    assert first == second
    assert before == after


def test_authority_drift_blocks_publication(tmp_path):
    value = run()
    with pytest.raises(CAA1PublicationError, match="Active authority changed"):
        publish_caa1_run(
            run=value,
            observations=(obs(value),),
            root=tmp_path,
            active_authority_loader=loader("sha256:" + "b" * 64),
        )
    assert not any(tmp_path.rglob("*"))


def test_conflicting_existing_run_is_blocked(tmp_path):
    value = run()
    result = publish_caa1_run(
        run=value,
        observations=(obs(value),),
        root=tmp_path,
        active_authority_loader=loader(),
    )
    result.run_path.write_bytes(b"conflict")
    with pytest.raises(CAA1PublicationError, match="Conflicting immutable"):
        publish_caa1_run(
            run=value,
            observations=(obs(value),),
            root=tmp_path,
            active_authority_loader=loader(),
        )


def test_conflicting_existing_observation_is_blocked(tmp_path):
    value = run()
    result = publish_caa1_run(
        run=value,
        observations=(obs(value),),
        root=tmp_path,
        active_authority_loader=loader(),
    )
    result.observation_paths[0].write_bytes(b"conflict")
    with pytest.raises(CAA1PublicationError, match="Conflicting immutable"):
        publish_caa1_run(
            run=value,
            observations=(obs(value),),
            root=tmp_path,
            active_authority_loader=loader(),
        )


def test_no_staging_residue(tmp_path):
    value = run()
    publish_caa1_run(
        run=value,
        observations=(obs(value),),
        root=tmp_path,
        active_authority_loader=loader(),
    )
    assert not tuple(tmp_path.rglob(".staging-*"))


def test_relative_root_is_rejected(tmp_path, monkeypatch):
    value = run()
    with pytest.raises(CAA1PublicationError, match="must be absolute"):
        publish_caa1_run(
            run=value,
            observations=(obs(value),),
            root=tmp_path.relative_to(tmp_path.parent),
            active_authority_loader=loader(),
        )


def test_empty_observation_set_is_published_as_a_valid_run(tmp_path):
    value = run()
    result = publish_caa1_run(
        run=value,
        observations=(),
        root=tmp_path,
        active_authority_loader=loader(),
    )
    assert result.run_path.is_file()
    assert result.observation_paths == ()
