from __future__ import annotations

import ast
from pathlib import Path


MODULE = "src/finance_data/immutable_dataset_assembly.py"

FORBIDDEN_IMPORT_ROOTS = {
    "finance_evidence",
    "finance_comps",
    "finance_reporting",
    "finance_report_projection_provider",
    "requests",
    "httpx",
    "aiohttp",
    "urllib",
    "socket",
    "streamlit",
}

FORBIDDEN_SIDE_EFFECT_CALLS = {
    "open",
    "write_text",
    "write_bytes",
    "mkdir",
    "makedirs",
    "remove",
    "unlink",
    "rename",
    "urlopen",
    "request",
    "post",
    "put",
    "delete",
}


def _repo() -> Path:
    return Path(__file__).resolve().parents[1]


def _tree() -> ast.AST:
    path = _repo() / MODULE
    return ast.parse(path.read_text(encoding="utf-8"), filename=MODULE)


def _import_roots() -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            roots.add((node.module or "").split(".")[0])
    return roots


def test_f7c_p5_is_additive_exact_three_path_scope():
    repo = _repo()
    expected = {
        "src/finance_data/immutable_dataset_assembly.py",
        "tests/test_finance_data_immutable_dataset_assembly.py",
        "tests/test_finance_data_immutable_dataset_assembly_architecture.py",
    }

    for relative in expected:
        assert (repo / relative).is_file()


def test_assembly_imports_existing_dataset_and_source_record_authorities():
    text = (_repo() / MODULE).read_text(encoding="utf-8")

    assert "finance_data.immutable_dataset" in text
    assert "finance_data.source_record_authority" in text
    assert "ValidatedImmutableDataset" in text
    assert "FinanceSourceRecordAuthority" in text
    assert "derive_immutable_dataset_identity" in text
    assert "validate_immutable_dataset_document" in text
    assert "validate_finance_source_record_authority" in text


def test_assembly_does_not_import_forbidden_layers_or_networks():
    roots = _import_roots()

    assert roots.isdisjoint(FORBIDDEN_IMPORT_ROOTS), roots & FORBIDDEN_IMPORT_ROOTS


def test_assembly_defines_no_parallel_schema_or_authority_class():
    classes = [
        node.name
        for node in _tree().body
        if isinstance(node, ast.ClassDef)
    ]

    assert classes == []


def test_assembly_has_no_persistence_network_or_runtime_side_effect_calls():
    for node in ast.walk(_tree()):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            tail = node.func.id
        elif isinstance(node.func, ast.Attribute):
            tail = node.func.attr
        else:
            tail = ""

        assert tail not in FORBIDDEN_SIDE_EFFECT_CALLS, (node.lineno, tail)


def test_assembly_has_exact_public_function_name_and_keyword_only_contract():
    functions = {
        node.name: node
        for node in _tree().body
        if isinstance(node, ast.FunctionDef)
    }
    fn = functions["assemble_immutable_finance_dataset"]

    assert fn.args.args == []
    assert [arg.arg for arg in fn.args.kwonlyargs] == [
        "provider_id",
        "dataset_id",
        "dataset_version",
        "workspace",
        "companies",
        "securities",
        "periods",
        "source_record_authorities",
    ]


def test_assembly_contains_no_deferred_layer_references():
    text = (_repo() / MODULE).read_text(encoding="utf-8").lower()
    forbidden_text = (
        "finance_evidence",
        "finance_comps",
        "finance_reporting",
        "finance_report_projection",
        "streamlit",
        "report_projections",
        "governed_analytical_authorities",
        "source_evidence_store",
        "data/cases.sqlite3",
    )

    for token in forbidden_text:
        assert token not in text, token
