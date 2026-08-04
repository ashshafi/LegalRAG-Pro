from __future__ import annotations

from case_analysis_m3_helpers import evidence, inputs, make_m5_result, proposition
from case_analysis_m3_live_fixture_capture import build_live_fixture_payload, dumps_live_fixture


def test_live_fixture_capture_is_deterministic_and_preserves_raw_summary_hash():
    ev = evidence(
        key="fixture-email",
        summary=(
            "From: Phil Jones <phil.jones@caci.co.uk> Sent: 14 June 2005 "
            "Subject: VF specification Phil, can you carry on with the VF specification as discussed."
        ),
    )
    result = make_m5_result(
        "LIM-001",
        evidence_by_element={"LIM-DATES": (ev,)},
        proposition_overrides={
            "LIM-DATES": (
                proposition("The mapped evidence contains factual material relevant to this element.", ("fixture-email",)),
            )
        },
    )
    _, matrices, frozen = inputs(result)
    first = build_live_fixture_payload(matrices, frozen)
    second = build_live_fixture_payload(matrices, tuple(reversed(frozen)))
    assert first == second
    assert first["fixture_version"] == "shafi-chronology-live-fixture/1.0"
    assert first["source_checkpoint"] == "4e906b3"
    item = first["evidence"][0]
    assert item["summary"].startswith("From: Phil Jones")
    assert len(item["summary_sha256"]) == 64
    assert dumps_live_fixture(first) == dumps_live_fixture(second)
