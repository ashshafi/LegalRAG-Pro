"""Tests for Sprint 2.3 structured legal-analysis domain models."""

from __future__ import annotations

import sys
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from evidence_classification import EvidenceSourceType  # noqa: E402
from legal_analysis.enums import (  # noqa: E402
    AnalysisStatus,
    AnalyticalRole,
    Confidence,
    EvidenceStatus,
    Materiality,
    ProvenanceBasis,
    ProvenanceConfidence,
)
from legal_analysis.models import (  # noqa: E402
    ISSUE_ANALYSIS_SCHEMA_VERSION,
    DisputedMatter,
    ElementAnalysis,
    EvidentialGap,
    EvidenceReference,
    IssueAnalysis,
    Proposition,
)
from legal_analysis.registry import DEFAULT_ISSUE_DEFINITION_REGISTRY  # noqa: E402


def _evidence(*, role: AnalyticalRole = AnalyticalRole.SUPPORTING) -> EvidenceReference:
    return EvidenceReference(
        document_id="doc-2005-email",
        document_name="CACI email 14 June 2005.pdf",
        page=2,
        chunk_id="chunk-14",
        summary="A manager discusses the claimant's return-to-work arrangements.",
        source_type=EvidenceSourceType.EMPLOYER_RECORD,
        provenance_type=EvidenceSourceType.EMPLOYER_RECORD,
        provenance_basis=ProvenanceBasis.EXPLICIT_SENDER,
        provenance_confidence=ProvenanceConfidence.HIGH,
        evidence_status=EvidenceStatus.EMPLOYER_EVIDENCE,
        analytical_role=role,
        date=date(2005, 6, 14),
        author="Terry Williamson",
        parties=("CACI Ltd", "Arshad Shafi"),
        citation="CACI email 14 June 2005, p.2",
    )


def test_evidence_reference_reuses_sprint_2_2_source_enum() -> None:
    evidence = _evidence()

    assert evidence.source_type is EvidenceSourceType.EMPLOYER_RECORD
    assert evidence.provenance_type is EvidenceSourceType.EMPLOYER_RECORD
    assert evidence.provenance_basis is ProvenanceBasis.EXPLICIT_SENDER
    assert evidence.provenance_confidence is ProvenanceConfidence.HIGH


def test_evidence_reference_defaults_provenance_type_to_source_type() -> None:
    evidence = EvidenceReference(
        document_name="Claimant response.pdf",
        summary="The claimant requests an Occupational Health referral.",
        source_type=EvidenceSourceType.CLAIMANT_CORRESPONDENCE,
        evidence_status=EvidenceStatus.CLAIMANT_EVIDENCE,
        analytical_role=AnalyticalRole.SUPPORTING,
        citation="Claimant response, p.1",
    )

    assert evidence.provenance_type is EvidenceSourceType.CLAIMANT_CORRESPONDENCE


def test_evidence_reference_rejects_invalid_page() -> None:
    with pytest.raises(ValueError, match="page must be 1 or greater"):
        replace(_evidence(), page=0)


def test_evidence_reference_rejects_untyped_analytical_role() -> None:
    with pytest.raises(ValueError, match="analytical_role"):
        EvidenceReference(
            document_name="x.pdf",
            summary="summary",
            source_type=EvidenceSourceType.OTHER,
            evidence_status=EvidenceStatus.SOURCE_ASSERTION,
            analytical_role="supporting",  # type: ignore[arg-type]
            citation="x",
        )


def test_proposition_preserves_evidence_and_confidence() -> None:
    evidence = _evidence()
    proposition = Proposition(
        text="CACI personnel participated in return-to-work discussions.",
        status=EvidenceStatus.DOCUMENTED_FACT,
        confidence=Confidence.HIGH,
        evidence=(evidence,),
    )

    assert proposition.evidence == (evidence,)
    assert proposition.confidence is Confidence.HIGH


def test_disputed_matter_can_hold_competing_positions() -> None:
    evidence = _evidence()
    dispute = DisputedMatter(
        proposition="CACI knew the full medical recommendation.",
        claimant_position="The claimant says CACI was fully aware.",
        respondent_position="The respondent disputes that knowledge.",
        contemporaneous_evidence=(evidence,),
        presently_established="CACI participated in RTW communications.",
        remains_unresolved="Whether the full recommendation was received.",
    )

    assert dispute.claimant_position is not None
    assert dispute.respondent_position is not None
    assert dispute.contemporaneous_evidence == (evidence,)


def test_disputed_matter_rejects_empty_conflict() -> None:
    with pytest.raises(ValueError, match="at least one position or evidence"):
        DisputedMatter(proposition="A disputed proposition")



