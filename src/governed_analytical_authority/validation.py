"""Fail-closed validation for governed analytical authority bundles and lifecycle state."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from case_analysis.m2.evidence_matrix import build_evidence_matrix
from case_analysis.m2.issue_matrix import build_issue_matrix
from case_analysis.m2.matrix_serialization import dumps_case_matrices
from case_analysis.m2.matrix_validation import validate_case_matrices
from case_analysis.validation import validate_source_analysis_results
from governed_evidence_analysis.serialization import dumps_governed_evidential_analysis
from governed_evidence_analysis.validation import validate_governed_evidential_analysis
from governed_issue_evidence.serialization import dumps_governed_issue_evidence_map
from governed_issue_evidence.validation import validate_governed_issue_evidence_map
from legal_analysis.legal_analysis import StructuredLegalAnalysisResult

from .identity import (
    canonical_sha256,
    derive_governed_analytical_authority_activation_id,
    derive_governed_analytical_authority_id,
    require_canonical_case_id,
    require_sha256_id,
)
from .models import (
    GOVERNED_ANALYTICAL_AUTHORITY_ACTIVATION_SCHEMA_VERSION,
    GOVERNED_ANALYTICAL_AUTHORITY_IDENTITY_VERSION,
    GOVERNED_ANALYTICAL_AUTHORITY_MANIFEST_SCHEMA_VERSION,
    GOVERNED_ANALYTICAL_AUTHORITY_POINTER_SCHEMA_VERSION,
    GovernedAnalyticalAuthorityActivationAction,
    GovernedAnalyticalAuthorityActivationReceipt,
    GovernedAnalyticalAuthorityActivePointer,
    GovernedAnalyticalAuthorityManifest,
)
from .serialization import (
    dumps_governed_analytical_authority_active_pointer,
    dumps_governed_analytical_authority_manifest,
    dumps_structured_legal_analysis_results,
)


class GovernedAnalyticalAuthorityValidationError(ValueError):
    """Raised when a B4/B6 authority or lifecycle object fails closed."""


def _fail(message: str, exc: Exception | None = None) -> None:
    if exc is None:
        raise GovernedAnalyticalAuthorityValidationError(message)
    raise GovernedAnalyticalAuthorityValidationError(message) from exc


def _source_ids(
    results: Iterable[StructuredLegalAnalysisResult],
) -> tuple[str, ...]:
    try:
        refs = validate_source_analysis_results(tuple(results))
    except (TypeError, ValueError) as exc:
        _fail("StructuredLegalAnalysisResult source set is invalid.", exc)
    return tuple(sorted(item.issue_analysis_id for item in refs))


def _matrix_use_index(matrices: Any) -> dict[tuple[str, str, str], Any]:
    index: dict[tuple[str, str, str], Any] = {}
    for record in matrices.evidence_matrix:
        for use in record.uses:
            if use.identity in index:
                _fail(f"Duplicate CaseMatrices EvidenceUse identity: {use.identity!r}.")
            index[use.identity] = use
    return index


def _governed_use_index(source_u9b: Any) -> dict[tuple[str, str, str], Any]:
    index: dict[tuple[str, str, str], Any] = {}
    for binding in source_u9b.bindings:
        identity = binding.use.identity
        if identity in index:
            _fail(f"Duplicate U9B EvidenceUse identity: {identity!r}.")
        if binding.evidence.evidence_key != binding.use.evidence_key:
            _fail("U9B binding evidence/use evidence_key mismatch.")
        index[identity] = binding.use
    return index


def _proposition_state(value: Any) -> tuple[Any, ...]:
    return (
        int(value.source_proposition_index),
        str(value.text),
        str(getattr(value.status, "value", value.status)),
        str(getattr(value.confidence, "value", value.confidence)),
        str(value.rationale),
        tuple(str(item) for item in value.evidence_keys),
    )


def _matrix_use_state(value: Any) -> tuple[Any, ...]:
    return (
        str(value.issue_analysis_id),
        str(value.issue_definition_id),
        str(value.issue_definition_version),
        str(value.element_id),
        int(value.element_ordinal),
        str(value.evidence_key),
        str(value.analytical_role.value),
        str(value.mapping_relevance.value),
        str(value.mapping_confidence.value),
        str(value.mapping_rationale),
        str(value.assessment_confidence.value),
        str(value.assessment_rationale),
        str(value.citation),
        tuple(_proposition_state(item) for item in value.proposition_links),
    )


def _u9b_use_state(value: Any) -> tuple[Any, ...]:
    return (
        str(value.issue_analysis_id),
        str(value.issue_definition_id),
        str(value.issue_definition_version),
        str(value.element_id),
        int(value.element_ordinal),
        str(value.evidence_key),
        str(value.analytical_role),
        str(value.mapping_relevance),
        str(value.mapping_confidence),
        str(value.mapping_rationale),
        str(value.assessment_confidence),
        str(value.assessment_rationale),
        str(value.citation),
        tuple(_proposition_state(item) for item in value.proposition_links),
    )


def validate_governed_analytical_authority_components(
    *,
    structured_legal_analysis_results: Iterable[StructuredLegalAnalysisResult],
    case_matrices: Any,
    governed_issue_evidence_map: Any,
    governed_evidential_analysis: Any,
) -> tuple[str, ...]:
    """Prove that the four supplied substantive components form one exact generation.

    This function validates only already-supplied state.  It never retrieves evidence,
    reruns mapping/assessment/rendering, or substitutes a rebuilt authority component.
    The M2 issue/evidence projection functions are used solely as equality validators
    over the complete supplied M5 graph.
    """

    results = tuple(structured_legal_analysis_results)
    source_ids = _source_ids(results)
    case_ids = {item.case_id for item in results}
    if len(case_ids) != 1:
        _fail("StructuredLegalAnalysisResult collection must contain exactly one case.")
    case_id = next(iter(case_ids))
    try:
        require_canonical_case_id(case_id)
    except ValueError as exc:
        _fail("Structured analytical case_id is not canonical.", exc)

    try:
        validate_case_matrices(case_matrices)
    except (TypeError, ValueError) as exc:
        _fail("CaseMatrices is invalid.", exc)
    if case_matrices.case_id != case_id:
        _fail("CaseMatrices case_id does not match StructuredLegalAnalysisResult state.")
    if tuple(sorted(case_matrices.source_analysis_ids)) != source_ids:
        _fail("CaseMatrices source_analysis_ids do not match the complete M5 source set.")

    # Equality validation only: supplied matrices must already equal the deterministic
    # projection of the complete supplied M5 graph.  The rebuilt tuples never become
    # candidate authority state and are never persisted.
    try:
        expected_issues = build_issue_matrix(results)
        expected_evidence = build_evidence_matrix(results)
    except (TypeError, ValueError) as exc:
        _fail("Complete M5 graph cannot validate against frozen M2 projection rules.", exc)
    if case_matrices.issue_matrix != expected_issues:
        _fail("Supplied CaseMatrices.issue_matrix does not exactly match the complete M5 graph.")
    if case_matrices.evidence_matrix != expected_evidence:
        _fail("Supplied CaseMatrices.evidence_matrix does not exactly match the complete M5 graph.")

    try:
        validate_governed_issue_evidence_map(governed_issue_evidence_map)
    except (TypeError, ValueError) as exc:
        _fail("GovernedIssueEvidenceMap is invalid.", exc)
    u9b = governed_issue_evidence_map
    if u9b.case_id != case_id:
        _fail("U9B case_id does not match the analytical generation.")
    if u9b.source_synthesis_id != case_matrices.synthesis_id:
        _fail("U9B source_synthesis_id does not match CaseMatrices.synthesis_id.")
    if u9b.source_matrices_schema_version != case_matrices.schema_version:
        _fail("U9B source matrix schema does not match CaseMatrices.")
    if u9b.source_matrix_builder_version != case_matrices.matrix_builder_version:
        _fail("U9B source matrix builder does not match CaseMatrices.")
    if tuple(sorted(u9b.source_analysis_ids)) != source_ids:
        _fail("U9B source_analysis_ids do not match the complete analytical source set.")

    matrix_uses = _matrix_use_index(case_matrices)
    governed_uses = _governed_use_index(u9b)
    if set(matrix_uses) != set(governed_uses):
        missing = sorted(set(matrix_uses) - set(governed_uses))
        extra = sorted(set(governed_uses) - set(matrix_uses))
        _fail(f"U9B/CaseMatrices EvidenceUse topology mismatch; missing={missing}, extra={extra}.")
    for identity, matrix_use in matrix_uses.items():
        if _matrix_use_state(matrix_use) != _u9b_use_state(governed_uses[identity]):
            _fail(f"U9B EvidenceUse state disagrees with CaseMatrices at {identity!r}.")

    mapped_keys = {identity[2] for identity in matrix_uses}
    if mapped_keys & set(u9b.unmapped_evidence_keys):
        _fail("U9B unmapped_evidence overlaps CaseMatrices analytical EvidenceUses.")

    try:
        validate_governed_evidential_analysis(governed_evidential_analysis, u9b)
    except (TypeError, ValueError) as exc:
        _fail("GovernedEvidentialAnalysis is invalid against the exact U9B state.", exc)
    if governed_evidential_analysis.case_id != case_id:
        _fail("U9C-B1 case_id does not match the analytical generation.")

    return source_ids


def build_governed_analytical_authority_manifest(
    *,
    structured_legal_analysis_results: Iterable[StructuredLegalAnalysisResult],
    case_matrices: Any,
    governed_issue_evidence_map: Any,
    governed_evidential_analysis: Any,
) -> GovernedAnalyticalAuthorityManifest:
    """Build the non-substantive B4 content manifest from a complete supplied bundle."""

    results = tuple(structured_legal_analysis_results)
    source_ids = validate_governed_analytical_authority_components(
        structured_legal_analysis_results=results,
        case_matrices=case_matrices,
        governed_issue_evidence_map=governed_issue_evidence_map,
        governed_evidential_analysis=governed_evidential_analysis,
    )
    m5_payload = dumps_structured_legal_analysis_results(results)
    matrices_payload = dumps_case_matrices(case_matrices)
    u9b_payload = dumps_governed_issue_evidence_map(governed_issue_evidence_map)
    u9c_payload = dumps_governed_evidential_analysis(
        governed_evidential_analysis,
        governed_issue_evidence_map,
    )
    component_hashes = {
        "structured_legal_analysis_results_sha256": canonical_sha256(m5_payload),
        "case_matrices_sha256": canonical_sha256(matrices_payload),
        "governed_issue_evidence_map_sha256": canonical_sha256(u9b_payload),
        "governed_evidential_analysis_sha256": canonical_sha256(u9c_payload),
    }
    case_id = results[0].case_id
    authority_id = derive_governed_analytical_authority_id(
        case_id=case_id,
        **component_hashes,
    )
    manifest = GovernedAnalyticalAuthorityManifest(
        schema_version=GOVERNED_ANALYTICAL_AUTHORITY_MANIFEST_SCHEMA_VERSION,
        identity_version=GOVERNED_ANALYTICAL_AUTHORITY_IDENTITY_VERSION,
        case_id=case_id,
        source_analysis_ids=source_ids,
        authority_id=authority_id,
        **component_hashes,
    )
    validate_governed_analytical_authority_manifest(
        manifest,
        structured_legal_analysis_results=results,
        case_matrices=case_matrices,
        governed_issue_evidence_map=governed_issue_evidence_map,
        governed_evidential_analysis=governed_evidential_analysis,
    )
    return manifest


def validate_governed_analytical_authority_manifest(
    manifest: GovernedAnalyticalAuthorityManifest,
    *,
    structured_legal_analysis_results: Iterable[StructuredLegalAnalysisResult],
    case_matrices: Any,
    governed_issue_evidence_map: Any,
    governed_evidential_analysis: Any,
) -> None:
    """Validate manifest identity, canonical hashes and complete cross-component lineage."""

    if not isinstance(manifest, GovernedAnalyticalAuthorityManifest):
        _fail("manifest must be a GovernedAnalyticalAuthorityManifest.")
    if manifest.schema_version != GOVERNED_ANALYTICAL_AUTHORITY_MANIFEST_SCHEMA_VERSION:
        _fail("Unsupported governed analytical-authority manifest schema.")
    if manifest.identity_version != GOVERNED_ANALYTICAL_AUTHORITY_IDENTITY_VERSION:
        _fail("Unsupported governed analytical-authority identity version.")
    try:
        require_canonical_case_id(manifest.case_id)
    except ValueError as exc:
        _fail("Manifest case_id is not canonical.", exc)

    results = tuple(structured_legal_analysis_results)
    source_ids = validate_governed_analytical_authority_components(
        structured_legal_analysis_results=results,
        case_matrices=case_matrices,
        governed_issue_evidence_map=governed_issue_evidence_map,
        governed_evidential_analysis=governed_evidential_analysis,
    )
    if not results or results[0].case_id != manifest.case_id:
        _fail("Manifest case_id does not match the supplied analytical bundle.")
    if manifest.source_analysis_ids != source_ids:
        _fail("Manifest source_analysis_ids are not the exact canonical source set.")

    expected_hashes = {
        "structured_legal_analysis_results_sha256": canonical_sha256(
            dumps_structured_legal_analysis_results(results)
        ),
        "case_matrices_sha256": canonical_sha256(dumps_case_matrices(case_matrices)),
        "governed_issue_evidence_map_sha256": canonical_sha256(
            dumps_governed_issue_evidence_map(governed_issue_evidence_map)
        ),
        "governed_evidential_analysis_sha256": canonical_sha256(
            dumps_governed_evidential_analysis(
                governed_evidential_analysis,
                governed_issue_evidence_map,
            )
        ),
    }
    for field_name, expected in expected_hashes.items():
        observed = getattr(manifest, field_name)
        try:
            require_sha256_id(observed, field_name=field_name)
        except ValueError as exc:
            _fail(f"Manifest {field_name} is malformed.", exc)
        if observed != expected:
            _fail(f"Manifest {field_name} does not match canonical component bytes.")

    expected_id = derive_governed_analytical_authority_id(
        case_id=manifest.case_id,
        schema_version=manifest.schema_version,
        identity_version=manifest.identity_version,
        **expected_hashes,
    )
    if manifest.authority_id != expected_id:
        _fail("Manifest authority_id does not match the exact four-component identity payload.")


def validate_governed_analytical_authority_active_pointer(
    pointer: GovernedAnalyticalAuthorityActivePointer,
) -> None:
    """Validate the tiny non-substantive active pointer."""

    if not isinstance(pointer, GovernedAnalyticalAuthorityActivePointer):
        _fail("pointer must be a GovernedAnalyticalAuthorityActivePointer.")
    if pointer.schema_version != GOVERNED_ANALYTICAL_AUTHORITY_POINTER_SCHEMA_VERSION:
        _fail("Unsupported governed analytical-authority pointer schema.")
    try:
        require_canonical_case_id(pointer.case_id)
        require_sha256_id(pointer.authority_id, field_name="authority_id")
        require_sha256_id(
            pointer.authority_manifest_sha256,
            field_name="authority_manifest_sha256",
        )
        require_sha256_id(pointer.activation_id, field_name="activation_id")
    except ValueError as exc:
        _fail("Active pointer identity is malformed.", exc)


def validate_governed_analytical_authority_activation_receipt(
    receipt: GovernedAnalyticalAuthorityActivationReceipt,
    *,
    active_pointer: GovernedAnalyticalAuthorityActivePointer,
    previous_active_pointer_payload: str | None = None,
) -> None:
    """Validate one immutable lifecycle receipt against the new active pointer."""

    if not isinstance(receipt, GovernedAnalyticalAuthorityActivationReceipt):
        _fail("receipt must be a GovernedAnalyticalAuthorityActivationReceipt.")
    if receipt.schema_version != GOVERNED_ANALYTICAL_AUTHORITY_ACTIVATION_SCHEMA_VERSION:
        _fail("Unsupported governed analytical-authority activation schema.")
    if not isinstance(receipt.action, GovernedAnalyticalAuthorityActivationAction):
        _fail("Activation receipt action is invalid.")
    validate_governed_analytical_authority_active_pointer(active_pointer)
    if receipt.case_id != active_pointer.case_id:
        _fail("Activation receipt case_id does not match active pointer.")
    if receipt.activation_id != active_pointer.activation_id:
        _fail("Activation receipt activation_id does not match active pointer.")
    if receipt.new_authority_id != active_pointer.authority_id:
        _fail("Activation receipt new_authority_id does not match active pointer.")

    for field_name in ("activation_id", "new_authority_id", "new_active_pointer_sha256"):
        try:
            require_sha256_id(getattr(receipt, field_name), field_name=field_name)
        except ValueError as exc:
            _fail(f"Activation receipt {field_name} is malformed.", exc)
    for field_name in (
        "previous_activation_id",
        "previous_authority_id",
        "previous_active_pointer_sha256",
    ):
        value = getattr(receipt, field_name)
        if value is not None:
            try:
                require_sha256_id(value, field_name=field_name)
            except ValueError as exc:
                _fail(f"Activation receipt {field_name} is malformed.", exc)

    expected_new_pointer_sha = canonical_sha256(
        dumps_governed_analytical_authority_active_pointer(active_pointer)
    )
    if receipt.new_active_pointer_sha256 != expected_new_pointer_sha:
        _fail("Activation receipt does not bind the exact new active-pointer bytes.")

    if previous_active_pointer_payload is None:
        if any(
            value is not None
            for value in (
                receipt.previous_activation_id,
                receipt.previous_authority_id,
                receipt.previous_active_pointer_sha256,
            )
        ):
            _fail("First activation cannot claim previous active-pointer provenance.")
        if receipt.action is not GovernedAnalyticalAuthorityActivationAction.ACTIVATE:
            _fail("First active-pointer transition must use ACTIVATE.")
    else:
        try:
            from .serialization import loads_governed_analytical_authority_active_pointer

            previous_pointer = loads_governed_analytical_authority_active_pointer(
                previous_active_pointer_payload
            )
            validate_governed_analytical_authority_active_pointer(previous_pointer)
        except (TypeError, ValueError) as exc:
            _fail("Previous active-pointer provenance is invalid.", exc)
        if previous_pointer.case_id != receipt.case_id:
            _fail("Previous active pointer belongs to a different case.")
        if receipt.previous_activation_id != previous_pointer.activation_id:
            _fail("Activation receipt previous_activation_id mismatch.")
        if receipt.previous_authority_id != previous_pointer.authority_id:
            _fail("Activation receipt previous_authority_id mismatch.")
        if receipt.previous_active_pointer_sha256 != canonical_sha256(
            previous_active_pointer_payload
        ):
            _fail("Activation receipt previous pointer SHA mismatch.")

    expected_activation_id = derive_governed_analytical_authority_activation_id(
        case_id=receipt.case_id,
        action=receipt.action,
        previous_activation_id=receipt.previous_activation_id,
        previous_authority_id=receipt.previous_authority_id,
        new_authority_id=receipt.new_authority_id,
        previous_active_pointer_sha256=receipt.previous_active_pointer_sha256,
        schema_version=receipt.schema_version,
    )
    if receipt.activation_id != expected_activation_id:
        _fail("Activation receipt activation_id is not deterministic for its transition.")


__all__ = [
    "GovernedAnalyticalAuthorityValidationError",
    "build_governed_analytical_authority_manifest",
    "validate_governed_analytical_authority_activation_receipt",
    "validate_governed_analytical_authority_active_pointer",
    "validate_governed_analytical_authority_components",
    "validate_governed_analytical_authority_manifest",
]
