"""Evidence-source classification for LegalRAG Pro.

This module classifies the provenance of retrieved/indexed evidence. Source
classification is deliberately separate from evidential status: a source can be
an employer document while a proposition drawn from it may still be disputed,
inferential, or only a legal argument.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

EVIDENCE_SOURCE_TYPE_KEY: Final[str] = "evidence_source_type"
EVIDENCE_SOURCE_LABEL_KEY: Final[str] = "evidence_source_label"
EVIDENCE_CLASSIFICATION_METHOD_KEY: Final[str] = "evidence_classification_method"


class EvidenceSourceType(StrEnum):
    """Stable machine-readable evidence source categories."""

    CLAIMANT_WITNESS_STATEMENT = "claimant_witness_statement"
    RESPONDENT_WITNESS_STATEMENT = "respondent_witness_statement"
    WITNESS_STATEMENT = "witness_statement"
    CLAIMANT_CORRESPONDENCE = "claimant_correspondence"
    EMPLOYER_RECORD = "employer_record"
    INDEPENDENT_MEDICAL = "independent_medical"
    OCCUPATIONAL_HEALTH = "occupational_health"
    INSURER_RECORD = "insurer_record"
    TRIBUNAL_RECORD = "tribunal_record"
    CLAIMANT_SUBMISSION = "claimant_submission"
    RESPONDENT_SUBMISSION = "respondent_submission"
    LEGAL_AUTHORITY = "legal_authority"
    SECONDARY_SUMMARY = "secondary_summary"
    MIXED_CORRESPONDENCE = "mixed_correspondence"
    OTHER = "other"


_SOURCE_LABELS: Final[dict[EvidenceSourceType, str]] = {
    EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT: "Claimant evidence",
    EvidenceSourceType.RESPONDENT_WITNESS_STATEMENT: "Respondent evidence",
    EvidenceSourceType.WITNESS_STATEMENT: "Witness evidence",
    EvidenceSourceType.CLAIMANT_CORRESPONDENCE: "Claimant evidence",
    EvidenceSourceType.EMPLOYER_RECORD: "Employer evidence",
    EvidenceSourceType.INDEPENDENT_MEDICAL: "Independent medical evidence",
    EvidenceSourceType.OCCUPATIONAL_HEALTH: "Occupational-health evidence",
    EvidenceSourceType.INSURER_RECORD: "Insurer evidence",
    EvidenceSourceType.TRIBUNAL_RECORD: "Tribunal record",
    EvidenceSourceType.CLAIMANT_SUBMISSION: "Claimant submission",
    EvidenceSourceType.RESPONDENT_SUBMISSION: "Respondent submission",
    EvidenceSourceType.LEGAL_AUTHORITY: "Legal authority",
    EvidenceSourceType.SECONDARY_SUMMARY: "Secondary summary",
    EvidenceSourceType.MIXED_CORRESPONDENCE: "Mixed / composite evidence",
    EvidenceSourceType.OTHER: "Unclassified evidence",
}


@dataclass(frozen=True, slots=True)
class EvidenceSourceClassification:
    """One source classification and the method used to obtain it."""

    source_type: EvidenceSourceType
    label: str
    method: str


def source_label(source_type: EvidenceSourceType | str) -> str:
    """Return the user-facing label for a source type."""

    parsed = _parse_source_type(source_type)
    return _SOURCE_LABELS[parsed]


def classify_evidence_source(
    *,
    file_name: str,
    text: str = "",
    document_hint: str = "",
    explicit_source_type: EvidenceSourceType | str | None = None,
) -> EvidenceSourceClassification:
    """Classify an evidence source conservatively.

    Args:
        file_name: Source filename.
        text: Current chunk/page text.
        document_hint: Limited same-document text used only to resolve a
            witness statement's party where possible.
        explicit_source_type: Optional manual/programmatic override.

    Returns:
        A stable source classification. Ambiguous material is left as a
        neutral/generic category rather than being upgraded to stronger
        evidence provenance.
    """

    if explicit_source_type is not None:
        parsed = _parse_source_type(explicit_source_type)
        return EvidenceSourceClassification(
            source_type=parsed,
            label=_SOURCE_LABELS[parsed],
            method="explicit",
        )

    file_text = _normalise(file_name)
    chunk_text = _normalise(text)
    hint_text = _normalise(document_hint)
    combined = f"{file_text} {chunk_text}".strip()

    if _looks_like_legal_authority(file_text):
        return _classification(EvidenceSourceType.LEGAL_AUTHORITY)

    if _looks_like_tribunal_record(file_text, chunk_text):
        return _classification(EvidenceSourceType.TRIBUNAL_RECORD)

    if _looks_like_claimant_submission(file_text):
        return _classification(EvidenceSourceType.CLAIMANT_SUBMISSION)

    if _looks_like_respondent_submission(file_text):
        return _classification(EvidenceSourceType.RESPONDENT_SUBMISSION)

    if _looks_like_witness_statement(file_text, chunk_text):
        party_text = f"{chunk_text} {hint_text}"
        if _contains_any(
            party_text,
            (
                "claimant witness statement",
                "witness statement of the claimant",
                "i am the claimant",
                "i, the claimant",
                "the claimant in these proceedings",
            ),
        ):
            return _classification(EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT)
        if _contains_any(
            party_text,
            (
                "respondent witness statement",
                "witness statement of the respondent",
                "i am a witness for the respondent",
                "on behalf of the respondent",
            ),
        ):
            return _classification(EvidenceSourceType.RESPONDENT_WITNESS_STATEMENT)
        return _classification(EvidenceSourceType.WITNESS_STATEMENT)

    if _looks_like_independent_medical(file_text, chunk_text):
        return _classification(EvidenceSourceType.INDEPENDENT_MEDICAL)

    if _looks_like_occupational_health(file_text, chunk_text):
        return _classification(EvidenceSourceType.OCCUPATIONAL_HEALTH)

    if _looks_like_insurer_record(file_text, chunk_text):
        return _classification(EvidenceSourceType.INSURER_RECORD)

    if _looks_like_secondary_summary(file_text):
        return _classification(EvidenceSourceType.SECONDARY_SUMMARY)

    if _looks_like_claimant_correspondence(file_text, chunk_text):
        return _classification(EvidenceSourceType.CLAIMANT_CORRESPONDENCE)

    if _looks_like_employer_record(file_text, chunk_text):
        return _classification(EvidenceSourceType.EMPLOYER_RECORD)

    if "correspondence" in file_text:
        return _classification(EvidenceSourceType.MIXED_CORRESPONDENCE)

    if _contains_any(
        combined,
        (
            "employment agreement",
            "employment contract",
            "contract of employment",
            "payslip",
            "p60",
        ),
    ):
        return _classification(EvidenceSourceType.EMPLOYER_RECORD)

    return _classification(EvidenceSourceType.OTHER)


def add_classification_to_metadata(
    metadata: dict[str, Any] | None,
    *,
    text: str = "",
    document_hint: str = "",
) -> dict[str, Any]:
    """Return a metadata copy with evidence-source fields populated.

    Existing valid source metadata is authoritative and is preserved. This
    makes explicit/manual classification possible while providing a backwards-
    compatible fallback for chunks indexed before Sprint 2.2 Milestone 2.
    """

    enriched = dict(metadata or {})
    existing_type = enriched.get(EVIDENCE_SOURCE_TYPE_KEY)

    if existing_type is not None:
        try:
            parsed = _parse_source_type(existing_type)
        except ValueError:
            parsed = EvidenceSourceType.OTHER
            method = "invalid-stored-fallback"
        else:
            method = str(
                enriched.get(EVIDENCE_CLASSIFICATION_METHOD_KEY) or "stored"
            )

        enriched[EVIDENCE_SOURCE_TYPE_KEY] = parsed.value
        enriched[EVIDENCE_SOURCE_LABEL_KEY] = _SOURCE_LABELS[parsed]
        enriched[EVIDENCE_CLASSIFICATION_METHOD_KEY] = method
        return enriched

    classification = classify_evidence_source(
        file_name=str(enriched.get("file") or ""),
        text=text,
        document_hint=document_hint,
    )
    enriched[EVIDENCE_SOURCE_TYPE_KEY] = classification.source_type.value
    enriched[EVIDENCE_SOURCE_LABEL_KEY] = classification.label
    enriched[EVIDENCE_CLASSIFICATION_METHOD_KEY] = classification.method
    return enriched


def enrich_retrieval_metadata(results: dict[str, Any]) -> dict[str, Any]:
    """Add evidence-source metadata to a Chroma-style retrieval response.

    This does not alter Chroma or case scoping. It provides a safe compatibility
    path for existing indexes so Milestone 2 works without re-indexing current
    case documents. New indexing persists the same fields at ingestion time.
    """

    documents = _first_query_row(results.get("documents"))
    metadatas = _first_query_row(results.get("metadatas"))
    if not metadatas:
        return results

    hints_by_file: dict[str, str] = {}
    for index, metadata in enumerate(metadatas):
        if not isinstance(metadata, dict):
            continue
        file_name = str(metadata.get("file") or "")
        if not file_name:
            continue
        document = ""
        if index < len(documents) and documents[index] is not None:
            document = str(documents[index])
        if document:
            current = hints_by_file.get(file_name, "")
            if len(current) < 6000:
                hints_by_file[file_name] = f"{current}\n{document}"[:6000]

    enriched_metadatas: list[dict[str, Any]] = []
    for index, metadata in enumerate(metadatas):
        metadata_dict = metadata if isinstance(metadata, dict) else {}
        file_name = str(metadata_dict.get("file") or "")
        document = ""
        if index < len(documents) and documents[index] is not None:
            document = str(documents[index])
        enriched_metadatas.append(
            add_classification_to_metadata(
                metadata_dict,
                text=document,
                document_hint=hints_by_file.get(file_name, ""),
            )
        )

    enriched = dict(results)
    enriched["metadatas"] = [enriched_metadatas]
    return enriched


def _classification(source_type: EvidenceSourceType) -> EvidenceSourceClassification:
    return EvidenceSourceClassification(
        source_type=source_type,
        label=_SOURCE_LABELS[source_type],
        method="automatic",
    )


def _parse_source_type(source_type: EvidenceSourceType | str) -> EvidenceSourceType:
    if isinstance(source_type, EvidenceSourceType):
        return source_type
    return EvidenceSourceType(str(source_type).strip())


def _normalise(value: str) -> str:
    return " ".join(value.casefold().replace("_", " ").replace("-", " ").split())


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _looks_like_legal_authority(file_text: str) -> bool:
    return _contains_any(
        file_text,
        (
            "legal authority",
            "authorities bundle",
            "case law",
            "equality act 2010",
            "employment rights act",
            "employment tribunal rules",
            "rules of procedure",
        ),
    )


def _looks_like_tribunal_record(file_text: str, chunk_text: str) -> bool:
    tribunal_terms = (
        "tribunal order",
        "case management order",
        "preliminary hearing order",
        "employment tribunal judgment",
        "notice of hearing",
        "record of preliminary hearing",
    )
    if _contains_any(file_text, tribunal_terms):
        return True
    return "employment tribunal" in chunk_text and _contains_any(
        chunk_text,
        ("ordered that", "judgment", "notice of hearing", "case management"),
    )


def _looks_like_claimant_submission(file_text: str) -> bool:
    return _contains_any(
        file_text,
        (
            "et1",
            "grounds of claim",
            "particulars of claim",
            "schedule of loss",
            "claimant skeleton",
            "claimant submission",
            "claimant submissions",
        ),
    )


def _looks_like_respondent_submission(file_text: str) -> bool:
    return _contains_any(
        file_text,
        (
            "et3",
            "grounds of resistance",
            "respondent skeleton",
            "respondent submission",
            "respondent submissions",
            "response to claim",
        ),
    )


def _looks_like_witness_statement(file_text: str, chunk_text: str) -> bool:
    return "witness statement" in file_text or "witness statement" in chunk_text


def _looks_like_independent_medical(file_text: str, chunk_text: str) -> bool:
    text = f"{file_text} {chunk_text}"
    return _contains_any(
        text,
        (
            "gp record",
            "gp records",
            "general practitioner",
            "consultant psychiatrist",
            "psychiatric report",
            "psychiatrist report",
            "medical records",
            "medical report",
            "nhs",
            "fit note",
        ),
    ) and not _looks_like_occupational_health(file_text, chunk_text)


def _looks_like_occupational_health(file_text: str, chunk_text: str) -> bool:
    text = f"{file_text} {chunk_text}"
    return _contains_any(
        text,
        (
            "occupational health",
            "occupational-health",
            "oh report",
            "occupational physician",
        ),
    )


def _looks_like_insurer_record(file_text: str, chunk_text: str) -> bool:
    text = f"{file_text} {chunk_text}"
    return _contains_any(
        text,
        (
            "unum",
            "swiss life",
            "insurer",
            "insurance benefit",
            "permanent health insurance",
            "group income protection",
            "income protection benefit",
        ),
    )


def _looks_like_secondary_summary(file_text: str) -> bool:
    return _contains_any(
        file_text,
        (
            "chronology",
            "case summary",
            "medical delay explanation",
            "summary of evidence",
        ),
    )


def _looks_like_claimant_correspondence(file_text: str, chunk_text: str) -> bool:
    text = f"{file_text} {chunk_text}"
    return _contains_any(
        text,
        (
            "claimant letter",
            "claimant email",
            "claimant correspondence",
            "from the claimant",
        ),
    )


def _looks_like_employer_record(file_text: str, chunk_text: str) -> bool:
    file_match = _contains_any(
        file_text,
        (
            "employer letter",
            "employer email",
            "employer correspondence",
            "caci letter",
            "caci email",
            "hr letter",
            "hr email",
            "capability letter",
            "return to work letter",
            "payslip",
            "p60",
            "employment agreement",
            "employment contract",
        ),
    )
    if file_match:
        return True

    # Content-only employer classification is deliberately narrow. The
    # presence of a company name alone is not enough because claimant letters
    # often quote or address the employer.
    return _contains_any(
        chunk_text,
        (
            "on behalf of the company",
            "human resources director",
            "hr director",
            "we are writing regarding your employment",
            "your employment with the company",
        ),
    )


def _first_query_row(value: Any) -> list[Any]:
    if not isinstance(value, list) or not value:
        return []
    first = value[0]
    return first if isinstance(first, list) else []
