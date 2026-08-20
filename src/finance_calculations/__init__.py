"""Finance F3 governed fact reconciliation and deterministic calculations."""

from .calculations import ebitda_margin, enterprise_value, equity_value, multiple, net_debt, revenue_growth
from .engine import DeterministicCalculationEngine, SUPPORTED_METRICS
from .facts import FactResolution, resolve_financial_fact
from .models import (
    AnalyticalStatus,
    CALCULATION_RESULT_SCHEMA_VERSION,
    CALCULATION_VERSION,
    CalculationClassification,
    CalculationResult,
    ValueClassification,
)
from .serialization import (
    calculation_result_identity_payload_to_dict,
    calculation_result_to_dict,
    dumps_calculation_result,
    loads_calculation_result,
)
from .validation import validate_calculation_result

__all__ = [
    "AnalyticalStatus",
    "CALCULATION_RESULT_SCHEMA_VERSION",
    "CALCULATION_VERSION",
    "CalculationClassification",
    "CalculationResult",
    "DeterministicCalculationEngine",
    "FactResolution",
    "SUPPORTED_METRICS",
    "ValueClassification",
    "calculation_result_identity_payload_to_dict",
    "calculation_result_to_dict",
    "dumps_calculation_result",
    "ebitda_margin",
    "enterprise_value",
    "equity_value",
    "loads_calculation_result",
    "multiple",
    "net_debt",
    "resolve_financial_fact",
    "revenue_growth",
    "validate_calculation_result",
]
