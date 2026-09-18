"""Practice-management matter source integration boundary for LegalRAG Pro."""

from matter_sources.base import MatterSourceConnector, MatterSourceError, MatterSourceUnavailableError
from matter_sources.models import (
    ConnectorCapabilities,
    DocumentObservation,
    ExternalDocument,
    ExternalMatter,
    ExternalParty,
    ProviderIdentity,
    SyncDisposition,
    SyncPlan,
    SyncPlanEntry,
)
from matter_sources.sync import AppliedDocument, MatterSourceSyncError, apply_pdf_sync_plan, build_sync_plan, observations_after_plan

__all__ = [
    "AppliedDocument", "ConnectorCapabilities", "DocumentObservation", "ExternalDocument",
    "ExternalMatter", "ExternalParty", "MatterSourceConnector", "MatterSourceError",
    "MatterSourceSyncError", "MatterSourceUnavailableError", "ProviderIdentity",
    "SyncDisposition", "SyncPlan", "SyncPlanEntry", "apply_pdf_sync_plan",
    "build_sync_plan", "observations_after_plan",
]
