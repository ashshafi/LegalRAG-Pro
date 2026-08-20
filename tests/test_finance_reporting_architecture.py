import ast
from pathlib import Path
import finance_reporting

PRODUCTION=("__init__.py","models.py","projection.py","serialization.py","validation.py","markdown.py","html.py")
BLOCKED=("finance_answer_authority","finance_data","finance_evidence.capture","finance_evidence.binding","finance_evidence.resolver","source_evidence","case_reporting","workspace_index","report_projection_provider","ui","streamlit","openai","langchain","chromadb","requests","httpx","sqlite3")

def test_production_boundary_is_exact_and_contains_no_blocked_imports_or_runtime_io():
    root=Path(finance_reporting.__file__).parent
    assert tuple(sorted(p.name for p in root.glob("*.py")))==tuple(sorted(PRODUCTION))
    for path in root.glob("*.py"):
        tree=ast.parse(path.read_text(encoding="utf-8"))
        imports=[]
        for n in ast.walk(tree):
            if isinstance(n,ast.Import): imports.extend(a.name for a in n.names)
            elif isinstance(n,ast.ImportFrom) and n.module: imports.append(n.module)
        for name in imports:
            assert not any(name==b or name.startswith(b+".") for b in BLOCKED), (path.name,name)
        text=path.read_text(encoding="utf-8")
        for forbidden in ("datetime.now(","open(","Path(","requests.","httpx.","read_blob(","resolve_finance_observation_evidence"):
            assert forbidden not in text, (path.name,forbidden)

def test_projection_module_does_not_import_calculation_engine_or_perform_financial_arithmetic():
    root=Path(finance_reporting.__file__).parent
    text=(root/"projection.py").read_text(encoding="utf-8")
    assert "finance_calculations.engine" not in text and "finance_calculations.calculations" not in text
    assert "mean(" not in text and "median(" not in text
