"""Immutable Finance F6 runtime answer-authority models."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from finance_calculations.models import AnalyticalStatus, CalculationClassification
from finance_comps.models import CellValueClassification, ComparableRole, PeerInclusionState, TargetPeerRelationship
from finance_evidence.models import FinanceDocumentEvidenceCoverage, ObservationDocumentBindingClass, ObservationSourceChannel


class FinanceContentClassification(StrEnum):
    SOURCE_FACT = "SOURCE_FACT"
    DERIVED_METRIC = "DERIVED_METRIC"
    MODEL_CALCULATION = "MODEL_CALCULATION"
    ANALYST_INTERPRETATION = "ANALYST_INTERPRETATION"
    AI_GENERATED_COMMENTARY = "AI_GENERATED_COMMENTARY"


class FinanceAnswerMode(StrEnum):
    ANSWER = "ANSWER"
    UNAVAILABLE = "UNAVAILABLE"


class FinanceUnavailableReason(StrEnum):
    OUTSIDE_FROZEN_AUTHORITY = "OUTSIDE_FROZEN_AUTHORITY"
    METRIC_NOT_ESTABLISHED = "METRIC_NOT_ESTABLISHED"
    CALCULATION_NOT_PRESENT = "CALCULATION_NOT_PRESENT"
    ANALYST_INTERPRETATION_NOT_AVAILABLE = "ANALYST_INTERPRETATION_NOT_AVAILABLE"
    QUESTION_AMBIGUOUS = "QUESTION_AMBIGUOUS"


class FinanceClaimType(StrEnum):
    ANALYSIS_AS_OF = "ANALYSIS_AS_OF"
    DATASET_IDENTITY = "DATASET_IDENTITY"
    MEMBER_STATUS = "MEMBER_STATUS"
    CELL_VALUE = "CELL_VALUE"
    CELL_STATUS = "CELL_STATUS"
    PEER_SUMMARY_VALUE = "PEER_SUMMARY_VALUE"
    PEER_SUMMARY_STATUS = "PEER_SUMMARY_STATUS"
    TARGET_PEER_RELATIONSHIP = "TARGET_PEER_RELATIONSHIP"
    CALCULATION_FORMULA = "CALCULATION_FORMULA"
    EVIDENCE_BINDING = "EVIDENCE_BINDING"
    EVIDENCE_COVERAGE = "EVIDENCE_COVERAGE"


class FinanceSummarySelector(StrEnum):
    MEAN = "MEAN"
    MEDIAN = "MEDIAN"
    MINIMUM = "MINIMUM"
    MAXIMUM = "MAXIMUM"


@dataclass(frozen=True, slots=True)
class RuntimeFinanceMember:
    member_id: str
    company_id: str
    company_name: str
    security_id: str
    role: ComparableRole
    inclusion_state: PeerInclusionState
    current_period_id: str
    prior_period_id: str
    exclusion_reason: str | None


@dataclass(frozen=True, slots=True)
class RuntimeFinanceCell:
    cell_id: str
    company_id: str
    company_name: str
    security_id: str
    metric_code: str
    value_classification: CellValueClassification
    calculation_classification: CalculationClassification | None
    status: AnalyticalStatus
    value: Decimal | None
    currency: str | None
    unit: str | None
    financial_period_id: str | None
    financial_period_label: str | None
    as_of: datetime
    source_fact_id: str | None
    source_result_id: str | None
    input_fact_ids: tuple[str, ...]
    observation_ids: tuple[str, ...]
    note: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_fact_ids", tuple(self.input_fact_ids))
        object.__setattr__(self, "observation_ids", tuple(self.observation_ids))


@dataclass(frozen=True, slots=True)
class RuntimeFinancePeerSummary:
    summary_id: str
    metric_code: str
    status: AnalyticalStatus
    selected_peer_count: int
    established_peer_count: int
    currency: str | None
    unit: str | None
    mean: Decimal | None
    median: Decimal | None
    minimum: Decimal | None
    maximum: Decimal | None
    input_cell_ids: tuple[str, ...]
    unavailable_cell_ids: tuple[str, ...]
    as_of: datetime
    note: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_cell_ids", tuple(self.input_cell_ids))
        object.__setattr__(self, "unavailable_cell_ids", tuple(self.unavailable_cell_ids))


@dataclass(frozen=True, slots=True)
class RuntimeFinanceTargetPosition:
    position_id: str
    metric_code: str
    status: AnalyticalStatus
    relationship: TargetPeerRelationship | None
    target_cell_id: str
    peer_summary_id: str
    as_of: datetime
    note: str | None


@dataclass(frozen=True, slots=True)
class RuntimeFinanceCalculation:
    result_id: str
    company_id: str
    company_name: str
    metric_code: str
    status: AnalyticalStatus
    calculation_code: str
    calculation_version: str
    formula: str
    input_fact_ids: tuple[str, ...]
    observation_ids: tuple[str, ...]
    note: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_fact_ids", tuple(self.input_fact_ids))
        object.__setattr__(self, "observation_ids", tuple(self.observation_ids))


@dataclass(frozen=True, slots=True)
class RuntimeFinanceEvidenceBinding:
    evidence_binding_id: str
    observation_id: str
    company_id: str
    company_name: str
    provider: str
    source_id: str
    source_version: str
    publication_at: datetime | None
    source_channel: ObservationSourceChannel
    binding_class: ObservationDocumentBindingClass
    document_snapshot_id: str | None
    page_number: int | None
    bound_text_sha256: str | None
    note: str | None


@dataclass(frozen=True, slots=True)
class RuntimeFinanceAnswerAuthorityContext:
    workspace_id: str
    analysis_id: str
    as_of: datetime
    provider_id: str
    dataset_id: str
    dataset_version: str
    dataset_identity: str
    definition_id: str
    document_evidence_manifest_id: str
    document_evidence_coverage: FinanceDocumentEvidenceCoverage
    members: tuple[RuntimeFinanceMember, ...]
    cells: tuple[RuntimeFinanceCell, ...]
    summaries: tuple[RuntimeFinancePeerSummary, ...]
    positions: tuple[RuntimeFinanceTargetPosition, ...]
    calculations: tuple[RuntimeFinanceCalculation, ...]
    evidence_bindings: tuple[RuntimeFinanceEvidenceBinding, ...]

    def __post_init__(self) -> None:
        for field in ("members", "cells", "summaries", "positions", "calculations", "evidence_bindings"):
            object.__setattr__(self, field, tuple(getattr(self, field)))


@dataclass(frozen=True, slots=True)
class FinanceAnswerStatementBinding:
    claim_id: str
    claim_type: FinanceClaimType
    authority_id: str
    selector: FinanceSummarySelector | None
    statement_text: str
    classifications: tuple[FinanceContentClassification, ...]
    analytical_status: AnalyticalStatus | None
    observation_ids: tuple[str, ...]
    evidence_binding_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "classifications", tuple(self.classifications))
        object.__setattr__(self, "observation_ids", tuple(self.observation_ids))
        object.__setattr__(self, "evidence_binding_ids", tuple(self.evidence_binding_ids))


@dataclass(frozen=True, slots=True)
class ValidatedFinanceAnswer:
    mode: FinanceAnswerMode
    answer: str
    bindings: tuple[FinanceAnswerStatementBinding, ...]
    relied_authority_ids: tuple[str, ...]
    relied_observation_ids: tuple[str, ...]
    relied_evidence_binding_ids: tuple[str, ...]
    unavailable_reason: FinanceUnavailableReason | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", tuple(self.bindings))
        object.__setattr__(self, "relied_authority_ids", tuple(self.relied_authority_ids))
        object.__setattr__(self, "relied_observation_ids", tuple(self.relied_observation_ids))
        object.__setattr__(self, "relied_evidence_binding_ids", tuple(self.relied_evidence_binding_ids))
