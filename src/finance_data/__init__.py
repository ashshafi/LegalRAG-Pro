"""Finance F2 frozen observation-provider foundation."""

from .frozen_demo import (
    FROZEN_DEMO_DATASET_ID,
    FROZEN_DEMO_DATASET_VERSION,
    FROZEN_DEMO_PROVIDER_ID,
    FrozenDemoProvider,
)
from .provider import FinanceDataLookupError, FinanceDataProviderError, FinancialDataProvider
from .serialization import (
    FROZEN_DATASET_SCHEMA_VERSION,
    dataset_identity_payload_to_dict,
    derive_dataset_identity,
    dumps_dataset_document,
    loads_dataset_document,
)
from .validation import ValidatedFrozenDataset, validate_frozen_dataset_document

__all__ = [
    "FROZEN_DATASET_SCHEMA_VERSION",
    "FROZEN_DEMO_DATASET_ID",
    "FROZEN_DEMO_DATASET_VERSION",
    "FROZEN_DEMO_PROVIDER_ID",
    "FinanceDataLookupError",
    "FinanceDataProviderError",
    "FinancialDataProvider",
    "FrozenDemoProvider",
    "ValidatedFrozenDataset",
    "dataset_identity_payload_to_dict",
    "derive_dataset_identity",
    "dumps_dataset_document",
    "loads_dataset_document",
    "validate_frozen_dataset_document",
]
