"""Deterministic U9B-to-U9C-B1 construction without new analytical semantics."""

from __future__ import annotations

from collections import defaultdict

from governed_evidence_analysis import (
    GOVERNED_EVIDENTIAL_ANALYSIS_IDENTITY_VERSION,
    GOVERNED_EVIDENTIAL_ANALYSIS_SCHEMA_VERSION,
    GovernedEvidenceAssessment,
    GovernedEvidenceObservation,
    GovernedEvidenceObservationType,
    GovernedEvidenceUseCoordinate,
    GovernedEvidentialAnalysis,
    derive_governed_evidential_analysis_id,
    source_u9b_sha256,
    validate_governed_evidential_analysis,
)
from governed_issue_evidence import (
    GovernedEvidenceRef,
    GovernedIssueEvidenceMap,
    validate_governed_issue_evidence_map,
)


def build_governed_evidential_analysis(
    source_u9b: GovernedIssueEvidenceMap,
) -> GovernedEvidentialAnalysis:
    """Construct the unique frozen U9C-B1 overlay implied by validated U9B state.

    The construction is deliberately non-analytical. It copies only structural and
    provenance observations already defined by U9C-B1 and then delegates identity
    derivation and final validation to the frozen public U9C-B1 API.

    Args:
        source_u9b: Complete validated governed issue/evidence map.

    Returns:
        The deterministically constructed and validated U9C-B1 analysis overlay.
    """

    validate_governed_issue_evidence_map(source_u9b)
    evidence_by_key, uses_by_key, roles_by_coordinate = _index_u9b(source_u9b)

    assessments = tuple(
        _build_assessment(
            evidence=evidence_by_key[evidence_key],
            source_uses=uses_by_key[evidence_key],
            roles_by_coordinate=roles_by_coordinate,
        )
        for evidence_key in sorted(evidence_by_key)
    )

    source_sha256 = source_u9b_sha256(source_u9b)
    analysis_id = derive_governed_evidential_analysis_id(
        schema_version=GOVERNED_EVIDENTIAL_ANALYSIS_SCHEMA_VERSION,
        identity_version=GOVERNED_EVIDENTIAL_ANALYSIS_IDENTITY_VERSION,
        case_id=source_u9b.case_id,
        source_u9b_sha256_value=source_sha256,
    )
    result = GovernedEvidentialAnalysis(
        schema_version=GOVERNED_EVIDENTIAL_ANALYSIS_SCHEMA_VERSION,
        identity_version=GOVERNED_EVIDENTIAL_ANALYSIS_IDENTITY_VERSION,
        case_id=source_u9b.case_id,
        source_u9b_sha256=source_sha256,
        analysis_id=analysis_id,
        evidence_assessments=assessments,
    )
    validate_governed_evidential_analysis(result, source_u9b)
    return result


def _index_u9b(
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
        evidence = binding.evidence
        evidence_by_key[evidence.evidence_key] = evidence
        coordinate = GovernedEvidenceUseCoordinate(
            issue_analysis_id=binding.use.issue_analysis_id,
            element_id=binding.use.element_id,
            evidence_key=evidence.evidence_key,
        )
        uses[evidence.evidence_key].append(coordinate)
        roles_by_coordinate[coordinate] = binding.use.analytical_role

    for evidence in source_u9b.unmapped_evidence:
        evidence_by_key[evidence.evidence_key] = evidence
        uses.setdefault(evidence.evidence_key, [])

    canonical_uses = {
        evidence_key: tuple(sorted(coordinates))
        for evidence_key, coordinates in uses.items()
    }
    return evidence_by_key, canonical_uses, roles_by_coordinate


def _build_assessment(
    *,
    evidence: GovernedEvidenceRef,
    source_uses: tuple[GovernedEvidenceUseCoordinate, ...],
    roles_by_coordinate: dict[GovernedEvidenceUseCoordinate, str],
) -> GovernedEvidenceAssessment:
    observations: list[GovernedEvidenceObservation] = [
        GovernedEvidenceObservation(
            GovernedEvidenceObservationType.ANALYTICALLY_BOUND
            if source_uses
            else GovernedEvidenceObservationType.ANALYTICALLY_UNMAPPED
        )
    ]

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

    return GovernedEvidenceAssessment(
        evidence_key=evidence.evidence_key,
        use_coordinates=source_uses,
        observations=tuple(sorted(observations, key=_observation_sort_key)),
    )


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


__all__ = ["build_governed_evidential_analysis"]
