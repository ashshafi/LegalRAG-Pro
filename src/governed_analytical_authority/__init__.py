"""Governed analytical-authority persistence, validation and selection infrastructure."""

from .activation import (
    GovernedAnalyticalAuthorityActivationError,
    activate_governed_analytical_authority,
)
from .identity import (
    canonical_sha256,
    derive_governed_analytical_authority_activation_id,
    derive_governed_analytical_authority_id,
)
from .models import (
    GOVERNED_ANALYTICAL_AUTHORITY_ACTIVATION_SCHEMA_VERSION,
    GOVERNED_ANALYTICAL_AUTHORITY_IDENTITY_VERSION,
    GOVERNED_ANALYTICAL_AUTHORITY_MANIFEST_SCHEMA_VERSION,
    GOVERNED_ANALYTICAL_AUTHORITY_POINTER_SCHEMA_VERSION,
    GOVERNED_ANALYTICAL_AUTHORITY_ROOT_NAME,
    GovernedAnalyticalAuthorityActivationAction,
    GovernedAnalyticalAuthorityActivationReceipt,
    GovernedAnalyticalAuthorityActivePointer,
    GovernedAnalyticalAuthorityManifest,
    GovernedRuntimeAnalyticalAuthority,
)
from .provider import (
    GovernedAnalyticalAuthorityProviderError,
    load_active_governed_analytical_authority,
)
from .publication import (
    GovernedAnalyticalAuthorityPublicationError,
    publish_governed_analytical_authority,
)
from .serialization import (
    dumps_governed_analytical_authority_activation_receipt,
    dumps_governed_analytical_authority_active_pointer,
    dumps_governed_analytical_authority_manifest,
    dumps_structured_legal_analysis_results,
    loads_governed_analytical_authority_activation_receipt,
    loads_governed_analytical_authority_active_pointer,
    loads_governed_analytical_authority_manifest,
    loads_structured_legal_analysis_results,
)
from .validation import (
    GovernedAnalyticalAuthorityValidationError,
    build_governed_analytical_authority_manifest,
    validate_governed_analytical_authority_activation_receipt,
    validate_governed_analytical_authority_active_pointer,
    validate_governed_analytical_authority_components,
    validate_governed_analytical_authority_manifest,
)


__all__ = [
    "GOVERNED_ANALYTICAL_AUTHORITY_ACTIVATION_SCHEMA_VERSION",
    "GOVERNED_ANALYTICAL_AUTHORITY_IDENTITY_VERSION",
    "GOVERNED_ANALYTICAL_AUTHORITY_MANIFEST_SCHEMA_VERSION",
    "GOVERNED_ANALYTICAL_AUTHORITY_POINTER_SCHEMA_VERSION",
    "GOVERNED_ANALYTICAL_AUTHORITY_ROOT_NAME",
    "GovernedAnalyticalAuthorityActivationAction",
    "GovernedAnalyticalAuthorityActivationError",
    "GovernedAnalyticalAuthorityActivationReceipt",
    "GovernedAnalyticalAuthorityActivePointer",
    "GovernedAnalyticalAuthorityManifest",
    "GovernedAnalyticalAuthorityProviderError",
    "GovernedAnalyticalAuthorityPublicationError",
    "GovernedAnalyticalAuthorityValidationError",
    "GovernedRuntimeAnalyticalAuthority",
    "activate_governed_analytical_authority",
    "build_governed_analytical_authority_manifest",
    "canonical_sha256",
    "derive_governed_analytical_authority_activation_id",
    "derive_governed_analytical_authority_id",
    "dumps_governed_analytical_authority_activation_receipt",
    "dumps_governed_analytical_authority_active_pointer",
    "dumps_governed_analytical_authority_manifest",
    "dumps_structured_legal_analysis_results",
    "load_active_governed_analytical_authority",
    "loads_governed_analytical_authority_activation_receipt",
    "loads_governed_analytical_authority_active_pointer",
    "loads_governed_analytical_authority_manifest",
    "loads_structured_legal_analysis_results",
    "publish_governed_analytical_authority",
    "validate_governed_analytical_authority_activation_receipt",
    "validate_governed_analytical_authority_active_pointer",
    "validate_governed_analytical_authority_components",
    "validate_governed_analytical_authority_manifest",
]
