from governed_issue_evidence.models import (
    GOVERNED_ISSUE_EVIDENCE_BUILDER_VERSION,
    GOVERNED_ISSUE_EVIDENCE_SCHEMA_VERSION,
    GovernedEvidenceUse,
    GovernedPropositionLink,
)


def test_versions_and_native_evidence_use_identity_are_frozen():
    proposition = GovernedPropositionLink(
        source_proposition_index=2,
        text="A proposition",
        status="supported_but_not_established",
        confidence="medium",
        rationale="Existing frozen rationale.",
        evidence_keys=["evidence-1"],
    )
    use = GovernedEvidenceUse(
        issue_analysis_id="analysis-1",
        issue_definition_id="EK-001",
        issue_definition_version="1.0",
        element_id="EK-DIRECT-KNOWLEDGE",
        element_ordinal=0,
        evidence_key="evidence-1",
        analytical_role="supporting",
        mapping_relevance="relevant",
        mapping_confidence="high",
        mapping_rationale="Existing mapper rationale.",
        assessment_confidence="medium",
        assessment_rationale="Existing assessor rationale.",
        citation="Employer letter.pdf, p.1",
        proposition_links=[proposition],
    )

    assert GOVERNED_ISSUE_EVIDENCE_SCHEMA_VERSION == "governed-issue-evidence-schema/1.0"
    assert GOVERNED_ISSUE_EVIDENCE_BUILDER_VERSION == "governed-issue-evidence-builder/1.0"
    assert use.identity == ("analysis-1", "EK-DIRECT-KNOWLEDGE", "evidence-1")
    assert isinstance(use.proposition_links, tuple)
    assert isinstance(use.proposition_links[0].evidence_keys, tuple)
