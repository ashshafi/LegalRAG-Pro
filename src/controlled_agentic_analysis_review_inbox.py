"""Read-only discovery of published CAA observations for PRW1 professional review.

PRW2 does not create analytical-change proposals and does not alter governed
authority.  It reconstructs only immutable CAA1/CAA2 publication records,
validates their exact source/run identities, and joins them to the append-only
PRW1 review ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import stat
from typing import Any

from controlled_agentic_analysis import (
    AgentObservation,
    CAA1EvidenceRef,
    CAA1Error,
    FrozenInspectionUniverse,
    Materiality,
    ObservationConfidence,
    ObservationType,
    RecommendedAction,
    dumps_agent_observation,
    dumps_frozen_inspection_universe,
    validate_agent_observation,
    validate_frozen_inspection_universe,
)
from controlled_agentic_analysis_gaps import (
    CAA2Error,
    GapAgentObservation,
    GapCandidate,
    GapObservationType,
    dumps_gap_candidates,
    dumps_gap_observation,
)
from controlled_agentic_analysis_publication import CAA1_PUBLICATION_ROOT
from controlled_agentic_analysis_gaps_publication import (
    CAA2_PUBLICATION_MANIFEST_SCHEMA,
    CAA2_PUBLICATION_ROOT,
)
from controlled_agentic_analysis_review import (
    ObservationSource,
    ProfessionalReviewEvent,
    ProfessionalReviewProjection,
    project_professional_review,
)
from controlled_agentic_analysis_review_publication import (
    ProfessionalReviewPublicationError,
    load_professional_review_events,
)


PRW2_INBOX_SCHEMA_VERSION = "controlled-agentic-professional-review-inbox/v1"


class ProfessionalReviewInboxError(RuntimeError):
    """Raised when immutable CAA review-inbox discovery fails closed."""


@dataclass(frozen=True, slots=True)
class ProfessionalReviewInboxItem:
    schema_version: str
    source_agent: ObservationSource
    run: FrozenInspectionUniverse
    observation: AgentObservation | GapAgentObservation
    publication_path: Path
    review_events: tuple[ProfessionalReviewEvent, ...]
    review_projection: ProfessionalReviewProjection | None


def _fail(message: str) -> None:
    raise ProfessionalReviewInboxError(message)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _is_reparse(path: Path) -> bool:
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(
        attributes
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _require_plain_directory(path: Path, *, label: str) -> None:
    if (
        path.is_symlink()
        or _is_reparse(path)
        or not path.is_dir()
    ):
        _fail(f"{label} is not a plain directory: {path}")


def _require_plain_file(path: Path, *, label: str) -> None:
    if (
        path.is_symlink()
        or _is_reparse(path)
        or not path.is_file()
    ):
        _fail(f"{label} is not a plain regular file: {path}")


def _case_component(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("case_id must be non-empty text.")
    result = value.strip()
    if result in {".", ".."} or "/" in result or "\\" in result:
        _fail("case_id must not contain path separators.")
    return result


def _storage_digest(value: str, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        _fail(f"{label} must be 64 lowercase hexadecimal characters.")
    return value


def _read_bytes(path: Path, *, label: str) -> bytes:
    _require_plain_file(path, label=label)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ProfessionalReviewInboxError(
            f"Unable to read {label}: {path}"
        ) from exc


def _json_from_bytes(payload: bytes, *, label: str) -> Any:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProfessionalReviewInboxError(
            f"{label} must be UTF-8."
        ) from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProfessionalReviewInboxError(
            f"{label} is not valid JSON."
        ) from exc


def _exact_object(
    value: Any,
    *,
    keys: set[str],
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        _fail(f"{label} keys are invalid.")
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_sha(value: Any) -> str:
    return "sha256:" + sha256(_canonical_json_bytes(value)).hexdigest()


def _load_ref(value: Any, *, label: str) -> CAA1EvidenceRef:
    data = _exact_object(
        value,
        keys={
            "schema_version",
            "case_id",
            "evidence_key",
            "evidence_binding_sha256",
        },
        label=label,
    )
    try:
        return CAA1EvidenceRef(
            schema_version=data["schema_version"],
            case_id=data["case_id"],
            evidence_key=data["evidence_key"],
            evidence_binding_sha256=data["evidence_binding_sha256"],
        )
    except (CAA1Error, TypeError, ValueError) as exc:
        raise ProfessionalReviewInboxError(
            f"{label} is invalid."
        ) from exc


def _load_run(path: Path) -> FrozenInspectionUniverse:
    payload = _read_bytes(path, label="CAA frozen run")
    data = _exact_object(
        _json_from_bytes(payload, label="CAA frozen run"),
        keys={
            "schema_version",
            "case_id",
            "active_authority_id",
            "evidence_scope_id",
            "evidence_bindings",
            "agent_definition_version",
            "analysis_engine_identity",
            "execution_configuration_sha256",
            "analysis_run_id",
        },
        label="CAA frozen run",
    )
    if not isinstance(data["evidence_bindings"], list):
        _fail("CAA frozen run evidence_bindings must be a list.")
    refs = tuple(
        _load_ref(item, label="CAA frozen run evidence reference")
        for item in data["evidence_bindings"]
    )
    try:
        run = FrozenInspectionUniverse(
            schema_version=data["schema_version"],
            case_id=data["case_id"],
            active_authority_id=data["active_authority_id"],
            evidence_scope_id=data["evidence_scope_id"],
            evidence_bindings=refs,
            agent_definition_version=data["agent_definition_version"],
            analysis_engine_identity=data["analysis_engine_identity"],
            execution_configuration_sha256=data[
                "execution_configuration_sha256"
            ],
            analysis_run_id=data["analysis_run_id"],
        )
        validate_frozen_inspection_universe(run)
    except (CAA1Error, TypeError, ValueError) as exc:
        raise ProfessionalReviewInboxError(
            "CAA frozen run failed sealed validation."
        ) from exc

    if dumps_frozen_inspection_universe(run).encode("utf-8") != payload:
        _fail("CAA frozen run bytes are not canonical.")
    return run


def _load_caa1_observation(
    *,
    path: Path,
    run: FrozenInspectionUniverse,
) -> AgentObservation:
    payload = _read_bytes(path, label="CAA1 observation")
    data = _exact_object(
        _json_from_bytes(payload, label="CAA1 observation"),
        keys={
            "schema_version",
            "observation_id",
            "case_id",
            "active_authority_id",
            "analysis_run_id",
            "agent_definition_version",
            "issue_analysis_id",
            "element_id",
            "observation_type",
            "title",
            "summary",
            "supporting_evidence_bindings",
            "contrary_evidence_bindings",
            "reasoning_summary",
            "materiality",
            "observation_confidence",
            "uncertainty",
            "limitations",
            "recommended_action",
        },
        label="CAA1 observation",
    )

    if not isinstance(data["supporting_evidence_bindings"], list):
        _fail("CAA1 supporting_evidence_bindings must be a list.")
    if not isinstance(data["contrary_evidence_bindings"], list):
        _fail("CAA1 contrary_evidence_bindings must be a list.")
    if not isinstance(data["limitations"], list):
        _fail("CAA1 limitations must be a list.")

    try:
        observation = AgentObservation(
            schema_version=data["schema_version"],
            observation_id=data["observation_id"],
            case_id=data["case_id"],
            active_authority_id=data["active_authority_id"],
            analysis_run_id=data["analysis_run_id"],
            agent_definition_version=data["agent_definition_version"],
            issue_analysis_id=data["issue_analysis_id"],
            element_id=data["element_id"],
            observation_type=ObservationType(data["observation_type"]),
            title=data["title"],
            summary=data["summary"],
            supporting_evidence_bindings=tuple(
                _load_ref(
                    item,
                    label="CAA1 supporting evidence reference",
                )
                for item in data["supporting_evidence_bindings"]
            ),
            contrary_evidence_bindings=tuple(
                _load_ref(
                    item,
                    label="CAA1 contrary evidence reference",
                )
                for item in data["contrary_evidence_bindings"]
            ),
            reasoning_summary=data["reasoning_summary"],
            materiality=Materiality(data["materiality"]),
            observation_confidence=ObservationConfidence(
                data["observation_confidence"]
            ),
            uncertainty=data["uncertainty"],
            limitations=tuple(data["limitations"]),
            recommended_action=RecommendedAction(
                data["recommended_action"]
            ),
        )
        validate_agent_observation(
            run=run,
            observation=observation,
        )
    except (CAA1Error, TypeError, ValueError) as exc:
        raise ProfessionalReviewInboxError(
            "CAA1 observation failed sealed validation."
        ) from exc

    if dumps_agent_observation(observation).encode("utf-8") != payload:
        _fail("CAA1 observation bytes are not canonical.")
    if path.stem != observation.observation_id[7:]:
        _fail("CAA1 observation filename does not match observation_id.")
    return observation


def _load_caa2_candidate(value: Any) -> GapCandidate:
    data = _exact_object(
        value,
        keys={
            "schema_version",
            "candidate_id",
            "case_id",
            "active_authority_id",
            "analysis_run_id",
            "issue_analysis_id",
            "issue_definition_id",
            "element_id",
            "gap_type",
            "legal_question",
            "finding_text",
            "related_evidence_keys",
            "governed_basis",
            "requires_engine_confirmation",
        },
        label="CAA2 candidate",
    )
    if not isinstance(data["related_evidence_keys"], list):
        _fail("CAA2 related_evidence_keys must be a list.")

    identity = dict(data)
    candidate_id = identity.pop("candidate_id")
    if _canonical_sha(identity) != candidate_id:
        _fail("CAA2 candidate identity is invalid.")

    try:
        return GapCandidate(
            schema_version=data["schema_version"],
            candidate_id=candidate_id,
            case_id=data["case_id"],
            active_authority_id=data["active_authority_id"],
            analysis_run_id=data["analysis_run_id"],
            issue_analysis_id=data["issue_analysis_id"],
            issue_definition_id=data["issue_definition_id"],
            element_id=data["element_id"],
            gap_type=GapObservationType(data["gap_type"]),
            legal_question=data["legal_question"],
            finding_text=data["finding_text"],
            related_evidence_keys=tuple(data["related_evidence_keys"]),
            governed_basis=data["governed_basis"],
            requires_engine_confirmation=data[
                "requires_engine_confirmation"
            ],
        )
    except (CAA2Error, TypeError, ValueError) as exc:
        raise ProfessionalReviewInboxError(
            "CAA2 candidate failed sealed validation."
        ) from exc


def _load_caa2_observation(
    *,
    path: Path,
    run: FrozenInspectionUniverse,
    candidate_by_id: dict[str, GapCandidate],
) -> GapAgentObservation:
    payload = _read_bytes(path, label="CAA2 observation")
    data = _exact_object(
        _json_from_bytes(payload, label="CAA2 observation"),
        keys={
            "schema_version",
            "observation_id",
            "candidate_id",
            "case_id",
            "active_authority_id",
            "analysis_run_id",
            "issue_analysis_id",
            "element_id",
            "observation_type",
            "title",
            "summary",
            "finding_text",
            "inspected_evidence_bindings",
            "reasoning_summary",
            "materiality",
            "observation_confidence",
            "uncertainty",
            "limitations",
            "recommended_action",
        },
        label="CAA2 observation",
    )
    if not isinstance(data["inspected_evidence_bindings"], list):
        _fail("CAA2 inspected_evidence_bindings must be a list.")
    if not isinstance(data["limitations"], list):
        _fail("CAA2 limitations must be a list.")

    identity = dict(data)
    observation_id = identity.pop("observation_id")
    if _canonical_sha(identity) != observation_id:
        _fail("CAA2 observation identity is invalid.")

    try:
        observation = GapAgentObservation(
            schema_version=data["schema_version"],
            observation_id=observation_id,
            candidate_id=data["candidate_id"],
            case_id=data["case_id"],
            active_authority_id=data["active_authority_id"],
            analysis_run_id=data["analysis_run_id"],
            issue_analysis_id=data["issue_analysis_id"],
            element_id=data["element_id"],
            observation_type=GapObservationType(
                data["observation_type"]
            ),
            title=data["title"],
            summary=data["summary"],
            finding_text=data["finding_text"],
            inspected_evidence_bindings=tuple(
                _load_ref(
                    item,
                    label="CAA2 inspected evidence reference",
                )
                for item in data["inspected_evidence_bindings"]
            ),
            reasoning_summary=data["reasoning_summary"],
            materiality=Materiality(data["materiality"]),
            observation_confidence=ObservationConfidence(
                data["observation_confidence"]
            ),
            uncertainty=data["uncertainty"],
            limitations=tuple(data["limitations"]),
            recommended_action=RecommendedAction(
                data["recommended_action"]
            ),
        )
    except (CAA1Error, CAA2Error, TypeError, ValueError) as exc:
        raise ProfessionalReviewInboxError(
            "CAA2 observation failed sealed validation."
        ) from exc

    if observation.case_id != run.case_id:
        _fail("CAA2 observation case_id does not match frozen run.")
    if observation.active_authority_id != run.active_authority_id:
        _fail("CAA2 observation authority does not match frozen run.")
    if observation.analysis_run_id != run.analysis_run_id:
        _fail("CAA2 observation analysis_run_id does not match frozen run.")

    allowed = {
        (
            ref.evidence_key,
            ref.evidence_binding_sha256,
        )
        for ref in run.evidence_bindings
    }
    used = {
        (
            ref.evidence_key,
            ref.evidence_binding_sha256,
        )
        for ref in observation.inspected_evidence_bindings
    }
    if not used.issubset(allowed):
        _fail("CAA2 observation references evidence outside frozen run.")

    candidate = candidate_by_id.get(observation.candidate_id)
    if candidate is None:
        _fail("CAA2 observation references an unknown candidate.")
    if candidate.case_id != run.case_id:
        _fail("CAA2 candidate case_id does not match frozen run.")
    if candidate.active_authority_id != run.active_authority_id:
        _fail("CAA2 candidate authority does not match frozen run.")
    if candidate.analysis_run_id != run.analysis_run_id:
        _fail("CAA2 candidate analysis_run_id does not match frozen run.")
    if observation.issue_analysis_id != candidate.issue_analysis_id:
        _fail("CAA2 observation issue does not match candidate.")
    if observation.element_id != candidate.element_id:
        _fail("CAA2 observation element does not match candidate.")
    if observation.observation_type is not candidate.gap_type:
        _fail("CAA2 observation type does not match candidate.")
    if observation.finding_text != candidate.finding_text:
        _fail("CAA2 observation finding_text does not match candidate.")

    if dumps_gap_observation(observation).encode("utf-8") != payload:
        _fail("CAA2 observation bytes are not canonical.")
    if path.stem != observation.observation_id[7:]:
        _fail("CAA2 observation filename does not match observation_id.")
    return observation


def _observation_sha256(
    observation: AgentObservation | GapAgentObservation,
) -> str:
    if isinstance(observation, AgentObservation):
        payload = dumps_agent_observation(observation).encode("utf-8")
    elif isinstance(observation, GapAgentObservation):
        payload = dumps_gap_observation(observation).encode("utf-8")
    else:
        _fail("Unsupported controlled-agent observation type.")
        raise AssertionError("unreachable")
    return "sha256:" + sha256(payload).hexdigest()


def _review_join(
    *,
    source_agent: ObservationSource,
    run: FrozenInspectionUniverse,
    observation: AgentObservation | GapAgentObservation,
    publication_path: Path,
    review_root: Path | None,
) -> ProfessionalReviewInboxItem:
    try:
        events = load_professional_review_events(
            case_id=run.case_id,
            observation_id=observation.observation_id,
            root=review_root,
        )
        projection = project_professional_review(events)
    except (
        ProfessionalReviewPublicationError,
        ValueError,
    ) as exc:
        raise ProfessionalReviewInboxError(
            "Professional review event history failed closed."
        ) from exc

    expected_sha = _observation_sha256(observation)
    expected_issue = getattr(
        observation,
        "issue_analysis_id",
        None,
    )
    expected_element = getattr(
        observation,
        "element_id",
        None,
    )
    expected_action = observation.recommended_action

    for event in events:
        if event.source_agent is not source_agent:
            _fail("Professional review event source agent mismatch.")
        if event.case_id != run.case_id:
            _fail("Professional review event case mismatch.")
        if event.active_authority_id != run.active_authority_id:
            _fail("Professional review event authority mismatch.")
        if event.analysis_run_id != run.analysis_run_id:
            _fail("Professional review event analysis run mismatch.")
        if event.observation_id != observation.observation_id:
            _fail("Professional review event observation mismatch.")
        if event.observation_sha256 != expected_sha:
            _fail("Professional review event observation payload mismatch.")
        if event.issue_analysis_id != expected_issue:
            _fail("Professional review event issue mismatch.")
        if event.element_id != expected_element:
            _fail("Professional review event element mismatch.")
        if event.recommended_action is not expected_action:
            _fail("Professional review event recommended action mismatch.")

    return ProfessionalReviewInboxItem(
        schema_version=PRW2_INBOX_SCHEMA_VERSION,
        source_agent=source_agent,
        run=run,
        observation=observation,
        publication_path=publication_path,
        review_events=events,
        review_projection=projection,
    )


def _load_caa1_items(
    *,
    case_id: str,
    root: Path,
    review_root: Path | None,
) -> list[ProfessionalReviewInboxItem]:
    case_root = root / case_id
    if not case_root.exists():
        return []
    _require_plain_directory(
        case_root,
        label="CAA1 case publication directory",
    )

    items: list[ProfessionalReviewInboxItem] = []
    for run_root in sorted(case_root.iterdir(), key=lambda value: value.name):
        _storage_digest(
            run_root.name,
            label="CAA1 run directory",
        )
        _require_plain_directory(
            run_root,
            label="CAA1 run publication directory",
        )

        entries = tuple(run_root.iterdir())
        for entry in entries:
            if entry.name == "run.json":
                _require_plain_file(entry, label="CAA1 run file")
            elif entry.name == "observations":
                _require_plain_directory(
                    entry,
                    label="CAA1 observation directory",
                )
            else:
                _fail(
                    "CAA1 run publication contains an unexpected path."
                )

        run_path = run_root / "run.json"
        if not run_path.exists():
            _fail("CAA1 run publication is missing run.json.")
        run = _load_run(run_path)
        if run.case_id != case_id:
            _fail("CAA1 run publication belongs to a different case.")
        if run.analysis_run_id[7:] != run_root.name:
            _fail("CAA1 run directory does not match analysis_run_id.")

        observation_root = run_root / "observations"
        if not observation_root.exists():
            continue

        for path in sorted(
            observation_root.iterdir(),
            key=lambda value: value.name,
        ):
            _require_plain_file(path, label="CAA1 observation file")
            if path.suffix != ".json":
                _fail("CAA1 observation directory contains a non-JSON file.")
            _storage_digest(
                path.stem,
                label="CAA1 observation filename",
            )
            observation = _load_caa1_observation(
                path=path,
                run=run,
            )
            items.append(
                _review_join(
                    source_agent=ObservationSource.CAA1,
                    run=run,
                    observation=observation,
                    publication_path=path,
                    review_root=review_root,
                )
            )
    return items


def _load_caa2_items(
    *,
    case_id: str,
    root: Path,
    review_root: Path | None,
) -> list[ProfessionalReviewInboxItem]:
    case_root = root / case_id
    if not case_root.exists():
        return []
    _require_plain_directory(
        case_root,
        label="CAA2 case publication directory",
    )

    items: list[ProfessionalReviewInboxItem] = []
    for run_root in sorted(case_root.iterdir(), key=lambda value: value.name):
        _storage_digest(
            run_root.name,
            label="CAA2 run directory",
        )
        _require_plain_directory(
            run_root,
            label="CAA2 run publication directory",
        )

        expected_names = {
            "run.json",
            "candidates.json",
            "manifest.json",
            "observations",
        }
        actual_names = {entry.name for entry in run_root.iterdir()}
        if actual_names != expected_names:
            _fail("CAA2 run publication path set is invalid.")

        run_path = run_root / "run.json"
        candidates_path = run_root / "candidates.json"
        manifest_path = run_root / "manifest.json"
        observation_root = run_root / "observations"

        _require_plain_file(run_path, label="CAA2 run file")
        _require_plain_file(
            candidates_path,
            label="CAA2 candidates file",
        )
        _require_plain_file(
            manifest_path,
            label="CAA2 manifest file",
        )
        _require_plain_directory(
            observation_root,
            label="CAA2 observation directory",
        )

        run = _load_run(run_path)
        if run.case_id != case_id:
            _fail("CAA2 run publication belongs to a different case.")
        if run.analysis_run_id[7:] != run_root.name:
            _fail("CAA2 run directory does not match analysis_run_id.")

        candidate_payload = _read_bytes(
            candidates_path,
            label="CAA2 candidates",
        )
        candidate_data = _json_from_bytes(
            candidate_payload,
            label="CAA2 candidates",
        )
        if not isinstance(candidate_data, list):
            _fail("CAA2 candidates root must be a list.")
        candidates = tuple(
            _load_caa2_candidate(value)
            for value in candidate_data
        )
        candidate_by_id = {
            candidate.candidate_id: candidate
            for candidate in candidates
        }
        if len(candidate_by_id) != len(candidates):
            _fail("CAA2 candidates contain duplicate identities.")
        if dumps_gap_candidates(candidates).encode("utf-8") != candidate_payload:
            _fail("CAA2 candidate bytes are not canonical.")
        for candidate in candidates:
            if candidate.case_id != run.case_id:
                _fail("CAA2 candidate case does not match frozen run.")
            if candidate.active_authority_id != run.active_authority_id:
                _fail("CAA2 candidate authority does not match frozen run.")
            if candidate.analysis_run_id != run.analysis_run_id:
                _fail("CAA2 candidate analysis run does not match frozen run.")

        manifest_payload = _read_bytes(
            manifest_path,
            label="CAA2 publication manifest",
        )
        manifest = _exact_object(
            _json_from_bytes(
                manifest_payload,
                label="CAA2 publication manifest",
            ),
            keys={
                "schema_version",
                "case_id",
                "active_authority_id",
                "analysis_run_id",
                "candidate_ids",
                "observation_ids",
            },
            label="CAA2 publication manifest",
        )
        if _canonical_json_bytes(manifest) != manifest_payload:
            _fail("CAA2 manifest bytes are not canonical.")
        if manifest["schema_version"] != CAA2_PUBLICATION_MANIFEST_SCHEMA:
            _fail("CAA2 publication manifest schema is unsupported.")
        if manifest["case_id"] != run.case_id:
            _fail("CAA2 manifest case does not match frozen run.")
        if manifest["active_authority_id"] != run.active_authority_id:
            _fail("CAA2 manifest authority does not match frozen run.")
        if manifest["analysis_run_id"] != run.analysis_run_id:
            _fail("CAA2 manifest analysis run does not match frozen run.")
        if not isinstance(manifest["candidate_ids"], list):
            _fail("CAA2 manifest candidate_ids must be a list.")
        if not isinstance(manifest["observation_ids"], list):
            _fail("CAA2 manifest observation_ids must be a list.")
        if tuple(manifest["candidate_ids"]) != tuple(
            candidate.candidate_id
            for candidate in candidates
        ):
            _fail("CAA2 manifest candidate identities do not match candidates.")

        observations_by_id: dict[str, GapAgentObservation] = {}
        paths_by_id: dict[str, Path] = {}
        for path in sorted(
            observation_root.iterdir(),
            key=lambda value: value.name,
        ):
            _require_plain_file(path, label="CAA2 observation file")
            if path.suffix != ".json":
                _fail("CAA2 observation directory contains a non-JSON file.")
            _storage_digest(
                path.stem,
                label="CAA2 observation filename",
            )
            observation = _load_caa2_observation(
                path=path,
                run=run,
                candidate_by_id=candidate_by_id,
            )
            if observation.observation_id in observations_by_id:
                _fail("CAA2 observations contain duplicate identities.")
            observations_by_id[observation.observation_id] = observation
            paths_by_id[observation.observation_id] = path

        manifest_observation_ids = tuple(manifest["observation_ids"])
        if len(manifest_observation_ids) != len(
            set(manifest_observation_ids)
        ):
            _fail("CAA2 manifest observation_ids contain duplicates.")
        if set(manifest_observation_ids) != set(observations_by_id):
            _fail("CAA2 manifest observation identities do not match files.")

        for observation_id in manifest_observation_ids:
            observation = observations_by_id[observation_id]
            items.append(
                _review_join(
                    source_agent=ObservationSource.CAA2,
                    run=run,
                    observation=observation,
                    publication_path=paths_by_id[observation_id],
                    review_root=review_root,
                )
            )
    return items


def load_professional_review_inbox(
    *,
    case_id: str,
    caa1_root: Path | None = None,
    caa2_root: Path | None = None,
    review_root: Path | None = None,
) -> tuple[ProfessionalReviewInboxItem, ...]:
    """Load exact published CAA observations joined to their PRW1 review state."""

    normalized_case = _case_component(case_id)
    effective_caa1_root = (
        _repo_root() / CAA1_PUBLICATION_ROOT
        if caa1_root is None
        else Path(caa1_root)
    )
    effective_caa2_root = (
        _repo_root() / CAA2_PUBLICATION_ROOT
        if caa2_root is None
        else Path(caa2_root)
    )

    items = (
        _load_caa1_items(
            case_id=normalized_case,
            root=effective_caa1_root,
            review_root=review_root,
        )
        + _load_caa2_items(
            case_id=normalized_case,
            root=effective_caa2_root,
            review_root=review_root,
        )
    )

    identities: set[tuple[ObservationSource, str]] = set()
    for item in items:
        identity = (
            item.source_agent,
            item.observation.observation_id,
        )
        if identity in identities:
            _fail("Professional review inbox contains duplicate observation identity.")
        identities.add(identity)

    return tuple(
        sorted(
            items,
            key=lambda item: (
                item.source_agent.value,
                item.run.analysis_run_id,
                item.observation.observation_id,
            ),
        )
    )


__all__ = [
    "PRW2_INBOX_SCHEMA_VERSION",
    "ProfessionalReviewInboxError",
    "ProfessionalReviewInboxItem",
    "load_professional_review_inbox",
]
