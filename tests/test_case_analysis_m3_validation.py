from __future__ import annotations

from dataclasses import replace

import pytest

from case_analysis.m3.chronology import build_case_chronology
from case_analysis.m3.chronology_validation import validate_case_chronology

from case_analysis_m3_helpers import evidence, inputs, make_m5_result, proposition


def base():
    ev = evidence(key="event", summary="CACI sent a capability review letter on 17 July 2026.")
    result = make_m5_result(
        "LIM-001",
        evidence_by_element={"LIM-DATES": (ev,)},
        proposition_overrides={"LIM-DATES": (proposition("CACI sent a capability review letter on 17 July 2026.", ("event",)),)},
    )
    return inputs(result)


def test_wrong_synthesis_id_fails_closed():
    foundation, matrices, results = base()
    bad = replace(matrices, synthesis_id="99999999-9999-4999-8999-999999999999")
    with pytest.raises(ValueError):
        build_case_chronology(foundation, bad, results)


def test_missing_source_result_fails_closed():
    foundation, matrices, results = base()
    with pytest.raises(ValueError):
        build_case_chronology(foundation, matrices, ())


def test_tampered_event_identity_fails_validation():
    foundation, matrices, results = base()
    chronology = build_case_chronology(foundation, matrices, results)
    bad_event = replace(chronology.events[0], event_id="99999999-9999-4999-8999-999999999999")
    bad = replace(chronology, events=(bad_event,))
    with pytest.raises(ValueError):
        validate_case_chronology(
            bad,
            foundation=foundation,
            matrices=matrices,
            results=results,
        )
