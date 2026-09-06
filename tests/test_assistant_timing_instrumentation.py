from pathlib import Path

def test_timing_is_environment_gated():
    r = Path("src/retriever.py").read_text(encoding="utf-8-sig")
    l = Path("src/legalrag.py").read_text(encoding="utf-8-sig")
    assert 'os.getenv("LEGALRAG_ASSISTANT_TIMING") == "1"' in r
    assert 'os.getenv("LEGALRAG_ASSISTANT_TIMING") == "1"' in l

def test_retriever_timing_markers_present():
    s = Path("src/retriever.py").read_text(encoding="utf-8-sig")
    for marker in (
        "LEGALRAG_TIMING QUERY_PREPARATION_MS=",
        "LEGALRAG_TIMING EMBEDDING_MS=",
        "LEGALRAG_TIMING CHROMA_RERANK_MS=",
        "LEGALRAG_TIMING RETRIEVER_TOTAL_MS=",
    ):
        assert marker in s

def test_legalrag_timing_markers_present():
    s = Path("src/legalrag.py").read_text(encoding="utf-8-sig")
    for marker in (
        "LEGALRAG_TIMING GOVERNED_PREPARATION_MS=",
        "LEGALRAG_TIMING PROMPT_PREPARATION_MS=",
        "LEGALRAG_TIMING OPENAI_LEGAL_ANSWER_MS=",
        "LEGALRAG_TIMING TOTAL_TO_PROVIDER_RESPONSE_MS=",
    ):
        assert marker in s

def test_model_and_scope_contracts_unchanged():
    r = Path("src/retriever.py").read_text(encoding="utf-8-sig")
    l = Path("src/legalrag.py").read_text(encoding="utf-8-sig")
    assert "model=EMBEDDING_MODEL" in r
    assert "AIProcessingPurpose.RETRIEVAL_EMBEDDING" in r
    assert "model=CHAT_MODEL" in l
    assert "AIProcessingPurpose.LEGAL_ANSWER" in l
    assert "interactive_semantic_only=True" in l
