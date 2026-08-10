from __future__ import annotations

import ast
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "evidence_search"
U8B_PACKAGE = ROOT / "src" / "evidence_retrieval"
U8C_PACKAGE = ROOT / "src" / "evidence_roles"
FILES = (
    PACKAGE / "__init__.py",
    PACKAGE / "models.py",
    PACKAGE / "orchestrator.py",
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
    "replace",
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

U8C_EXPECTED_SHA256 = {
    "__init__.py": "07dfb35606fffeb79fb7208062910046550eee396220a5453121e4652b3650a3",
    "models.py": "b41cad658da99e6fb357ebd4e1db11a549bcec1f38fd2557b8115eb620a575a9",
    "classifier.py": "642273b60692e75134bacadac29c21bb071e9342766c69ffa9b20693a62a13d0",
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


def test_u8d_is_exactly_three_additive_source_files():
    assert PACKAGE.is_dir()
    assert sorted(path.name for path in PACKAGE.iterdir() if path.is_file()) == [
        "__init__.py",
        "models.py",
        "orchestrator.py",
    ]


def test_u8d_preserves_u8b_and_u8c_source_files_byte_exact():
    assert sorted(path.name for path in U8B_PACKAGE.iterdir() if path.is_file()) == [
        "__init__.py",
        "document_complete.py",
        "models.py",
    ]
    assert sorted(path.name for path in U8C_PACKAGE.iterdir() if path.is_file()) == [
        "__init__.py",
        "classifier.py",
        "models.py",
    ]
    for name, expected in U8B_EXPECTED_SHA256.items():
        assert _sha256(U8B_PACKAGE / name) == expected
    for name, expected in U8C_EXPECTED_SHA256.items():
        assert _sha256(U8C_PACKAGE / name) == expected


def test_u8d_has_no_chroma_openai_ui_analysis_or_direct_source_store_dependency():
    for path in FILES:
        imported = _import_roots(_tree(path))
        assert imported.isdisjoint(PROHIBITED_IMPORT_ROOTS), (path, imported)


def test_u8d_has_no_file_source_store_or_dynamic_mutation_calls():
    for path in FILES:
        assert _calls(_tree(path)).isdisjoint(PROHIBITED_CALLS)


def test_u8d_orchestrates_existing_governed_layers_instead_of_redefining_them():
    source = (PACKAGE / "orchestrator.py").read_text(encoding="utf-8")
    models = (PACKAGE / "models.py").read_text(encoding="utf-8")
    assert "list_case_documents" in source
    assert "inspect_document_complete" in source
    assert "classify_document_evidence_roles" in source
    assert "DocumentEvidenceChunk" in models
    assert "EvidenceRoleClassification" in models
    assert "SourceDocumentManifest" not in source + models
    assert "EvidenceBinding" not in source + models


def test_u8d_search_mode_vocabulary_is_exact():
    tree = _tree(PACKAGE / "models.py")
    mode_class = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "EvidenceSearchMode"
    )
    members = [
        target.id
        for stmt in mode_class.body
        if isinstance(stmt, ast.Assign)
        for target in stmt.targets
        if isinstance(target, ast.Name)
    ]
    assert members == [
        "SEMANTIC_DISCOVERY",
        "DOCUMENT_COMPLETE",
        "CHRONOLOGY",
        "PERSON",
        "EXHAUSTIVE_EVIDENCE",
    ]


def test_u8d_receipt_contains_explicit_negative_finding_and_coverage_fields():
    source = (PACKAGE / "models.py").read_text(encoding="utf-8")
    for field in (
        "case_document_count",
        "scope_document_count",
        "documents_completely_expanded",
        "pages_inspected",
        "chunks_inspected",
        "searched_document_ids",
        "matched_evidence_keys",
        "completion",
        "case_corpus_complete",
        "negative_finding_scope",
        "negative_finding_permitted",
    ):
        assert field in source


def test_u8d_semantic_discovery_is_receipted_but_not_executed_via_retriever():
    source = (PACKAGE / "orchestrator.py").read_text(encoding="utf-8")
    assert "record_semantic_discovery" in source
    assert "SEMANTIC_DISCOVERY is external to U8D" in source
    assert "from retriever" not in source
    assert "import retriever" not in source
