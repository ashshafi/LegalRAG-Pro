from pathlib import Path

def test_preprovider_r1_timing_markers_present():
    s = Path("src/legalrag.py").read_text(encoding="utf-8-sig")
    for marker in (
        "LEGALRAG_TIMING SEMANTIC_ENRICHMENT_MS=",
        "LEGALRAG_TIMING INTERACTIVE_PROMPT_BUILD_MS=",
        "LEGALRAG_TIMING DERIVED_TRANSCRIPTION_AUGMENT_MS=",
        "LEGALRAG_TIMING AUTHORITY_IMPORT_MS=",
        "LEGALRAG_TIMING AUTHORITY_LOAD_MS=",
        "LEGALRAG_TIMING AUTHORITY_ROUTING_MS=",
        "LEGALRAG_TIMING AUTHORITY_CONTEXT_BUILD_MS=",
        "LEGALRAG_TIMING AUTHORITY_CONSTRAINT_PROMPT_MS=",
    ):
        assert marker in s

def test_existing_top_level_timings_retained():
    s = Path("src/legalrag.py").read_text(encoding="utf-8-sig")
    assert "LEGALRAG_TIMING PROMPT_PREPARATION_MS=" in s
    assert "LEGALRAG_TIMING OPENAI_LEGAL_ANSWER_MS=" in s
    assert "LEGALRAG_TIMING TOTAL_TO_PROVIDER_RESPONSE_MS=" in s
