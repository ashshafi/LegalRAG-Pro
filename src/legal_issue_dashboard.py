"""Read-only projection of an activated governed analytical authority for dashboard display."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from governed_analytical_authority.models import GovernedRuntimeAnalyticalAuthority


DASHBOARD_SCHEMA_VERSION = "legal-issue-dashboard/1.2"
_ALLOWED_ROLES = ("supporting", "adverse", "corroborative", "neutral", "conflicting")
_ALLOWED_CONFIDENCE = ("high", "medium", "low")


class LegalIssueDashboardError(RuntimeError):
    """Raised when frozen analytical state cannot be projected safely."""


@dataclass(frozen=True, slots=True)
class DashboardStatement:
    """One frozen M5 statement with its existing traceability."""

    text: str
    evidence_keys: tuple[str, ...]
    citations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DashboardGap:
    """One frozen evidential gap."""

    gap_id: str
    description: str
    related_element_id: str
    materiality: str
    reason: str
    suggested_evidence_target: str | None


@dataclass(frozen=True, slots=True)
class DashboardDispute:
    """One frozen disputed matter."""

    disputed_matter_id: str
    proposition: str
    claimant_position: str | None
    respondent_position: str | None


@dataclass(frozen=True, slots=True)
class DashboardEvidenceCounts:
    """Unique frozen Case Matrix evidence-key counts by analytical role."""

    supporting: int
    adverse: int
    corroborative: int
    neutral: int
    conflicting: int
    distinct_any_role: int

    @property
    def role_memberships(self) -> int:
        """Return role-membership total; this is not a distinct-evidence total."""

        return (
            self.supporting
            + self.adverse
            + self.corroborative
            + self.neutral
            + self.conflicting
        )


@dataclass(frozen=True, slots=True)
class DashboardSynthesisCounts:
    """Mechanical counts copied from the frozen issue synthesis buckets."""

    well_supported: int
    partially_supported: int
    disputed: int
    insufficiently_evidenced: int
    unresolved: int


@dataclass(frozen=True, slots=True)
class DashboardConfidenceCounts:
    """Mechanical count of element-level M5 analysis confidence."""

    high: int
    medium: int
    low: int


@dataclass(frozen=True, slots=True)
class DashboardElement:
    """Read-only projection of one frozen legal-analysis element."""

    element_id: str
    element_name: str
    legal_question: str
    current_evidential_position: str
    provisional_status: str
    analysis_confidence: str
    established_matters: tuple[DashboardStatement, ...]
    supported_matters: tuple[DashboardStatement, ...]
    not_supported_matters: tuple[DashboardStatement, ...]
    source_assertions: tuple[DashboardStatement, ...]
    adverse_material: tuple[DashboardStatement, ...]
    corroborative_material: tuple[DashboardStatement, ...]
    contextual_material: tuple[DashboardStatement, ...]
    conflicting_material: tuple[DashboardStatement, ...]
    disputed_matters: tuple[DashboardDispute, ...]
    legal_significance: str
    limitations: tuple[str, ...]
    unresolved_matters: tuple[str, ...]
    evidential_gaps: tuple[DashboardGap, ...]
    provisional_analysis: str
    evidence_counts: DashboardEvidenceCounts
    supporting_evidence_keys: tuple[str, ...] = ()
    adverse_evidence_keys: tuple[str, ...] = ()
    corroborative_evidence_keys: tuple[str, ...] = ()
    neutral_evidence_keys: tuple[str, ...] = ()
    conflicting_evidence_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DashboardIssue:
    """Read-only dashboard projection for one frozen governed legal issue."""

    issue_analysis_id: str
    issue_definition_id: str
    issue_definition_version: str
    issue_name: str
    original_user_question: str
    issue_summary: str
    synthesis_counts: DashboardSynthesisCounts
    confidence_counts: DashboardConfidenceCounts
    evidence_counts: DashboardEvidenceCounts
    evidential_gap_count: int
    unresolved_matter_count: int
    overall_limitations: tuple[str, ...]
    elements: tuple[DashboardElement, ...]


@dataclass(frozen=True, slots=True)
class LegalIssueDashboard:
    """Exact case-bound dashboard snapshot derived from one activated authority."""

    schema_version: str
    case_id: str
    authority_id: str
    activation_id: str
    issues: tuple[DashboardIssue, ...]


def _text(value: Any, *, field_name: str) -> str:
    raw = getattr(value, "value", value)
    if not isinstance(raw, str):
        raise LegalIssueDashboardError(f"{field_name} must be textual.")
    return raw


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    if not isinstance(raw, str):
        raise LegalIssueDashboardError("Optional dashboard text must be textual.")
    return raw


def _statements(values: Iterable[Any]) -> tuple[DashboardStatement, ...]:
    result: list[DashboardStatement] = []
    for value in values:
        result.append(
            DashboardStatement(
                text=_text(value.text, field_name="statement.text"),
                evidence_keys=tuple(
                    _text(item, field_name="statement.evidence_key")
                    for item in value.evidence_keys
                ),
                citations=tuple(
                    _text(item, field_name="statement.citation")
                    for item in value.citations
                ),
            )
        )
    return tuple(result)


def _gaps(values: Iterable[Any]) -> tuple[DashboardGap, ...]:
    result: list[DashboardGap] = []
    for value in values:
        result.append(
            DashboardGap(
                gap_id=_text(value.gap_id, field_name="gap_id"),
                description=_text(value.description, field_name="gap.description"),
                related_element_id=_text(
                    value.related_element_id,
                    field_name="gap.related_element_id",
                ),
                materiality=_text(value.materiality, field_name="gap.materiality"),
                reason=_text(value.reason, field_name="gap.reason"),
                suggested_evidence_target=_optional_text(
                    value.suggested_evidence_target
                ),
            )
        )
    return tuple(result)


def _disputes(values: Iterable[Any]) -> tuple[DashboardDispute, ...]:
    result: list[DashboardDispute] = []
    for value in values:
        result.append(
            DashboardDispute(
                disputed_matter_id=_text(
                    value.disputed_matter_id,
                    field_name="disputed_matter_id",
                ),
                proposition=_text(value.proposition, field_name="dispute.proposition"),
                claimant_position=_optional_text(value.claimant_position),
                respondent_position=_optional_text(value.respondent_position),
            )
        )
    return tuple(result)


def _matrix_role_keys(matrix_element: Any) -> dict[str, tuple[str, ...]]:
    buckets: dict[str, tuple[str, ...]] = {}
    for role in _ALLOWED_ROLES:
        field_name = f"{role}_evidence_keys"
        values = tuple(
            _text(item, field_name=f"{field_name}.item")
            for item in getattr(matrix_element, field_name)
        )
        if len(values) != len(set(values)):
            raise LegalIssueDashboardError(
                f"Duplicate {role} evidence key within frozen Case Matrix element."
            )
        buckets[role] = values
    return buckets


def _evidence_counts_from_buckets(
    buckets: dict[str, Iterable[str]],
) -> DashboardEvidenceCounts:
    unique_by_role = {
        role: frozenset(buckets[role])
        for role in _ALLOWED_ROLES
    }
    distinct_any_role = frozenset(
        key
        for role in _ALLOWED_ROLES
        for key in unique_by_role[role]
    )
    return DashboardEvidenceCounts(
        supporting=len(unique_by_role["supporting"]),
        adverse=len(unique_by_role["adverse"]),
        corroborative=len(unique_by_role["corroborative"]),
        neutral=len(unique_by_role["neutral"]),
        conflicting=len(unique_by_role["conflicting"]),
        distinct_any_role=len(distinct_any_role),
    )


def _issue_evidence_counts(
    matrix_elements: Iterable[Any],
) -> DashboardEvidenceCounts:
    issue_buckets: dict[str, set[str]] = {
        role: set()
        for role in _ALLOWED_ROLES
    }
    for matrix_element in matrix_elements:
        for role, keys in _matrix_role_keys(matrix_element).items():
            issue_buckets[role].update(keys)
    return _evidence_counts_from_buckets(issue_buckets)


def _confidence_counts(elements: Iterable[DashboardElement]) -> DashboardConfidenceCounts:
    counts = {level: 0 for level in _ALLOWED_CONFIDENCE}
    for element in elements:
        if element.analysis_confidence not in counts:
            raise LegalIssueDashboardError(
                "Unsupported M5 analysis confidence in frozen authority: "
                + element.analysis_confidence
            )
        counts[element.analysis_confidence] += 1
    return DashboardConfidenceCounts(**counts)


def _issue_identity(value: Any) -> tuple[str, str, str]:
    return (
        _text(value.issue_definition_id, field_name="issue_definition_id"),
        _text(value.issue_definition_version, field_name="issue_definition_version"),
        _text(value.issue_analysis_id, field_name="issue_analysis_id"),
    )


def _build_issue(result: Any, matrix_issue: Any, *, case_id: str) -> DashboardIssue:
    if _text(result.case_id, field_name="result.case_id") != case_id:
        raise LegalIssueDashboardError("Structured analysis result is cross-case.")

    assessed_analysis = result.assessment_result.assessed_analysis
    if _text(assessed_analysis.case_id, field_name="assessed_analysis.case_id") != case_id:
        raise LegalIssueDashboardError("Assessed analysis is cross-case.")

    result_identity = _issue_identity(result)
    matrix_identity = _issue_identity(matrix_issue)
    if result_identity != matrix_identity:
        raise LegalIssueDashboardError(
            "Structured analysis and Case Matrix issue identities do not match."
        )

    issue_definition_id, issue_definition_version, issue_analysis_id = result_identity
    if _text(
        assessed_analysis.issue_definition_id,
        field_name="assessed_analysis.issue_definition_id",
    ) != issue_definition_id:
        raise LegalIssueDashboardError("Issue-definition identity mismatch.")
    if _text(
        assessed_analysis.issue_definition_version,
        field_name="assessed_analysis.issue_definition_version",
    ) != issue_definition_version:
        raise LegalIssueDashboardError("Issue-definition version mismatch.")

    analysis_elements = tuple(assessed_analysis.elements)
    legal_elements = tuple(result.element_analyses)
    m4_elements = tuple(result.assessment_result.element_assessments)
    matrix_elements = tuple(matrix_issue.element_records)

    analysis_ids = tuple(
        _text(item.element_id, field_name="analysis.element_id")
        for item in analysis_elements
    )
    legal_ids = tuple(
        _text(item.element_id, field_name="legal.element_id")
        for item in legal_elements
    )
    m4_ids = tuple(
        _text(item.element_id, field_name="m4.element_id")
        for item in m4_elements
    )
    matrix_ids = tuple(
        _text(item.element_id, field_name="matrix.element_id")
        for item in matrix_elements
    )
    if (
        analysis_ids != legal_ids
        or legal_ids != m4_ids
        or m4_ids != matrix_ids
    ):
        raise LegalIssueDashboardError(
            "Frozen element order/identity is inconsistent across M3/M4/M5/Case Matrix."
        )
    if len(set(legal_ids)) != len(legal_ids):
        raise LegalIssueDashboardError("Duplicate element identity in frozen issue.")

    elements: list[DashboardElement] = []
    for analysis_element, legal_element, matrix_element in zip(
        analysis_elements,
        legal_elements,
        matrix_elements,
        strict=True,
    ):
        matrix_buckets = _matrix_role_keys(matrix_element)
        elements.append(
            DashboardElement(
                element_id=_text(legal_element.element_id, field_name="element_id"),
                element_name=_text(
                    analysis_element.element_name,
                    field_name="element_name",
                ),
                legal_question=_text(
                    legal_element.legal_question,
                    field_name="legal_question",
                ),
                current_evidential_position=_text(
                    legal_element.current_evidential_position,
                    field_name="current_evidential_position",
                ),
                provisional_status=_text(
                    legal_element.provisional_status,
                    field_name="provisional_status",
                ),
                analysis_confidence=_text(
                    legal_element.analysis_confidence,
                    field_name="analysis_confidence",
                ),
                established_matters=_statements(legal_element.established_matters),
                supported_matters=_statements(legal_element.supported_matters),
                not_supported_matters=_statements(legal_element.not_supported_matters),
                source_assertions=_statements(legal_element.source_assertions),
                adverse_material=_statements(legal_element.adverse_material),
                corroborative_material=_statements(
                    legal_element.corroborative_material
                ),
                contextual_material=_statements(legal_element.contextual_material),
                conflicting_material=_statements(legal_element.conflicting_material),
                disputed_matters=_disputes(legal_element.disputed_matters),
                legal_significance=_text(
                    legal_element.legal_significance,
                    field_name="legal_significance",
                ),
                limitations=tuple(
                    _text(item, field_name="element.limitation")
                    for item in legal_element.limitations
                ),
                unresolved_matters=tuple(
                    _text(item, field_name="element.unresolved_matter")
                    for item in legal_element.unresolved_matters
                ),
                evidential_gaps=_gaps(legal_element.evidential_gaps),
                provisional_analysis=_text(
                    legal_element.provisional_analysis,
                    field_name="provisional_analysis",
                ),
                evidence_counts=_evidence_counts_from_buckets(matrix_buckets),
                supporting_evidence_keys=matrix_buckets["supporting"],
                adverse_evidence_keys=matrix_buckets["adverse"],
                corroborative_evidence_keys=matrix_buckets["corroborative"],
                neutral_evidence_keys=matrix_buckets["neutral"],
                conflicting_evidence_keys=matrix_buckets["conflicting"],
            )
        )

    synthesis = result.issue_synthesis
    projected_elements = tuple(elements)
    synthesis_counts = DashboardSynthesisCounts(
        well_supported=len(tuple(synthesis.well_supported_elements)),
        partially_supported=len(tuple(synthesis.partially_supported_elements)),
        disputed=len(tuple(synthesis.disputed_elements)),
        insufficiently_evidenced=len(
            tuple(synthesis.insufficiently_evidenced_elements)
        ),
        unresolved=len(tuple(synthesis.unresolved_elements)),
    )

    return DashboardIssue(
        issue_analysis_id=issue_analysis_id,
        issue_definition_id=issue_definition_id,
        issue_definition_version=issue_definition_version,
        issue_name=_text(assessed_analysis.issue_name, field_name="issue_name"),
        original_user_question=_text(
            assessed_analysis.user_question,
            field_name="user_question",
        ),
        issue_summary=_text(synthesis.summary, field_name="issue_synthesis.summary"),
        synthesis_counts=synthesis_counts,
        confidence_counts=_confidence_counts(projected_elements),
        evidence_counts=_issue_evidence_counts(matrix_elements),
        evidential_gap_count=sum(
            len(element.evidential_gaps) for element in projected_elements
        ),
        unresolved_matter_count=sum(
            len(element.unresolved_matters) for element in projected_elements
        ),
        overall_limitations=tuple(
            _text(item, field_name="overall_limitation")
            for item in result.overall_limitations
        ),
        elements=projected_elements,
    )


def build_legal_issue_dashboard(
    *,
    active_case_id: str,
    authority: GovernedRuntimeAnalyticalAuthority,
) -> LegalIssueDashboard:
    """Project one already-validated active authority without creating legal meaning."""

    case_id = _text(active_case_id, field_name="active_case_id")
    manifest_case_id = _text(authority.manifest.case_id, field_name="manifest.case_id")
    pointer_case_id = _text(
        authority.active_pointer.case_id,
        field_name="active_pointer.case_id",
    )
    matrices_case_id = _text(
        authority.case_matrices.case_id,
        field_name="case_matrices.case_id",
    )
    if (
        manifest_case_id != case_id
        or pointer_case_id != case_id
        or matrices_case_id != case_id
    ):
        raise LegalIssueDashboardError(
            "Activated authority is not consistently bound to the active case."
        )

    authority_id = _text(authority.manifest.authority_id, field_name="authority_id")
    if _text(
        authority.active_pointer.authority_id,
        field_name="active_pointer.authority_id",
    ) != authority_id:
        raise LegalIssueDashboardError(
            "Active pointer does not identify the loaded governed authority."
        )

    results = tuple(authority.structured_legal_analysis_results)
    matrix_issues = tuple(authority.case_matrices.issue_matrix)
    if not results:
        raise LegalIssueDashboardError(
            "Activated authority contains no structured legal-analysis results."
        )
    if not matrix_issues:
        raise LegalIssueDashboardError(
            "Activated authority contains no frozen Case Matrix issues."
        )

    result_identities = tuple(_issue_identity(result) for result in results)
    matrix_identities = tuple(_issue_identity(issue) for issue in matrix_issues)

    if len(set(result_identities)) != len(result_identities):
        raise LegalIssueDashboardError("Duplicate structured issue identity.")
    if len(set(matrix_identities)) != len(matrix_identities):
        raise LegalIssueDashboardError("Duplicate Case Matrix issue identity.")
    if result_identities != matrix_identities:
        raise LegalIssueDashboardError(
            "Structured analyses and Case Matrix issues differ in identity or order."
        )

    issues = tuple(
        _build_issue(result, matrix_issue, case_id=case_id)
        for result, matrix_issue in zip(results, matrix_issues, strict=True)
    )

    definition_ids = tuple(
        (issue.issue_definition_id, issue.issue_definition_version)
        for issue in issues
    )
    if len(set(definition_ids)) != len(definition_ids):
        raise LegalIssueDashboardError("Duplicate governed issue identity.")

    return LegalIssueDashboard(
        schema_version=DASHBOARD_SCHEMA_VERSION,
        case_id=case_id,
        authority_id=authority_id,
        activation_id=_text(
            authority.active_pointer.activation_id,
            field_name="activation_id",
        ),
        issues=issues,
    )


__all__ = [
    "DASHBOARD_SCHEMA_VERSION",
    "DashboardConfidenceCounts",
    "DashboardDispute",
    "DashboardElement",
    "DashboardEvidenceCounts",
    "DashboardGap",
    "DashboardIssue",
    "DashboardStatement",
    "DashboardSynthesisCounts",
    "LegalIssueDashboard",
    "LegalIssueDashboardError",
    "build_legal_issue_dashboard",
]
