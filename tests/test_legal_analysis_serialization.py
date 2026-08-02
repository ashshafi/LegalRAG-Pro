"""Round-trip and deterministic serialization tests for IssueAnalysis."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path
from uuid import uuid4

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from evidence_classification import EvidenceSourceType  # noqa: E402
from legal_analysis.enums import (  # noqa: E402
    AnalyticalRole,
    Confidence,
    EvidenceStatus,
    Materiality,
    ProvenanceBasis,
    ProvenanceConfidence,
)
from legal_analysis.models import (  # noqa: E402
    DisputedMatter,
    ElementAnalysis,
    EvidentialGap,
    EvidenceReference,
    IssueAnalysis,
    Proposition,
)
from legal_analysis.registry import DEFAULT_ISSUE_DEFINITION_REGISTRY  # noqa: E402
from legal_analysis.serialization import (  # noqa: E402
    dumps_issue_analysis,
    issue_analysis_from_dict,
    issue_analysis_to_dict,
    loads_issue_analysis,
)


def _complete_analysis() -> IssueAnalysis:
    definition = DEFAULT_ISSUE_DEFINITION_REGISTRY.get_definition("EK-001", "1.0")
    base = IssueAnalysis.from_definition(
        case_id=str(uuid4()),
        user_question="What did the employer actually know?",
        definition=definition,
    )
    employer_email = EvidenceReference(
        document_id="doc-1",
        document_name="14 June 2005 email.pdf",
        page=2,
        chunk_id="chunk-1",
        summary="A CACI manager discusses the return-to-work arrangements.",
        source_type=EvidenceSourceType.EMPLOYER_RECORD,
        provenance_type=EvidenceSourceType.EMPLOYER_RECORD,
        provenance_basis=ProvenanceBasis.EXPLICIT_SENDER,
        provenance_confidence=ProvenanceConfidence.HIGH,
        evidence_status=EvidenceStatus.EMPLOYER_EVIDENCE,
        analytical_role=AnalyticalRole.SUPPORTING,
        date=date(2005, 6, 14),
        author="Terry Williamson",
        parties=("CACI Ltd", "Arshad Shafi"),
        citation="14 June 2005 email, p.2",
    )
    claimant_statement = EvidenceReference(
        document_id="doc-2",
        document_name="Supplementary Witness Statement.pdf",
        page=1,
        chunk_id="chunk-2",
        summary="The claimant states that management was aware of the circumstances.",
        source_type=EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT,
        provenance_type=EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT,
        provenance_basis=ProvenanceBasis.KNOWN_DOCUMENT_AUTHOR,
        provenance_confidence=ProvenanceConfidence.HIGH,
        evidence_status=EvidenceStatus.CLAIMANT_EVIDENCE,
        analytical_role=AnalyticalRole.CORROBORATIVE,
        author="Arshad Shafi",
        parties=("Arshad Shafi",),
        citation="Supplementary Witness Statement, p.1",
    )
    proposition = Proposition(
        text="CACI personnel participated in rehabilitation communications.",
        status=EvidenceStatus.DOCUMENTED_FACT,
        confidence=Confidence.HIGH,
        evidence=(employer_email,),
    )
    inference = Proposition(
        text="Participation may support an inference of awareness of sickness-related circumstances.",
        status=EvidenceStatus.INFERENCE,
        confidence=Confidence.MEDIUM,
        evidence=(employer_email, claimant_statement),
    )
    dispute = DisputedMatter(
        proposition="CACI knew the full medical recommendation.",
        claimant_position="The claimant says CACI was fully aware.",
        claimant_evidence=(claimant_statement,),
        contemporaneous_evidence=(employer_email,),
        presently_established="CACI participated in rehabilitation communications.",
        remains_unresolved="Whether the full recommendation was received and understood.",
    )
    gap = EvidentialGap(
        description="No direct CACI acknowledgement of the full recommendation has been located.",
        related_element_id="EK-DIRECT-KNOWLEDGE",
        materiality=Materiality.HIGH,
        reason="Direct acknowledgement would materially bear on actual knowledge.",
        suggested_evidence_target="Contemporaneous CACI email acknowledging the recommendation.",
    )
    elements = list(base.elements)
    index = next(
        i for i, element in enumerate(elements) if element.element_id == "EK-DIRECT-KNOWLEDGE"
    )
    elements[index] = ElementAnalysis(
        element_id="EK-DIRECT-KNOWLEDGE",
        element_name=elements[index].element_name,
        question_to_determine=elements[index].question_to_determine,
        propositions=(proposition,),
        supporting_evidence=(employer_email,),
        corroborative_evidence=(claimant_statement,),
        disputed_matters=(dispute,),
        inferences=(inference,),
        evidential_gaps=(gap,),
        respondent_position=("The respondent disputes knowledge of particular matters.",),
        legal_analysis="The direct email establishes participation, not necessarily full medical knowledge.",
        assessment="Direct participation is evidenced; the scope of knowledge remains disputed.",
        confidence=Confidence.MEDIUM,
    )
    return replace(base, elements=tuple(elements))


def test_issue_analysis_dict_round_trip_has_no_information_loss() -> None:
    analysis = _complete_analysis()

    restored = issue_analysis_from_dict(issue_analysis_to_dict(analysis))

    assert restored == analysis


def test_issue_analysis_json_round_trip_has_no_information_loss() -> None:
    analysis = _complete_analysis()

    restored = loads_issue_analysis(dumps_issue_analysis(analysis))

    assert restored == analysis


def test_serialization_retains_schema_and_issue_definition_versions() -> None:
    data = issue_analysis_to_dict(_complete_analysis())

    assert data["schema_version"] == "issue-analysis-schema/1.0"
    assert data["issue_definition_id"] == "EK-001"
    assert data["issue_definition_version"] == "1.0"


def test_json_serialization_is_deterministic() -> None:
    analysis = _complete_analysis()

    first = dumps_issue_analysis(analysis)
    second = dumps_issue_analysis(analysis)

    assert first == second
    parsed = json.loads(first)
    assert parsed["case_id"] == analysis.case_id


def test_nested_provenance_and_evidence_status_survive_round_trip() -> None:
    restored = loads_issue_analysis(dumps_issue_analysis(_complete_analysis()))
    element = next(
        item for item in restored.elements if item.element_id == "EK-DIRECT-KNOWLEDGE"
    )
    evidence = element.supporting_evidence[0]

    assert evidence.source_type is EvidenceSourceType.EMPLOYER_RECORD
    assert evidence.provenance_basis is ProvenanceBasis.EXPLICIT_SENDER
    assert evidence.provenance_confidence is ProvenanceConfidence.HIGH
    assert evidence.evidence_status is EvidenceStatus.EMPLOYER_EVIDENCE
    assert evidence.analytical_role is AnalyticalRole.SUPPORTING
