"""Harness-only H4 semantic drift comparison for M3 Gate 2 observation.

H4 compares one validated frozen H2 analytical snapshot with a *supplied*
current native M5/M1/M2 state.  It never regenerates retrieval, M5, M1 or M2
and never writes either side.  Strict native equivalence and semantic
analytical equivalence are deliberately reported separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable, Mapping

from case_analysis.m2.matrices import CaseMatrices
from case_analysis.m3.chronology_validation import resolve_chronology_inputs
from case_analysis.models import CaseAnalysisFoundation
from legal_analysis.legal_analysis import StructuredLegalAnalysisResult

from case_analysis_m3_frozen_gate1 import load_frozen_gate1_inputs
from case_analysis_m3_frozen_snapshot_envelope import build_frozen_snapshot


class DriftCategory(StrEnum):
    RUN_INSTANCE_IDENTITY_DRIFT = "RUN_INSTANCE_IDENTITY_DRIFT"
    VERSION_DRIFT = "VERSION_DRIFT"
    SOURCE_SET_DRIFT = "SOURCE_SET_DRIFT"
    ISSUE_MAPPING_DRIFT = "ISSUE_MAPPING_DRIFT"
    ELEMENT_MAPPING_DRIFT = "ELEMENT_MAPPING_DRIFT"
    EVIDENCE_IDENTITY_DRIFT = "EVIDENCE_IDENTITY_DRIFT"
    EVIDENCE_SUMMARY_DRIFT = "EVIDENCE_SUMMARY_DRIFT"
    M4_OCCURRENCE_DRIFT = "M4_OCCURRENCE_DRIFT"
    ROLE_DRIFT = "ROLE_DRIFT"
    MAPPING_CONFIDENCE_DRIFT = "MAPPING_CONFIDENCE_DRIFT"
    ASSESSMENT_CONFIDENCE_DRIFT = "ASSESSMENT_CONFIDENCE_DRIFT"
    PROPOSITION_DRIFT = "PROPOSITION_DRIFT"
    PROPOSITION_STATUS_DRIFT = "PROPOSITION_STATUS_DRIFT"
    PROPOSITION_CONFIDENCE_DRIFT = "PROPOSITION_CONFIDENCE_DRIFT"
    M5_STATUS_DRIFT = "M5_STATUS_DRIFT"
    M5_CONFIDENCE_DRIFT = "M5_CONFIDENCE_DRIFT"
    M5_CONTENT_DRIFT = "M5_CONTENT_DRIFT"
    MATRIX_DRIFT = "MATRIX_DRIFT"
    AMBIGUOUS_ISSUE_ALIGNMENT = "AMBIGUOUS_ISSUE_ALIGNMENT"


@dataclass(frozen=True, slots=True)
class AnalyticalDrift:
    category: DriftCategory
    path: str
    frozen: Any
    current: Any
    detail: str


@dataclass(frozen=True, slots=True)
class Gate2DriftReport:
    frozen_analytical_state_sha256: str
    current_analytical_state_sha256: str
    strict_native_match: bool
    semantic_analytical_match: bool
    drifts: tuple[AnalyticalDrift, ...]

    @property
    def categories(self) -> tuple[DriftCategory, ...]:
        return tuple(dict.fromkeys(item.category for item in self.drifts))


def _issue_key(result: StructuredLegalAnalysisResult) -> tuple[str, str]:
    return (result.issue_definition_id, result.issue_definition_version)


def _ordered_results(
    values: Iterable[StructuredLegalAnalysisResult],
) -> tuple[StructuredLegalAnalysisResult, ...]:
    return tuple(sorted(tuple(values), key=lambda item: (*_issue_key(item), item.issue_analysis_id)))


def _unique_by_issue(
    values: Iterable[StructuredLegalAnalysisResult],
) -> tuple[dict[tuple[str, str], StructuredLegalAnalysisResult], tuple[tuple[str, str], ...]]:
    grouped: dict[tuple[str, str], list[StructuredLegalAnalysisResult]] = {}
    for item in values:
        grouped.setdefault(_issue_key(item), []).append(item)
    ambiguous = tuple(sorted(key for key, items in grouped.items() if len(items) != 1))
    resolved = {key: items[0] for key, items in grouped.items() if len(items) == 1}
    return resolved, ambiguous


def _evidence_identity(evidence) -> tuple[Any, ...]:
    return (
        evidence.document_id,
        evidence.document_name,
        evidence.page,
        evidence.chunk_id,
        evidence.citation,
        evidence.source_type.value,
        evidence.provenance_type.value if evidence.provenance_type else None,
        evidence.provenance_basis.value,
        evidence.provenance_confidence.value,
        evidence.evidence_status.value,
        evidence.date.isoformat() if evidence.date else None,
        evidence.author,
        tuple(evidence.parties),
    )


def _mapping_index(result: StructuredLegalAnalysisResult) -> dict[tuple[str, str], Any]:
    values: dict[tuple[str, str], Any] = {}
    for element in result.assessment_result.mapping_result.element_results:
        for mapping in element.mappings:
            key = (element.element_id, mapping.evidence_key)
            values[key] = mapping
    return values


def _mapping_order(result: StructuredLegalAnalysisResult) -> dict[str, tuple[str, ...]]:
    return {
        element.element_id: tuple(mapping.evidence_key for mapping in element.mappings)
        for element in result.assessment_result.mapping_result.element_results
    }


def _assessment_index(result: StructuredLegalAnalysisResult) -> dict[tuple[str, str], Any]:
    values: dict[tuple[str, str], Any] = {}
    for element in result.assessment_result.element_assessments:
        for assessment in element.evidence_assessments:
            values[(element.element_id, assessment.mapping.evidence_key)] = assessment
    return values


def _proposition_index(result: StructuredLegalAnalysisResult) -> dict[tuple[str, int], Any]:
    values: dict[tuple[str, int], Any] = {}
    for element in result.assessment_result.element_assessments:
        for index, proposition in enumerate(element.assessed_propositions):
            values[(element.element_id, index)] = proposition
    return values


def _m5_element_index(result: StructuredLegalAnalysisResult) -> dict[str, Any]:
    return {item.element_id: item for item in result.element_analyses}


def _semantic_use_index(matrices: CaseMatrices) -> dict[tuple[str, str, str, str], Any]:
    values: dict[tuple[str, str, str, str], Any] = {}
    for record in matrices.evidence_matrix:
        for use in record.uses:
            key = (
                use.issue_definition_id,
                use.issue_definition_version,
                use.element_id,
                use.evidence_key,
            )
            values[key] = use
    return values


def _record_index(matrices: CaseMatrices) -> dict[str, Any]:
    return {record.evidence_key: record for record in matrices.evidence_matrix}


def _append(
    drifts: list[AnalyticalDrift],
    category: DriftCategory,
    path: str,
    frozen: Any,
    current: Any,
    detail: str,
) -> None:
    drifts.append(AnalyticalDrift(category, path, frozen, current, detail))


def _compare_issue_result(
    key: tuple[str, str],
    frozen: StructuredLegalAnalysisResult,
    current: StructuredLegalAnalysisResult,
    drifts: list[AnalyticalDrift],
) -> None:
    prefix = f"{key[0]}/{key[1]}"
    frozen_versions = (
        frozen.assessment_result.mapping_result.mapper_version,
        frozen.assessment_result.assessor_version,
        frozen.analyser_version,
    )
    current_versions = (
        current.assessment_result.mapping_result.mapper_version,
        current.assessment_result.assessor_version,
        current.analyser_version,
    )
    if frozen_versions != current_versions:
        _append(
            drifts,
            DriftCategory.VERSION_DRIFT,
            prefix,
            frozen_versions,
            current_versions,
            "Mapper/assessor/analyser versions differ.",
        )

    frozen_mappings = _mapping_index(frozen)
    current_mappings = _mapping_index(current)
    frozen_keys = set(frozen_mappings)
    current_keys = set(current_mappings)
    if frozen_keys != current_keys:
        _append(
            drifts,
            DriftCategory.ELEMENT_MAPPING_DRIFT,
            prefix,
            tuple(sorted(frozen_keys)),
            tuple(sorted(current_keys)),
            "Element/evidence mapping relationships differ.",
        )

    for mapping_key in sorted(frozen_keys & current_keys):
        fm = frozen_mappings[mapping_key]
        cm = current_mappings[mapping_key]
        path = f"{prefix}/{mapping_key[0]}/{mapping_key[1]}"
        if _evidence_identity(fm.evidence) != _evidence_identity(cm.evidence):
            _append(
                drifts,
                DriftCategory.EVIDENCE_IDENTITY_DRIFT,
                path,
                _evidence_identity(fm.evidence),
                _evidence_identity(cm.evidence),
                "Stable evidence identity/provenance fields differ.",
            )
        if fm.evidence.summary != cm.evidence.summary:
            _append(
                drifts,
                DriftCategory.EVIDENCE_SUMMARY_DRIFT,
                path,
                fm.evidence.summary,
                cm.evidence.summary,
                "Evidence summary differs for the same semantic mapping key.",
            )
        if fm.relevance != cm.relevance or fm.mapping_rationale != cm.mapping_rationale:
            _append(
                drifts,
                DriftCategory.ISSUE_MAPPING_DRIFT,
                path,
                (fm.relevance.value, fm.mapping_rationale),
                (cm.relevance.value, cm.mapping_rationale),
                "Mapping relevance or rationale differs.",
            )
        if fm.mapping_confidence != cm.mapping_confidence:
            _append(
                drifts,
                DriftCategory.MAPPING_CONFIDENCE_DRIFT,
                path,
                fm.mapping_confidence.value,
                cm.mapping_confidence.value,
                "Mapping confidence differs.",
            )

    frozen_order = _mapping_order(frozen)
    current_order = _mapping_order(current)
    for element_id in sorted(set(frozen_order) & set(current_order)):
        if set(frozen_order[element_id]) == set(current_order[element_id]) and frozen_order[element_id] != current_order[element_id]:
            _append(
                drifts,
                DriftCategory.M4_OCCURRENCE_DRIFT,
                f"{prefix}/{element_id}",
                frozen_order[element_id],
                current_order[element_id],
                "M4 mapping occurrence order differs while the evidence set is unchanged.",
            )

    frozen_assessments = _assessment_index(frozen)
    current_assessments = _assessment_index(current)
    for assessment_key in sorted(set(frozen_assessments) & set(current_assessments)):
        fa = frozen_assessments[assessment_key]
        ca = current_assessments[assessment_key]
        path = f"{prefix}/{assessment_key[0]}/{assessment_key[1]}"
        if fa.analytical_role != ca.analytical_role:
            _append(
                drifts,
                DriftCategory.ROLE_DRIFT,
                path,
                fa.analytical_role.value,
                ca.analytical_role.value,
                "M4 analytical role differs.",
            )
        if fa.assessment_confidence != ca.assessment_confidence:
            _append(
                drifts,
                DriftCategory.ASSESSMENT_CONFIDENCE_DRIFT,
                path,
                fa.assessment_confidence.value,
                ca.assessment_confidence.value,
                "M4 assessment confidence differs.",
            )

    frozen_props = _proposition_index(frozen)
    current_props = _proposition_index(current)
    if set(frozen_props) != set(current_props):
        _append(
            drifts,
            DriftCategory.PROPOSITION_DRIFT,
            prefix,
            tuple(sorted(frozen_props)),
            tuple(sorted(current_props)),
            "Assessed proposition coordinates differ.",
        )
    for prop_key in sorted(set(frozen_props) & set(current_props)):
        fp = frozen_props[prop_key]
        cp = current_props[prop_key]
        path = f"{prefix}/{prop_key[0]}/proposition[{prop_key[1]}]"
        factual_frozen = (fp.text, tuple(fp.evidence_keys), fp.rationale)
        factual_current = (cp.text, tuple(cp.evidence_keys), cp.rationale)
        if factual_frozen != factual_current:
            _append(
                drifts,
                DriftCategory.PROPOSITION_DRIFT,
                path,
                factual_frozen,
                factual_current,
                "M4 proposition text/evidence/rationale differs.",
            )
        if fp.status != cp.status:
            _append(
                drifts,
                DriftCategory.PROPOSITION_STATUS_DRIFT,
                path,
                fp.status.value,
                cp.status.value,
                "M4 proposition status differs.",
            )
        if fp.confidence != cp.confidence:
            _append(
                drifts,
                DriftCategory.PROPOSITION_CONFIDENCE_DRIFT,
                path,
                fp.confidence.value,
                cp.confidence.value,
                "M4 proposition confidence differs.",
            )

    frozen_m5 = _m5_element_index(frozen)
    current_m5 = _m5_element_index(current)
    for element_id in sorted(set(frozen_m5) & set(current_m5)):
        fe = frozen_m5[element_id]
        ce = current_m5[element_id]
        path = f"{prefix}/{element_id}"
        if fe.provisional_status != ce.provisional_status:
            _append(
                drifts,
                DriftCategory.M5_STATUS_DRIFT,
                path,
                fe.provisional_status.value,
                ce.provisional_status.value,
                "M5 provisional element status differs.",
            )
        if fe.analysis_confidence != ce.analysis_confidence:
            _append(
                drifts,
                DriftCategory.M5_CONFIDENCE_DRIFT,
                path,
                fe.analysis_confidence.value,
                ce.analysis_confidence.value,
                "M5 analysis confidence differs.",
            )
        frozen_content = (
            fe.current_evidential_position,
            fe.legal_significance,
            fe.provisional_analysis,
            tuple(fe.limitations),
            tuple(fe.unresolved_matters),
        )
        current_content = (
            ce.current_evidential_position,
            ce.legal_significance,
            ce.provisional_analysis,
            tuple(ce.limitations),
            tuple(ce.unresolved_matters),
        )
        if frozen_content != current_content:
            _append(
                drifts,
                DriftCategory.M5_CONTENT_DRIFT,
                path,
                frozen_content,
                current_content,
                "M5 rendered analytical content differs.",
            )


def _compare_matrices(
    frozen: CaseMatrices,
    current: CaseMatrices,
    drifts: list[AnalyticalDrift],
) -> None:
    frozen_uses = _semantic_use_index(frozen)
    current_uses = _semantic_use_index(current)
    if set(frozen_uses) != set(current_uses):
        _append(
            drifts,
            DriftCategory.MATRIX_DRIFT,
            "M2/evidence_uses",
            tuple(sorted(frozen_uses)),
            tuple(sorted(current_uses)),
            "Semantic M2 EvidenceUse relationships differ.",
        )

    for key in sorted(set(frozen_uses) & set(current_uses)):
        fu = frozen_uses[key]
        cu = current_uses[key]
        frozen_state = (
            fu.analytical_role.value,
            fu.mapping_relevance.value,
            fu.mapping_confidence.value,
            fu.mapping_rationale,
            fu.assessment_confidence.value,
            fu.assessment_rationale,
            tuple(
                (
                    link.source_proposition_index,
                    link.text,
                    link.status.value,
                    link.confidence.value,
                    link.rationale,
                    tuple(link.evidence_keys),
                )
                for link in fu.proposition_links
            ),
        )
        current_state = (
            cu.analytical_role.value,
            cu.mapping_relevance.value,
            cu.mapping_confidence.value,
            cu.mapping_rationale,
            cu.assessment_confidence.value,
            cu.assessment_rationale,
            tuple(
                (
                    link.source_proposition_index,
                    link.text,
                    link.status.value,
                    link.confidence.value,
                    link.rationale,
                    tuple(link.evidence_keys),
                )
                for link in cu.proposition_links
            ),
        )
        if frozen_state != current_state:
            _append(
                drifts,
                DriftCategory.MATRIX_DRIFT,
                f"M2/use/{'/'.join(key)}",
                frozen_state,
                current_state,
                "M2 frozen relationship state differs.",
            )

    frozen_records = _record_index(frozen)
    current_records = _record_index(current)
    if set(frozen_records) != set(current_records):
        _append(
            drifts,
            DriftCategory.EVIDENCE_IDENTITY_DRIFT,
            "M2/evidence_records",
            tuple(sorted(frozen_records)),
            tuple(sorted(current_records)),
            "Canonical M2 evidence-key set differs.",
        )


def _run_identity_changed(
    frozen_results: Iterable[StructuredLegalAnalysisResult],
    current_results: Iterable[StructuredLegalAnalysisResult],
    frozen_foundation: CaseAnalysisFoundation,
    current_foundation: CaseAnalysisFoundation,
    frozen_matrices: CaseMatrices,
    current_matrices: CaseMatrices,
) -> bool:
    frozen_map, frozen_amb = _unique_by_issue(frozen_results)
    current_map, current_amb = _unique_by_issue(current_results)
    if frozen_amb or current_amb or set(frozen_map) != set(current_map):
        return True
    for key in frozen_map:
        fa = frozen_map[key].assessment_result.assessed_analysis
        ca = current_map[key].assessment_result.assessed_analysis
        if fa.issue_analysis_id != ca.issue_analysis_id or fa.created_at != ca.created_at:
            return True
    return (
        frozen_foundation.synthesis_id != current_foundation.synthesis_id
        or frozen_foundation.created_at != current_foundation.created_at
        or frozen_foundation.source_issue_analysis_ids != current_foundation.source_issue_analysis_ids
        or frozen_matrices.synthesis_id != current_matrices.synthesis_id
        or frozen_matrices.source_analysis_ids != current_matrices.source_analysis_ids
    )


def compare_gate2_analytical_state(
    frozen_snapshot: str | Mapping[str, Any],
    *,
    current_results: Iterable[StructuredLegalAnalysisResult],
    current_foundation: CaseAnalysisFoundation,
    current_matrices: CaseMatrices,
    expected_legacy_fixture_sha256: str | None = None,
) -> Gate2DriftReport:
    """Compare supplied current native state with one validated frozen snapshot.

    This function performs no retrieval or upstream regeneration.  The caller
    owns generation of the current integration state; H4 only validates and
    compares it.
    """

    frozen = load_frozen_gate1_inputs(
        frozen_snapshot,
        expected_legacy_fixture_sha256=expected_legacy_fixture_sha256,
    )
    current = _ordered_results(tuple(current_results))
    if not current:
        raise ValueError("Gate 2 comparison requires at least one current M5 result.")
    resolved = resolve_chronology_inputs(current_foundation, current_matrices, current)
    if resolved != current:
        raise ValueError("Gate 2 current M5 source order does not match M1 lineage.")

    # Reuse H2 to derive the strict current native analytical identity.  Capture
    # metadata is copied from the frozen manifest but does not participate in
    # analytical_state_sha256.
    if isinstance(frozen_snapshot, str):
        import json

        frozen_envelope = json.loads(frozen_snapshot)
    else:
        frozen_envelope = dict(frozen_snapshot)
    manifest = frozen_envelope["manifest"]
    legacy = manifest["legacy_fixture"]
    current_envelope = build_frozen_snapshot(
        results=current,
        foundation=current_foundation,
        matrices=current_matrices,
        legacy_fixture_name=str(legacy["name"]),
        legacy_fixture_version=str(legacy["fixture_version"]),
        legacy_fixture_sha256=str(legacy["sha256"]),
        captured_at=str(manifest["captured_at"]),
        source_checkpoint=str(manifest["source_checkpoint"]),
    )
    strict_match = (
        frozen.analytical_state_sha256 == current_envelope["analytical_state_sha256"]
    )

    drifts: list[AnalyticalDrift] = []
    frozen_by_issue, frozen_ambiguous = _unique_by_issue(frozen.results)
    current_by_issue, current_ambiguous = _unique_by_issue(current)
    for key in sorted(set(frozen_ambiguous) | set(current_ambiguous)):
        _append(
            drifts,
            DriftCategory.AMBIGUOUS_ISSUE_ALIGNMENT,
            f"{key[0]}/{key[1]}",
            key in frozen_ambiguous,
            key in current_ambiguous,
            "Issue definition/version is not unique on one or both sides.",
        )

    frozen_issue_keys = set(frozen_by_issue)
    current_issue_keys = set(current_by_issue)
    if frozen_issue_keys != current_issue_keys:
        _append(
            drifts,
            DriftCategory.SOURCE_SET_DRIFT,
            "M5/issues",
            tuple(sorted(frozen_issue_keys)),
            tuple(sorted(current_issue_keys)),
            "Semantic issue-definition source set differs.",
        )

    for key in sorted(frozen_issue_keys & current_issue_keys):
        _compare_issue_result(key, frozen_by_issue[key], current_by_issue[key], drifts)

    _compare_matrices(frozen.matrices, current_matrices, drifts)

    semantic_categories = tuple(
        item.category
        for item in drifts
        if item.category is not DriftCategory.RUN_INSTANCE_IDENTITY_DRIFT
    )
    semantic_match = not semantic_categories

    if _run_identity_changed(
        frozen.results,
        current,
        frozen.foundation,
        current_foundation,
        frozen.matrices,
        current_matrices,
    ):
        _append(
            drifts,
            DriftCategory.RUN_INSTANCE_IDENTITY_DRIFT,
            "native/run_identity",
            (
                tuple(item.issue_analysis_id for item in frozen.results),
                frozen.foundation.synthesis_id,
            ),
            (
                tuple(item.issue_analysis_id for item in current),
                current_foundation.synthesis_id,
            ),
            "Run-instance UUID/timestamp-derived native identity differs.",
        )

    drifts.sort(key=lambda item: (item.category.value, item.path, repr(item.frozen), repr(item.current)))
    # Re-evaluate after deterministic sort; run-instance identity is explicitly
    # excluded from semantic analytical equivalence.
    semantic_match = all(
        item.category is DriftCategory.RUN_INSTANCE_IDENTITY_DRIFT for item in drifts
    )

    return Gate2DriftReport(
        frozen_analytical_state_sha256=frozen.analytical_state_sha256,
        current_analytical_state_sha256=str(current_envelope["analytical_state_sha256"]),
        strict_native_match=strict_match,
        semantic_analytical_match=semantic_match,
        drifts=tuple(drifts),
    )


__all__ = [
    "AnalyticalDrift",
    "DriftCategory",
    "Gate2DriftReport",
    "compare_gate2_analytical_state",
]
