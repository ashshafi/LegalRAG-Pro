"""Structured legal-analysis domain foundation for LegalRAG Pro."""

from .definitions import INITIAL_ISSUE_DEFINITIONS
from .enums import (
    AnalysisStatus,
    AnalyticalRole,
    Confidence,
    EvidenceSourceType,
    EvidenceStatus,
    IssueDefinitionStatus,
    Materiality,
    ProvenanceBasis,
    ProvenanceConfidence,
)
from .models import (
    ISSUE_ANALYSIS_SCHEMA_VERSION,
    DisputedMatter,
    ElementAnalysis,
    EvidentialGap,
    EvidenceReference,
    IssueAnalysis,
    IssueDefinition,
    IssueElementDefinition,
    Proposition,
)
from .registry import DEFAULT_ISSUE_DEFINITION_REGISTRY, IssueDefinitionRegistry
from .serialization import (
    dumps_issue_analysis,
    issue_analysis_from_dict,
    issue_analysis_to_dict,
    loads_issue_analysis,
)
from .validation import (
    validate_analysis_against_definition,
    validate_issue_analysis,
    validate_issue_definition,
)

__all__ = [
    "AnalysisStatus",
    "AnalyticalRole",
    "Confidence",
    "DEFAULT_ISSUE_DEFINITION_REGISTRY",
    "DisputedMatter",
    "ElementAnalysis",
    "EvidentialGap",
    "EvidenceReference",
    "EvidenceSourceType",
    "EvidenceStatus",
    "INITIAL_ISSUE_DEFINITIONS",
    "ISSUE_ANALYSIS_SCHEMA_VERSION",
    "IssueAnalysis",
    "IssueDefinition",
    "IssueDefinitionRegistry",
    "IssueDefinitionStatus",
    "IssueElementDefinition",
    "Materiality",
    "Proposition",
    "ProvenanceBasis",
    "ProvenanceConfidence",
    "dumps_issue_analysis",
    "issue_analysis_from_dict",
    "issue_analysis_to_dict",
    "loads_issue_analysis",
    "validate_analysis_against_definition",
    "validate_issue_analysis",
    "validate_issue_definition",
]
