from __future__ import annotations

import ast
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PACKAGE = SRC / "evidence_references"
FILES = (
    PACKAGE / "__init__.py",
    PACKAGE / "models.py",
    PACKAGE / "resolver.py",
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

FROZEN_EXPECTED_SHA256 = {
    "evidence_retrieval/__init__.py": "42261497069873076703ef9101666d4356f283aac9c256eee10110da439ab13f",
    "evidence_retrieval/models.py": "6b260ee070bfb62b9d15757c9ba15d3a2fd15f8607e9f88a48bcf512c07aabac",
    "evidence_retrieval/document_complete.py": "4174a332b66e3eabbf15c7474c49d04f8359f1e1495829dd897d5eccdd502a56",
    "evidence_roles/__init__.py": "07dfb35606fffeb79fb7208062910046550eee396220a5453121e4652b3650a3",
    "evidence_roles/models.py": "b41cad658da99e6fb357ebd4e1db11a549bcec1f38fd2557b8115eb620a575a9",
    "evidence_roles/classifier.py": "642273b60692e75134bacadac29c21bb071e9342766c69ffa9b20693a62a13d0",
    "evidence_search/__init__.py": "c8906c73562c357fb1d35cc254444acf20385c9c7bec3e6a554e67eeca6bd716",
    "evidence_search/models.py": "205c2ba437b0dc9d6047ab48553b7562860dd7ef8d6bb75e7ff20d91008e4e75",
    "evidence_search/orchestrator.py": "81c2623f7c5322a335d1a82207368aabf5bfe2d45cde235f0f3bd56b2217ba0e",
    "app.py": "9ae3a64146897ba58d9398f2ea949fb992001a663677059d1643686dc4170e8b",
    "ui/document_register.py": "98f104daa2388f537dbd4d9007df3c7c685737f70a1c301d2c08b65f9d473d90",
    "ui/evidence_inspection.py": "118b70e33966e8a125eacad9374355e001862e1d345062e38a89fef284e61d73",
    "evidence_answer/__init__.py": "1be8ae0674594c93e46ad6fd9dbffb4f32003816ada5c7afb2a05c447f4b2184",
    "evidence_answer/governed_retrieval.py": "8dae58a06d63007064dd5c6a09fe266913fa607034b55c4db7e4f6ae47fd8159",
    "legalrag.py": "b0c67200850ab843fe1a2d3de7b1e750029b6c8c952edc414ce1776b168dfa52",
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


def test_u8fc1_is_exactly_three_additive_source_files():
    assert PACKAGE.is_dir()
    assert sorted(path.name for path in PACKAGE.iterdir() if path.is_file()) == [
        "__init__.py",
        "models.py",
        "resolver.py",
    ]


def test_u8fc1_preserves_u8b_through_u8f_production_files_byte_exact():
    for relative, expected in FROZEN_EXPECTED_SHA256.items():
        assert _sha256(SRC / relative) == expected, relative


def test_u8fc1_has_no_chroma_openai_ui_retriever_or_direct_source_dependency():
    for path in FILES:
        imported = _import_roots(_tree(path))
        assert imported.isdisjoint(PROHIBITED_IMPORT_ROOTS), (path, imported)


def test_u8fc1_has_no_file_database_source_store_or_dynamic_mutation_calls():
    for path in FILES:
        assert _calls(_tree(path)).isdisjoint(PROHIBITED_CALLS)


def test_u8fc1_consumes_u8d_result_and_u8c_roles_without_reopening_lower_layers():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in FILES)
    assert "CaseEvidenceSearchResult" in combined
    assert "EvidenceSearchCompletion" in combined
    assert "NegativeFindingScope" in combined
    assert "EvidenceRole.PRIMARY_SOURCE" in combined
    assert "EvidenceRole.MIXED" in combined
    assert "SourceDocumentManifest" not in combined
    assert "EvidenceBinding" not in combined
    assert "list_case_documents" not in combined
    assert "inspect_document_complete" not in combined


def test_u8fc1_resolution_vocabulary_is_exact():
    tree = _tree(PACKAGE / "models.py")
    cls = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "EvidenceReferenceResolutionStatus"
    )
    members = [
        target.id
        for stmt in cls.body
        if isinstance(stmt, ast.Assign)
        for target in stmt.targets
        if isinstance(target, ast.Name)
    ]
    assert members == [
        "RESOLVED",
        "AMBIGUOUS",
        "POSSIBLE_REFERENCED_BUT_NOT_LOCATED",
        "UNRESOLVED_REFERENCE",
    ]


def test_possible_not_located_is_tied_to_complete_case_corpus_authority():
    source = (PACKAGE / "resolver.py").read_text(encoding="utf-8")
    models = (PACKAGE / "models.py").read_text(encoding="utf-8")
    assert "case_corpus_complete" in source
    assert "NegativeFindingScope.CASE_CORPUS" in source
    assert "POSSIBLE_REFERENCED_BUT_NOT_LOCATED" in source
    assert "possible_not_located_permitted" in models
    assert "POSSIBLE_REFERENCED_BUT_NOT_LOCATED requires complete case-corpus authority" in models


def test_u8fc1_does_not_bridge_into_answer_or_ui_yet():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in FILES)
    assert "build_governed_answer_prompt" not in combined
    assert "prepare_governed_answer_evidence" not in combined
    assert "streamlit" not in combined.casefold()
