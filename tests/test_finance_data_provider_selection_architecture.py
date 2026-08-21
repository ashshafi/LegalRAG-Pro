import ast
from pathlib import Path


SOURCE = Path(__file__).parents[1] / "src" / "finance_data" / "provider_selection.py"


def _tree() -> ast.Module:
    return ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))


def test_provider_selection_is_additive_and_has_only_expected_dependencies():
    tree = _tree()
    imports = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    assert imports <= {
        "__future__",
        "pathlib",
        "finance_data.frozen_demo",
        "finance_data.immutable_provider",
        "finance_data.provider",
    }

    source = SOURCE.read_text(encoding="utf-8").lower()
    forbidden = (
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "socket",
        "yfinance",
        "openai",
        "chromadb",
        "os.environ",
        "os.getenv",
        "getenv(",
        "finance_data.immutable_dataset_publication",
        "publish_immutable_finance_dataset",
        "streamlit",
        "finance_reporting",
        "finance_report_projection",
    )
    for token in forbidden:
        assert token not in source


def test_selector_contract_is_keyword_only_and_returns_generic_provider():
    tree = _tree()
    selector = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "select_financial_data_provider"
    )

    assert selector.args.args == []
    assert [arg.arg for arg in selector.args.kwonlyargs] == [
        "mode",
        "dataset_path",
        "expected_provider_id",
        "expected_dataset_id",
        "expected_dataset_version",
    ]
    assert ast.unparse(selector.returns) == "FinancialDataProvider"

    defaults = selector.args.kw_defaults
    assert defaults[0] is None
    assert all(isinstance(value, ast.Constant) and value.value is None for value in defaults[1:])


def test_selector_constructs_only_governed_existing_provider_types():
    tree = _tree()
    calls = []
    forbidden_mutations = {
        "open",
        "write_text",
        "write_bytes",
        "mkdir",
        "unlink",
        "replace",
        "rename",
        "remove",
        "rmdir",
    }

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            calls.append(node.func.id)
            assert node.func.id not in forbidden_mutations
        elif isinstance(node.func, ast.Attribute):
            calls.append(node.func.attr)
            assert node.func.attr not in forbidden_mutations

    assert calls.count("ImmutableDatasetProvider") == 1
    assert calls.count("FrozenDemoProvider") == 1


def test_no_implicit_dataset_root_or_environment_discovery_is_encoded():
    tree = _tree()
    string_literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    forbidden_path_fragments = (
        "source_evidence_store",
        "governed_analytical_authorities",
        "report_projections",
        "data/cases.sqlite3",
        "db/",
        "db\\",
    )
    for literal in string_literals:
        lower = literal.lower()
        assert not any(fragment in lower for fragment in forbidden_path_fragments)

    names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    }
    assert "environ" not in names
    assert "getenv" not in names
