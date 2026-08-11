from dataclasses import FrozenInstanceError

import pytest

from governed_evidence_analysis.models import (
    GOVERNED_EVIDENTIAL_ANALYSIS_IDENTITY_VERSION,
    GOVERNED_EVIDENTIAL_ANALYSIS_SCHEMA_VERSION,
    GovernedEvidenceAssessment,
    GovernedEvidenceObservation,
    GovernedEvidenceObservationType,
    GovernedEvidenceUseCoordinate,
)


def test_versions_and_observation_vocabulary_are_exact():
    assert GOVERNED_EVIDENTIAL_ANALYSIS_SCHEMA_VERSION == "governed-evidential-analysis-schema/1.0"
    assert GOVERNED_EVIDENTIAL_ANALYSIS_IDENTITY_VERSION == "governed-evidential-analysis-identity/1.0"
    assert tuple(item.value for item in GovernedEvidenceObservationType) == (
        "analytically_bound",
        "analytically_unmapped",
        "primary_source_bound",
        "primary_source_unmapped",
        "adverse_role_present",
        "conflicting_role_present",
    )


def test_natural_use_coordinate_and_tuple_normalisation_are_immutable():
    coordinate = GovernedEvidenceUseCoordinate("analysis-1", "EK-KNOWLEDGE", "evidence-1")
    assessment = GovernedEvidenceAssessment(
        evidence_key="evidence-1",
        use_coordinates=[coordinate],
        observations=[
            GovernedEvidenceObservation(GovernedEvidenceObservationType.ANALYTICALLY_BOUND)
        ],
    )
    assert assessment.use_coordinates == (coordinate,)
    assert isinstance(assessment.observations, tuple)
    with pytest.raises(FrozenInstanceError):
        coordinate.element_id = "changed"
