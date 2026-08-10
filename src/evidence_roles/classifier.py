"""Conservative deterministic evidence-role classification for U8.

The classifier consumes the already complete, immutable U8B inspection.  It
reuses the frozen Sprint 2.2 source/provenance classifiers but introduces a
separate role dimension so primary underlying records can be distinguished from
commentary, structural wrappers, and cross-references without redefining legacy
source types.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Final

from chunk_provenance import classify_chunk_provenance
from evidence_classification import (
    EvidenceSourceClassification,
    EvidenceSourceType,
    classify_evidence_source,
)
from evidence_retrieval.models import DocumentEvidenceInspection

from .models import (
    DocumentEvidenceRoleInspection,
    EvidenceRole,
    EvidenceRoleChunk,
    EvidenceRoleClassification,
    EvidenceRoleCount,
    EvidenceRolePage,
)


_DIRECT_PRIMARY_TYPES: Final[frozenset[EvidenceSourceType]] = frozenset(
    {
        EvidenceSourceType.CLAIMANT_CORRESPONDENCE,
        EvidenceSourceType.EMPLOYER_RECORD,
        EvidenceSourceType.INDEPENDENT_MEDICAL,
        EvidenceSourceType.OCCUPATIONAL_HEALTH,
        EvidenceSourceType.INSURER_RECORD,
        EvidenceSourceType.TRIBUNAL_RECORD,
    }
)

_COMMENTARY_TYPES: Final[frozenset[EvidenceSourceType]] = frozenset(
    {
        EvidenceSourceType.CLAIMANT_WITNESS_STATEMENT,
        EvidenceSourceType.RESPONDENT_WITNESS_STATEMENT,
        EvidenceSourceType.WITNESS_STATEMENT,
        EvidenceSourceType.CLAIMANT_SUBMISSION,
        EvidenceSourceType.RESPONDENT_SUBMISSION,
        EvidenceSourceType.SECONDARY_SUMMARY,
    }
)

_COMMENTARY_HEADING_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"^relevance\s+to\s+(?:the\s+)?claim\b", re.IGNORECASE),
    re.compile(r"^(?:claimant(?:'s)?\s+)?commentary\b", re.IGNORECASE),
    re.compile(r"^(?:evidence\s+)?summary\b", re.IGNORECASE),
    re.compile(r"^witness\s+summary\b", re.IGNORECASE),
    re.compile(r"^legal\s+significance\b", re.IGNORECASE),
    re.compile(r"^evidential\s+significance\b", re.IGNORECASE),
    re.compile(r"^why\s+this\s+matters\b", re.IGNORECASE),
    re.compile(r"^analysis\b", re.IGNORECASE),
)

_CROSS_REFERENCE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\bsee\s+(?:also\s+)?appendix\s+[a-z0-9.-]+\b", re.IGNORECASE),
    re.compile(r"\brefer(?:red|s|ring)?\s+to\s+appendix\s+[a-z0-9.-]+\b", re.IGNORECASE),
    re.compile(r"\bcross[-\s]?reference(?:d|s)?\b", re.IGNORECASE),
    re.compile(r"\bfor\s+(?:the\s+)?(?:email|letter|correspondence|record)\s+see\b", re.IGNORECASE),
    re.compile(r"\battached\s+(?:at|as)\s+appendix\b", re.IGNORECASE),
)

_EMAIL_HEADER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?im)^\s*(?:from|sender)\s*:\s*\S.+$"
)

_EMBEDDED_EMAIL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?im)^\s*email\s+\d+\s*[-–—:]?\s*\S.+?(?:→|->)\s*\S.+$"
)

_END_OF_APPENDIX_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?im)^\s*end\s+of\s+appendix\b"
)

_COMMENTARY_FILENAME_TERMS: Final[tuple[str, ...]] = (
    "chronology",
    "timeline",
    "written submissions",
    "written submission",
    "skeleton argument",
)


class EvidenceRoleClassificationError(RuntimeError):
    """Raised when a complete U8B inspection cannot be classified coherently."""


def classify_document_evidence_roles(
    inspection: DocumentEvidenceInspection,
) -> DocumentEvidenceRoleInspection:
    """Classify every governed U8B chunk without changing the evidence surface.

    Args:
        inspection: A complete immutable document inspection produced by U8B.

    Returns:
        A deterministic role inspection preserving every U8B page and chunk.

    Raises:
        EvidenceRoleClassificationError: If the supplied U8B structure is
            internally inconsistent or role classification loses/reorders a
            governed chunk.
    """

    _validate_complete_surface(inspection)
    document_hint = _document_hint(inspection)
    document_source = classify_evidence_source(
        file_name=inspection.original_filename,
        text=document_hint,
        document_hint=document_hint,
    )

    pages: list[EvidenceRolePage] = []
    counter: Counter[EvidenceRole] = Counter()
    classified_count = 0
    embedded_communication_active = False

    for page in inspection.pages:
        classified_chunks: list[EvidenceRoleChunk] = []
        for chunk in page.chunks:
            provenance = classify_chunk_provenance(
                file_name=inspection.original_filename,
                text=chunk.text,
                document_source_type=document_source.source_type,
            )

            leading_lines = _leading_nonempty_lines(chunk.text)
            embedded_start = _has_embedded_email_start(chunk.text)
            leading_commentary = _starts_with_commentary_heading(leading_lines)
            structural = _looks_like_cover_or_index(
                text=chunk.text,
                leading_lines=leading_lines,
            )
            cross_reference = _looks_like_standalone_cross_reference(
                text=chunk.text
            )
            end_of_appendix = _looks_like_end_of_appendix(chunk.text)

            embedded_continuation = (
                provenance.source_type is EvidenceSourceType.MIXED_CORRESPONDENCE
                and embedded_communication_active
                and not embedded_start
                and not leading_commentary
                and not structural
                and not cross_reference
                and not end_of_appendix
            )

            decision = _classify_role(
                file_name=inspection.original_filename,
                text=chunk.text,
                document_source=document_source,
                source_type=provenance.source_type,
                source_label=provenance.label,
                provenance_method=provenance.method,
                primary_tier=provenance.primary_tier,
                primary_label=provenance.primary_label,
                embedded_communication=embedded_start,
                embedded_continuation=embedded_continuation,
            )

            if provenance.source_type is EvidenceSourceType.MIXED_CORRESPONDENCE:
                if embedded_start or embedded_continuation:
                    embedded_communication_active = True
                if (
                    leading_commentary
                    or structural
                    or cross_reference
                    or end_of_appendix
                ):
                    embedded_communication_active = False
            else:
                embedded_communication_active = False

            classified_chunks.append(
                EvidenceRoleChunk(
                    chunk=chunk,
                    classification=decision,
                )
            )
            counter[decision.role] += 1
            classified_count += 1

        if tuple(item.chunk for item in classified_chunks) != page.chunks:
            raise EvidenceRoleClassificationError(
                "Evidence-role classification changed or reordered governed chunks."
            )

        pages.append(EvidenceRolePage(page=page, chunks=tuple(classified_chunks)))

    if classified_count != inspection.evidence_chunk_count:
        raise EvidenceRoleClassificationError(
            "Evidence-role classification did not cover every governed chunk."
        )
    if tuple(item.page for item in pages) != inspection.pages:
        raise EvidenceRoleClassificationError(
            "Evidence-role classification changed or reordered governed pages."
        )

    counts = tuple(
        EvidenceRoleCount(role=role, count=counter[role]) for role in EvidenceRole
    )
    return DocumentEvidenceRoleInspection(
        document=inspection,
        document_source_type=document_source.source_type,
        document_source_label=document_source.label,
        document_source_method=document_source.method,
        pages=tuple(pages),
        role_counts=counts,
    )


def classify_evidence_role(
    *,
    file_name: str,
    text: str,
    document_hint: str = "",
) -> EvidenceRoleClassification:
    """Classify one text item using the same deterministic U8C rules.

    This helper is intended for focused testing and future orchestration.  It
    does not assert corpus completeness; U8D remains responsible for search
    coverage and negative-finding receipts.
    """

    document_source = classify_evidence_source(
        file_name=file_name,
        text=document_hint or text,
        document_hint=document_hint,
    )
    provenance = classify_chunk_provenance(
        file_name=file_name,
        text=text,
        document_source_type=document_source.source_type,
    )
    return _classify_role(
        file_name=file_name,
        text=text,
        document_source=document_source,
        source_type=provenance.source_type,
        source_label=provenance.label,
        provenance_method=provenance.method,
        primary_tier=provenance.primary_tier,
        primary_label=provenance.primary_label,
        embedded_communication=_has_embedded_email_start(text),
        embedded_continuation=False,
    )


def _classify_role(
    *,
    file_name: str,
    text: str,
    document_source: EvidenceSourceClassification,
    source_type: EvidenceSourceType,
    source_label: str,
    provenance_method: str,
    primary_tier: int,
    primary_label: str,
    embedded_communication: bool = False,
    embedded_continuation: bool = False,
) -> EvidenceRoleClassification:
    normalised = _normalise(text)
    leading_lines = _leading_nonempty_lines(text)

    structural = _looks_like_cover_or_index(text=text, leading_lines=leading_lines)
    commentary = _looks_like_commentary(
        file_name=file_name,
        leading_lines=leading_lines,
    )
    commentary_anywhere = _contains_commentary_heading(leading_lines)
    cross_reference = _looks_like_standalone_cross_reference(text=text)

    provenance_direct = source_type in _DIRECT_PRIMARY_TYPES
    embedded_direct = (
        source_type is EvidenceSourceType.MIXED_CORRESPONDENCE
        and (embedded_communication or embedded_continuation)
    )
    direct = provenance_direct or embedded_direct

    # A real underlying communication may share a chunk with an editorial
    # "Relevance to the Claim" block.  That is materially mixed and must not be
    # promoted to pure primary evidence.  For embedded correspondence, inspect
    # the entire governed chunk for an explicit commentary heading because the
    # communication can begin before the editorial block.
    if direct and (commentary or commentary_anywhere):
        if embedded_direct:
            return _decision(
                EvidenceRole.MIXED,
                "u8c.mixed.embedded-communication-and-commentary.v1",
                "A deterministic embedded communication and an editorial commentary heading occur in the same governed chunk.",
                source_type,
                source_label,
                provenance_method,
                primary_tier,
                primary_label,
            )
        return _decision(
            EvidenceRole.MIXED,
            "u8c.mixed.primary-and-commentary.v1",
            "Direct-source provenance and a commentary heading occur in the same governed chunk.",
            source_type,
            source_label,
            provenance_method,
            primary_tier,
            primary_label,
        )

    # Structural wrappers are recognised only when no direct communication is
    # established for the chunk itself.
    if structural and not direct:
        return _decision(
            EvidenceRole.COVER_OR_INDEX,
            "u8c.cover-or-index.structural-wrapper.v1",
            "The short governed chunk is an appendix/contents/index structural wrapper.",
            source_type,
            source_label,
            provenance_method,
            primary_tier,
            primary_label,
        )

    # Cross-reference classification is deliberately narrow: a direct email or
    # letter that happens to cite another appendix remains primary evidence.
    if cross_reference and not direct and not commentary:
        return _decision(
            EvidenceRole.CROSS_REFERENCE,
            "u8c.cross-reference.standalone-reference.v1",
            "The governed chunk principally points to another appendix or evidential item.",
            source_type,
            source_label,
            provenance_method,
            primary_tier,
            primary_label,
        )

    if commentary:
        return _decision(
            EvidenceRole.COMMENTARY,
            "u8c.commentary.heading-or-chronology.v1",
            "The governed chunk is marked as commentary/summary/significance material or belongs to a chronology container.",
            source_type,
            source_label,
            provenance_method,
            primary_tier,
            primary_label,
        )

    if source_type in _COMMENTARY_TYPES:
        return _decision(
            EvidenceRole.COMMENTARY,
            "u8c.commentary.source-type.v1",
            "Existing provenance identifies testimonial, submission, or secondary-summary material rather than an underlying contemporaneous record.",
            source_type,
            source_label,
            provenance_method,
            primary_tier,
            primary_label,
        )

    if direct:
        if embedded_direct:
            if embedded_communication:
                rule_id = "u8c.primary.embedded-communication.v1"
                basis = (
                    "The governed chunk contains a deterministic embedded "
                    "Email n sender-to-recipient communication marker."
                )
            else:
                rule_id = "u8c.primary.embedded-communication-continuation.v1"
                basis = (
                    "The governed chunk continues a deterministic embedded "
                    "communication established by the preceding governed chunk."
                )
            return _decision(
                EvidenceRole.PRIMARY_SOURCE,
                rule_id,
                basis,
                source_type,
                source_label,
                provenance_method,
                primary_tier,
                primary_label,
            )
        return _decision(
            EvidenceRole.PRIMARY_SOURCE,
            "u8c.primary.direct-source.v1",
            "Existing chunk provenance identifies a direct correspondence, employer, medical, occupational-health, insurer, or tribunal record.",
            source_type,
            source_label,
            provenance_method,
            primary_tier,
            primary_label,
        )

    # Ambiguous correspondence containers are intentionally not upgraded merely
    # because their filenames mention an insurer/employer.  The existing chunk
    # provenance classifier returns MIXED_CORRESPONDENCE for that situation.
    if source_type is EvidenceSourceType.MIXED_CORRESPONDENCE:
        return _decision(
            EvidenceRole.UNCLASSIFIED,
            "u8c.unclassified.mixed-correspondence.v1",
            "The correspondence container lacks a deterministic local authorship signal.",
            source_type,
            source_label,
            provenance_method,
            primary_tier,
            primary_label,
        )

    # Legal authority is intentionally not called primary case evidence here;
    # its later analytical use remains outside U8C.
    if source_type is EvidenceSourceType.LEGAL_AUTHORITY:
        return _decision(
            EvidenceRole.UNCLASSIFIED,
            "u8c.unclassified.legal-authority.v1",
            "Legal authority is not classified as primary factual evidence by the U8 evidence-role layer.",
            source_type,
            source_label,
            provenance_method,
            primary_tier,
            primary_label,
        )

    if not normalised:
        return _decision(
            EvidenceRole.UNCLASSIFIED,
            "u8c.unclassified.empty-text.v1",
            "The governed chunk contains no classifiable text.",
            source_type,
            source_label,
            provenance_method,
            primary_tier,
            primary_label,
        )

    return _decision(
        EvidenceRole.UNCLASSIFIED,
        "u8c.unclassified.no-deterministic-rule.v1",
        "No deterministic U8C rule safely establishes a primary, commentary, structural, or cross-reference role.",
        source_type,
        source_label,
        provenance_method,
        primary_tier,
        primary_label,
    )


def _validate_complete_surface(inspection: DocumentEvidenceInspection) -> None:
    if inspection.page_count != len(inspection.pages):
        raise EvidenceRoleClassificationError(
            "U8B inspection page_count does not match its governed pages."
        )

    counted = 0
    for expected_page_number, page in enumerate(inspection.pages, start=1):
        if page.page_number != expected_page_number:
            raise EvidenceRoleClassificationError(
                "U8B inspection pages are not in deterministic page order."
            )
        for expected_ordinal, chunk in enumerate(page.chunks):
            if chunk.page_number != page.page_number:
                raise EvidenceRoleClassificationError(
                    "U8B chunk page coordinate does not match its governed page."
                )
            if chunk.chunk_ordinal != expected_ordinal:
                raise EvidenceRoleClassificationError(
                    "U8B chunks are not in deterministic ordinal order."
                )
            counted += 1

    if counted != inspection.evidence_chunk_count:
        raise EvidenceRoleClassificationError(
            "U8B inspection evidence_chunk_count does not match its governed chunks."
        )


def _document_hint(inspection: DocumentEvidenceInspection, max_chars: int = 6000) -> str:
    text = "\n".join(page.text for page in inspection.pages)
    return text[:max_chars]


def _has_embedded_email_start(text: str) -> bool:
    return bool(_EMBEDDED_EMAIL_PATTERN.search(text))


def _contains_commentary_heading(leading_lines: tuple[str, ...]) -> bool:
    for line in leading_lines:
        stripped = line.strip(" :-–—\t")
        if any(pattern.search(stripped) for pattern in _COMMENTARY_HEADING_PATTERNS):
            return True
    return False


def _starts_with_commentary_heading(leading_lines: tuple[str, ...]) -> bool:
    if not leading_lines:
        return False
    stripped = leading_lines[0].strip(" :-–—\t")
    return any(pattern.search(stripped) for pattern in _COMMENTARY_HEADING_PATTERNS)


def _looks_like_end_of_appendix(text: str) -> bool:
    return bool(_END_OF_APPENDIX_PATTERN.search(text))


def _looks_like_commentary(*, file_name: str, leading_lines: tuple[str, ...]) -> bool:
    filename = _normalise(file_name)
    if any(term in filename for term in _COMMENTARY_FILENAME_TERMS):
        return True

    return _contains_commentary_heading(leading_lines[:8])


def _looks_like_cover_or_index(*, text: str, leading_lines: tuple[str, ...]) -> bool:
    if (
        not leading_lines
        or len(text) > 500
        or _EMAIL_HEADER_PATTERN.search(text)
        or _EMBEDDED_EMAIL_PATTERN.search(text)
    ):
        return False

    first = _normalise(leading_lines[0])
    joined = _normalise(" ".join(leading_lines[:6]))

    if re.fullmatch(r"appendix\s+[a-z](?:\d+)?(?:\s+.*)?", first):
        return True
    if first in {"contents", "table of contents", "index", "document index", "cover sheet"}:
        return True
    if joined.startswith("evidence bundle index") or joined.startswith("appendix index"):
        return True
    return False


def _looks_like_standalone_cross_reference(*, text: str) -> bool:
    if (
        len(text) > 700
        or _EMAIL_HEADER_PATTERN.search(text)
        or _EMBEDDED_EMAIL_PATTERN.search(text)
    ):
        return False
    return any(pattern.search(text) for pattern in _CROSS_REFERENCE_PATTERNS)


def _leading_nonempty_lines(text: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in text.splitlines() if line.strip())


def _normalise(value: str) -> str:
    return " ".join(value.casefold().replace("_", " ").replace("-", " ").split())


def _decision(
    role: EvidenceRole,
    rule_id: str,
    basis: str,
    source_type: EvidenceSourceType,
    source_label: str,
    provenance_method: str,
    primary_tier: int,
    primary_label: str,
) -> EvidenceRoleClassification:
    return EvidenceRoleClassification(
        role=role,
        rule_id=rule_id,
        basis=basis,
        source_type=source_type,
        source_label=source_label,
        provenance_method=provenance_method,
        primary_tier=primary_tier,
        primary_label=primary_label,
    )


__all__ = [
    "EvidenceRoleClassificationError",
    "classify_document_evidence_roles",
    "classify_evidence_role",
]
