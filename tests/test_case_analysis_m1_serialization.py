from __future__ import annotations

import json

import pytest

from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.serialization import (
    case_analysis_foundation_to_dict,
    dumps_case_analysis_foundation,
    loads_case_analysis_foundation,
)
from case_analysis_m1_helpers import make_m5_result


def _foundation():
    return build_case_analysis_foundation(
        (
            make_m5_result("RA-001", issue_analysis_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
            make_m5_result("EK-001", issue_analysis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        )
    )


def test_foundation_json_round_trip_is_identical():
    foundation = _foundation()

    payload = dumps_case_analysis_foundation(foundation)
    restored = loads_case_analysis_foundation(payload)

    assert restored == foundation
    assert dumps_case_analysis_foundation(restored) == payload


def test_foundation_serialization_has_deterministic_source_order():
    foundation = _foundation()
    data = case_analysis_foundation_to_dict(foundation)

    assert [item["issue_analysis_id"] for item in data["source_analyses"]] == sorted(
        item["issue_analysis_id"] for item in data["source_analyses"]
    )


def test_serialized_foundation_references_sources_without_embedding_m5_graph():
    data = case_analysis_foundation_to_dict(_foundation())
    payload = json.dumps(data)

    assert "assessment_result" not in payload
    assert "element_analyses" not in payload
    assert "mapping_result" not in payload
    assert "evidence_assessments" not in payload


def test_deserialization_fails_closed_if_synthesis_id_is_tampered():
    data = case_analysis_foundation_to_dict(_foundation())
    data["synthesis_id"] = "99999999-9999-4999-8999-999999999999"

    with pytest.raises(ValueError, match="does not match"):
        loads_case_analysis_foundation(json.dumps(data))


def test_json_payload_must_be_an_object():
    with pytest.raises(ValueError, match="must contain an object"):
        loads_case_analysis_foundation("[]")
