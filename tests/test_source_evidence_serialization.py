from __future__ import annotations

import json
from dataclasses import replace

import pytest

from source_evidence.identity import canonical_json_bytes, derive_sha256_id, sha256_bytes
from source_evidence.models import (
    EVIDENCE_BINDING_SCHEMA_VERSION,
    PROJECTION_EVIDENCE_BINDING_SCHEMA_VERSION,
    SOURCE_BOUND_ANALYSIS_RECEIPT_SCHEMA_VERSION,
    BindingClass,
    BoundTextRole,
    ProjectionBindingCoverage,
    ProjectionBindingEntry,
    ProjectionEvidenceBindingManifest,
    SourceBoundAnalysisReceipt,
    VerifiedEvidenceUse,
)
from source_evidence.serialization import (
    dumps_evidence_binding,
    dumps_projection_evidence_binding_manifest,
    dumps_source_bound_analysis_receipt,
    dumps_source_document_manifest,
    evidence_binding_identity_payload_to_dict,
    loads_evidence_binding,
    loads_projection_evidence_binding_manifest,
    loads_source_bound_analysis_receipt,
    loads_source_document_manifest,
    projection_evidence_binding_manifest_identity_payload_to_dict,
    source_bound_analysis_receipt_identity_payload_to_dict,
)

from test_source_evidence_models import (
    CASE_ID,
    REPORT_ID,
    REPORT_MANIFEST_ID,
    make_binding,
    make_manifest,
)


def make_receipt() -> SourceBoundAnalysisReceipt:
    binding = make_binding()
    value = SourceBoundAnalysisReceipt(
        schema_version=SOURCE_BOUND_ANALYSIS_RECEIPT_SCHEMA_VERSION,
        case_id=CASE_ID,
        verifier_version="source-bound-retrieval-verifier/1.0",
        verified_evidence=(
            VerifiedEvidenceUse(
                evidence_key="chunk-1",
                evidence_binding_id=binding.evidence_binding_id,
                chunk_text_sha256=binding.chunk_text_sha256 or "",
            ),
        ),
        source_bound_analysis_receipt_id="sha256:" + "0" * 64,
    )
    return replace(
        value,
        source_bound_analysis_receipt_id=derive_sha256_id(
            source_bound_analysis_receipt_identity_payload_to_dict(value)
        ),
    )


def make_projection_manifest() -> ProjectionEvidenceBindingManifest:
    binding = make_binding()
    receipt = make_receipt()
    value = ProjectionEvidenceBindingManifest(
        schema_version=PROJECTION_EVIDENCE_BINDING_SCHEMA_VERSION,
        case_id=CASE_ID,
        report_projection_id=REPORT_ID,
        projection_payload_sha256=sha256_bytes(b"projection"),
        manifest_id=REPORT_MANIFEST_ID,
        coverage=ProjectionBindingCoverage.FULLY_SOURCE_BOUND,
        entries=(
            ProjectionBindingEntry(
                citation_id="chunk-1",
                evidence_key="chunk-1",
                binding_class=BindingClass.FULL_CHAIN_BOUND,
                evidence_binding_id=binding.evidence_binding_id,
                source_bound_analysis_receipt_id=receipt.source_bound_analysis_receipt_id,
            ),
        ),
        projection_evidence_binding_manifest_id="sha256:" + "0" * 64,
    )
    return replace(
        value,
        projection_evidence_binding_manifest_id=derive_sha256_id(
            projection_evidence_binding_manifest_identity_payload_to_dict(value)
        ),
    )


def test_canonical_json_bytes_are_sorted_compact_utf8_and_one_lf() -> None:
    payload = {"z": "Straße", "a": 1}
    assert canonical_json_bytes(payload) == b'{"a":1,"z":"Stra\xc3\x9fe"}\n'


def test_source_document_manifest_round_trip_is_exact() -> None:
    value = make_manifest()
    payload = dumps_source_document_manifest(value)
    assert payload.endswith("\n") and not payload.endswith("\n\n")
    assert loads_source_document_manifest(payload) == value
    assert dumps_source_document_manifest(loads_source_document_manifest(payload)) == payload


def test_evidence_binding_round_trip_is_exact() -> None:
    value = make_binding()
    payload = dumps_evidence_binding(value)
    assert loads_evidence_binding(payload) == value


def test_analysis_receipt_round_trip_is_exact() -> None:
    value = make_receipt()
    payload = dumps_source_bound_analysis_receipt(value)
    assert loads_source_bound_analysis_receipt(payload) == value


def test_projection_binding_round_trip_is_exact() -> None:
    value = make_projection_manifest()
    payload = dumps_projection_evidence_binding_manifest(value)
    assert loads_projection_evidence_binding_manifest(payload) == value


