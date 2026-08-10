from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "evidence_retrieval"
FILES = (
    PACKAGE / "__init__.py",
    PACKAGE / "models.py",
    PACKAGE / "document_complete.py",
)

PROHIBITED_IMPORT_ROOTS = {
    "chromadb",
    "openai",
    "streamlit",
    "retriever",
    "legalrag",
    "document_manager",
    "document_upload",
    "index_documents",
    "ocr",
    "case_analysis",
    "legal_analysis",
    "case_reporting",
    "workspace_index",
    "document_catalog",
}

PROHIBITED_STORE_MUTATIONS = {
    "put_blob",
    "publish_document_manifest",
    "publish_evidence_binding",
    "publish_analysis_receipt",
    "publish_projection_binding",
}

PROHIBITED_GENERIC_IO = {
    "open",
    "write_bytes",
    "write_text",
    "unlink",
    "rename",
    "replace",
    "mkdir",
    "rmdir",
    "remove",
    "delete",
    "upsert",
    "add",
}

ALLOWED_SOURCE_STORE_READS = {
    "load_document_manifest",
    "load_evidence_binding",
    "read_blob",
}


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _import_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _attribute_calls(tree: ast.AST) -> set[str]:
    return {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }


def _name_calls(tree: ast.AST) -> set[str]:
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def test_u8b_package_is_additive_and_present_on_exact_three_source_paths():
    assert PACKAGE.is_dir()
    assert sorted(path.name for path in PACKAGE.iterdir() if path.is_file()) == [
        "__init__.py",
        "document_complete.py",
        "models.py",
    ]


def test_u8b_has_no_chroma_openai_ui_legacy_or_analysis_dependencies():
    for path in FILES:
        imported = _import_roots(_tree(path))
        assert imported.isdisjoint(PROHIBITED_IMPORT_ROOTS), (path, imported)


def test_u8b_source_store_usage_is_read_only():
    document_complete = _tree(PACKAGE / "document_complete.py")
    calls = _attribute_calls(document_complete)
    assert calls.isdisjoint(PROHIBITED_STORE_MUTATIONS)
    assert ALLOWED_SOURCE_STORE_READS.issubset(calls)


def test_u8b_has_no_generic_file_writes_or_dynamic_execution():
    for path in FILES:
        tree = _tree(path)
        assert _attribute_calls(tree).isdisjoint(PROHIBITED_GENERIC_IO)
        assert _name_calls(tree).isdisjoint({"open", "exec", "eval"})


def test_u8b_does_not_read_original_pdf_blob_implicitly():
    source = (PACKAGE / "document_complete.py").read_text(encoding="utf-8")
    assert "read_blob(manifest.original_blob_sha256" not in source
    assert "digest=manifest.original_blob_sha256" not in source


def test_u8b_models_are_frozen_dataclasses_and_do_not_redefine_source_identity():
    source = (PACKAGE / "models.py").read_text(encoding="utf-8")
    tree = _tree(PACKAGE / "models.py")
    decorators = [
        decorator
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        for decorator in node.decorator_list
    ]
    rendered = {ast.unparse(item) for item in decorators}
    assert "dataclass(frozen=True, slots=True)" in rendered
    assert "source_snapshot_id" in source
    assert "evidence_binding_id" in source
    assert "derive_" not in source


def test_u8b_does_not_define_search_modes_roles_or_analysis_receipts_early():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in FILES)
    assert "EvidenceSearchReceipt" not in combined
    assert "PRIMARY_SOURCE" not in combined
    assert "SEMANTIC_DISCOVERY" not in combined
    assert "EXHAUSTIVE_EVIDENCE" not in combined
    assert "SourceBoundAnalysisReceipt" not in combined
