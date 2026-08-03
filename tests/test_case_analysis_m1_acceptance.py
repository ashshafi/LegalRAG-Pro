from __future__ import annotations

from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.serialization import dumps_case_analysis_foundation, loads_case_analysis_foundation
from case_analysis_m1_helpers import make_m5_result


def test_four_issue_case_foundation_acceptance_exercise():
    results = tuple(
        make_m5_result(issue_id, issue_analysis_id=analysis_id)
        for issue_id, analysis_id in (
            ("EK-001", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            ("RA-001", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
            ("DA-001", "cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
            ("LIM-001", "dddddddd-dddd-4ddd-8ddd-dddddddddddd"),
        )
    )

    foundation = build_case_analysis_foundation(results)
    payload = dumps_case_analysis_foundation(foundation)
    restored = loads_case_analysis_foundation(payload)

    assert restored == foundation
    assert len(restored.source_analyses) == 4
    assert {item.issue_definition_id for item in restored.source_analyses} == {
        "EK-001",
        "RA-001",
        "DA-001",
        "LIM-001",
    }
    assert all(item.mapper_version == "element-mapper/1.0" for item in restored.source_analyses)
    assert all(item.assessor_version == "element-assessor/1.0" for item in restored.source_analyses)
    assert all(item.analyser_version == "legal-analyser/1.0" for item in restored.source_analyses)
