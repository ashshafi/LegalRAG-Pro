"""Chunk-level provenance for mixed legal evidence bundles.

Sprint 2.2 Milestone 2 classifies a document/container conservatively. This
module adds a second, narrower provenance layer for the individual retrieved
chunk. It deliberately does not overwrite Milestone 2 metadata: a mixed PDF can
remain document-classified as insurer or composite material while an individual
email chunk is identified as employer, insurer, medical, or claimant material.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final

from evidence_classification import (
    EVIDENCE_SOURCE_TYPE_KEY,
    EvidenceSourceType,
    source_label,
)

CHUNK_SOURCE_TYPE_KEY: Final[str] = "chunk_source_type"
CHUNK_SOURCE_LABEL_KEY: Final[str] = "chunk_source_label"
CHUNK_PROVENANCE_METHOD_KEY: Final[str] = "chunk_provenance_method"
PRIMARY_SOURCE_TIER_KEY: Final[str] = "primary_source_tier"
PRIMARY_SOURCE_LABEL_KEY: Final[str] = "primary_source_label"


@dataclass(frozen=True, slots=True)
class ChunkProvenance:
    """Provenance classification for one chunk."""

    source_type: EvidenceSourceType
    label: str
    method: str
    primary_tier: int
    primary_label: str


_PRIMARY_SOURCE_TIERS: Final[dict[EvidenceSourceType, tuple[int, str]]] = {
    EvidenceSourceType.EMPLOYER_RECORD: (4, "Primary/direct record"),
    EvidenceSourceType.INDEPENDENT_MEDICAL: (4, "Primary/direct record"),
    EvidenceSourceType.OCCUPATIONAL_HEALTH: (4, "Primary/direct record"),
    EvidenceSourceType.INSURER_RECORD: (4, "Primary/direct record"),
    EvidenceSourceType.TRIBUNAL_RECORD: (4, "Primary/direct record"),
    EvidenceSourceType.CLAIMANT_CORRESPONDENCE: (
        3,
        "Direct party correspondence",
    ),
    EvidenceSourceType.MIXED_CORRESPONDENCE: (3, "Mixed direct correspondence"),
    EvidenceSourceType.LEGAL_AUTHORITY: (2, "Legal/procedural source"),
    EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT: (
        1,
        "Retrospective/testimonial evidence",
    ),
    EvidenceSourceType.RESPONDENT_WITNESS_STATEMENT: (
        1,
        "Retrospective/testimonial evidence",
    ),
    EvidenceSourceType.WITNESS_STATEMENT: (
        1,
        "Retrospective/testimonial evidence",
    ),
    EvidenceSourceType.CLAIMANT_SUBMISSION: (1, "Party submission"),
    EvidenceSourceType.RESPONDENT_SUBMISSION: (1, "Party submission"),
    EvidenceSourceType.SECONDARY_SUMMARY: (0, "Secondary summary"),
    EvidenceSourceType.OTHER: (0, "Unclassified source"),
}


# These classifications identify the author/source of the document itself.
# Body references to another actor must never override them.
_AUTHORSHIP_DOCUMENT_TYPES: Final[frozenset[EvidenceSourceType]] = frozenset(
    {
        EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT,
        EvidenceSourceType.RESPONDENT_WITNESS_STATEMENT,
        EvidenceSourceType.WITNESS_STATEMENT,
        EvidenceSourceType.CLAIMANT_CORRESPONDENCE,
        EvidenceSourceType.CLAIMANT_SUBMISSION,
        EvidenceSourceType.RESPONDENT_SUBMISSION,
        EvidenceSourceType.LEGAL_AUTHORITY,
        EvidenceSourceType.TRIBUNAL_RECORD,
        EvidenceSourceType.SECONDARY_SUMMARY,
    }
)


def classify_chunk_provenance(
    *,
    file_name: str,
    text: str,
    document_source_type: EvidenceSourceType | str | None = None,
) -> ChunkProvenance:
    """Classify the local provenance of one retrieved/indexed chunk.

    Strong chunk-local signals take priority over the container/document label.
    This is particularly important for appendices that contain several parties'
    emails in the same PDF. If local signals remain ambiguous, the function
    inherits a safe document-level category or returns mixed/unclassified
    provenance rather than guessing.
    """

    parsed_document_type = _parse_optional_source_type(document_source_type)
    leading = _leading_text(text).casefold()

    # Provenance is about authorship/source, not subject matter. When the
    # document classification already establishes who authored the material
    # (for example a claimant witness statement or claimant submission), that
    # authorship takes precedence over references in the body to CACI, Unum,
    # Occupational Health, doctors, or other actors.
    if parsed_document_type in _AUTHORSHIP_DOCUMENT_TYPES:
        return _provenance(
            parsed_document_type,
            method="document-authorship-inherited",
        )

    leading_type = _leading_sender_type(leading)
    if leading_type is not None:
        return _provenance(leading_type, method="chunk-leading-sender")

    signature_type = _signature_sender_type(text)
    if signature_type is not None:
        return _provenance(signature_type, method="chunk-signature")

    if parsed_document_type is not None:
        # A container called "Unum correspondence" or "CACI return-to-work
        # correspondence" should not turn every ambiguous excerpt into insurer
        # or employer evidence. Without identifiable authorship, a bundled
        # correspondence chunk is composite evidence.
        if parsed_document_type in {
            EvidenceSourceType.INSURER_RECORD,
            EvidenceSourceType.EMPLOYER_RECORD,
            EvidenceSourceType.MIXED_CORRESPONDENCE,
        } and _looks_like_correspondence_container(file_name):
            return _provenance(
                EvidenceSourceType.MIXED_CORRESPONDENCE,
                method="mixed-container-fallback",
            )

        return _provenance(parsed_document_type, method="document-inherited")

    return _provenance(EvidenceSourceType.OTHER, method="unclassified")


def add_chunk_provenance_to_metadata(
    metadata: dict[str, Any] | None,
    *,
    text: str,
) -> dict[str, Any]:
    """Return a metadata copy populated with chunk-level provenance fields."""

    enriched = dict(metadata or {})
    stored_type = enriched.get(CHUNK_SOURCE_TYPE_KEY)
    stored_method = str(
        enriched.get(CHUNK_PROVENANCE_METHOD_KEY) or ""
    ).strip().casefold()

    # Only explicit/manual provenance is authoritative across classifier
    # revisions. Automatically generated stored labels are deliberately
    # recomputed so an earlier subject-matter misclassification cannot become
    # permanently embedded in the index.
    if stored_type is not None and stored_method in {"manual", "explicit"}:
        parsed = _parse_optional_source_type(stored_type)
        if parsed is not None:
            tier, primary_label = primary_source_tier(parsed)
            enriched[CHUNK_SOURCE_TYPE_KEY] = parsed.value
            enriched[CHUNK_SOURCE_LABEL_KEY] = source_label(parsed)
            enriched[CHUNK_PROVENANCE_METHOD_KEY] = stored_method
            enriched[PRIMARY_SOURCE_TIER_KEY] = tier
            enriched[PRIMARY_SOURCE_LABEL_KEY] = primary_label
            return enriched

    provenance = classify_chunk_provenance(
        file_name=str(enriched.get("file") or ""),
        text=text,
        document_source_type=enriched.get(EVIDENCE_SOURCE_TYPE_KEY),
    )
    enriched[CHUNK_SOURCE_TYPE_KEY] = provenance.source_type.value
    enriched[CHUNK_SOURCE_LABEL_KEY] = provenance.label
    enriched[CHUNK_PROVENANCE_METHOD_KEY] = provenance.method
    enriched[PRIMARY_SOURCE_TIER_KEY] = provenance.primary_tier
    enriched[PRIMARY_SOURCE_LABEL_KEY] = provenance.primary_label
    return enriched


def enrich_chunk_provenance(results: dict[str, Any]) -> dict[str, Any]:
    """Add chunk provenance to an already case-scoped Chroma response."""

    documents = _first_query_row(results.get("documents"))
    metadatas = _first_query_row(results.get("metadatas"))
    if not metadatas:
        return results

    enriched_metadatas: list[dict[str, Any]] = []
    for index, metadata in enumerate(metadatas):
        metadata_dict = metadata if isinstance(metadata, dict) else {}
        document = ""
        if index < len(documents) and documents[index] is not None:
            document = str(documents[index])
        enriched_metadatas.append(
            add_chunk_provenance_to_metadata(metadata_dict, text=document)
        )

    enriched = dict(results)
    enriched["metadatas"] = [enriched_metadatas]
    return enriched


def primary_source_tier(
    source_type: EvidenceSourceType | str,
) -> tuple[int, str]:
    """Return bounded retrieval preference tier and its user-facing label."""

    parsed = _parse_optional_source_type(source_type) or EvidenceSourceType.OTHER
    return _PRIMARY_SOURCE_TIERS[parsed]


def _provenance(source_type: EvidenceSourceType, *, method: str) -> ChunkProvenance:
    tier, primary_label = primary_source_tier(source_type)
    return ChunkProvenance(
        source_type=source_type,
        label=source_label(source_type),
        method=method,
        primary_tier=tier,
        primary_label=primary_label,
    )


def _parse_optional_source_type(
    source_type: EvidenceSourceType | str | None,
) -> EvidenceSourceType | None:
    if source_type is None:
        return None
    if isinstance(source_type, EvidenceSourceType):
        return source_type
    try:
        return EvidenceSourceType(str(source_type).strip())
    except ValueError:
        return None


def _leading_text(text: str, max_chars: int = 1200) -> str:
    return text[:max_chars]


def _leading_sender_type(leading: str) -> EvidenceSourceType | None:
    """Infer provenance from a clear leading sender/header when available."""

    sender_match = re.search(
        r"(?:^|\n)\s*(?:from|sender)\s*:\s*([^\n]{1,220})",
        leading,
    )
    if sender_match:
        sender_zone = _normalise(sender_match.group(1))
    else:
        # Outlook/PDF exports sometimes lose the literal "From:" label but
        # retain a sender name/role on the first line. Only treat that line as
        # authorship when it looks like an identity/role; ordinary prose must
        # never be mined for subject-matter keywords.
        first_line = next(
            (line.strip() for line in leading.splitlines() if line.strip()),
            "",
        )
        if not _looks_like_identity_line(first_line):
            return None
        sender_zone = _normalise(first_line)

    return _author_type_from_identity_zone(sender_zone)


def _signature_sender_type(text: str) -> EvidenceSourceType | None:
    """Infer authorship from a clear closing signature/role only.

    The function intentionally examines only a short trailing signature zone.
    It must not treat body references to HR, Unum, OH or medical evidence as
    proof that those actors authored the chunk.
    """

    trailing_lines = [line.strip() for line in text[-1600:].splitlines() if line.strip()]
    if not trailing_lines:
        return None

    # Prefer text after a conventional sign-off. If no sign-off survives PDF
    # extraction, use only the last few lines rather than the whole body.
    signoff_index: int | None = None
    for index, line in enumerate(trailing_lines):
        normalised_line = _normalise(line)
        if normalised_line in {
            "kind regards",
            "regards",
            "best regards",
            "many thanks",
            "thank you",
            "yours sincerely",
            "yours faithfully",
        }:
            signoff_index = index

    if signoff_index is not None:
        signature_zone = " ".join(trailing_lines[signoff_index + 1 : signoff_index + 7])
        return _author_type_from_identity_zone(_normalise(signature_zone))

    # Without a sign-off, only accept a short final identity/role line. Never
    # scan ordinary trailing prose, which could merely mention another source.
    final_line = trailing_lines[-1]
    if not _looks_like_identity_line(final_line):
        return None
    return _author_type_from_identity_zone(_normalise(final_line))


def _looks_like_identity_line(line: str) -> bool:
    """Return whether a final line plausibly identifies an author/role."""

    stripped = line.strip()
    if not stripped or len(stripped) > 120:
        return False
    if stripped.endswith((".", ";", ":", "?", "!")):
        return False
    if len(stripped.split()) > 10:
        return False

    normalised = _normalise(stripped)
    if normalised in {"you", "me"}:
        return True
    return _contains_any(
        normalised,
        (
            "hr director",
            "human resources",
            "people director",
            "occupational health",
            "occupational physician",
            "oh adviser",
            "oh advisor",
            "consultant psychiatrist",
            "psychiatrist",
            "general practitioner",
            "medical practice",
            "medical centre",
            "unum",
            "unumprovident",
            "swiss life",
            "claims assessor",
            "claimant",
        ),
    )


def _author_type_from_identity_zone(zone: str) -> EvidenceSourceType | None:
    """Classify a sender/signature zone using author-identifying language."""

    candidates: set[EvidenceSourceType] = set()

    if _contains_any(
        zone,
        (
            "occupational health",
            "occupational physician",
            "oh adviser",
            "oh advisor",
        ),
    ):
        candidates.add(EvidenceSourceType.OCCUPATIONAL_HEALTH)

    if _contains_any(
        zone,
        (
            "nhs",
            "general practitioner",
            "consultant psychiatrist",
            "psychiatrist",
            "medical centre",
            "medical practice",
        ),
    ):
        candidates.add(EvidenceSourceType.INDEPENDENT_MEDICAL)

    if _contains_any(
        zone,
        (
            "unum",
            "unumprovident",
            "swiss life",
            "claims assessor",
            "income protection",
            "group income protection",
        ),
    ):
        candidates.add(EvidenceSourceType.INSURER_RECORD)

    if _contains_any(
        zone,
        (
            "head of hr",
            "hr director",
            "human resources director",
            "human resources manager",
            "human resources",
            "people director",
            "people manager",
            "on behalf of the company",
        ),
    ):
        candidates.add(EvidenceSourceType.EMPLOYER_RECORD)

    if _contains_any(
        zone,
        (
            "the claimant",
            "claimant correspondence",
            "claimant email",
            "claimant letter",
        ),
    ) or zone in {"you", "me"}:
        candidates.add(EvidenceSourceType.CLAIMANT_CORRESPONDENCE)

    if len(candidates) == 1:
        return next(iter(candidates))
    return None


def _looks_like_correspondence_container(file_name: str) -> bool:
    normalised = _normalise(file_name)
    return _contains_any(
        normalised,
        (
            "correspondence",
            "emails",
            "email chain",
            "return to work",
            "appendix h",
        ),
    )


def _normalise(value: str) -> str:
    return " ".join(value.casefold().replace("_", " ").replace("-", " ").split())


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _first_query_row(value: Any) -> list[Any]:
    if not isinstance(value, list) or not value:
        return []
    first = value[0]
    return first if isinstance(first, list) else []
