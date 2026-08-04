from __future__ import annotations

from case_analysis.m3.chronology import build_case_chronology
from case_analysis.m3.chronology_serialization import dumps_case_chronology, loads_case_chronology

from case_analysis_m3_helpers import evidence, inputs, make_m5_result, proposition


def test_chronology_round_trip_is_byte_stable():
    ev = evidence(key="event", summary="CACI sent a letter on 17 July 2026.")
    result = make_m5_result(
        "LIM-001",
        evidence_by_element={"LIM-DATES": (ev,)},
        proposition_overrides={"LIM-DATES": (proposition("CACI sent a letter on 17 July 2026.", ("event",)),)},
    )
    foundation, matrices, results = inputs(result)
    chronology = build_case_chronology(foundation, matrices, results)
    payload = dumps_case_chronology(chronology)
    restored = loads_case_chronology(payload)
    assert restored == chronology
    assert dumps_case_chronology(restored) == payload
