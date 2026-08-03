from __future__ import annotations

import copy

from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.m2.matrices import build_case_matrices
from case_analysis.m2.matrix_serialization import dumps_case_matrices, loads_case_matrices
from case_analysis_m2_helpers import evidence, make_m5_result


def test_four_issue_case_matrix_acceptance_exercise():
    shared = evidence(key="shared-return-to-work")
    results = (
        make_m5_result(
            "EK-001",
            issue_analysis_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            evidence_by_element={"EK-INFORMATION": (shared,)},
        ),
        make_m5_result(
            "RA-001",
            issue_analysis_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            evidence_by_element={"RA-KNOWLEDGE": (shared,)},
        ),
        make_m5_result(
            "DA-001",
            issue_analysis_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        ),
        make_m5_result(
            "LIM-001",
            issue_analysis_id="dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        ),
    )
    before = copy.deepcopy(results)
    foundation = build_case_analysis_foundation(results)
    foundation_before = copy.deepcopy(foundation)

    matrices = build_case_matrices(foundation, tuple(reversed(results)))
    payload = dumps_case_matrices(matrices)
    restored = loads_case_matrices(payload)

    assert restored == matrices
    assert len(matrices.issue_matrix) == 4
    assert {item.issue_definition_id for item in matrices.issue_matrix} == {
        "EK-001",
        "RA-001",
        "DA-001",
        "LIM-001",
    }
    assert len(matrices.evidence_matrix) == 1
    assert len(matrices.evidence_matrix[0].uses) == 2
    assert foundation == foundation_before
    assert results == before
