from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

from candidate_transcription import (
    CandidateTranscriptionStore,
    TranscriptionReviewEventStore,
    TranscriptionReviewState,
)
from candidate_transcription.crop_lineage import (
    loads_candidate_crop_lineage_binding,
)
from candidate_transcription.review import project_transcription_review
from candidate_transcription.serialization import loads_candidate_record
from candidate_transcription.targeted_publication import (
    loads_targeted_candidate_publication_receipt,
)
from marriage_document_extraction import (
    MarriageFactExtractionProvider,
    extract_marriage_document_intelligence,
)
from marriage_document_workspace import (
    MarriageDocumentWorkspace,
    build_marriage_document_workspace,
)


class LiveMarriageDocumentError(RuntimeError):
    pass


@dataclass(frozen=True)
class LiveMarriageCandidateBundle:
    candidate: Any
    review_projection: Any
    binding: Any
    receipt: Any
    transcription_text: str


def candidate_transcription_base(
    environment: dict[str, str] | None = None,
) -> Path:
    env = os.environ if environment is None else environment
    override = str(
        env.get("LEGALRAG_CANDIDATE_TRANSCRIPTION_ROOT", "")
    ).strip()

    if override:
        return Path(override)

    local_appdata = str(env.get("LOCALAPPDATA", "")).strip()
    if not local_appdata:
        raise LiveMarriageDocumentError(
            "LOCALAPPDATA is unavailable and no candidate-transcription root override was supplied."
        )

    return (
        Path(local_appdata)
        / "LegalRAG-Pro"
        / "candidate_transcription"
        / "v1"
    )


def looks_like_marriage_document_filename(filename: str) -> bool:
    value = filename.casefold()
    return any(
        token in value
        for token in ("nikah", "nikkah", "marriage")
    )


def _candidate_records(base: Path):
    root = base / "candidate_store" / "candidates"
    if not root.is_dir():
        return ()

    values = []
    for path in sorted(root.glob("*.json")):
        try:
            record = loads_candidate_record(
                path.read_text(encoding="utf-8")
            )
        except Exception as exc:
            raise LiveMarriageDocumentError(
                f"Candidate record could not be loaded: {path.name}"
            ) from exc
        values.append(record)
    return tuple(values)


def _lineage_bindings(base: Path, candidate: Any):
    digest = candidate.record_id.removeprefix("sha256:")
    root = (
        base
        / "crop_lineage_store"
        / "candidate_crop_lineage"
        / digest
    )
    if not root.is_dir():
        return ()

    values = []
    for path in sorted(root.glob("*.json")):
        try:
            binding = loads_candidate_crop_lineage_binding(
                path.read_text(encoding="utf-8")
            )
        except Exception as exc:
            raise LiveMarriageDocumentError(
                f"Candidate lineage could not be loaded: {path.name}"
            ) from exc

        if (
            binding.candidate_record_id == candidate.record_id
            and binding.transcription_sha256
            == candidate.transcription_sha256
        ):
            values.append(binding)

    return tuple(values)


def _publication_receipts(base: Path, candidate: Any):
    digest = candidate.record_id.removeprefix("sha256:")
    root = (
        base
        / "targeted_publication_receipt_store"
        / "targeted_candidate_publication_receipts"
        / digest
    )
    if not root.is_dir():
        return ()

    values = []
    for path in sorted(root.glob("*.json")):
        try:
            receipt = loads_targeted_candidate_publication_receipt(
                path.read_text(encoding="utf-8")
            )
        except Exception as exc:
            raise LiveMarriageDocumentError(
                f"Candidate publication receipt could not be loaded: {path.name}"
            ) from exc

        if (
            receipt.candidate_record_id == candidate.record_id
            and receipt.transcription_sha256
            == candidate.transcription_sha256
        ):
            values.append(receipt)

    return tuple(values)