@pytest.mark.parametrize(
    ("dumps", "loads", "value"),
    [
        (dumps_source_document_manifest, loads_source_document_manifest, make_manifest()),
        (dumps_evidence_binding, loads_evidence_binding, make_binding()),
        (dumps_source_bound_analysis_receipt, loads_source_bound_analysis_receipt, make_receipt()),
        (
            dumps_projection_evidence_binding_manifest,
            loads_projection_evidence_binding_manifest,
            make_projection_manifest(),
        ),
    ],
)
def test_pretty_printed_and_extra_newline_json_are_rejected(dumps, loads, value) -> None:
    canonical = dumps(value)
    data = json.loads(canonical)
    pretty = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    with pytest.raises(ValueError, match="canonical"):
        loads(pretty)
    with pytest.raises(ValueError, match="canonical"):
        loads(canonical + "\n")


def test_unknown_top_level_field_is_rejected() -> None:
    data = json.loads(dumps_source_document_manifest(make_manifest()))
    data["future_field"] = "not allowed"
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    with pytest.raises(ValueError, match="extra"):
        loads_source_document_manifest(payload)


def test_unknown_nested_field_is_rejected() -> None:
    data = json.loads(dumps_source_document_manifest(make_manifest()))
    data["extraction_profile"]["future"] = "not allowed"
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    with pytest.raises(ValueError, match="extra"):
        loads_source_document_manifest(payload)


def test_unknown_enum_value_is_rejected() -> None:
    data = json.loads(dumps_evidence_binding(make_binding()))
    data["binding_class"] = "super_bound"
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    with pytest.raises(ValueError, match="Unknown BindingClass"):
        loads_evidence_binding(payload)


def test_schema_version_tamper_is_rejected_even_with_rederived_identity() -> None:
    value = make_binding(BindingClass.ANALYTICAL_TEXT_BOUND)
    bad = replace(value, schema_version="evidence-binding/9.9")
    bad = replace(bad, evidence_binding_id=derive_sha256_id(evidence_binding_identity_payload_to_dict(bad)))
    payload = json.dumps(
        json.loads(dumps_evidence_binding(bad)),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"
    with pytest.raises(ValueError, match="schema_version"):
        loads_evidence_binding(payload)


def test_identity_tamper_is_rejected() -> None:
    data = json.loads(dumps_evidence_binding(make_binding()))
    data["evidence_binding_id"] = "sha256:" + "f" * 64
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    with pytest.raises(ValueError, match="evidence_binding_id"):
        loads_evidence_binding(payload)


def test_duplicate_json_object_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate JSON object key"):
        loads_evidence_binding('{"a":1,"a":2}\n')


def test_bool_is_not_accepted_for_integer_field() -> None:
    data = json.loads(dumps_source_document_manifest(make_manifest()))
    data["original_byte_length"] = True
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    with pytest.raises(ValueError, match="Expected int"):
        loads_source_document_manifest(payload)


def test_enums_serialize_as_exact_controlled_strings() -> None:
    data = json.loads(dumps_evidence_binding(make_binding()))
    assert data["binding_class"] == "full_chain_bound"
    assert data["bound_text_role"] == "chunk_text"


def test_identity_changes_when_semantic_payload_changes() -> None:
    value = make_binding(BindingClass.ANALYTICAL_TEXT_BOUND)
    original_id = value.evidence_binding_id
    changed = replace(value, document_name="different.pdf")
    changed_id = derive_sha256_id(evidence_binding_identity_payload_to_dict(changed))
    assert changed_id != original_id


def test_json_root_must_be_object() -> None:
    with pytest.raises(ValueError, match="root"):
        loads_source_document_manifest("[]\n")


def test_fixed_golden_core_identities() -> None:
    manifest = make_manifest()
    binding = make_binding()
    receipt = make_receipt()
    projection_binding = make_projection_manifest()

    assert manifest.source_document_instance_id == "3f28d1dd-a514-58d0-bfee-f9a3d9cec89f"
    assert manifest.source_snapshot_id == (
        "sha256:e6947b758229660f44ff4e602d000e15812659aebc7f8f0f457d07c89cf7f794"
    )
    assert binding.evidence_binding_id == (
        "sha256:65cd82b8a51c437f572dde2acc921277286c863972753b503434c45ec539d018"
    )
    assert receipt.source_bound_analysis_receipt_id == (
        "sha256:1d8da52707e630fc778850672664782b5bd6d9ffe806b1ef8c3847440af15712"
    )
    assert projection_binding.projection_evidence_binding_manifest_id == (
        "sha256:4dc503c49d08f346c1f2e33292531d925e776b2d4c86ad49badb44efa1edb5f6"
    )


def test_fixed_golden_serialized_record_hashes() -> None:
    records = (
        (dumps_source_document_manifest(make_manifest()), "1a2fc8484502c57b7715a5c0b5154e4025d6034bb1e36e3966fbde8cc81eaf2a"),
        (dumps_evidence_binding(make_binding()), "43536a8e89b58be88ffdb03f0f35531b8dc107977e09b3094620f169f7d7cc9d"),
        (dumps_source_bound_analysis_receipt(make_receipt()), "08e3ddf6b6de05a648e7cee3c00c8bffa87474ca4237e461dc8277877ce27b0f"),
        (dumps_projection_evidence_binding_manifest(make_projection_manifest()), "a1111a58478f5f05f24833e52dad66c5f080aafe528047f3eb60f24acf5f75df"),
    )
    for payload, expected in records:
        assert sha256_bytes(payload.encode("utf-8")) == expected
