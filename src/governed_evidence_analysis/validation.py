"""Fail-closed validation for U9C-B1 governed evidential analysis overlays."""

from __future__ import annotations

from collections import defaultdict

from governed_issue_evidence.models import GovernedEvidenceRef, GovernedIssueEvidenceMap
from governed_issue_evidence.validation import validate_governed_issue_evidence_map

from .identity import derive_governed_evidential_analysis_id, source_u9b_sha256
from .models import (
    GOVERNED_EVIDENTIAL_ANALYSIS_IDENTITY_VERSION,
    GOVERNED_EVIDENTIAL_ANALYSIS_SCHEMA_VERSION,
    GovernedEvidenceAssessment,
    GovernedEvidenceObservation,
    GovernedEvidenceObservationType,
    GovernedEvidenceUseCoordinate,
    GovernedEvidentialAnalysis,
)


class GovernedEvidentialAnalysisValidationError(ValueError):
    """Raised when U9C state exceeds or disagrees with its frozen U9B authority."""


def validate_governed_evidential_analysis(
    value: GovernedEvidentialAnalysis,
    source_u9b: GovernedIssueEvidenceMap,
) -> None:
    """Validate one complete deterministic U9C overlay against supplied frozen U9B state."""

    validate_governed_issue_evidence_map(source_u9b)

    if value.schema_version != GOVERNED_EVIDENTIAL_ANALYSIS_SCHEMA_VERSION:
        raise GovernedEvidentialAnalysisValidationError(
            "Unsupported governed evidential-analysis schema."
        )
    if value.identity_version != GOVERNED_EVIDENTIAL_ANALYSIS_IDENTITY_VERSION:
        raise GovernedEvidentialAnalysisValidationError(
            "Unsupported governed evidential-analysis identity version."
        )
    if value.case_id != source_u9b.case_id:
        raise GovernedEvidentialAnalysisValidationError(
            "U9C case_id does not match frozen U9B authority."
        )

    expected_source_sha = source_u9b_sha256(source_u9b)
    if value.source_u9b_sha256 != expected_source_sha:
        raise GovernedEvidentialAnalysisValidationError(
            "source_u9b_sha256 does not match canonical frozen U9B bytes."
        )

    expected_analysis_id = derive_governed_evidential_analysis_id(
        schema_version=value.schema_version,
        identity_version=value.identity_version,
        case_id=value.case_id,
        source_u9b_sha256_value=value.source_u9b_sha256,
    )
    if value.analysis_id != expected_analysis_id:
        raise GovernedEvidentialAnalysisValidationError(
            "analysis_id does not match the deterministic U9C identity payload."
        )

    evidence_by_key, uses_by_key, roles_by_coordinate = _source_indexes(source_u9b)
    expected_keys = tuple(sorted(evidence_by_key))
    observed_keys = tuple(item.evidence_key for item in value.evidence_assessments)

    if observed_keys != expected_keys:
        raise GovernedEvidentialAnalysisValidationError(
            "U9C evidence assessments must exactly cover U9B evidence keys in canonical order."
        )
    if len(set(observed_keys)) != len(observed_keys):
        raise GovernedEvidentialAnalysisValidationError(
            "U9C evidence assessments contain duplicate evidence keys."
        )

    for assessment in value.evidence_assessments:
        _validate_assessment(
            assessment,
            evidence=evidence_by_key[assessment.evidence_key],
            source_uses=uses_by_key[assessment.evidence_key],
            roles_by_coordinate=roles_by_coordinate,
        )


def _source_indexes(
    source_u9b: GovernedIssueEvidenceMap,
) -> tuple[
    dict[str, GovernedEvidenceRef],
    dict[str, tuple[GovernedEvidenceUseCoordinate, ...]],
    dict[GovernedEvidenceUseCoordinate, str],
]:
    evidence_by_key: dict[str, GovernedEvidenceRef] = {}
    uses: dict[str, list[GovernedEvidenceUseCoordinate]] = defaultdict(list)
    roles_by_coordinate: dict[GovernedEvidenceUseCoordinate, str] = {}

    for binding in source_u9b.bindings:
        key = binding.evidence.evidence_key
        evidence_by_key[key] = binding.evidence
        coordinate = GovernedEvidenceUseCoordinate(
            issue_analysis_id=binding.use.issue_analysis_id,
            element_id=binding.use.element_id,
            evidence_key=key,
        )
        uses[key].append(coordinate)
        roles_by_coordinate[coordinate] = binding.use.analytical_role

    for evidence in source_u9b.unmapped_evidence:
        evidence_by_key[evidence.evidence_key] = evidence
        uses.setdefault(evidence.evidence_key, [])

    return (
        evidence_by_key,
        {key: tuple(sorted(coordinates)) for key, coordinates in uses.items()},
        roles_by_coordinate,
    )


