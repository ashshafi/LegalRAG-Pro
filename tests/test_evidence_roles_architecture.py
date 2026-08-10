from __future__ import annotations

import ast
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "evidence_roles"
U8B_PACKAGE = ROOT / "src" / "evidence_retrieval"
FILES = (
    PACKAGE / "__init__.py",
    PACKAGE / "models.py",
    PACKAGE / "classifier.py",
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
    "source_evidence",
}

PROHIBITED_CALLS = {
    "open",
    "exec",
    "eval",
    "write_bytes",
    "write_text",
    "unlink",
    "rename",
    "mkdir",
    "rmdir",
    "remove",
    "delete",
    "upsert",
    "add",
    "put_blob",
    "publish_document_manifest",
    "publish_evidence_binding",
    "publish_analysis_receipt",
    "publish_projection_binding",
}

U8B_EXPECTED_SHA256 = {
    "__init__.py": "42261497069873076703ef9101666d4356f283aac9c256eee10110da439ab13f",
    "models.py": "6b260ee070bfb62b9d15757c9ba15d3a2fd15f8607e9f88a48bcf512c07aabac",
    "document_complete.py": "4174a332b66e3eabbf15c7474c49d04f8359f1e1495829dd897d5eccdd502a56",
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


def _calls(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_u8c_is_exactly_three_additive_source_files():
    assert PACKAGE.is_dir()
    assert sorted(path.name for path in PACKAGE.iterdir() if path.is_file()) == [
        "__init__.py",
        "classifier.py",
        "models.py",
    ]


def test_u8c_preserves_all_u8b_source_files_byte_exact():
    assert sorted(path.name for path in U8B_PACKAGE.iterdir() if path.is_file()) == [
        "__init__.py",
        "document_complete.py",
        "models.py",
    ]
    for name, expected in U8B_EXPECTED_SHA256.items():
        assert _sha256(U8B_PACKAGE / name) == expected


def test_u8c_has_no_chroma_openai_ui_source_store_or_analysis_dependencies():
    for path in FILES:
        imported = _import_roots(_tree(path))
        assert imported.isdisjoint(PROHIBITED_IMPORT_ROOTS), (path, imported)


def test_u8c_has_no_file_source_store_or_dynamic_mutation_calls():
    for path in FILES:
        assert _calls(_tree(path)).isdisjoint(PROHIBITED_CALLS)


def test_u8c_reuses_existing_provenance_and_u8b_models_without_redefining_them():
    classifier = (PACKAGE / "classifier.py").read_text(encoding="utf-8")
    models = (PACKAGE / "models.py").read_text(encoding="utf-8")
    assert "classify_evidence_source" in classifier
    assert "classify_chunk_provenance" in classifier
    assert "DocumentEvidenceInspection" in classifier
    assert "DocumentEvidenceChunk" in models
    assert "SourceDocumentManifest" not in classifier + models
    assert "EvidenceBinding" not in classifier + models


def test_u8c_role_vocabulary_is_exact_and_fail_closed():
    source = (PACKAGE / "models.py").read_text(encoding="utf-8")
    tree = _tree(PACKAGE / "models.py")
    role_class = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "EvidenceRole"
    )
    members = [
        target.id
        for stmt in role_class.body
        if isinstance(stmt, ast.Assign)
        for target in stmt.targets
        if isinstance(target, ast.Name)
    ]
    assert members == [
        "PRIMARY_SOURCE",
        "COMMENTARY",
        "CROSS_REFERENCE",
        "COVER_OR_INDEX",
        "MIXED",
        "UNCLASSIFIED",
    ]
    assert "UNCLASSIFIED" in source


def test_u8c_does_not_introduce_search_receipts_or_search_modes_early():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in FILES)
    assert "EvidenceSearchReceipt" not in combined
    assert "SEMANTIC_DISCOVERY" not in combined
    assert "EXHAUSTIVE_EVIDENCE" not in combined
    assert "negative_finding_permitted" not in combined
