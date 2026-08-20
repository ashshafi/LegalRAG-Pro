"""Immutable Finance F4 comparable-company analytical authority models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final

from finance_calculations import AnalyticalStatus, CalculationClassification, CalculationResult
from finance_domain import Company, FinancialFact, FinancialObservation, FinancialPeriod, Security

COMPARABLE_MEMBER_SCHEMA_VERSION: Final[str] = "finance-comparable-member/1.0"
COMPARABLE_SET_SCHEMA_VERSION: Final[str] = "finance-comparable-set/1.0"
COMPARABLE_CELL_SCHEMA_VERSION: Final[str] = "finance-comparable-cell/1.0"
PEER_SUMMARY_SCHEMA_VERSION: Final[str] = "finance-peer-summary/1.0"
TARGET_POSITION_SCHEMA_VERSION: Final[str] = "finance-target-position/1.0"
COMPARABLE_ANALYSIS_SCHEMA_VERSION: Final[str] = "finance-comparable-analysis/1.0"
COMPARABLE_ANALYSIS_IDENTITY_VERSION: Final[str] = "1.0"

MATRIX_METRICS: Final[tuple[str, ...]] = (
    "REVENUE",
    "REVENUE_GROWTH",
    "EBITDA",
    "EBITDA_MARGIN",
    "ENTERPRISE_VALUE",
    "EV_REVENUE",
    "EV_EBITDA",
    "PE_RATIO",
    "NET_DEBT_EBITDA",
)
SOURCE_FACT_METRICS: Final[tuple[str, ...]] = ("REVENUE", "EBITDA")
DERIVED_MATRIX_METRICS: Final[tuple[str, ...]] = tuple(
    item for item in MATRIX_METRICS if item not in SOURCE_FACT_METRICS
)


class ComparableRole(StrEnum):
    TARGET = "TARGET"
    PEER = "PEER"


class PeerInclusionState(StrEnum):
    INCLUDED = "INCLUDED"
    EXCLUDED = "EXCLUDED"


class CellValueClassification(StrEnum):
    SOURCE_FACT = "SOURCE_FACT"
    DERIVED_METRIC = "DERIVED_METRIC"


class TargetPeerRelationship(StrEnum):
    BELOW_PEER_MEDIAN = "BELOW_PEER_MEDIAN"
    AT_PEER_MEDIAN = "AT_PEER_MEDIAN"
    ABOVE_PEER_MEDIAN = "ABOVE_PEER_MEDIAN"


@dataclass(frozen=True, slots=True)
class ComparableMemberSelection:
    schema_version: str
    company_id: str
    security_id: str
    role: ComparableRole
    inclusion_state: PeerInclusionState
    current_period_id: str
    prior_period_id: str
    exclusion_reason: str | None
    member_id: str


@dataclass(frozen=True, slots=True)
class ComparableSetDefinition:
    schema_version: str
    workspace_id: str
    as_of: datetime
    members: tuple[ComparableMemberSelection, ...]
    definition_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "members", tuple(self.members))


@dataclass(frozen=True, slots=True)
class ComparableMetricCell:
    schema_version: str
    workspace_id: str
    company_id: str
    security_id: str
    metric_code: str
    value_classification: CellValueClassification
    calculation_classification: CalculationClassification | None
    status: AnalyticalStatus
    value: Decimal | None
    currency: str | None
    unit: str | None
    financial_period_id: str | None
    as_of: datetime
    source_fact_id: str | None
    source_result_id: str | None
    input_fact_ids: tuple[str, ...]
    observation_ids: tuple[str, ...]
    note: str | None
    cell_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_fact_ids", tuple(self.input_fact_ids))
        object.__setattr__(self, "observation_ids", tuple(self.observation_ids))


@dataclass(frozen=True, slots=True)
class PeerMetricSummary:
    schema_version: str
    workspace_id: str
    metric_code: str
    status: AnalyticalStatus
    value_classification: CellValueClassification
    calculation_classification: CalculationClassification
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
    summary_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_cell_ids", tuple(self.input_cell_ids))
        object.__setattr__(self, "unavailable_cell_ids", tuple(self.unavailable_cell_ids))


@dataclass(frozen=True, slots=True)
class TargetPeerPosition:
    schema_version: str
    workspace_id: str
    metric_code: str
    status: AnalyticalStatus
    relationship: TargetPeerRelationship | None
    target_cell_id: str
    peer_summary_id: str
    as_of: datetime
    note: str | None
    position_id: str


@dataclass(frozen=True, slots=True)
class ComparableCompanyAnalysis:
    schema_version: str
    identity_version: str
    workspace_id: str
    provider_id: str
    dataset_id: str
    dataset_version: str
    dataset_identity: str
    as_of: datetime
    definition: ComparableSetDefinition
    companies: tuple[Company, ...]
    securities: tuple[Security, ...]
    periods: tuple[FinancialPeriod, ...]
    source_observations: tuple[FinancialObservation, ...]
    source_facts: tuple[FinancialFact, ...]
    calculation_results: tuple[CalculationResult, ...]
    cells: tuple[ComparableMetricCell, ...]
    summaries: tuple[PeerMetricSummary, ...]
    positions: tuple[TargetPeerPosition, ...]
    analysis_id: str

    def __post_init__(self) -> None:
        for name in (
            "companies", "securities", "periods", "source_observations", "source_facts",
            "calculation_results", "cells", "summaries", "positions",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))


__all__ = [
    "COMPARABLE_ANALYSIS_IDENTITY_VERSION",
    "COMPARABLE_ANALYSIS_SCHEMA_VERSION",
    "COMPARABLE_CELL_SCHEMA_VERSION",
    "COMPARABLE_MEMBER_SCHEMA_VERSION",
    "COMPARABLE_SET_SCHEMA_VERSION",
    "DERIVED_MATRIX_METRICS",
    "MATRIX_METRICS",
    "PEER_SUMMARY_SCHEMA_VERSION",
    "SOURCE_FACT_METRICS",
    "TARGET_POSITION_SCHEMA_VERSION",
    "CellValueClassification",
    "ComparableCompanyAnalysis",
    "ComparableMemberSelection",
    "ComparableMetricCell",
    "ComparableRole",
    "ComparableSetDefinition",
    "PeerInclusionState",
    "PeerMetricSummary",
    "TargetPeerPosition",
    "TargetPeerRelationship",
]