def _validate_assessment(
    assessment: GovernedEvidenceAssessment,
    *,
    evidence: GovernedEvidenceRef,
    source_uses: tuple[GovernedEvidenceUseCoordinate, ...],
    roles_by_coordinate: dict[GovernedEvidenceUseCoordinate, str],
) -> None:
    if not assessment.evidence_key.strip():
        raise GovernedEvidentialAnalysisValidationError("evidence_key must be non-empty.")

    coordinates = tuple(assessment.use_coordinates)
    if coordinates != tuple(sorted(coordinates)):
        raise GovernedEvidentialAnalysisValidationError(
            "U9C EvidenceUse coordinates must be in canonical order."
        )
    if len(set(coordinates)) != len(coordinates):
        raise GovernedEvidentialAnalysisValidationError(
            "U9C EvidenceUse coordinates contain duplicates."
        )
    if coordinates != source_uses:
        raise GovernedEvidentialAnalysisValidationError(
            "U9C EvidenceUse coordinates do not exactly match frozen U9B uses."
        )
    if any(item.evidence_key != assessment.evidence_key for item in coordinates):
        raise GovernedEvidentialAnalysisValidationError(
            "U9C EvidenceUse coordinate points to a different evidence key."
        )

    expected_observations = _expected_observations(
        evidence=evidence,
        source_uses=source_uses,
        roles_by_coordinate=roles_by_coordinate,
    )
    observations = tuple(assessment.observations)
    if observations != tuple(sorted(observations, key=_observation_sort_key)):
        raise GovernedEvidentialAnalysisValidationError(
            "U9C observations must be in canonical order."
        )
    if len(set(observations)) != len(observations):
        raise GovernedEvidentialAnalysisValidationError(
            "U9C observations contain duplicates."
        )

    for observation in observations:
        _validate_observation_topology(
            observation,
            assessment_key=assessment.evidence_key,
            source_uses=source_uses,
        )

    if observations != expected_observations:
        raise GovernedEvidentialAnalysisValidationError(
            "U9C observations do not exactly match deterministic frozen U9B facts."
        )


def _expected_observations(
    *,
    evidence: GovernedEvidenceRef,
    source_uses: tuple[GovernedEvidenceUseCoordinate, ...],
    roles_by_coordinate: dict[GovernedEvidenceUseCoordinate, str],
) -> tuple[GovernedEvidenceObservation, ...]:
    observations: list[GovernedEvidenceObservation] = []

    if source_uses:
        observations.append(
            GovernedEvidenceObservation(
                GovernedEvidenceObservationType.ANALYTICALLY_BOUND
            )
        )
    else:
        observations.append(
            GovernedEvidenceObservation(
                GovernedEvidenceObservationType.ANALYTICALLY_UNMAPPED
            )
        )

    if evidence.evidence_role == "primary_source":
        observations.append(
            GovernedEvidenceObservation(
                GovernedEvidenceObservationType.PRIMARY_SOURCE_BOUND
                if source_uses
                else GovernedEvidenceObservationType.PRIMARY_SOURCE_UNMAPPED
            )
        )

    for coordinate in source_uses:
        role = roles_by_coordinate[coordinate]
        if role == "adverse":
            observations.append(
                GovernedEvidenceObservation(
                    GovernedEvidenceObservationType.ADVERSE_ROLE_PRESENT,
                    use_coordinate=coordinate,
                )
            )
        elif role == "conflicting":
            observations.append(
                GovernedEvidenceObservation(
                    GovernedEvidenceObservationType.CONFLICTING_ROLE_PRESENT,
                    use_coordinate=coordinate,
                )
            )

    return tuple(sorted(observations, key=_observation_sort_key))


def _validate_observation_topology(
    observation: GovernedEvidenceObservation,
    *,
    assessment_key: str,
    source_uses: tuple[GovernedEvidenceUseCoordinate, ...],
) -> None:
    evidence_level = {
        GovernedEvidenceObservationType.ANALYTICALLY_BOUND,
        GovernedEvidenceObservationType.ANALYTICALLY_UNMAPPED,
        GovernedEvidenceObservationType.PRIMARY_SOURCE_BOUND,
        GovernedEvidenceObservationType.PRIMARY_SOURCE_UNMAPPED,
    }
    use_level = {
        GovernedEvidenceObservationType.ADVERSE_ROLE_PRESENT,
        GovernedEvidenceObservationType.CONFLICTING_ROLE_PRESENT,
    }

    if observation.observation_type in evidence_level:
        if observation.use_coordinate is not None:
            raise GovernedEvidentialAnalysisValidationError(
                "Evidence-level U9C observations cannot carry an EvidenceUse coordinate."
            )
        return

    if observation.observation_type in use_level:
        coordinate = observation.use_coordinate
        if coordinate is None:
            raise GovernedEvidentialAnalysisValidationError(
                "Role-presence U9C observations require an EvidenceUse coordinate."
            )
        if coordinate.evidence_key != assessment_key or coordinate not in source_uses:
            raise GovernedEvidentialAnalysisValidationError(
                "Role-presence observation does not resolve to this frozen U9B evidence use."
            )
        return

    raise GovernedEvidentialAnalysisValidationError("Unsupported U9C observation type.")


def _observation_sort_key(
    observation: GovernedEvidenceObservation,
) -> tuple[str, str, str, str]:
    coordinate = observation.use_coordinate
    return (
        observation.observation_type.value,
        "" if coordinate is None else coordinate.issue_analysis_id,
        "" if coordinate is None else coordinate.element_id,
        "" if coordinate is None else coordinate.evidence_key,
    )


__all__ = [
    "GovernedEvidentialAnalysisValidationError",
    "validate_governed_evidential_analysis",
]
