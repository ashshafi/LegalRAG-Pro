from __future__ import annotations

from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"src"/"legal_analysis"


def test_m4_modules_do_not_import_retrieval_or_openai():
    text="\n".join((SRC/name).read_text(encoding="utf-8") for name in ("evidence_assessment.py","assessment_rules.py","element_assessor.py"))
    forbidden=("import retriever","from retriever","openai","chromadb","search_profiles","legal_analysis_retrieval_adapter")
    assert not any(item in text.casefold() for item in forbidden)


def test_m4_does_not_modify_m3_by_importing_mapper_implementation():
    text=(SRC/"element_assessor.py").read_text(encoding="utf-8")
    assert "evidence_mapper" not in text
    assert "ElementEvidenceMapper" not in text


def test_m4_local_proposition_status_does_not_modify_m1_enums():
    m1=(SRC/"enums.py").read_text(encoding="utf-8")
    assert "PropositionAssessmentStatus" not in m1
    m4=(SRC/"evidence_assessment.py").read_text(encoding="utf-8")
    assert "class PropositionAssessmentStatus" in m4


def test_m4_does_not_reexport_itself_through_frozen_m1_init():
    init=(SRC/"__init__.py").read_text(encoding="utf-8")
    assert "ElementEvidenceAssessor" not in init
    assert "EvidenceAssessmentResult" not in init
