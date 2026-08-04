"""M5.1 deterministic renderer-neutral case-report projection."""

from .models import (
    REPORT_MANIFEST_BUILDER_VERSION,
    REPORT_MANIFEST_SCHEMA_VERSION,
    REPORT_PROJECTION_SCHEMA_VERSION,
    REPORT_PROJECTOR_VERSION,
    CaseReportMetadata,
    CaseReportProjection,
    ReportManifest,
)
from .projection import build_case_report_projection
from .serialization import (
    case_report_projection_from_dict,
    case_report_projection_to_dict,
    dumps_case_report_projection,
    loads_case_report_projection,
)
from .validation import validate_case_report_projection

__all__ = [
    "REPORT_MANIFEST_BUILDER_VERSION",
    "REPORT_MANIFEST_SCHEMA_VERSION",
    "REPORT_PROJECTION_SCHEMA_VERSION",
    "REPORT_PROJECTOR_VERSION",
    "CaseReportMetadata",
    "CaseReportProjection",
    "ReportManifest",
    "build_case_report_projection",
    "case_report_projection_from_dict",
    "case_report_projection_to_dict",
    "dumps_case_report_projection",
    "loads_case_report_projection",
    "validate_case_report_projection",
]
