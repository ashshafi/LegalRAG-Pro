from __future__ import annotations

from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.m2.matrices import build_case_matrices
from case_analysis.m2.matrix_serialization import dumps_case_matrices, loads_case_matrices
from case_analysis_m2_helpers import evidence, make_m5_result


def _inputs():
    shared = evidence(key="shared")
    ek = make_m5_result(
        "EK-001",
        issue_analysis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        evidence_by_element={"EK-INFORMATION": (shared,)},
    )
    ra = make_m5_result(
        "RA-001",
        issue_analysis_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        evidence_by_element={"RA-KNOWLEDGE": (shared,)},
    )
    return ek, ra


def test_matrix_json_round_trip_is_exact():
    ek, ra = _inputs()
    foundation = build_case_analysis_foundation((ek, ra))
    matrices = build_case_matrices(foundation, (ek, ra))

    payload = dumps_case_matrices(matrices)
    restored = loads_case_matrices(payload)

    assert restored == matrices
    assert dumps_case_matrices(restored) == payload


def test_caller_source_order_does_not_change_matrix_or_json():
    ek, ra = _inputs()
    foundation = build_case_analysis_foundation((ra, ek))

    first = build_case_matrices(foundation, (ek, ra))
    second = build_case_matrices(foundation, (ra, ek))

    assert second == first
    assert dumps_case_matrices(second) == dumps_case_matrices(first)
