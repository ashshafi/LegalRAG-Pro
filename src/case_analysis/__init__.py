"""Sprint 2.4 case-wide analysis package.

Milestone 1 exposes only the immutable case-analysis foundation.  Matrices,
chronology, gaps/conflicts consolidation and case synthesis belong to later
milestones.
"""

from .foundation import build_case_analysis_foundation
from .models import (
    CASE_SYNTHESIS_SCHEMA_VERSION,
    CASE_SYNTHESISER_VERSION,
    CaseAnalysisFoundation,
    SourceAnalysisReference,
    derive_synthesis_id,
)
from .serialization import (
    dumps_case_analysis_foundation,
    loads_case_analysis_foundation,
)
from .validation import validate_foundation, validate_source_analysis_results

__all__ = [
    "CASE_SYNTHESIS_SCHEMA_VERSION",
    "CASE_SYNTHESISER_VERSION",
    "CaseAnalysisFoundation",
    "SourceAnalysisReference",
    "build_case_analysis_foundation",
    "derive_synthesis_id",
    "dumps_case_analysis_foundation",
    "loads_case_analysis_foundation",
    "validate_foundation",
    "validate_source_analysis_results",
]
