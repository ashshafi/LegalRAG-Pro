"""Fail-closed approval policy for outbound AI processing in LegalRAG Pro.

This module does not assert that a provider is regulatorily compliant.  It
requires LegalRAG deployment to bind each outbound AI call to an explicitly
approved provider/data-use profile whose underlying contractual and technical
evidence is maintained outside the repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import os
from typing import Mapping

AI_PROVIDER_POLICY_SCHEMA_VERSION = "legalrag-ai-provider-policy/1.0"
_APPROVAL_TRUE = "true"
_TRAINING_DISABLED = "disabled"
_SUPPORTED_PROVIDER = "openai"


class AIProviderPolicyError(RuntimeError):
    """Raised when outbound AI processing is not explicitly authorised."""


class AIDataClassification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CLIENT_CONFIDENTIAL = "client_confidential"
    PRIVILEGED = "privileged"


class AIProcessingPurpose(str, Enum):
    CONTROLLED_ANALYSIS = "controlled_analysis"
    DERIVED_TRANSCRIPTION_EMBEDDING = "derived_transcription_embedding"
    FOLLOW_UP_REWRITE = "follow_up_rewrite"
    DOCUMENT_EMBEDDING = "document_embedding"
    LEGAL_ANSWER = "legal_answer"
    QUERY_EXPANSION = "query_expansion"
    RETRIEVAL_EMBEDDING = "retrieval_embedding"
    SOURCE_EVIDENCE_EMBEDDING = "source_evidence_embedding"


@dataclass(frozen=True, slots=True)
class ApprovedAIProviderProfile:
    schema_version: str
    profile_reference: str
    external_evidence_reference: str
    provider: str
    training_use: str
    retention_profile: str
    allowed_purposes: tuple[AIProcessingPurpose, ...]
    allowed_data_classifications: tuple[AIDataClassification, ...]
    policy_sha256: str


@dataclass(frozen=True, slots=True)
class AIProcessingAuthorization:
    policy_sha256: str
    profile_reference: str
    external_evidence_reference: str
    provider: str
    purpose: AIProcessingPurpose
    data_classification: AIDataClassification
    model: str
    retention_profile: str


def _fail(message: str) -> None:
    raise AIProviderPolicyError(message)


def _required(environment: Mapping[str, str], name: str) -> str:
    value = str(environment.get(name, "")).strip()
    if not value:
        _fail(f"Required AI provider policy setting is missing: {name}.")
    return value


def _enum_list(value: str, enum_type: type[Enum], *, field_name: str):
    raw = tuple(item.strip() for item in value.split(",") if item.strip())
    if not raw:
        _fail(f"{field_name} must contain at least one value.")
    if len(raw) != len(set(raw)):
        _fail(f"{field_name} must not contain duplicate values.")
    try:
        return tuple(enum_type(item) for item in raw)
    except ValueError as exc:
        _fail(f"{field_name} contains an unsupported value.")
        raise AssertionError from exc


def _policy_identity(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def load_approved_ai_provider_profile(
    environment: Mapping[str, str] | None = None,
) -> ApprovedAIProviderProfile:
    """Load one explicit deployment approval profile or fail closed.

    The environment carries approval metadata only.  API keys and client case
    data are neither read nor included in the policy identity.
    """

    values = os.environ if environment is None else environment

    approved = str(values.get("LEGALRAG_AI_PROVIDER_POLICY_APPROVED", "")).strip().lower()
    if approved != _APPROVAL_TRUE:
        _fail("Outbound AI processing is not explicitly approved by deployment policy.")

    profile_reference = _required(values, "LEGALRAG_AI_PROVIDER_POLICY_REFERENCE")
    external_evidence_reference = _required(
        values,
        "LEGALRAG_AI_PROVIDER_EXTERNAL_EVIDENCE_REFERENCE",
    )
    provider = _required(values, "LEGALRAG_AI_PROVIDER_NAME").lower()
    if provider != _SUPPORTED_PROVIDER:
        _fail("The approved AI provider profile is not for OpenAI.")

    training_use = _required(values, "LEGALRAG_AI_PROVIDER_TRAINING_USE").lower()
    if training_use != _TRAINING_DISABLED:
        _fail("LegalRAG requires provider model-training use to be explicitly disabled.")

    retention_profile = _required(values, "LEGALRAG_AI_PROVIDER_RETENTION_PROFILE")
    purposes = _enum_list(
        _required(values, "LEGALRAG_AI_PROVIDER_ALLOWED_PURPOSES"),
        AIProcessingPurpose,
        field_name="LEGALRAG_AI_PROVIDER_ALLOWED_PURPOSES",
    )
    data_classes = _enum_list(
        _required(values, "LEGALRAG_AI_PROVIDER_ALLOWED_DATA_CLASSES"),
        AIDataClassification,
        field_name="LEGALRAG_AI_PROVIDER_ALLOWED_DATA_CLASSES",
    )

    identity_payload = {
        "schema_version": AI_PROVIDER_POLICY_SCHEMA_VERSION,
        "profile_reference": profile_reference,
        "external_evidence_reference": external_evidence_reference,
        "provider": provider,
        "training_use": training_use,
        "retention_profile": retention_profile,
        "allowed_purposes": sorted(item.value for item in purposes),
        "allowed_data_classifications": sorted(item.value for item in data_classes),
    }

    return ApprovedAIProviderProfile(
        schema_version=AI_PROVIDER_POLICY_SCHEMA_VERSION,
        profile_reference=profile_reference,
        external_evidence_reference=external_evidence_reference,
        provider=provider,
        training_use=training_use,
        retention_profile=retention_profile,
        allowed_purposes=tuple(sorted(purposes, key=lambda item: item.value)),
        allowed_data_classifications=tuple(
            sorted(data_classes, key=lambda item: item.value)
        ),
        policy_sha256=_policy_identity(identity_payload),
    )


def assert_ai_processing_allowed(
    *,
    provider: str,
    purpose: AIProcessingPurpose | str,
    data_classification: AIDataClassification | str,
    model: str,
    environment: Mapping[str, str] | None = None,
) -> AIProcessingAuthorization:
    """Require explicit provider, purpose and data-class approval before a call."""

    profile = load_approved_ai_provider_profile(environment)

    requested_provider = str(provider).strip().lower()
    if requested_provider != profile.provider:
        _fail("Outbound AI provider does not match the approved provider profile.")

    try:
        requested_purpose = AIProcessingPurpose(purpose)
    except ValueError as exc:
        _fail("Outbound AI processing purpose is unsupported.")
        raise AssertionError from exc

    try:
        requested_data_class = AIDataClassification(data_classification)
    except ValueError as exc:
        _fail("Outbound AI data classification is unsupported.")
        raise AssertionError from exc

    if requested_purpose not in profile.allowed_purposes:
        _fail("Outbound AI processing purpose is not approved by deployment policy.")
    if requested_data_class not in profile.allowed_data_classifications:
        _fail("Outbound AI data classification is not approved by deployment policy.")

    requested_model = str(model).strip()
    if not requested_model:
        _fail("Outbound AI model identity must not be empty.")

    return AIProcessingAuthorization(
        policy_sha256=profile.policy_sha256,
        profile_reference=profile.profile_reference,
        external_evidence_reference=profile.external_evidence_reference,
        provider=profile.provider,
        purpose=requested_purpose,
        data_classification=requested_data_class,
        model=requested_model,
        retention_profile=profile.retention_profile,
    )


__all__ = [
    "AI_PROVIDER_POLICY_SCHEMA_VERSION",
    "AIDataClassification",
    "AIProcessingAuthorization",
    "AIProcessingPurpose",
    "AIProviderPolicyError",
    "ApprovedAIProviderProfile",
    "assert_ai_processing_allowed",
    "load_approved_ai_provider_profile",
]
