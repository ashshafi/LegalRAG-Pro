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
from marriage_document_source_native import (
    SourceEvidenceNativePage,
    build_source_evidence_native_workspace_bridge,
    load_source_evidence_native_pages,
)
from source_evidence.store import (
    SourceEvidenceStore,
    SourceEvidenceStoreError,
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


@dataclass(frozen=True)
class LiveMarriageNativeSourceContext:
    store: Any
    manifest: Any
    pages: tuple[SourceEvidenceNativePage, ...]

    @property
    def page_numbers(self) -> tuple[int, ...]:
        return tuple(
            value.provenance.page_number
            for value in self.pages
        )


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


def _bundle_source_identity(
    bundles: Iterable[LiveMarriageCandidateBundle],
):
    material = tuple(bundles)
    if not material:
        return None

    candidates = tuple(
        value.candidate
        for value in material
    )

    fields = (
        "case_id",
        "source_document_instance_id",
        "source_snapshot_id",
        "original_filename",
        "original_blob_sha256",
        "original_byte_length",
    )
    resolved = {}

    for field in fields:
        values = {
            getattr(candidate, field)
            for candidate in candidates
        }
        if len(values) != 1:
            return None
        resolved[field] = next(iter(values))

    return resolved


def _native_structure_is_supported(
    pages: tuple[SourceEvidenceNativePage, ...],
) -> bool:
    by_page = {
        value.provenance.page_number:
            " ".join(value.text.casefold().split())
        for value in pages
    }

    required = {
        2: (
            "name of the bridegroom",
            "name of the bride",
            "name of the witnesses to the marriage",
            "date on which the marriage was",
            "amount of dower",
        ),
        3: (
            "person by whom the marriage was",
            "date of registration of marriage",
        ),
        4: (
            "arbitration council",
        ),
    }

    for page_number, tokens in required.items():
        text = by_page.get(page_number, "")
        if not text:
            return False
        if any(token not in text for token in tokens):
            return False

    return True


def discover_optional_native_marriage_source_context(
    bundles: Iterable[LiveMarriageCandidateBundle],
    *,
    store: SourceEvidenceStore | None = None,
) -> LiveMarriageNativeSourceContext | None:
    material = tuple(bundles)
    identity = _bundle_source_identity(material)
    if identity is None:
        return None

    resolved_store = (
        SourceEvidenceStore()
        if store is None
        else store
    )

    try:
        manifest = resolved_store.load_document_manifest(
            identity["case_id"],
            identity["source_document_instance_id"],
        )
    except SourceEvidenceStoreError:
        return None

    identity_pairs = (
        (
            "source_document_instance_id",
            manifest.source_document_instance_id,
        ),
        (
            "source_snapshot_id",
            manifest.source_snapshot_id,
        ),
        (
            "original_filename",
            manifest.original_filename,
        ),
        (
            "original_blob_sha256",
            manifest.original_blob_sha256,
        ),
        (
            "original_byte_length",
            manifest.original_byte_length,
        ),
    )

    for field, manifest_value in identity_pairs:
        if manifest_value != identity[field]:
            raise LiveMarriageDocumentError(
                "Governed native marriage source identity does not "
                "match the approved candidate source."
            )

    by_page = {
        int(page.page_number): page
        for page in manifest.pages
    }
    required_pages = (2, 3, 4)

    if any(page_number not in by_page for page_number in required_pages):
        return None

    for page_number in required_pages:
        page = by_page[page_number]
        method = (
            page.extraction_method.value
            if hasattr(page.extraction_method, "value")
            else str(page.extraction_method)
        )
        if method != "pypdf_text":
            return None
        if int(page.page_text_byte_length) <= 0:
            return None

    try:
        pages = load_source_evidence_native_pages(
            store=resolved_store,
            manifest=manifest,
            page_numbers=required_pages,
        )
    except Exception as exc:
        raise LiveMarriageDocumentError(
            "Governed native marriage source failed integrity verification."
        ) from exc

    if not _native_structure_is_supported(pages):
        return None

    return LiveMarriageNativeSourceContext(
        store=resolved_store,
        manifest=manifest,
        pages=pages,
    )


def _validate_native_context_for_bundles(
    *,
    bundles: tuple[LiveMarriageCandidateBundle, ...],
    native_context: LiveMarriageNativeSourceContext,
) -> None:
    identity = _bundle_source_identity(bundles)
    if identity is None:
        raise LiveMarriageDocumentError(
            "Native marriage enrichment requires one exact source identity."
        )

    manifest = native_context.manifest

    checks = (
        manifest.source_document_instance_id
        == identity["source_document_instance_id"],
        manifest.source_snapshot_id
        == identity["source_snapshot_id"],
        manifest.original_filename
        == identity["original_filename"],
        manifest.original_blob_sha256
        == identity["original_blob_sha256"],
        manifest.original_byte_length
        == identity["original_byte_length"],
    )
    if not all(checks):
        raise LiveMarriageDocumentError(
            "Native marriage source context is stale or source-mismatched."
        )

    if native_context.page_numbers != (2, 3, 4):
        raise LiveMarriageDocumentError(
            "Native marriage source context has an unsupported page set."
        )


def live_marriage_review_fingerprint(
    bundles: Iterable[LiveMarriageCandidateBundle],
    *,
    native_context: LiveMarriageNativeSourceContext | None = None,
) -> str:
    material = tuple(bundles)

    payload = {
        "candidate_fingerprint":
            live_marriage_candidate_fingerprint(material),
        "native_source": None,
    }

    if native_context is not None:
        payload["native_source"] = {
            "source_document_instance_id":
                native_context.manifest.source_document_instance_id,
            "source_snapshot_id":
                native_context.manifest.source_snapshot_id,
            "original_blob_sha256":
                native_context.manifest.original_blob_sha256,
            "pages": [
                {
                    "page_number":
                        value.provenance.page_number,
                    "page_text_sha256":
                        value.provenance.page_text_sha256,
                    "page_text_byte_length":
                        value.provenance.page_text_byte_length,
                    "extraction_method":
                        value.provenance.extraction_method,
                }
                for value in native_context.pages
            ],
        }

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(canonical).hexdigest()


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
    native_context: LiveMarriageNativeSourceContext | None = None,
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

    workspace = build_marriage_document_workspace(
        tuple(records)
    )

    if native_context is None:
        return workspace

    _validate_native_context_for_bundles(
        bundles=material,
        native_context=native_context,
    )

    bridged = build_source_evidence_native_workspace_bridge(
        base_workspace=workspace,
        store=native_context.store,
        manifest=native_context.manifest,
        page_numbers=native_context.page_numbers,
    )
    return bridged.workspace
