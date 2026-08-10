from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PACKAGE = SRC / "evidence_answer"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_u8f_bridge_is_separate_from_source_evidence_storage_and_ui_layers():
    imports = set()
    for path in PACKAGE.glob("*.py"):
        imports |= _imports(path)

    forbidden_prefixes = (
        "chromadb",
        "openai",
        "streamlit",
        "source_evidence",
        "document_manager",
        "document_upload",
        "index_documents",
        "ocr",
        "case_analysis",
        "legal_analysis",
        "case_reporting",
        "workspace_index",
    )
    assert not any(
        name == prefix or name.startswith(prefix + ".")
        for name in imports
        for prefix in forbidden_prefixes
    )


def test_u8f_bridge_uses_u8d_and_document_catalog_instead_of_direct_chroma_access():
    imports = _imports(PACKAGE / "governed_retrieval.py")
    assert "evidence_search" in imports
    assert "document_catalog" in imports
    source = (PACKAGE / "governed_retrieval.py").read_text(encoding="utf-8")
    assert "from retriever import retrieve as retriever_callable" in source
    assert ".query(" not in source
    assert "collection.query" not in source


def test_u8f_bridge_contains_no_source_store_or_filesystem_write_operations():
    source = (PACKAGE / "governed_retrieval.py").read_text(encoding="utf-8")
    forbidden = (
        "SourceEvidenceStore",
        "publish_document_manifest",
        "publish_evidence_binding",
        "publish_analysis_receipt",
        "publish_projection_binding",
        "put_blob",
        "write_text(",
        "write_bytes(",
        "open(\"w",
        "open('w",
    )
    for token in forbidden:
        assert token not in source


def test_legalrag_consumes_only_u8f_answer_boundary_not_u8_internal_layers_directly():
    imports = _imports(SRC / "legalrag.py")
    assert "evidence_answer" in imports
    assert "evidence_search" not in imports
    assert "evidence_retrieval" not in imports
    assert "evidence_roles" not in imports
    assert "source_evidence" not in imports


def test_legalrag_keeps_legacy_retriever_for_non_case_questions():
    source = (SRC / "legalrag.py").read_text(encoding="utf-8")
    assert "if case_id is not None:" in source
    assert "prepare_governed_answer_evidence(" in source
    assert "results = retrieve(" in source
    assert "n_results=10" in source


def test_u8f_prompt_rule_forbids_unqualified_no_evidence_claim_without_case_completion():
    source = (PACKAGE / "governed_retrieval.py").read_text(encoding="utf-8")
    assert 'Never write an unqualified statement such as "there is no evidence"' in source
    assert "completely searched candidate documents" in source
    assert "searched case corpus" in source


def test_u8f_semantic_discovery_is_broader_than_legacy_answer_top_ten():
    source = (PACKAGE / "governed_retrieval.py").read_text(encoding="utf-8")
    assert "GOVERNED_DISCOVERY_N_RESULTS: Final[int] = 30" in source
