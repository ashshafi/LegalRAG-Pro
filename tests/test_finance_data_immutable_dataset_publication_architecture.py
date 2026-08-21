from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "src" / "finance_data" / "immutable_dataset_publication.py"
TEST = ROOT / "tests" / "test_finance_data_immutable_dataset_publication.py"
ARCH = ROOT / "tests" / "test_finance_data_immutable_dataset_publication_architecture.py"

EXPECTED_F7C_P6_PATHS = {
    "src/finance_data/immutable_dataset_publication.py",
    "tests/test_finance_data_immutable_dataset_publication.py",
    "tests/test_finance_data_immutable_dataset_publication_architecture.py",
}

FORBIDDEN_IMPORT_PREFIXES = (
    "finance_evidence",
    "finance_comps",
    "finance_calculations",
    "finance_answer_authority",
    "finance_reporting",
    "finance_report_projection",
    "finance_workspace",
    "source_evidence",
    "case_management",
    "case_analysis",
    "legal_analysis",
    "ui",
    "streamlit",
    "openai",
    "langchain",
    "chromadb",
    "requests",
    "httpx",
    "aiohttp",
    "sqlite3",
    "socket",
)

FORBIDDEN_TEXT = (
    "report_projections",
    "source_evidence_store",
    "governed_analytical_authorities",
    "data/cases.sqlite3",
    "PersistentClient",
    "OpenAI(",
    "requests.",
    "httpx.",
    "aiohttp.",
    "streamlit.",
)


def _tree() -> ast.Module:
    return ast.parse(SOURCE.read_text(encoding="utf-8"))


def _imports() -> set[str]:
    result: set[str] = set()
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_f7c_p6_is_exactly_three_additive_paths():
    assert SOURCE.is_file()
    assert TEST.is_file()
    assert ARCH.is_file()
    assert EXPECTED_F7C_P6_PATHS == {
        "src/finance_data/immutable_dataset_publication.py",
        "tests/test_finance_data_immutable_dataset_publication.py",
        "tests/test_finance_data_immutable_dataset_publication_architecture.py",
    }


def test_publication_imports_only_governed_dataset_provider_and_domain_serializers():
    imports = _imports()
    assert "finance_data.immutable_dataset" in imports
    assert "finance_data.immutable_provider" in imports
    assert "finance_domain.serialization" in imports
    assert "finance_data.immutable_dataset_assembly" not in imports

    for imported in imports:
        assert not imported.startswith(FORBIDDEN_IMPORT_PREFIXES)


def test_publication_has_no_network_runtime_projection_or_protected_root_wiring():
    text = SOURCE.read_text(encoding="utf-8")
    for token in FORBIDDEN_TEXT:
        assert token not in text


def test_publication_signature_requires_validated_dataset_and_explicit_keyword_path():
    tree = _tree()
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "publish_immutable_finance_dataset"
    )

    positional = [arg.arg for arg in function.args.args]
    keyword_only = [arg.arg for arg in function.args.kwonlyargs]
    assert positional == ["dataset"]
    assert keyword_only == ["target_path"]
    assert ast.unparse(function.args.args[0].annotation) == "ValidatedImmutableDataset"
    assert ast.unparse(function.args.kwonlyargs[0].annotation) == "Path"
    assert ast.unparse(function.returns) == "Path"


def test_publication_uses_canonical_serializer_revalidation_fsync_and_hardlink():
    text = SOURCE.read_text(encoding="utf-8")
    assert "validate_immutable_dataset_document(" in text
    assert "dumps_immutable_dataset_document(" in text
    assert 'path.open("xb")' in text
    assert "handle.flush()" in text
    assert "os.fsync(" in text
    assert "os.link(" in text
    assert "FileExistsError" in text
    assert "staging.unlink(missing_ok=True)" in text


def test_publication_never_overwrites_or_uses_implicit_production_root():
    text = SOURCE.read_text(encoding="utf-8")
    forbidden = (
        "os.replace(",
        ".replace(staging",
        "shutil.move",
        "shutil.copy",
        "shutil.copy2",
        "write_text(",
        "write_bytes(payload",
        "root: Path | None",
        "project_root",
        "__file__).resolve().parent.parent",
    )
    for token in forbidden:
        assert token not in text


def test_object_to_document_conversion_is_local_explicit_and_identity_preserving():
    text = SOURCE.read_text(encoding="utf-8")
    assert "def _document_from_validated_dataset(" in text
    assert '"dataset_identity": dataset.dataset_identity' in text
    assert "dumps_finance_workspace(dataset.workspace)" in text
    assert "dumps_company(company)" in text
    assert "dumps_security(security)" in text
    assert "dumps_financial_period(period)" in text
    assert "dumps_financial_observation(observation)" in text
    assert "reconstructed != dataset" in text


def test_provider_handoff_occurs_after_publication():
    text = SOURCE.read_text(encoding="utf-8")
    assert "ImmutableDatasetProvider(" in text
    assert "_verify_provider_handoff(dataset, target)" in text


def test_no_acquisition_calculation_comparable_evidence_or_ai_authority():
    text = SOURCE.read_text(encoding="utf-8").lower()
    for token in (
        "fetch(",
        "request(",
        "scrape",
        "yfinance",
        "bloomberg",
        "refinitiv",
        "comparable",
        "valuation",
        "llm",
        "prompt",
        "finance_evidence",
    ):
        assert token not in text