def test_evidential_gap_rejects_untyped_materiality() -> None:
    with pytest.raises(ValueError, match="materiality"):
        EvidentialGap(
            description="Missing direct evidence.",
            related_element_id="EK-DIRECT-KNOWLEDGE",
            materiality="high",  # type: ignore[arg-type]
            reason="It bears on actual knowledge.",
        )

def test_evidential_gap_must_match_element_when_nested() -> None:
    gap = EvidentialGap(
        description="No direct acknowledgement has been located.",
        related_element_id="EK-DIRECT-KNOWLEDGE",
        materiality=Materiality.HIGH,
        reason="Direct receipt is material to actual knowledge.",
    )

    with pytest.raises(ValueError, match="must match"):
        ElementAnalysis(
            element_id="EK-RECIPIENT",
            element_name="Recipient",
            question_to_determine="Who received the information?",
            evidential_gaps=(gap,),
        )


def test_issue_analysis_from_definition_carries_case_and_version() -> None:
    definition = DEFAULT_ISSUE_DEFINITION_REGISTRY.get_definition("RA-001", "1.0")
    case_id = str(uuid4())

    analysis = IssueAnalysis.from_definition(
        case_id=case_id,
        user_question="What reasonable adjustments evidence exists?",
        definition=definition,
    )

    assert analysis.case_id == case_id
    assert analysis.issue_definition_id == "RA-001"
    assert analysis.issue_definition_version == "1.0"
    assert analysis.schema_version == ISSUE_ANALYSIS_SCHEMA_VERSION
    assert analysis.analysis_status is AnalysisStatus.PRELIMINARY
    assert [item.element_id for item in analysis.elements] == [
        item.element_id for item in definition.elements
    ]


def test_issue_analysis_rejects_non_uuid_case_id() -> None:
    definition = DEFAULT_ISSUE_DEFINITION_REGISTRY.get_definition("RA-001")
    with pytest.raises(ValueError, match="case_id must be a valid UUID"):
        IssueAnalysis.from_definition(
            case_id="not-a-case-uuid",
            user_question="question",
            definition=definition,
        )


def test_issue_analysis_rejects_naive_timestamp() -> None:
    definition = DEFAULT_ISSUE_DEFINITION_REGISTRY.get_definition("RA-001")
    analysis = IssueAnalysis.from_definition(
        case_id=str(uuid4()),
        user_question="question",
        definition=definition,
    )

    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        replace(analysis, created_at=datetime(2026, 8, 2, 12, 0, 0))


def test_issue_analysis_rejects_unsupported_status_string() -> None:
    definition = DEFAULT_ISSUE_DEFINITION_REGISTRY.get_definition("RA-001")
    analysis = IssueAnalysis.from_definition(
        case_id=str(uuid4()),
        user_question="question",
        definition=definition,
    )

    with pytest.raises(ValueError, match="analysis_status"):
        replace(analysis, analysis_status="complete")  # type: ignore[arg-type]


def test_domain_models_are_frozen() -> None:
    evidence = _evidence()
    with pytest.raises(FrozenInstanceError):
        evidence.summary = "changed"  # type: ignore[misc]


def test_element_analysis_explicitly_represents_all_evidence_roles() -> None:
    supporting = _evidence(role=AnalyticalRole.SUPPORTING)
    adverse = replace(_evidence(), analytical_role=AnalyticalRole.ADVERSE)
    corroborative = replace(_evidence(), analytical_role=AnalyticalRole.CORROBORATIVE)
    neutral = replace(_evidence(), analytical_role=AnalyticalRole.NEUTRAL)
    conflicting = replace(_evidence(), analytical_role=AnalyticalRole.CONFLICTING)

    element = ElementAnalysis(
        element_id="EK-DIRECT-KNOWLEDGE",
        element_name="Direct knowledge",
        question_to_determine="What direct evidence exists?",
        supporting_evidence=(supporting,),
        adverse_evidence=(adverse,),
        corroborative_evidence=(corroborative,),
        neutral_evidence=(neutral,),
        conflicting_evidence=(conflicting,),
    )

    assert element.supporting_evidence == (supporting,)
    assert element.adverse_evidence == (adverse,)
    assert element.corroborative_evidence == (corroborative,)
    assert element.neutral_evidence == (neutral,)
    assert element.conflicting_evidence == (conflicting,)


def test_element_analysis_rejects_evidence_in_wrong_role_bucket() -> None:
    with pytest.raises(ValueError, match="supporting_evidence"):
        ElementAnalysis(
            element_id="EK-DIRECT-KNOWLEDGE",
            element_name="Direct knowledge",
            question_to_determine="What direct evidence exists?",
            supporting_evidence=(_evidence(role=AnalyticalRole.ADVERSE),),
        )
