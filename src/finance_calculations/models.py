"""Immutable deterministic calculation records for Finance F3."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final

CALCULATION_RESULT_SCHEMA_VERSION: Final[str] = "finance-calculation-result/1.0"
CALCULATION_VERSION: Final[str] = "1.0"


class AnalyticalStatus(StrEnum):
    ESTABLISHED = "ESTABLISHED"
    NOT_ESTABLISHED = "NOT_ESTABLISHED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    DATA_NOT_AVAILABLE = "DATA_NOT_AVAILABLE"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    STALE_DATA = "STALE_DATA"
    ASSUMPTION_REQUIRED = "ASSUMPTION_REQUIRED"


class ValueClassification(StrEnum):
    DERIVED_METRIC = "DERIVED_METRIC"


class CalculationClassification(StrEnum):
    MODEL_CALCULATION = "MODEL_CALCULATION"


@dataclass(frozen=True, slots=True)
class CalculationResult:
    schema_version: str
    workspace_id: str
    company_id: str
    security_id: str | None
    metric_code: str
    classification: ValueClassification
    calculation_classification: CalculationClassification
    status: AnalyticalStatus
    value: Decimal | None
    currency: str | None
    unit: str | None
    financial_period_id: str | None
    as_of: datetime
    calculation_code: str
    calculation_version: str
    formula: str
    input_fact_ids: tuple[str, ...]
    note: str | None
    result_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_fact_ids", tuple(self.input_fact_ids))


__all__ = [
    "AnalyticalStatus",
    "CALCULATION_RESULT_SCHEMA_VERSION",
    "CALCULATION_VERSION",
    "CalculationClassification",
    "CalculationResult",
    "ValueClassification",
]
