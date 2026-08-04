"""Durable models for Sprint 2.4 Milestone 4.1 whole-case synthesis.

M4.1 defines only the deterministic language used by later synthesis.  It does
not derive findings, rebuild upstream analysis, retrieve evidence, or invoke an
LLM.  Every durable object is an immutable projection over frozen M1/M2/M3
state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, TypeAlias
from uuid import UUID

from legal_analysis.enums import Confidence, Materiality

WHOLE_CASE_SYNTHESIS_SCHEMA_VERSION: Final[str] = "whole-case-synthesis-schema/1.0"
WHOLE_CASE_SYNTHESISER_VERSION: Final[str] = "whole-case-synthesiser/1.0"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _required(value: str, *, field_name: str) -> str:
    cleaned = str(value).strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty.")
    return cleaned


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _uuid(value: str, *, field_name: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"{field_name} must be a valid UUID string.") from exc


def _sha256(value: str, *, field_name: str) -> str:
    cleaned = str(value).strip()
    if not _SHA256_RE.fullmatch(cleaned):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest.")
    return cleaned


def _unique_strings(
    values: tuple[str, ...],
    *,
    field_name: str,
    sort: bool = False,
    uuid_values: bool = False,
) -> tuple[str, ...]:
    if uuid_values:
        cleaned = tuple(_uuid(item, field_name=field_name) for item in values)
    else:
        cleaned = tuple(str(item).strip() for item in values if str(item).strip())
    if len(cleaned) != len(set(cleaned)):
        raise ValueError(f"{field_name} must contain unique values.")
    if sort:
        return tuple(sorted(cleaned))
    return cleaned


def _unique_enum_values(values, *, field_name: str):
    values = tuple(values)
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must contain unique values.")
    return tuple(sorted(values, key=lambda item: item.value))


class FindingType(StrEnum):
    SUPPORTING_FEATURE = "supporting_feature"
    LIMITING_FEATURE = "limiting_feature"
    CROSS_ISSUE_FEATURE = "cross_issue_feature"


class AnalyticalBasis(StrEnum):
    ESTABLISHED_PROPOSITION = "established_proposition"
    SUPPORTED_PROPOSITION = "supported_proposition"
    MULTIPLE_SUPPORTING_PROPOSITIONS = "multiple_supporting_propositions"
    CORROBORATED_EVIDENCE = "corroborated_evidence"
    REQUIRED_ELEMENT_COVERAGE = "required_element_coverage"
    CROSS_ELEMENT_COVERAGE = "cross_element_coverage"
    CROSS_ISSUE_COVERAGE = "cross_issue_coverage"
    TEMPORAL_CONSISTENCY = "temporal_consistency"
    ADVERSE_EVIDENCE = "adverse_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    DISPUTED_PROPOSITION = "disputed_proposition"
    UNRESOLVED_PROPOSITION = "unresolved_proposition"
    UNRESOLVED_REQUIRED_ELEMENT = "unresolved_required_element"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    LOW_CONFIDENCE_SUPPORT = "low_confidence_support"
    MATERIAL_EVIDENCE_GAP = "material_evidence_gap"
    TIMING_UNCERTAINTY = "timing_uncertainty"
    SOURCE_POSITION_CONFLICT = "source_position_conflict"
    DEPENDENCY_ON_SINGLE_EVIDENCE_SOURCE = "dependency_on_single_evidence_source"
    DEPENDENCY_ON_QUALIFIED_ASSERTION = "dependency_on_qualified_assertion"


class FindingScope(StrEnum):
    ELEMENT = "element"
    ISSUE = "issue"
    CROSS_ISSUE = "cross_issue"
    CASE = "case"


class FindingStatus(StrEnum):
    ESTABLISHED_BY_FROZEN_STATE = "established_by_frozen_state"
    SUPPORTED_BY_FROZEN_STATE = "supported_by_frozen_state"
    DISPUTED_IN_FROZEN_STATE = "disputed_in_frozen_state"
    UNRESOLVED_IN_FROZEN_STATE = "unresolved_in_frozen_state"


class IssuePositionStatus(StrEnum):
    WELL_SUPPORTED = "well_supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    MATERIALLY_DISPUTED = "materially_disputed"
    EVIDENCE_INCOMPLETE = "evidence_incomplete"
    UNRESOLVED = "unresolved"


class GapType(StrEnum):
    MISSING_EVIDENCE = "missing_evidence"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNRESOLVED_PROPOSITION = "unresolved_proposition"
    UNRESOLVED_REQUIRED_ELEMENT = "unresolved_required_element"
    MISSING_TEMPORAL_SUPPORT = "missing_temporal_support"
    MISSING_CORROBORATION = "missing_corroboration"


class ConflictType(StrEnum):
    FACTUAL_CONFLICT = "factual_conflict"
    TIMING_CONFLICT = "timing_conflict"
    SOURCE_POSITION_CONFLICT = "source_position_conflict"


class RiskType(StrEnum):
    EVIDENCE_RISK = "evidence_risk"
    CONFLICT_RISK = "conflict_risk"
    TIMING_RISK = "timing_risk"
    ELEMENT_COVERAGE_RISK = "element_coverage_risk"
    CROSS_ISSUE_DEPENDENCY_RISK = "cross_issue_dependency_risk"


class PriorityLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PriorityBasis(StrEnum):
    REQUIRED_ELEMENT = "required_element"
    MATERIAL_CONFLICT = "material_conflict"
    MATERIAL_GAP = "material_gap"
    TIMING_DEPENDENCY = "timing_dependency"
    CROSS_ISSUE_DEPENDENCY = "cross_issue_dependency"


class OverallState(StrEnum):
    WELL_DEVELOPED = "well_developed"
    PARTIALLY_DEVELOPED = "partially_developed"
    EVIDENCE_INCOMPLETE = "evidence_incomplete"
    MATERIALLY_DISPUTED = "materially_disputed"


class SynthesisProvenanceType(StrEnum):
    ISSUE = "issue"
    ELEMENT = "element"
    EVIDENCE_USE = "evidence_use"
    PROPOSITION = "proposition"
    EVENT = "event"
    EVENT_ASSERTION = "event_assertion"
    EVIDENTIAL_GAP = "evidential_gap"
    DISPUTED_MATTER = "disputed_matter"


@dataclass(frozen=True, slots=True)
class SynthesisSourceLineage:
    case_id: str
    foundation_synthesis_id: str
    foundation_schema_version: str
    foundation_synthesiser_version: str
    matrices_schema_version: str
    matrices_builder_version: str
    source_matrices_sha256: str
    chronology_schema_version: str
    chronology_builder_version: str
    source_chronology_sha256: str
    source_analysis_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _uuid(self.case_id, field_name="case_id"))
        object.__setattr__(
            self,
            "foundation_synthesis_id",
            _uuid(self.foundation_synthesis_id, field_name="foundation_synthesis_id"),
        )
        for field_name in (
            "foundation_schema_version",
            "foundation_synthesiser_version",
            "matrices_schema_version",
            "matrices_builder_version",
            "chronology_schema_version",
            "chronology_builder_version",
        ):
            object.__setattr__(
                self,
                field_name,
                _required(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(
            self,
            "source_matrices_sha256",
            _sha256(self.source_matrices_sha256, field_name="source_matrices_sha256"),
        )
        object.__setattr__(
            self,
            "source_chronology_sha256",
            _sha256(self.source_chronology_sha256, field_name="source_chronology_sha256"),
        )
        source_ids = _unique_strings(
            tuple(self.source_analysis_ids),
            field_name="source_analysis_ids",
            sort=True,
            uuid_values=True,
        )
        if not source_ids:
            raise ValueError("source_analysis_ids must not be empty.")
        object.__setattr__(self, "source_analysis_ids", source_ids)


@dataclass(frozen=True, slots=True)
class IssueRef:
    issue_analysis_id: str
    issue_definition_id: str
    issue_definition_version: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "issue_analysis_id",
            _uuid(self.issue_analysis_id, field_name="issue_analysis_id"),
        )
        object.__setattr__(
            self,
            "issue_definition_id",
            _required(self.issue_definition_id, field_name="issue_definition_id"),
        )
        object.__setattr__(
            self,
            "issue_definition_version",
            _required(self.issue_definition_version, field_name="issue_definition_version"),
        )


@dataclass(frozen=True, slots=True)
class ElementRef:
    issue_analysis_id: str
    element_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "issue_analysis_id",
            _uuid(self.issue_analysis_id, field_name="issue_analysis_id"),
        )
        object.__setattr__(self, "element_id", _required(self.element_id, field_name="element_id"))


@dataclass(frozen=True, slots=True)
class EvidenceUseRef:
    issue_analysis_id: str
    element_id: str
    evidence_key: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "issue_analysis_id",
            _uuid(self.issue_analysis_id, field_name="issue_analysis_id"),
        )
        object.__setattr__(self, "element_id", _required(self.element_id, field_name="element_id"))
        object.__setattr__(
            self,
            "evidence_key",
            _required(self.evidence_key, field_name="evidence_key"),
        )

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.issue_analysis_id, self.element_id, self.evidence_key)


@dataclass(frozen=True, slots=True)
class PropositionRef:
    evidence_use_ref: EvidenceUseRef
    source_proposition_index: int

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_use_ref, EvidenceUseRef):
            raise ValueError("evidence_use_ref must be an EvidenceUseRef.")
        if self.source_proposition_index < 0:
            raise ValueError("source_proposition_index must be zero or greater.")


@dataclass(frozen=True, slots=True)
class EventRef:
    event_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _uuid(self.event_id, field_name="event_id"))


@dataclass(frozen=True, slots=True)
class EventAssertionRef:
    event_id: str
    assertion_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _uuid(self.event_id, field_name="event_id"))
        object.__setattr__(
            self,
            "assertion_id",
            _uuid(self.assertion_id, field_name="assertion_id"),
        )


@dataclass(frozen=True, slots=True)
class EvidentialGapRef:
    issue_analysis_id: str
    element_id: str
    gap_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "issue_analysis_id",
            _uuid(self.issue_analysis_id, field_name="issue_analysis_id"),
        )
        object.__setattr__(self, "element_id", _required(self.element_id, field_name="element_id"))
        object.__setattr__(self, "gap_id", _uuid(self.gap_id, field_name="gap_id"))


@dataclass(frozen=True, slots=True)
class DisputedMatterRef:
    issue_analysis_id: str
    element_id: str
    disputed_matter_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "issue_analysis_id",
            _uuid(self.issue_analysis_id, field_name="issue_analysis_id"),
        )
        object.__setattr__(self, "element_id", _required(self.element_id, field_name="element_id"))
        object.__setattr__(
            self,
            "disputed_matter_id",
            _uuid(self.disputed_matter_id, field_name="disputed_matter_id"),
        )


ProvenanceTarget: TypeAlias = (
    IssueRef
    | ElementRef
    | EvidenceUseRef
    | PropositionRef
    | EventRef
    | EventAssertionRef
    | EvidentialGapRef
    | DisputedMatterRef
)


def provenance_type_for(target: ProvenanceTarget) -> SynthesisProvenanceType:
    if isinstance(target, IssueRef):
        return SynthesisProvenanceType.ISSUE
    if isinstance(target, ElementRef):
        return SynthesisProvenanceType.ELEMENT
    if isinstance(target, EvidenceUseRef):
        return SynthesisProvenanceType.EVIDENCE_USE
    if isinstance(target, PropositionRef):
        return SynthesisProvenanceType.PROPOSITION
    if isinstance(target, EventRef):
        return SynthesisProvenanceType.EVENT
    if isinstance(target, EventAssertionRef):
        return SynthesisProvenanceType.EVENT_ASSERTION
    if isinstance(target, EvidentialGapRef):
        return SynthesisProvenanceType.EVIDENTIAL_GAP
    if isinstance(target, DisputedMatterRef):
        return SynthesisProvenanceType.DISPUTED_MATTER
    raise ValueError(f"Unsupported provenance target {type(target)!r}.")


def provenance_sort_key(target: ProvenanceTarget) -> tuple[str, ...]:
    reference_type = provenance_type_for(target).value
    if isinstance(target, IssueRef):
        return (
            reference_type,
            target.issue_analysis_id,
            target.issue_definition_id,
            target.issue_definition_version,
        )
    if isinstance(target, ElementRef):
        return (reference_type, target.issue_analysis_id, target.element_id)
    if isinstance(target, EvidenceUseRef):
        return (reference_type, *target.identity)
    if isinstance(target, PropositionRef):
        return (
            reference_type,
            *target.evidence_use_ref.identity,
            f"{target.source_proposition_index:012d}",
        )
    if isinstance(target, EventRef):
        return (reference_type, target.event_id)
    if isinstance(target, EventAssertionRef):
        return (reference_type, target.event_id, target.assertion_id)
    if isinstance(target, EvidentialGapRef):
        return (reference_type, target.issue_analysis_id, target.element_id, target.gap_id)
    if isinstance(target, DisputedMatterRef):
        return (
            reference_type,
            target.issue_analysis_id,
            target.element_id,
            target.disputed_matter_id,
        )
    raise ValueError(f"Unsupported provenance target {type(target)!r}.")


@dataclass(frozen=True, slots=True)
class SynthesisProvenanceRef:
    target: ProvenanceTarget

    def __post_init__(self) -> None:
        provenance_type_for(self.target)

    @property
    def reference_type(self) -> SynthesisProvenanceType:
        return provenance_type_for(self.target)

    @property
    def sort_key(self) -> tuple[str, ...]:
        return provenance_sort_key(self.target)


def _provenance_tuple(
    values: tuple[SynthesisProvenanceRef, ...],
    *,
    field_name: str,
    allow_empty: bool = False,
) -> tuple[SynthesisProvenanceRef, ...]:
    refs = tuple(values)
    if any(not isinstance(item, SynthesisProvenanceRef) for item in refs):
        raise ValueError(f"{field_name} must contain SynthesisProvenanceRef values.")
    if not allow_empty and not refs:
        raise ValueError(f"{field_name} must not be empty.")
    if len(refs) != len(set(refs)):
        raise ValueError(f"{field_name} must contain unique provenance references.")
    return tuple(sorted(refs, key=lambda item: item.sort_key))


@dataclass(frozen=True, slots=True)
class SynthesisFinding:
    finding_id: str
    finding_type: FindingType
    analytical_bases: tuple[AnalyticalBasis, ...]
    scope: FindingScope
    summary: str
    status: FindingStatus
    confidence: Confidence
    provenance_refs: tuple[SynthesisProvenanceRef, ...]
    related_finding_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "finding_id", _uuid(self.finding_id, field_name="finding_id"))
        if not isinstance(self.finding_type, FindingType):
            raise ValueError("finding_type must be a FindingType.")
        if not isinstance(self.scope, FindingScope):
            raise ValueError("scope must be a FindingScope.")
        if not isinstance(self.status, FindingStatus):
            raise ValueError("status must be a FindingStatus.")
        if not isinstance(self.confidence, Confidence):
            raise ValueError("confidence must be a Confidence.")
        raw_bases = tuple(self.analytical_bases)
        if any(not isinstance(item, AnalyticalBasis) for item in raw_bases):
            raise ValueError("analytical_bases must contain AnalyticalBasis values.")
        bases = _unique_enum_values(raw_bases, field_name="analytical_bases")
        if not bases:
            raise ValueError("analytical_bases must not be empty.")
        object.__setattr__(self, "analytical_bases", bases)
        object.__setattr__(self, "summary", _required(self.summary, field_name="summary"))
        object.__setattr__(
            self,
            "provenance_refs",
            _provenance_tuple(self.provenance_refs, field_name="provenance_refs"),
        )
        object.__setattr__(
            self,
            "related_finding_ids",
            _unique_strings(
                self.related_finding_ids,
                field_name="related_finding_ids",
                sort=True,
                uuid_values=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class MaterialConflict:
    conflict_id: str
    conflict_type: ConflictType
    scope: FindingScope
    subject: str
    side_a_refs: tuple[SynthesisProvenanceRef, ...]
    side_b_refs: tuple[SynthesisProvenanceRef, ...]
    materiality: Materiality
    status: FindingStatus
    related_issue_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "conflict_id", _uuid(self.conflict_id, field_name="conflict_id"))
        if not isinstance(self.conflict_type, ConflictType):
            raise ValueError("conflict_type must be a ConflictType.")
        if not isinstance(self.scope, FindingScope):
            raise ValueError("scope must be a FindingScope.")
        if not isinstance(self.materiality, Materiality):
            raise ValueError("materiality must be a Materiality.")
        if not isinstance(self.status, FindingStatus):
            raise ValueError("status must be a FindingStatus.")
        object.__setattr__(self, "subject", _required(self.subject, field_name="subject"))
        object.__setattr__(
            self,
            "side_a_refs",
            _provenance_tuple(self.side_a_refs, field_name="side_a_refs"),
        )
        object.__setattr__(
            self,
            "side_b_refs",
            _provenance_tuple(self.side_b_refs, field_name="side_b_refs"),
        )
        if set(self.side_a_refs) == set(self.side_b_refs):
            raise ValueError("Conflict sides must not be identical.")
        issue_ids = _unique_strings(
            self.related_issue_ids,
            field_name="related_issue_ids",
            sort=True,
            uuid_values=True,
        )
        if not issue_ids:
            raise ValueError("related_issue_ids must not be empty.")
        object.__setattr__(self, "related_issue_ids", issue_ids)


@dataclass(frozen=True, slots=True)
class EvidenceGap:
    gap_id: str
    gap_type: GapType
    scope: FindingScope
    issue_analysis_id: str
    issue_definition_id: str
    issue_definition_version: str
    description: str
    materiality: Materiality
    unresolved_question: str
    provenance_refs: tuple[SynthesisProvenanceRef, ...]
    element_id: str | None = None
    related_finding_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "gap_id", _uuid(self.gap_id, field_name="gap_id"))
        if not isinstance(self.gap_type, GapType):
            raise ValueError("gap_type must be a GapType.")
        if not isinstance(self.scope, FindingScope):
            raise ValueError("scope must be a FindingScope.")
        if not isinstance(self.materiality, Materiality):
            raise ValueError("materiality must be a Materiality.")
        object.__setattr__(
            self,
            "issue_analysis_id",
            _uuid(self.issue_analysis_id, field_name="issue_analysis_id"),
        )
        object.__setattr__(
            self,
            "issue_definition_id",
            _required(self.issue_definition_id, field_name="issue_definition_id"),
        )
        object.__setattr__(
            self,
            "issue_definition_version",
            _required(self.issue_definition_version, field_name="issue_definition_version"),
        )
        object.__setattr__(self, "element_id", _optional(self.element_id))
        object.__setattr__(self, "description", _required(self.description, field_name="description"))
        object.__setattr__(
            self,
            "unresolved_question",
            _required(self.unresolved_question, field_name="unresolved_question"),
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _provenance_tuple(self.provenance_refs, field_name="provenance_refs"),
        )
        object.__setattr__(
            self,
            "related_finding_ids",
            _unique_strings(
                self.related_finding_ids,
                field_name="related_finding_ids",
                sort=True,
                uuid_values=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class RiskArea:
    risk_id: str
    risk_type: RiskType
    scope: FindingScope
    materiality: Materiality
    description: str
    basis_finding_ids: tuple[str, ...] = ()
    conflict_ids: tuple[str, ...] = ()
    gap_ids: tuple[str, ...] = ()
    provenance_refs: tuple[SynthesisProvenanceRef, ...] = ()
    affected_issue_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "risk_id", _uuid(self.risk_id, field_name="risk_id"))
        if not isinstance(self.risk_type, RiskType):
            raise ValueError("risk_type must be a RiskType.")
        if not isinstance(self.scope, FindingScope):
            raise ValueError("scope must be a FindingScope.")
        if not isinstance(self.materiality, Materiality):
            raise ValueError("materiality must be a Materiality.")
        object.__setattr__(self, "description", _required(self.description, field_name="description"))
        for field_name in ("basis_finding_ids", "conflict_ids", "gap_ids"):
            object.__setattr__(
                self,
                field_name,
                _unique_strings(
                    tuple(getattr(self, field_name)),
                    field_name=field_name,
                    sort=True,
                    uuid_values=True,
                ),
            )
        object.__setattr__(
            self,
            "provenance_refs",
            _provenance_tuple(
                self.provenance_refs,
                field_name="provenance_refs",
                allow_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "affected_issue_ids",
            _unique_strings(
                self.affected_issue_ids,
                field_name="affected_issue_ids",
                sort=True,
                uuid_values=True,
            ),
        )
        if not (
            self.basis_finding_ids
            or self.conflict_ids
            or self.gap_ids
            or self.provenance_refs
        ):
            raise ValueError("RiskArea must retain a machine-resolvable analytical basis.")


@dataclass(frozen=True, slots=True)
class PriorityQuestion:
    question_id: str
    question: str
    priority: PriorityLevel
    basis_type: PriorityBasis
    affected_issue_ids: tuple[str, ...]
    affected_element_ids: tuple[str, ...] = ()
    finding_ids: tuple[str, ...] = ()
    gap_ids: tuple[str, ...] = ()
    conflict_ids: tuple[str, ...] = ()
    provenance_refs: tuple[SynthesisProvenanceRef, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "question_id", _uuid(self.question_id, field_name="question_id"))
        object.__setattr__(self, "question", _required(self.question, field_name="question"))
        if not isinstance(self.priority, PriorityLevel):
            raise ValueError("priority must be a PriorityLevel.")
        if not isinstance(self.basis_type, PriorityBasis):
            raise ValueError("basis_type must be a PriorityBasis.")
        object.__setattr__(
            self,
            "affected_issue_ids",
            _unique_strings(
                self.affected_issue_ids,
                field_name="affected_issue_ids",
                sort=True,
                uuid_values=True,
            ),
        )
        if not self.affected_issue_ids:
            raise ValueError("affected_issue_ids must not be empty.")
        object.__setattr__(
            self,
            "affected_element_ids",
            _unique_strings(
                self.affected_element_ids,
                field_name="affected_element_ids",
                sort=True,
            ),
        )
        for field_name in ("finding_ids", "gap_ids", "conflict_ids"):
            object.__setattr__(
                self,
                field_name,
                _unique_strings(
                    tuple(getattr(self, field_name)),
                    field_name=field_name,
                    sort=True,
                    uuid_values=True,
                ),
            )
        object.__setattr__(
            self,
            "provenance_refs",
            _provenance_tuple(
                self.provenance_refs,
                field_name="provenance_refs",
                allow_empty=True,
            ),
        )
        if not (self.finding_ids or self.gap_ids or self.conflict_ids or self.provenance_refs):
            raise ValueError("PriorityQuestion must retain a machine-resolvable analytical basis.")


@dataclass(frozen=True, slots=True)
class IssuePosition:
    issue_definition_id: str
    issue_definition_version: str
    issue_analysis_id: str
    issue_name: str
    position_status: IssuePositionStatus
    basis_refs: tuple[SynthesisProvenanceRef, ...]
    confidence: Confidence
    material_finding_ids: tuple[str, ...] = ()
    conflict_ids: tuple[str, ...] = ()
    gap_ids: tuple[str, ...] = ()
    risk_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "issue_analysis_id",
            _uuid(self.issue_analysis_id, field_name="issue_analysis_id"),
        )
        for field_name in ("issue_definition_id", "issue_definition_version", "issue_name"):
            object.__setattr__(
                self,
                field_name,
                _required(getattr(self, field_name), field_name=field_name),
            )
        if not isinstance(self.position_status, IssuePositionStatus):
            raise ValueError("position_status must be an IssuePositionStatus.")
        if not isinstance(self.confidence, Confidence):
            raise ValueError("confidence must be a Confidence.")
        object.__setattr__(
            self,
            "basis_refs",
            _provenance_tuple(self.basis_refs, field_name="basis_refs"),
        )
        for field_name in ("material_finding_ids", "conflict_ids", "gap_ids", "risk_ids"):
            object.__setattr__(
                self,
                field_name,
                _unique_strings(
                    tuple(getattr(self, field_name)),
                    field_name=field_name,
                    sort=True,
                    uuid_values=True,
                ),
            )


@dataclass(frozen=True, slots=True)
class CaseSynthesis:
    case_id: str
    synthesis_id: str
    source_lineage: SynthesisSourceLineage
    issue_positions: tuple[IssuePosition, ...]
    findings: tuple[SynthesisFinding, ...] = ()
    conflicts: tuple[MaterialConflict, ...] = ()
    gaps: tuple[EvidenceGap, ...] = ()
    risks: tuple[RiskArea, ...] = ()
    priority_questions: tuple[PriorityQuestion, ...] = ()
    overall_state: OverallState = OverallState.PARTIALLY_DEVELOPED
    schema_version: str = WHOLE_CASE_SYNTHESIS_SCHEMA_VERSION
    synthesiser_version: str = WHOLE_CASE_SYNTHESISER_VERSION

    def __post_init__(self) -> None:
        case_id = _uuid(self.case_id, field_name="case_id")
        object.__setattr__(self, "case_id", case_id)
        object.__setattr__(self, "synthesis_id", _uuid(self.synthesis_id, field_name="synthesis_id"))
        if self.schema_version != WHOLE_CASE_SYNTHESIS_SCHEMA_VERSION:
            raise ValueError(f"Unsupported whole-case synthesis schema {self.schema_version!r}.")
        if self.synthesiser_version != WHOLE_CASE_SYNTHESISER_VERSION:
            raise ValueError(f"Unsupported whole-case synthesiser {self.synthesiser_version!r}.")
        if not isinstance(self.source_lineage, SynthesisSourceLineage):
            raise ValueError("source_lineage must be a SynthesisSourceLineage.")
        if self.source_lineage.case_id != case_id:
            raise ValueError("CaseSynthesis.case_id must match source_lineage.case_id.")
        if not isinstance(self.overall_state, OverallState):
            raise ValueError("overall_state must be an OverallState.")

        issue_positions = tuple(
            sorted(
                self.issue_positions,
                key=lambda item: (
                    item.issue_definition_id,
                    item.issue_definition_version,
                    item.issue_analysis_id,
                ),
            )
        )
        if not issue_positions:
            raise ValueError("CaseSynthesis.issue_positions must not be empty.")
        if len({item.issue_analysis_id for item in issue_positions}) != len(issue_positions):
            raise ValueError("CaseSynthesis must contain one IssuePosition per issue_analysis_id.")
        object.__setattr__(self, "issue_positions", issue_positions)

        findings = tuple(sorted(self.findings, key=lambda item: (item.scope.value, item.finding_type.value, item.finding_id)))
        conflicts = tuple(sorted(self.conflicts, key=lambda item: (item.conflict_type.value, item.conflict_id)))
        gaps = tuple(sorted(self.gaps, key=lambda item: (-_materiality_rank(item.materiality), item.issue_definition_id, item.element_id or "", item.gap_id)))
        risks = tuple(sorted(self.risks, key=lambda item: (-_materiality_rank(item.materiality), item.risk_type.value, item.risk_id)))
        questions = tuple(sorted(self.priority_questions, key=lambda item: (-_priority_rank(item.priority), item.basis_type.value, item.question_id)))

        for field_name, values, id_name in (
            ("findings", findings, "finding_id"),
            ("conflicts", conflicts, "conflict_id"),
            ("gaps", gaps, "gap_id"),
            ("risks", risks, "risk_id"),
            ("priority_questions", questions, "question_id"),
        ):
            ids = tuple(getattr(item, id_name) for item in values)
            if len(ids) != len(set(ids)):
                raise ValueError(f"CaseSynthesis.{field_name} contains duplicate identities.")
            object.__setattr__(self, field_name, values)


def _materiality_rank(value: Materiality) -> int:
    return {Materiality.LOW: 0, Materiality.MEDIUM: 1, Materiality.HIGH: 2}[value]


def _priority_rank(value: PriorityLevel) -> int:
    return {PriorityLevel.LOW: 0, PriorityLevel.MEDIUM: 1, PriorityLevel.HIGH: 2}[value]


__all__ = [
    "WHOLE_CASE_SYNTHESIS_SCHEMA_VERSION",
    "WHOLE_CASE_SYNTHESISER_VERSION",
    "AnalyticalBasis",
    "CaseSynthesis",
    "ConflictType",
    "DisputedMatterRef",
    "ElementRef",
    "EvidenceGap",
    "EvidenceUseRef",
    "EventAssertionRef",
    "EventRef",
    "EvidentialGapRef",
    "FindingScope",
    "FindingStatus",
    "FindingType",
    "GapType",
    "IssuePosition",
    "IssuePositionStatus",
    "IssueRef",
    "MaterialConflict",
    "OverallState",
    "PriorityBasis",
    "PriorityLevel",
    "PriorityQuestion",
    "PropositionRef",
    "ProvenanceTarget",
    "RiskArea",
    "RiskType",
    "SynthesisFinding",
    "SynthesisProvenanceRef",
    "SynthesisProvenanceType",
    "SynthesisSourceLineage",
    "provenance_sort_key",
    "provenance_type_for",
]
