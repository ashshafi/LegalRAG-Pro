"""Post-retrieval evidence semantics for Sprint 2.2 Milestone 4.

This layer deliberately runs *after* the frozen Milestone 3 retrieval and
reranking pipeline. It does not change candidate selection, ranks, primary
source tiers, case scope, or deduplication. Its purpose is to describe how
reliably provenance is known and whether an excerpt contains a knowledge
assertion or a direct communication/acknowledgement indicator.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final

from chunk_provenance import (
    CHUNK_PROVENANCE_METHOD_KEY,
    CHUNK_SOURCE_TYPE_KEY,
)
from evidence_classification import (
    EVIDENCE_CLASSIFICATION_METHOD_KEY,
    EVIDENCE_SOURCE_TYPE_KEY,
    EvidenceSourceType,
    source_label,
)

SEMANTIC_SOURCE_TYPE_KEY: Final[str] = "semantic_source_type"
SEMANTIC_SOURCE_LABEL_KEY: Final[str] = "semantic_source_label"
PROVENANCE_BASIS_KEY: Final[str] = "provenance_basis"
PROVENANCE_CONFIDENCE_KEY: Final[str] = "provenance_confidence"
PROVENANCE_WARNING_KEY: Final[str] = "provenance_warning"
KNOWLEDGE_SIGNAL_KEY: Final[str] = "knowledge_signal"
KNOWLEDGE_SIGNAL_LABEL_KEY: Final[str] = "knowledge_signal_label"

_HIGH: Final[str] = "high"
_MEDIUM: Final[str] = "medium"
_LOW: Final[str] = "low"


@dataclass(frozen=True, slots=True)
class EvidenceSemanticAssessment:
    """Semantic assessment for one already-retrieved evidence chunk."""

    source_type: EvidenceSourceType
    label: str
    basis: str
    confidence: str
    warning: str
    knowledge_signal: str
    knowledge_signal_label: str


_ROLE_BASED_TYPES: Final[frozenset[EvidenceSourceType]] = frozenset(
    {
        EvidenceSourceType.EMPLOYER_RECORD,
        EvidenceSourceType.INDEPENDENT_MEDICAL,
        EvidenceSourceType.OCCUPATIONAL_HEALTH,
        EvidenceSourceType.INSURER_RECORD,
    }
)

_AUTHORSHIP_TYPES: Final[frozenset[EvidenceSourceType]] = frozenset(
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

_KNOWLEDGE_ASSERTION_PATTERNS: Final[tuple[str, ...]] = (
    r"\bfully aware\b",
    r"\baware of\b",
    r"\bwas aware\b",
    r"\bwere aware\b",
    r"\bknew\b",
    r"\bhad knowledge\b",
    r"\bon notice\b",
    r"\brecognised\b",
    r"\brecognized\b",
    r"\bunderstood\b",
    r"\baccepted\b",
)

_DIRECT_COMMUNICATION_PATTERNS: Final[tuple[str, ...]] = (
    r"\bwe received\b",
    r"\bi received\b",
    r"\bhas received\b",
    r"\breceipt of\b",
    r"\backnowledg(?:e|ed|ement|ment)\b",
    r"\bdiscussed with\b",
    r"\bdiscussed at\b",
    r"\bconfirmed receipt\b",
    r"\bconfirmed that .* received\b",
    r"(?:^|\n)\s*to\s*:\s*[^\n]+",
    r"(?:^|\n)\s*cc\s*:\s*[^\n]+",
)


def enrich_evidence_semantics(results: dict[str, Any]) -> dict[str, Any]:
    """Add Milestone 4 semantic metadata without reordering retrieval results."""

    documents = _first_query_row(results.get("documents"))
    metadatas = _first_query_row(results.get("metadatas"))
    if not metadatas:
        return results

    enriched_metadatas: list[dict[str, Any]] = []
    for index, metadata in enumerate(metadatas):
        metadata_dict = dict(metadata) if isinstance(metadata, dict) else {}
        text = ""
        if index < len(documents) and documents[index] is not None:
            text = str(documents[index])
        assessment = assess_evidence_semantics(metadata_dict, text=text)
        metadata_dict[SEMANTIC_SOURCE_TYPE_KEY] = assessment.source_type.value
        metadata_dict[SEMANTIC_SOURCE_LABEL_KEY] = assessment.label
        metadata_dict[PROVENANCE_BASIS_KEY] = assessment.basis
        metadata_dict[PROVENANCE_CONFIDENCE_KEY] = assessment.confidence
        metadata_dict[PROVENANCE_WARNING_KEY] = assessment.warning
        metadata_dict[KNOWLEDGE_SIGNAL_KEY] = assessment.knowledge_signal
        metadata_dict[KNOWLEDGE_SIGNAL_LABEL_KEY] = assessment.knowledge_signal_label
        enriched_metadatas.append(metadata_dict)

    enriched = dict(results)
    enriched["metadatas"] = [enriched_metadatas]
    return enriched


def assess_evidence_semantics(
    metadata: dict[str, Any] | None,
    *,
    text: str,
) -> EvidenceSemanticAssessment:
    """Assess post-retrieval provenance reliability and assertion semantics."""

    metadata = dict(metadata or {})
    source_type = _parse_source_type(metadata.get(CHUNK_SOURCE_TYPE_KEY))
    method = str(metadata.get(CHUNK_PROVENANCE_METHOD_KEY) or "").strip().casefold()
    file_name = str(metadata.get("file") or "")
    classification_method = str(
        metadata.get(EVIDENCE_CLASSIFICATION_METHOD_KEY) or ""
    ).strip().casefold()

    semantic_type = source_type
    basis, confidence, warning = _basis_confidence(
        source_type=source_type,
        method=method,
        file_name=file_name,
        classification_method=classification_method,
    )

    # A role-based label inherited from an automatic container classification
    # is not reliable authorship when the filename itself does not identify
    # that source. This catches anomalies such as a "Leadership Continuity"
    # document becoming OH evidence merely because its body mentions OH.
    if (
        source_type in _ROLE_BASED_TYPES
        and method == "document-inherited"
        and classification_method not in {"explicit", "manual"}
        and not _filename_supports_source_type(file_name, source_type)
    ):
        semantic_type = EvidenceSourceType.OTHER
        basis = "container_fallback"
        confidence = _LOW
        warning = (
            "Automatic container/content classification does not establish "
            "the chunk's author or source."
        )

    # Party-authored correspondence must not inherit provenance merely because
    # a copy is held in another party's bundle. This correction is deliberately
    # post-retrieval: it changes semantic attribution only and therefore cannot
    # alter Milestone 3 ranking or source selection.
    party_override = _party_authorship_override(
        file_name=file_name,
        text=text,
        current_type=semantic_type,
        basis=basis,
        confidence=confidence,
        warning=warning,
    )
    if party_override is not None:
        semantic_type, basis, confidence, warning = party_override

    knowledge_signal, knowledge_signal_label = _knowledge_signal(text)

    return EvidenceSemanticAssessment(
        source_type=semantic_type,
        label=source_label(semantic_type),
        basis=basis,
        confidence=confidence,
        warning=warning,
        knowledge_signal=knowledge_signal,
        knowledge_signal_label=knowledge_signal_label,
    )



def _party_authorship_override(
    *,
    file_name: str,
    text: str,
    current_type: EvidenceSourceType,
    basis: str,
    confidence: str,
    warning: str,
) -> tuple[EvidenceSourceType, str, str, str] | None:
    """Return a conservative party-authorship semantic override when reliable.

    The function is intentionally limited to weak/unknown container provenance.
    It never overrides manual/explicit sender/signature attribution and never
    feeds back into retrieval or reranking.
    """

    if basis not in {"container_fallback", "unknown"}:
        return None

    # A filename that names the claimant and identifies a response/letter is
    # strong document-identity evidence of authorship, even if a copy is stored
    # in an employer correspondence bundle.
    if _filename_identifies_claimant_correspondence(file_name):
        return (
            EvidenceSourceType.CLAIMANT_CORRESPONDENCE,
            "known_document_author",
            _HIGH,
            "",
        )

    # A claimant signature is stronger than container ownership. Restrict the
    # check to the trailing signature zone so an employer letter merely naming
    # the claimant in its address block is not misclassified.
    if _claimant_signature_present(text):
        return (
            EvidenceSourceType.CLAIMANT_CORRESPONDENCE,
            "signature",
            _HIGH,
            "",
        )

    # Some PDF/export filenames describe the recipient or container rather than
    # the author (for example, an employer-held copy of a claimant response).
    # In that narrow case, strong first-person response/request language can
    # establish party authorship semantically. Confidence remains medium because
    # the author is inferred from the passage rather than an explicit header.
    if _looks_like_claimant_first_person_correspondence(text):
        return (
            EvidenceSourceType.CLAIMANT_CORRESPONDENCE,
            "known_document_author",
            _MEDIUM,
            (
                "Party authorship is identified from strong first-person "
                "claimant-response language; container ownership does not "
                "determine authorship."
            ),
        )

    # Keep the prior semantic assessment unchanged where party authorship cannot
    # be established reliably.
    return None


def _filename_identifies_claimant_correspondence(file_name: str) -> bool:
    name = _normalise(file_name)
    claimant_identity = any(
        phrase in name
        for phrase in (
            "arshad shafi",
            "mr arshad shafi",
            "claimant response",
            "claimant letter",
            "claimant email",
            "claimant correspondence",
        )
    )
    correspondence_identity = any(
        phrase in name
        for phrase in (
            "response",
            "capability review",
            "letter",
            "email",
            "correspondence",
        )
    )
    return claimant_identity and correspondence_identity


def _claimant_signature_present(text: str) -> bool:
    trailing_lines = [line.strip() for line in text[-900:].splitlines() if line.strip()]
    if not trailing_lines:
        return False

    # Prefer a conventional sign-off followed by the claimant's name.
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
            signature_zone = _normalise(" ".join(trailing_lines[index + 1 : index + 5]))
            if "arshad shafi" in signature_zone:
                return True

    # PDF extraction can lose the sign-off. Accept the claimant's exact name
    # only in the final few lines, never anywhere in the body/header.
    final_zone = _normalise(" ".join(trailing_lines[-4:]))
    return "arshad shafi" in final_zone


def _looks_like_claimant_first_person_correspondence(text: str) -> bool:
    """Recognise a claimant-authored response without using topic words alone."""

    normalised = " ".join(text.casefold().split())
    if not normalised:
        return False

    # Require first-person authorship plus a response posture directed to the
    # other party. This avoids treating an employer's "I am writing regarding
    # your employment" as claimant correspondence.
    first_person = bool(re.search(r"\b(?:i|my|me)\b", normalised))
    if not first_person:
        return False

    response_cues = (
        r"\bthank you for your (?:email|letter)\b",
        r"\bmy response to your (?:email|letter)\b",
        r"\byour letter dated\b",
        r"\byour email dated\b",
        r"\bplease refer me\b",
    )
    claimant_position_cues = (
        r"\bmy employment\b",
        r"\bmy fitness\b",
        r"\bmy health\b",
        r"\bmy disability\b",
        r"\bmy medical\b",
        r"\bmy return to work\b",
        r"\bi (?:request|am requesting|ask)\b",
        r"\bi welcome the opportunity to engage\b",
        r"\bthe company'?s capability review\b",
    )

    response_matches = sum(bool(re.search(pattern, normalised)) for pattern in response_cues)
    position_matches = sum(
        bool(re.search(pattern, normalised)) for pattern in claimant_position_cues
    )

    # Two independent signals are required. At least one must show the response
    # relationship, so ordinary first-person employer prose cannot qualify.
    return response_matches >= 1 and (response_matches + position_matches) >= 2

def _basis_confidence(
    *,
    source_type: EvidenceSourceType,
    method: str,
    file_name: str,
    classification_method: str,
) -> tuple[str, str, str]:
    if method == "manual":
        return "manual", _HIGH, ""
    if method == "explicit":
        return "manual", _HIGH, ""
    if method == "chunk-leading-sender":
        return "explicit_sender", _HIGH, ""
    if method == "chunk-signature":
        return "signature", _HIGH, ""
    if method == "document-authorship-inherited":
        if source_type in _AUTHORSHIP_TYPES:
            return "known_document_author", _HIGH, ""
        return "known_document_author", _MEDIUM, ""
    if method == "mixed-container-fallback":
        return (
            "mixed",
            _MEDIUM,
            "No single author is reliably attributable within this chunk.",
        )
    if method == "document-inherited":
        if classification_method in {"explicit", "manual"}:
            return "known_document_author", _HIGH, ""
        if _filename_supports_source_type(file_name, source_type):
            return "container_fallback", _MEDIUM, ""
        return (
            "container_fallback",
            _LOW,
            "The source label is inherited from a weak container classification.",
        )
    if method in {"unclassified", ""}:
        return "unknown", _LOW, "Provenance could not be established."
    return "unknown", _LOW, "Provenance method is not sufficiently reliable."


def _filename_supports_source_type(
    file_name: str,
    source_type: EvidenceSourceType,
) -> bool:
    name = _normalise(file_name)
    phrases: dict[EvidenceSourceType, tuple[str, ...]] = {
        EvidenceSourceType.EMPLOYER_RECORD: (
            "caci",
            "employer",
            "human resources",
            "hr letter",
            "employment contract",
            "employment agreement",
            "payslip",
            "p60",
        ),
        EvidenceSourceType.INDEPENDENT_MEDICAL: (
            "gp",
            "nhs",
            "psychiatrist",
            "psychiatric report",
            "medical report",
            "medical records",
            "fit note",
        ),
        EvidenceSourceType.OCCUPATIONAL_HEALTH: (
            "occupational health",
            "oh report",
            "occupational physician",
        ),
        EvidenceSourceType.INSURER_RECORD: (
            "unum",
            "swiss life",
            "insurer",
            "insurance",
            "income protection",
        ),
        EvidenceSourceType.TRIBUNAL_RECORD: (
            "tribunal",
            "et order",
            "judgment",
            "notice of hearing",
        ),
    }
    return any(phrase in name for phrase in phrases.get(source_type, ()))


def _knowledge_signal(text: str) -> tuple[str, str]:
    normalised = text.casefold()
    has_direct_indicator = any(
        re.search(pattern, normalised, flags=re.MULTILINE | re.DOTALL)
        for pattern in _DIRECT_COMMUNICATION_PATTERNS
    )
    has_assertion = any(
        re.search(pattern, normalised, flags=re.MULTILINE)
        for pattern in _KNOWLEDGE_ASSERTION_PATTERNS
    )

    if has_direct_indicator:
        return (
            "direct_communication_indicator",
            "Direct communication/acknowledgement indicator present",
        )
    if has_assertion:
        return (
            "source_assertion",
            "Knowledge/awareness assertion present",
        )
    return "none", "No explicit knowledge indicator detected"


def _parse_source_type(value: Any) -> EvidenceSourceType:
    try:
        return EvidenceSourceType(str(value).strip())
    except ValueError:
        return EvidenceSourceType.OTHER


def _normalise(value: str) -> str:
    return " ".join(value.casefold().replace("_", " ").replace("-", " ").split())


def _first_query_row(value: Any) -> list[Any]:
    if not isinstance(value, list) or not value:
        return []
    first = value[0]
    return first if isinstance(first, list) else []
