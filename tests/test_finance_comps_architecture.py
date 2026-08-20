import ast
from pathlib import Path

BLOCKED={
    "case_management","case_analysis","legal_analysis","governed_analytical_authority","governed_answer_authority",
    "governed_issue_evidence","governed_evidence_analysis","case_reporting","ui","streamlit","chromadb","openai",
    "langchain","sqlite3","requests","httpx",
}
ALLOWED_ROOTS={"finance_comps","finance_domain","finance_data","finance_calculations"}


def test_finance_comps_isolated_from_legal_ui_runtime_network_and_persistence_imports():
    root=Path(__file__).resolve().parents[1]/"src"/"finance_comps"
    assert sorted(p.name for p in root.glob("*.py"))==["__init__.py","builder.py","models.py","serialization.py","statistics.py","validation.py"]
    for path in root.glob("*.py"):
        tree=ast.parse(path.read_text(encoding="utf-8"),filename=str(path))
        for node in ast.walk(tree):
            names=[]
            if isinstance(node,ast.Import): names=[a.name for a in node.names]
            elif isinstance(node,ast.ImportFrom) and node.module: names=[node.module]
            for name in names:
                root_name=name.split(".")[0]
                assert root_name not in BLOCKED, f"{path.name} imports blocked {name}"


def test_f4_has_no_filesystem_or_network_call_primitives():
    root=Path(__file__).resolve().parents[1]/"src"/"finance_comps"
    forbidden=("open(","Path(","read_text(","write_text(","requests.","httpx.","sqlite3.")
    text="\n".join(p.read_text(encoding="utf-8") for p in root.glob("*.py"))
    for token in forbidden:
        assert token not in text
