from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from controlled_agentic_analysis import (
    CAA1_EVIDENCE_REF_SCHEMA_VERSION,
    CAA1EvidenceRef,
    build_frozen_inspection_universe,
)
from controlled_agentic_analysis_gaps import (
    CAA2_EVIDENCE_TEXT_SCHEMA_VERSION,
    CAA2EvidenceText,
    execute_caa2_analysis,
    project_gap_candidates,
)
from controlled_agentic_analysis_gaps_publication import (
    CAA2PublicationError,
    publish_caa2_analysis,
)


CASE = "8081166d-9889-40bb-8add-5d0893037ff0"
AUTH = "sha256:" + "a" * 64


def run():
    return build_frozen_inspection_universe(
        case_id=CASE,
        active_authority_id=AUTH,
        evidence_bindings=(
            CAA1EvidenceRef(
                schema_version=CAA1_EVIDENCE_REF_SCHEMA_VERSION,
                case_id=CASE,
                evidence_key="E1",
                evidence_binding_sha256="sha256:" + "1" * 64,
            ),
        ),
        agent_definition_version="caa2/v1",
        analysis_engine_identity="test/v1",
        execution_configuration={"mode": "bounded"},
    )


def authority():
    element = SimpleNamespace(
        element_id="E-MISSING",
        legal_question="What evidence supports this element?",
        analysis_status="insufficiently_evidenced",
        established_matters=(),
        supported_matters=(),
        not_supported_matters=(),
        supporting_evidence_keys=(),
        adverse_evidence_keys=(),
        corroborative_evidence_keys=(),
        neutral_evidence_keys=(),
        conflicting_evidence_keys=(),
        unresolved_matters=(),
    )
    issue = SimpleNamespace(
        issue_analysis_id="ISSUE-1",
        issue_definition_id="DEF-1",
        element_records=(element,),
    )
    return SimpleNamespace(
        manifest=SimpleNamespace(case_id=CASE, authority_id=AUTH),
        case_matrices=SimpleNamespace(issue_matrix=(issue,)),
        structured_legal_analysis_results=(),
    )


def text():
    raw = "alpha"
    import hashlib
    return CAA2EvidenceText(
        schema_version=CAA2_EVIDENCE_TEXT_SCHEMA_VERSION,
        case_id=CASE,
        evidence_key="E1",
        evidence_binding_sha256="sha256:" + "1" * 64,
        bound_text_sha256="sha256:" + hashlib.sha256(raw.encode()).hexdigest(),
        text=raw,
    )


def result():
    r = run()
    a = authority()
    return execute_caa2_analysis(
        run=r,
        authority=a,
        evidence_texts=(text(),),
        analysis_engine=lambda request: [],
        active_authority_loader=lambda case_id: a,
    )


def loader(authority_id=AUTH):
    return lambda case_id: SimpleNamespace(
        manifest=SimpleNamespace(case_id=CASE, authority_id=authority_id)
    )


def test_publication_is_immutable_and_idempotent(tmp_path):
    value = result()
    first = publish_caa2_analysis(
        result=value,
        root=tmp_path,
        active_authority_loader=loader(),
    )
    before = {
        path: path.read_bytes()
        for path in (first.manifest_path, first.run_path, first.candidates_path, *first.observation_paths)
    }
    second = publish_caa2_analysis(
        result=value,
        root=tmp_path,
        active_authority_loader=loader(),
    )
    assert first == second
    assert before == {
        path: path.read_bytes()
        for path in (second.manifest_path, second.run_path, second.candidates_path, *second.observation_paths)
    }


def test_conflicting_existing_payload_is_never_repaired(tmp_path):
    value = result()
    published = publish_caa2_analysis(
        result=value,
        root=tmp_path,
        active_authority_loader=loader(),
    )
    published.candidates_path.write_bytes(b"conflict")
    with pytest.raises(CAA2PublicationError, match="Conflicting immutable"):
        publish_caa2_analysis(
            result=value,
            root=tmp_path,
            active_authority_loader=loader(),
        )
    assert published.candidates_path.read_bytes() == b"conflict"


def test_authority_drift_blocks_publication_before_writes(tmp_path):
    value = result()
    with pytest.raises(CAA2PublicationError, match="Active authority changed"):
        publish_caa2_analysis(
            result=value,
            root=tmp_path,
            active_authority_loader=loader("sha256:" + "f" * 64),
        )
    assert not any(tmp_path.rglob("*"))


def test_zero_observation_result_is_publishable(tmp_path):
    r = run()
    a = SimpleNamespace(
        manifest=SimpleNamespace(case_id=CASE, authority_id=AUTH),
        case_matrices=SimpleNamespace(issue_matrix=()),
        structured_legal_analysis_results=(),
    )
    value = execute_caa2_analysis(
        run=r,
        authority=a,
        evidence_texts=(text(),),
        analysis_engine=lambda request: [],
        active_authority_loader=lambda case_id: a,
    )
    assert value.observations == ()
    published = publish_caa2_analysis(
        result=value,
        root=tmp_path,
        active_authority_loader=loader(),
    )
    assert published.observation_paths == ()
    assert published.manifest_path.is_file()


def test_relative_root_is_rejected(tmp_path):
    with pytest.raises(CAA2PublicationError, match="must be absolute"):
        publish_caa2_analysis(
            result=result(),
            root=tmp_path.relative_to(tmp_path.parent),
            active_authority_loader=loader(),
        )


def test_no_staging_residue(tmp_path):
    published = publish_caa2_analysis(
        result=result(),
        root=tmp_path,
        active_authority_loader=loader(),
    )
    assert not tuple(published.run_root.rglob(".staging-*"))