def _resolve_exact_bundle(
    *,
    base: Path,
    candidate_store: CandidateTranscriptionStore,
    review_store: TranscriptionReviewEventStore,
    candidate: Any,
) -> LiveMarriageCandidateBundle | None:
    projection = project_transcription_review(
        review_store.load_events(candidate.record_id)
    )

    if (
        projection is None
        or projection.state is not TranscriptionReviewState.APPROVED
    ):
        return None

    bindings = _lineage_bindings(base, candidate)
    receipts = _publication_receipts(base, candidate)

    pairs = [
        (binding, receipt)
        for binding in bindings
        for receipt in receipts
        if (
            receipt.binding_id == binding.binding_id
            and receipt.candidate_record_id == candidate.record_id
            and receipt.transcription_sha256
            == candidate.transcription_sha256
            and receipt.derived_artifact_sha256
            == binding.derived_artifact_sha256
        )
    ]

    if len(pairs) != 1:
        raise LiveMarriageDocumentError(
            "Approved marriage candidate does not resolve to exactly one current lineage/publication pair."
        )

    binding, receipt = pairs[0]

    try:
        transcription = candidate_store.read_transcription(candidate)
    except Exception as exc:
        raise LiveMarriageDocumentError(
            "Approved marriage transcription could not be read."
        ) from exc

    return LiveMarriageCandidateBundle(
        candidate=candidate,
        review_projection=projection,
        binding=binding,
        receipt=receipt,
        transcription_text=transcription,
    )


def discover_approved_marriage_candidate_bundles(
    active_case_id: str,
    *,
    base: Path | None = None,
) -> tuple[LiveMarriageCandidateBundle, ...]:
    if not isinstance(active_case_id, str) or not active_case_id.strip():
        raise LiveMarriageDocumentError(
            "An active matter ID is required."
        )

    resolved_base = candidate_transcription_base() if base is None else base
    candidate_store = CandidateTranscriptionStore(
        resolved_base / "candidate_store"
    )
    review_store = TranscriptionReviewEventStore(
        resolved_base / "review_event_store"
    )

    bundles = []

    for candidate in _candidate_records(resolved_base):
        if candidate.case_id != active_case_id:
            continue
        if not looks_like_marriage_document_filename(
            candidate.original_filename
        ):
            continue

        bundle = _resolve_exact_bundle(
            base=resolved_base,
            candidate_store=candidate_store,
            review_store=review_store,
            candidate=candidate,
        )
        if bundle is not None:
            bundles.append(bundle)

    return tuple(
        sorted(
            bundles,
            key=lambda value: value.candidate.record_id,
        )
    )


def live_marriage_candidate_fingerprint(
    bundles: Iterable[LiveMarriageCandidateBundle],
) -> str:
    material = tuple(bundles)

    payload = [
        {
            "candidate_record_id": value.candidate.record_id,
            "case_id": value.candidate.case_id,
            "transcription_sha256": value.candidate.transcription_sha256,
            "review_event_id": value.review_projection.latest_event_id,
            "binding_id": value.binding.binding_id,
            "publication_receipt_id": value.receipt.receipt_id,
        }
        for value in material
    ]

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(canonical).hexdigest()


def build_live_marriage_document_workspace(
    *,
    bundles: Iterable[LiveMarriageCandidateBundle],
    provider: MarriageFactExtractionProvider,
    model: str,
) -> MarriageDocumentWorkspace:
    material = tuple(bundles)
    if not material:
        raise LiveMarriageDocumentError(
            "No currently approved marriage-document fragments are available."
        )

    case_ids = {
        value.candidate.case_id
        for value in material
    }
    if len(case_ids) != 1:
        raise LiveMarriageDocumentError(
            "Marriage-document candidates span more than one matter."
        )

    records = []

    for value in material:
        record = extract_marriage_document_intelligence(
            candidate=value.candidate,
            transcription_text=value.transcription_text,
            binding=value.binding,
            receipt=value.receipt,
            review_projection=value.review_projection,
            provider=provider,
            model=model,
        )
        records.append(record)

    return build_marriage_document_workspace(tuple(records))
