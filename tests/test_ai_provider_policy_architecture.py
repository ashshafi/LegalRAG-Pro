from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

EXPECTED_GUARDS = {
    "controlled_agentic_analysis_openai.py": "CONTROLLED_ANALYSIS",
    "derived_transcription_answer_context.py": "DERIVED_TRANSCRIPTION_EMBEDDING",
    "follow_up_context.py": "FOLLOW_UP_REWRITE",
    "index_documents.py": "DOCUMENT_EMBEDDING",
    "legalrag.py": "LEGAL_ANSWER",
    "query_expander.py": "QUERY_EXPANSION",
    "retriever.py": "RETRIEVAL_EMBEDDING",
    "source_evidence/ingestion.py": "SOURCE_EVIDENCE_EMBEDDING",
}


def test_every_authorised_production_ai_boundary_has_fail_closed_policy_guard():
    for relative, purpose in EXPECTED_GUARDS.items():
        source = (SRC / relative).read_text(encoding="utf-8")
        assert "assert_ai_processing_allowed(" in source, relative
        assert f"AIProcessingPurpose.{purpose}" in source, relative
        assert "AIDataClassification.PRIVILEGED" in source, relative
        ast.parse(source, filename=relative)


def test_provider_policy_does_not_import_openai_chroma_or_case_data_modules():
    path = SRC / "ai_provider_policy.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert not any(name.startswith("openai") for name in imported)
    assert not any(name.startswith("chromadb") for name in imported)
    assert not any(name.startswith("case_") for name in imported)
    assert not any(name.startswith("source_evidence") for name in imported)


def test_policy_guard_is_before_each_direct_sdk_call_where_order_is_material():
    checks = {
        "controlled_agentic_analysis_openai.py": "response = create(",
        "derived_transcription_answer_context.py": ".embeddings.create(",
        "follow_up_context.py": "client.responses.create(",
        "index_documents.py": "client.embeddings.create(",
        "legalrag.py": "openai_client.responses.create(",
        "query_expander.py": "openai_client.responses.create(",
        "retriever.py": "openai_client.embeddings.create(",
        "source_evidence/ingestion.py": "openai_client.embeddings.create(",
    }
    for relative, call_marker in checks.items():
        source = (SRC / relative).read_text(encoding="utf-8")
        guard = source.rfind("assert_ai_processing_allowed(", 0, source.index(call_marker))
        assert guard >= 0, relative
        assert guard < source.index(call_marker), relative


def _call_target(node: ast.Call) -> str:
    try:
        return ast.unparse(node.func)
    except Exception:
        return ""


def _store_keyword_is_literal_false(node: ast.Call) -> bool:
    matches = [kw.value for kw in node.keywords if kw.arg == "store"]
    return (
        len(matches) == 1
        and isinstance(matches[0], ast.Constant)
        and matches[0].value is False
    )


def test_every_responses_api_call_explicitly_disables_response_storage():
    expected = {
        "controlled_agentic_analysis_openai.py": "create",
        "follow_up_context.py": "client.responses.create",
        "legalrag.py": "openai_client.responses.create",
        "query_expander.py": "openai_client.responses.create",
    }

    for relative, target in expected.items():
        path = SRC / relative
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and _call_target(node) == target
        ]

        if relative == "controlled_agentic_analysis_openai.py":
            # The local alias `create` is defined inside the single
            # _call_responses boundary. Other create(...) calls are excluded.
            owner_calls = []
            for fn in tree.body:
                if isinstance(fn, ast.FunctionDef) and fn.name == "_call_responses":
                    owner_calls = [
                        node
                        for node in ast.walk(fn)
                        if isinstance(node, ast.Call) and _call_target(node) == target
                    ]
            calls = owner_calls

        assert len(calls) == 1, relative
        assert _store_keyword_is_literal_false(calls[0]), relative
