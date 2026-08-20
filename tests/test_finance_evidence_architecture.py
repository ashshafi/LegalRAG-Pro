import ast
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]
ROOT=PROJECT/"src"/"finance_evidence"
ALLOWED={"finance_domain","finance_comps","source_evidence.identity","source_evidence.extraction","source_evidence.models","source_evidence.validation"}
BLOCKED_PREFIXES=("case_management","case_analysis","legal_analysis","case_reporting","governed_analytical_authority","governed_answer_authority","governed_issue_evidence","governed_evidence_analysis","ui","streamlit","chromadb","openai","langchain","sqlite3","requests","httpx","source_evidence.capture","source_evidence.ingestion","source_evidence.chunking","source_evidence.store","source_evidence.verified_retrieval","source_evidence.projection_binding","source_evidence.resolver","source_evidence.migration","source_evidence.historical_","source_evidence.production_","source_evidence.offline_cutover")

def test_f5_is_exact_additive_architecture_without_forbidden_imports_or_persistence_network_calls():
    files=sorted(p.name for p in ROOT.glob("*.py")); assert files==["__init__.py","binding.py","capture.py","models.py","resolver.py","serialization.py","validation.py"]
    tests=sorted(p.name for p in (PROJECT/"tests").glob("test_finance_evidence_*.py")); assert tests==["test_finance_evidence_architecture.py","test_finance_evidence_binding.py","test_finance_evidence_capture.py","test_finance_evidence_models.py","test_finance_evidence_resolver.py","test_finance_evidence_serialization.py","test_finance_evidence_validation.py"]
    for path in ROOT.glob("*.py"):
        tree=ast.parse(path.read_text(encoding="utf-8"),filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node,ast.Import): names=[a.name for a in node.names]
            elif isinstance(node,ast.ImportFrom): names=[node.module or ""]
            else: names=[]
            for name in names:
                assert not any(name==b or name.startswith(b+".") for b in BLOCKED_PREFIXES), (path,name)
        text=path.read_text(encoding="utf-8")
        for token in ("PersistentClient","requests.","httpx.","OpenAI(","sqlite3.","os.replace","subprocess."):
            assert token not in text, (path,token)

def test_f5_does_not_modify_or_redefine_finance_or_source_evidence_models():
    text="\n".join(p.read_text(encoding="utf-8") for p in ROOT.glob("*.py"))
    assert "class FinancialObservation" not in text and "class SourceDocumentManifest" not in text and "case_id" not in text
