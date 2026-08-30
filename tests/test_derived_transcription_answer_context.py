from pathlib import Path

from derived_transcription_answer_context import (
    format_candidate_context,
)

from derived_transcription_search_activation import (
    ActivationQueryHit,
    ActivationQueryResult,
)


def test_derived_context_remains_candidate_only():
    hit = ActivationQueryHit(
        candidate_id=
            "dtx:sha256:" + ("a" * 64),
        document=
            "Marriage Date: 12-Aug-2000",
        metadata={
            "source_document_instance_id":
                "document-1",
            "source_snapshot_id":
                "sha256:" + ("b" * 64),
            "page":
                1,
            "derived_record_id":
                "sha256:" + ("c" * 64),
            "transcription_sha256":
                "d" * 64,
        },
        distance=0.0,
    )

    result = ActivationQueryResult(
        hits=(hit,)
    )

    context = format_candidate_context(
        result
    )

    assert "candidate_discovery_only" in context
    assert "negative_finding_authoritative=false" in context
    assert "NOT FULL_CHAIN source evidence" in context
    assert hit.document in context


def test_zero_hit_is_not_negative_authority():
    result = ActivationQueryResult(
        hits=()
    )

    assert (
        result.negative_finding_authoritative
        is False
    )

    assert (
        format_candidate_context(
            result
        )
        == ""
    )


def test_answer_hook_precedes_analytical_projection():
    source = Path(
        "src/legalrag.py"
    ).read_text(
        encoding="utf-8"
    )

    derived = source.index(
        "augment_governed_answer_prompt_with_derived_candidates("
    )

    analytical = source.index(
        "build_runtime_authority_context(",
        derived,
    )

    assert derived < analytical
