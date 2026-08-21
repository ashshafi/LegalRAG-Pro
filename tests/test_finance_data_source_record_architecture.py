from __future__ import annotations

import ast
from pathlib import Path


MODULES = (
    "src/finance_data/source_record_authority.py",
    "src/finance_data/source_record_serialization.py",
)

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
}

FORBIDDEN_CALL_TAILS = {
    "open",
    "write_text",
    "write_bytes",
    "mkdir",
    "makedirs",
    "remove",
    "unlink",
    "rename",
    "request",
    "get",
    "post",
    "put",
    "delete",
    "urlopen",
}


def _repo() -> Path:
    return Path(__file__).resolve().parents[1]


def _tree(relative: str) -> ast.AST:
    path = _repo() / relative
    return ast.parse(path.read_text(encoding="utf-8"), filename=relative)


def test_f7c_p4_source_record_authority_is_additive_exact_four_path_scope():
    repo = _repo()
    expected = {
        "src/finance_data/source_record_authority.py",
        "src/finance_data/source_record_serialization.py",
        "tests/test_finance_data_source_record_authority.py",
        "tests/test_finance_data_source_record_architecture.py",
    }

    for relative in expected:
        assert (repo / relative).is_file()


def test_source_record_modules_do_not_import_forbidden_authorities_or_networks():
    for relative in MODULES:
        for node in ast.walk(_tree(relative)):
            roots: set[str] = set()
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                roots.add((node.module or "").split(".")[0])

            assert roots.isdisjoint(FORBIDDEN_IMPORT_ROOTS), (
                relative,
                roots & FORBIDDEN_IMPORT_ROOTS,
            )


def test_source_record_modules_have_no_persistence_network_or_runtime_side_effect_calls():
    for relative in MODULES:
        for node in ast.walk(_tree(relative)):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                tail = node.func.id
            elif isinstance(node.func, ast.Attribute):
                tail = node.func.attr
            else:
                tail = ""

            assert tail not in FORBIDDEN_CALL_TAILS, (relative, node.lineno, tail)


def test_source_record_modules_do_not_reference_deferred_runtime_projection_or_comparable_layers():
    forbidden_text = (
        "streamlit",
        "finance_workspace",
        "finance_reports",
        "finance_report_projection",
        "comparable_set",
        "report_projections",
        "governed_analytical_authorities",
        "source_evidence_store",
        "data/cases.sqlite3",
    )

    for relative in MODULES:
        text = (_repo() / relative).read_text(encoding="utf-8").lower()
        for token in forbidden_text:
            assert token not in text, (relative, token)


def test_source_record_authority_schema_is_distinct_and_exact():
    text = (_repo() / "src/finance_data/source_record_authority.py").read_text(
        encoding="utf-8"
    )

    assert 'finance-source-record-authority/1.0' in text
    assert 'finance-immutable-dataset/1.0' not in text
    assert 'finance-source-document/1.0' not in text
