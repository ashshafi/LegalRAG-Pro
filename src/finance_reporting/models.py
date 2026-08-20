"""Immutable Finance F7A reporting projection models."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final

from finance_calculations import AnalyticalStatus, CalculationClassification
from finance_comps import (
    CellValueClassification,
    ComparableRole,
    PeerInclusionState,
    TargetPeerRelationship,
)
from finance_evidence import (
    FinanceDocumentEvidenceCoverage,
    ObservationDocumentBindingClass,
    ObservationSourceChannel,
)

FINANCE_REPORT_PROJECTION_SCHEMA_VERSION: Final[str] = "finance-report-projection/1.0"
FINANCE_REPORT_PROJECTOR_VERSION: Final[str] = "1.0"
FINANCE_REPORT_MANIFEST_SCHEMA_VERSION: Final[str] = "finance-report-manifest/1.0"

class FinanceReportLimitationType(StrEnum):
    ANALYTICAL_STATUS = "ANALYTICAL_STATUS"
    EVIDENCE_GAP = "EVIDENCE_GAP"
    EVIDENCE_COVERAGE = "EVIDENCE_COVERAGE"

@dataclass(frozen=True, slots=True)
class FinanceReportHeader:
    workspace_id: str
    analysis_id: str
    as_of: datetime
    provider_id: str
    dataset_id: str
    dataset_version: str
    dataset_identity: str
    definition_id: str
    document_evidence_manifest_id: str

@dataclass(frozen=True, slots=True)
class FinanceReportMember:
    member_id: str
    company_id: str
    company_name: str
    security_id: str
    role: ComparableRole
    inclusion_state: PeerInclusionState
    current_period_id: str
    current_period_label: str
    prior_period_id: str
    prior_period_label: str
    exclusion_reason: str | None

@dataclass(frozen=True, slots=True)
class FinanceReportMetricCell:
    cell_id: str
    company_id: str
    company_name: str
    security_id: str
    metric_code: str
    value_classification: CellValueClassification
    calculation_classification: CalculationClassification | None
    analytical_status: AnalyticalStatus
    value: Decimal | None
    currency: str | None
    unit: str | None
    financial_period_id: str | None
    financial_period_label: str | None
    source_fact_id: str | None
    source_result_id: str | None
    input_fact_ids: tuple[str, ...]
    observation_ids: tuple[str, ...]
    evidence_binding_ids: tuple[str, ...]
    note: str | None
    def __post_init__(self) -> None:
        for field in ("input_fact_ids", "observation_ids", "evidence_binding_ids"):
            object.__setattr__(self, field, tuple(getattr(self, field)))

@dataclass(frozen=True, slots=True)
class FinanceReportPeerSummary:
    summary_id: str
    metric_code: str
    analytical_status: AnalyticalStatus
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
    observation_ids: tuple[str, ...]
    evidence_binding_ids: tuple[str, ...]
    note: str | None
    def __post_init__(self) -> None:
        for field in ("input_cell_ids", "unavailable_cell_ids", "observation_ids", "evidence_binding_ids"):
            object.__setattr__(self, field, tuple(getattr(self, field)))

@dataclass(frozen=True, slots=True)
class FinanceReportTargetPosition:
    position_id: str
    metric_code: str
    analytical_status: AnalyticalStatus
    relationship: TargetPeerRelationship | None
    target_cell_id: str
    peer_summary_id: str
    observation_ids: tuple[str, ...]
    evidence_binding_ids: tuple[str, ...]
    note: str | None
    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_ids", tuple(self.observation_ids))
        object.__setattr__(self, "evidence_binding_ids", tuple(self.evidence_binding_ids))

@dataclass(frozen=True, slots=True)
class FinanceReportCalculation:
    result_id: str
    company_id: str
    company_name: str
    metric_code: str
    analytical_status: AnalyticalStatus
    calculation_classification: CalculationClassification
    calculation_code: str
    calculation_version: str
    formula: str
    input_fact_ids: tuple[str, ...]
    observation_ids: tuple[str, ...]
    evidence_binding_ids: tuple[str, ...]
    note: str | None
    def __post_init__(self) -> None:
        for field in ("input_fact_ids", "observation_ids", "evidence_binding_ids"):
            object.__setattr__(self, field, tuple(getattr(self, field)))

@dataclass(frozen=True, slots=True)
class FinanceReportEvidenceRecord:
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
class FinanceReportLimitation:
    limitation_id: str
    limitation_type: FinanceReportLimitationType
    authority_id: str
    raw_status: str
    note: str | None

@dataclass(frozen=True, slots=True)
class FinanceReportManifestSection:
    section_id: str
    ordered_object_ids: tuple[str, ...]
    def __post_init__(self) -> None:
        object.__setattr__(self, "ordered_object_ids", tuple(self.ordered_object_ids))

@dataclass(frozen=True, slots=True)
class FinanceReportManifest:
    schema_version: str
    manifest_id: str
    report_projection_id: str
    projection_payload_sha256: str
    ordered_section_ids: tuple[str, ...]
    sections: tuple[FinanceReportManifestSection, ...]
    ordered_member_ids: tuple[str, ...]
    ordered_cell_ids: tuple[str, ...]
    ordered_summary_ids: tuple[str, ...]
    ordered_position_ids: tuple[str, ...]
    ordered_calculation_ids: tuple[str, ...]
    ordered_evidence_binding_ids: tuple[str, ...]
    ordered_limitation_ids: tuple[str, ...]
    raw_status_inventory: tuple[tuple[str, int], ...]
    source_channel_inventory: tuple[tuple[str, int], ...]
    binding_class_inventory: tuple[tuple[str, int], ...]
    evidence_coverage: FinanceDocumentEvidenceCoverage
    def __post_init__(self) -> None:
        for field in (
            "ordered_section_ids", "sections", "ordered_member_ids", "ordered_cell_ids",
            "ordered_summary_ids", "ordered_position_ids", "ordered_calculation_ids",
            "ordered_evidence_binding_ids", "ordered_limitation_ids", "raw_status_inventory",
            "source_channel_inventory", "binding_class_inventory",
        ):
            object.__setattr__(self, field, tuple(getattr(self, field)))

@dataclass(frozen=True, slots=True)
class FinanceReportProjection:
    schema_version: str
    projector_version: str
    report_projection_id: str
    source_analysis_id: str
    source_document_evidence_manifest_id: str
    projection_payload_sha256: str
    header: FinanceReportHeader
    members: tuple[FinanceReportMember, ...]
    cells: tuple[FinanceReportMetricCell, ...]
    summaries: tuple[FinanceReportPeerSummary, ...]
    positions: tuple[FinanceReportTargetPosition, ...]
    calculations: tuple[FinanceReportCalculation, ...]
    evidence: tuple[FinanceReportEvidenceRecord, ...]
    limitations: tuple[FinanceReportLimitation, ...]
    manifest: FinanceReportManifest
    def __post_init__(self) -> None:
        for field in ("members", "cells", "summaries", "positions", "calculations", "evidence", "limitations"):
            object.__setattr__(self, field, tuple(getattr(self, field)))

__all__ = [name for name in globals() if name.startswith("Finance") or name.startswith("FINANCE_")]
