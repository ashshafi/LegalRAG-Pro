"""Harness-only deterministic envelope for Sprint 2.4 M3 frozen inputs.

H2 deliberately implements only the frozen snapshot manifest/envelope.  It
reuses the H1 M5 serializer and the existing production M1/M2 serializers;
it does not reconstruct Gate 1 native inputs or run any analytical pipeline.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any, Final

from case_analysis import serialization as m1_serialization
from case_analysis.m2 import matrix_serialization as m2_serialization
from case_analysis.m2.matrices import CaseMatrices
from case_analysis.models import CaseAnalysisFoundation
from legal_analysis.legal_analysis import StructuredLegalAnalysisResult

from case_analysis_m3_frozen_m5_serialization import (
    structured_legal_analysis_result_to_dict,
)

FROZEN_SNAPSHOT_SCHEMA_VERSION: Final[str] = "m3-frozen-analytical-snapshot/1.0"
HASH_ALGORITHM: Final[str] = "sha256"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_text(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _require_sha256(value: object, *, field_name: str) -> str:
    text = str(value).strip().lower()
    if not _SHA256_RE.fullmatch(text):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest.")
    return text


def _require_text(value: object, *, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty.")
    return text


def _m5_sort_key(value: StructuredLegalAnalysisResult) -> tuple[str, str, str]:
    analysis = value.assessment_result.assessed_analysis
    return (
        analysis.issue_definition_id,
        analysis.issue_definition_version,
        analysis.issue_analysis_id,
    )


def _canonical_m5_component(
    results: Iterable[StructuredLegalAnalysisResult],
) -> list[dict[str, Any]]:
    resolved = tuple(results)
    if not resolved:
        raise ValueError("Frozen snapshot requires at least one M5 result.")
    ordered = tuple(sorted(resolved, key=_m5_sort_key))
    keys = tuple(_m5_sort_key(item) for item in ordered)
    if len(keys) != len(set(keys)):
        raise ValueError("Frozen snapshot M5 result identities must be unique.")
    return [structured_legal_analysis_result_to_dict(item) for item in ordered]


def _component_hashes(components: Mapping[str, Any]) -> dict[str, str]:
    return {
        "m5_results_sha256": _sha256_text(_canonical_json(components["m5_results"])),
        "foundation_sha256": _sha256_text(_canonical_json(components["foundation"])),
        "matrices_sha256": _sha256_text(_canonical_json(components["matrices"])),
    }


def _analytical_state_sha256(component_hashes: Mapping[str, str]) -> str:
    analytical_manifest = {
        "m5_results_sha256": component_hashes["m5_results_sha256"],
        "foundation_sha256": component_hashes["foundation_sha256"],
        "matrices_sha256": component_hashes["matrices_sha256"],
    }
    return _sha256_text(_canonical_json(analytical_manifest))


def _m5_identity_fields(component: list[dict[str, Any]]) -> tuple[tuple[str, str, str, str], ...]:
    identities: list[tuple[str, str, str, str]] = []
    for item in component:
        try:
            analysis = item["assessment_result"]["assessed_analysis"]
            identities.append(
                (
                    str(analysis["case_id"]),
                    str(analysis["issue_definition_id"]),
                    str(analysis["issue_definition_version"]),
                    str(analysis["issue_analysis_id"]),
                )
            )
        except (KeyError, TypeError) as exc:
            raise ValueError("M5 component is missing required analytical identity fields.") from exc
    return tuple(identities)


def _validate_manifest_relationships(snapshot: Mapping[str, Any]) -> None:
    manifest = snapshot["manifest"]
    components = snapshot["components"]
    foundation = components["foundation"]
    matrices = components["matrices"]
    m5_identities = _m5_identity_fields(components["m5_results"])

    case_id = _require_text(manifest.get("case_id"), field_name="manifest.case_id")
    synthesis_id = _require_text(
        manifest.get("synthesis_id"), field_name="manifest.synthesis_id"
    )
    manifest_source_ids = tuple(str(item) for item in manifest.get("source_analysis_ids", ()))
    if not manifest_source_ids or len(manifest_source_ids) != len(set(manifest_source_ids)):
        raise ValueError("manifest.source_analysis_ids must be non-empty and unique.")

    if str(foundation.get("case_id")) != case_id or str(matrices.get("case_id")) != case_id:
        raise ValueError("Snapshot manifest case_id does not match M1/M2 components.")
    if any(identity[0] != case_id for identity in m5_identities):
        raise ValueError("Snapshot M5 case_id does not match manifest.case_id.")

    if str(foundation.get("synthesis_id")) != synthesis_id:
        raise ValueError("Snapshot manifest synthesis_id does not match M1 foundation.")
    if str(matrices.get("synthesis_id")) != synthesis_id:
        raise ValueError("Snapshot manifest synthesis_id does not match M2 matrices.")

    foundation_source_ids = tuple(
        str(item["issue_analysis_id"]) for item in foundation.get("source_analyses", ())
    )
    matrix_source_ids = tuple(str(item) for item in matrices.get("source_analysis_ids", ()))
    m5_source_ids = tuple(identity[3] for identity in m5_identities)
    expected_set = set(manifest_source_ids)
    if set(foundation_source_ids) != expected_set:
        raise ValueError("M1 source-analysis IDs do not match snapshot manifest.")
    if set(matrix_source_ids) != expected_set:
        raise ValueError("M2 source-analysis IDs do not match snapshot manifest.")
    if set(m5_source_ids) != expected_set:
        raise ValueError("M5 source-analysis IDs do not match snapshot manifest.")


def build_frozen_snapshot(
    *,
    results: Iterable[StructuredLegalAnalysisResult],
    foundation: CaseAnalysisFoundation,
    matrices: CaseMatrices,
    legacy_fixture_name: str,
    legacy_fixture_version: str,
    legacy_fixture_sha256: str,
    captured_at: str,
    source_checkpoint: str,
) -> dict[str, Any]:
    """Build one deterministic H2 snapshot envelope from existing native inputs.

    This function serializes supplied M5/M1/M2 objects.  It never rebuilds M1
    or M2 and never invokes retrieval, OpenAI, mapping, assessment, or M5.
    """

    m5_component = _canonical_m5_component(results)
    foundation_component = json.loads(m1_serialization.dumps_case_analysis_foundation(foundation))
    matrices_component = json.loads(m2_serialization.dumps_case_matrices(matrices))
    components = {
        "m5_results": m5_component,
        "foundation": foundation_component,
        "matrices": matrices_component,
    }
    hashes = _component_hashes(components)
    analytical_hash = _analytical_state_sha256(hashes)

    snapshot = {
        "schema_version": FROZEN_SNAPSHOT_SCHEMA_VERSION,
        "hash_algorithm": HASH_ALGORITHM,
        "analytical_state_sha256": analytical_hash,
        "component_hashes": hashes,
        "manifest": {
            "case_id": foundation.case_id,
            "synthesis_id": foundation.synthesis_id,
            "source_analysis_ids": list(foundation.source_issue_analysis_ids),
            "captured_at": _require_text(captured_at, field_name="captured_at"),
            "source_checkpoint": _require_text(
                source_checkpoint, field_name="source_checkpoint"
            ),
            "legacy_fixture": {
                "name": _require_text(
                    legacy_fixture_name, field_name="legacy_fixture_name"
                ),
                "fixture_version": _require_text(
                    legacy_fixture_version, field_name="legacy_fixture_version"
                ),
                "sha256": _require_sha256(
                    legacy_fixture_sha256, field_name="legacy_fixture_sha256"
                ),
            },
        },
        "components": components,
    }
    validate_frozen_snapshot(snapshot)
    return snapshot


def validate_frozen_snapshot(
    snapshot: Mapping[str, Any],
    *,
    expected_legacy_fixture_sha256: str | None = None,
) -> None:
    """Fail closed unless the H2 envelope is internally consistent."""

    if not isinstance(snapshot, Mapping):
        raise ValueError("Frozen analytical snapshot must contain an object at the root.")
    if snapshot.get("schema_version") != FROZEN_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported frozen snapshot schema {snapshot.get('schema_version')!r}."
        )
    if snapshot.get("hash_algorithm") != HASH_ALGORITHM:
        raise ValueError("Unsupported frozen snapshot hash algorithm.")

    components = snapshot.get("components")
    component_hashes = snapshot.get("component_hashes")
    manifest = snapshot.get("manifest")
    if not isinstance(components, Mapping):
        raise ValueError("Frozen snapshot components must contain an object.")
    if not isinstance(component_hashes, Mapping):
        raise ValueError("Frozen snapshot component_hashes must contain an object.")
    if not isinstance(manifest, Mapping):
        raise ValueError("Frozen snapshot manifest must contain an object.")
    if set(components) != {"m5_results", "foundation", "matrices"}:
        raise ValueError("Frozen snapshot components must contain exactly M5, M1 and M2.")
    if not isinstance(components["m5_results"], list) or not components["m5_results"]:
        raise ValueError("Frozen snapshot M5 component must be a non-empty list.")
    if not isinstance(components["foundation"], Mapping):
        raise ValueError("Frozen snapshot M1 component must contain an object.")
    if not isinstance(components["matrices"], Mapping):
        raise ValueError("Frozen snapshot M2 component must contain an object.")

    expected_hashes = _component_hashes(components)
    if dict(component_hashes) != expected_hashes:
        raise ValueError("Frozen snapshot component hash verification failed.")
    expected_analytical_hash = _analytical_state_sha256(expected_hashes)
    if snapshot.get("analytical_state_sha256") != expected_analytical_hash:
        raise ValueError("Frozen snapshot analytical-state hash verification failed.")

    legacy = manifest.get("legacy_fixture")
    if not isinstance(legacy, Mapping):
        raise ValueError("manifest.legacy_fixture must contain an object.")
    _require_text(legacy.get("name"), field_name="manifest.legacy_fixture.name")
    _require_text(
        legacy.get("fixture_version"),
        field_name="manifest.legacy_fixture.fixture_version",
    )
    actual_legacy_sha = _require_sha256(
        legacy.get("sha256"), field_name="manifest.legacy_fixture.sha256"
    )
    if expected_legacy_fixture_sha256 is not None:
        expected = _require_sha256(
            expected_legacy_fixture_sha256,
            field_name="expected_legacy_fixture_sha256",
        )
        if actual_legacy_sha != expected:
            raise ValueError("Frozen snapshot legacy-fixture SHA does not match expectation.")

    _require_text(manifest.get("captured_at"), field_name="manifest.captured_at")
    _require_text(
        manifest.get("source_checkpoint"), field_name="manifest.source_checkpoint"
    )
    _validate_manifest_relationships(snapshot)


def dumps_frozen_snapshot(snapshot: Mapping[str, Any]) -> str:
    """Validate and return canonical deterministic JSON for one H2 envelope."""

    validate_frozen_snapshot(snapshot)
    return _canonical_json(snapshot)


def loads_frozen_snapshot(
    payload: str,
    *,
    expected_legacy_fixture_sha256: str | None = None,
) -> dict[str, Any]:
    """Load and validate one H2 envelope without reconstructing native inputs."""

    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("Frozen analytical snapshot payload must contain an object.")
    validate_frozen_snapshot(
        parsed,
        expected_legacy_fixture_sha256=expected_legacy_fixture_sha256,
    )
    return parsed


__all__ = [
    "FROZEN_SNAPSHOT_SCHEMA_VERSION",
    "HASH_ALGORITHM",
    "build_frozen_snapshot",
    "dumps_frozen_snapshot",
    "loads_frozen_snapshot",
    "validate_frozen_snapshot",
]
