from pathlib import Path


def test_retriever_has_expansion_default_and_direct_branch():
    s = Path("src/retriever.py").read_text(encoding="utf-8-sig")
    assert "expand_search_query: bool = True" in s
    assert "expand_query(question) if expand_search_query else question" in s


def test_interactive_governed_path_disables_expansion_only_for_default_retriever():
    s = Path("src/evidence_answer/governed_retrieval.py").read_text(encoding="utf-8-sig")
    assert "expand_search_query=not interactive_semantic_only" in s
    assert "from retriever import retrieve as default_retriever" in s
    assert "semantic_results = retriever_callable(" in s


def test_embedding_policy_and_existing_query_expander_import_are_preserved():
    s = Path("src/retriever.py").read_text(encoding="utf-8-sig")
    assert "from query_expander import expand_query" in s
    assert "AIProcessingPurpose.RETRIEVAL_EMBEDDING" in s
    assert "input=expanded_query" in s
