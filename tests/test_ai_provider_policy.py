from __future__ import annotations

import pytest

from ai_provider_policy import (
    AIDataClassification,
    AIProcessingPurpose,
    AIProviderPolicyError,
    assert_ai_processing_allowed,
    load_approved_ai_provider_profile,
)


def _environment(**overrides: str) -> dict[str, str]:
    values = {
        "LEGALRAG_AI_PROVIDER_POLICY_APPROVED": "true",
        "LEGALRAG_AI_PROVIDER_POLICY_REFERENCE": "sra-c1-test-profile",
        "LEGALRAG_AI_PROVIDER_EXTERNAL_EVIDENCE_REFERENCE": "external-evidence:test",
        "LEGALRAG_AI_PROVIDER_NAME": "openai",
        "LEGALRAG_AI_PROVIDER_TRAINING_USE": "disabled",
        "LEGALRAG_AI_PROVIDER_RETENTION_PROFILE": "test-explicit-retention-profile",
        "LEGALRAG_AI_PROVIDER_ALLOWED_PURPOSES": ",".join(
            item.value for item in AIProcessingPurpose
        ),
        "LEGALRAG_AI_PROVIDER_ALLOWED_DATA_CLASSES": ",".join(
            item.value for item in AIDataClassification
        ),
    }
    values.update(overrides)
    return values


def test_policy_fails_closed_without_explicit_approval():
    with pytest.raises(AIProviderPolicyError, match="not explicitly approved"):
        load_approved_ai_provider_profile({})


def test_policy_requires_external_evidence_reference_and_disabled_training_use():
    values = _environment()
    values.pop("LEGALRAG_AI_PROVIDER_EXTERNAL_EVIDENCE_REFERENCE")
    with pytest.raises(AIProviderPolicyError, match="EXTERNAL_EVIDENCE_REFERENCE"):
        load_approved_ai_provider_profile(values)

    with pytest.raises(AIProviderPolicyError, match="training"):
        load_approved_ai_provider_profile(
            _environment(LEGALRAG_AI_PROVIDER_TRAINING_USE="enabled")
        )


def test_policy_identity_is_deterministic_and_excludes_api_credentials():
    one = load_approved_ai_provider_profile(_environment(OPENAI_API_KEY="secret-one"))
    two = load_approved_ai_provider_profile(_environment(OPENAI_API_KEY="secret-two"))
    assert one.policy_sha256 == two.policy_sha256
    assert one.policy_sha256.startswith("sha256:")
    assert "secret" not in repr(one)


def test_authorization_is_exact_for_provider_purpose_data_class_and_model():
    environment = _environment(
        LEGALRAG_AI_PROVIDER_ALLOWED_PURPOSES=AIProcessingPurpose.LEGAL_ANSWER.value,
        LEGALRAG_AI_PROVIDER_ALLOWED_DATA_CLASSES=AIDataClassification.PRIVILEGED.value,
    )
    auth = assert_ai_processing_allowed(
        provider="openai",
        purpose=AIProcessingPurpose.LEGAL_ANSWER,
        data_classification=AIDataClassification.PRIVILEGED,
        model="gpt-test",
        environment=environment,
    )
    assert auth.purpose is AIProcessingPurpose.LEGAL_ANSWER
    assert auth.data_classification is AIDataClassification.PRIVILEGED
    assert auth.model == "gpt-test"

    with pytest.raises(AIProviderPolicyError, match="purpose"):
        assert_ai_processing_allowed(
            provider="openai",
            purpose=AIProcessingPurpose.QUERY_EXPANSION,
            data_classification=AIDataClassification.PRIVILEGED,
            model="gpt-test",
            environment=environment,
        )

    with pytest.raises(AIProviderPolicyError, match="data classification"):
        assert_ai_processing_allowed(
            provider="openai",
            purpose=AIProcessingPurpose.LEGAL_ANSWER,
            data_classification=AIDataClassification.CLIENT_CONFIDENTIAL,
            model="gpt-test",
            environment=environment,
        )

    with pytest.raises(AIProviderPolicyError, match="provider"):
        assert_ai_processing_allowed(
            provider="other",
            purpose=AIProcessingPurpose.LEGAL_ANSWER,
            data_classification=AIDataClassification.PRIVILEGED,
            model="gpt-test",
            environment=environment,
        )


def test_policy_rejects_unknown_or_duplicate_enum_values():
    with pytest.raises(AIProviderPolicyError, match="unsupported"):
        load_approved_ai_provider_profile(
            _environment(LEGALRAG_AI_PROVIDER_ALLOWED_PURPOSES="not-a-purpose")
        )
    with pytest.raises(AIProviderPolicyError, match="duplicate"):
        load_approved_ai_provider_profile(
            _environment(
                LEGALRAG_AI_PROVIDER_ALLOWED_DATA_CLASSES="privileged,privileged"
            )
        )
