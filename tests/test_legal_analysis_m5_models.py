from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

from legal_analysis.enums import Confidence
from legal_analysis.legal_analysis import (
    ElementAnalysisStatus,
    ElementLegalAnalysis,
    EvidenceBackedStatement,
    IssueLevelSynthesis,
)


def test_evidence_backed_statement_requires_key_and_citation():
    with pytest.raises(ValueError):
        EvidenceBackedStatement("Fact", (), ("Doc p.1",))
    with pytest.raises(ValueError):
        EvidenceBackedStatement("Fact", ("k",), ())


def test_evidence_backed_statement_deduplicates_traceability():
    item = EvidenceBackedStatement("Fact", ("k", "k"), ("Doc p.1", "Doc p.1"))
    assert item.evidence_keys == ("k",)
    assert item.citations == ("Doc p.1",)


def _element() -> ElementLegalAnalysis:
    return ElementLegalAnalysis(
        issue_definition_id="EK-001",
        issue_definition_version="1.0",
        element_id="EK-DIRECT-KNOWLEDGE",
        legal_question="What direct evidence records knowledge?",
        current_evidential_position="The record is partial.",
        established_matters=(),
        supported_matters=(),
        not_supported_matters=(),
        source_assertions=(),
        adverse_material=(),
        corroborative_material=(),
        contextual_material=(),
        conflicting_material=(),
        disputed_matters=(),
        legal_significance="Direct communications may bear on actual knowledge.",
        limitations=("Specific receipt remains unresolved.",),
        unresolved_matters=("Who received the report remains unresolved.",),
        evidential_gaps=(),
        provisional_status=ElementAnalysisStatus.UNRESOLVED,
        provisional_analysis="The record remains unresolved.",
        analysis_confidence=Confidence.LOW,
    )


def test_element_legal_analysis_normalises_strings_and_tuples():
    item = _element()
    assert item.element_id == "EK-DIRECT-KNOWLEDGE"
    assert item.limitations == ("Specific receipt remains unresolved.",)


def test_element_legal_analysis_requires_m5_status():
    with pytest.raises(ValueError):
        replace(_element(), provisional_status="unresolved")  # type: ignore[arg-type]


def test_issue_level_synthesis_requires_summary():
    with pytest.raises(ValueError):
        IssueLevelSynthesis(summary=" ")


def test_issue_level_synthesis_deduplicates_element_ids():
    synthesis = IssueLevelSynthesis(
        partially_supported_elements=("EK-DIRECT-KNOWLEDGE", "EK-DIRECT-KNOWLEDGE"),
        summary="Mechanical synthesis only.",
    )
    assert synthesis.partially_supported_elements == ("EK-DIRECT-KNOWLEDGE",)
