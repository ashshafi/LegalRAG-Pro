"""Deterministic reconciliation of explicit governed evidence references.

The resolver consumes a *complete* U8D ``CaseEvidenceSearchResult``.  It never
opens Chroma, the source store, PDFs, OCR, or the filesystem.  Explicit appendix
and communication references are extracted from the immutable governed chunk
text already present in the U8D surface, then compared with the completely
inspected documents/chunks in that same surface.

A zero-match reference becomes ``POSSIBLE_REFERENCED_BUT_NOT_LOCATED`` only
when the U8D receipt proves the whole governed case corpus was completely
searched.  In a narrower document-complete scope, the same zero-match reference
remains ``UNRESOLVED_REFERENCE``.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Final

from evidence_roles import EvidenceRole
from evidence_search import (
    CaseEvidenceSearchResult,
    EvidenceSearchCompletion,
    NegativeFindingScope,
)

from .models import (
    CaseEvidenceReferenceResolution,
    EvidenceReference,
    EvidenceReferenceKind,
    EvidenceReferenceResolution,
    EvidenceReferenceResolutionReceipt,
    EvidenceReferenceResolutionStatus,
)


_RECEIPT_SCHEMA_VERSION: Final[str] = "1.0"

# An explicit cue is mandatory so title/cover chunks containing "Appendix H4"
# are not treated as references to themselves.
_APPENDIX_REFERENCE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b(?:see|refer(?:red)?\s+to|reference(?:d)?(?:\s+in)?|"
    r"cross[- ]?reference(?:d)?\s+to|contained\s+in|set\s+out\s+in)\s+"
    r"(?:the\s+)?(?:appendix|exhibit)\s+(?P<label>[A-Z]{1,3}\s*\d{1,4}(?:\.\d+)?)\b"
)
_APPENDIX_LABEL_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)\bappendix\s+(?P<label>[A-Z]{1,3}\s*\d{1,4}(?:\.\d+)?)\b"
)

_MONTHS: Final[dict[str, int]] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
_MONTH_PATTERN: Final[str] = "(?:" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + ")"
_NAMED_DATE_PATTERN: Final[str] = rf"\d{{1,2}}\s+{_MONTH_PATTERN}\s+\d{{4}}"
_ISO_DATE_PATTERN: Final[str] = r"\d{4}-\d{2}-\d{2}"
_NUMERIC_DATE_PATTERN: Final[str] = r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
_DATE_PATTERN: Final[str] = rf"(?:{_NAMED_DATE_PATTERN}|{_ISO_DATE_PATTERN}|{_NUMERIC_DATE_PATTERN})"

_COMMUNICATION_TYPE_PATTERN: Final[str] = (
    r"(?P<communication_type>e-?mail|email|letter|correspondence|message|memorandum|memo)"
)
_PERSON_BEFORE_DATE: Final[str] = r"(?P<person>[^\n,;:]{2,80}?)"
_PERSON_TRAILING: Final[str] = r"(?P<person>[^\n,;:]{2,80}?)"
_PERSON_END_LOOKAHEAD: Final[str] = (
    r"(?=\s+(?:was|is|were|has|had|which|that|and|but|supports?|confirms?|"
    r"shows?|records?|states?|was\s+considered|is\s+referenced)\b|[.,;:]|$)"
)

_COMMUNICATION_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        rf"(?i)\b{_COMMUNICATION_TYPE_PATTERN}\s+from\s+{_PERSON_BEFORE_DATE}\s+"
        rf"(?:dated|of|on)\s+(?P<date>{_DATE_PATTERN})\b"
    ),
    re.compile(
        rf"(?i)\b{_COMMUNICATION_TYPE_PATTERN}\s+(?:dated|of|on)\s+"
        rf"(?P<date>{_DATE_PATTERN})\s+from\s+{_PERSON_TRAILING}{_PERSON_END_LOOKAHEAD}"
    ),
    re.compile(
        rf"(?i)\b{_COMMUNICATION_TYPE_PATTERN}\s+(?:dated|of|on)\s+"
        rf"(?P<date>{_DATE_PATTERN})\b"
    ),
    re.compile(
        rf"(?i)\b{_COMMUNICATION_TYPE_PATTERN}\s+from\s+{_PERSON_TRAILING}{_PERSON_END_LOOKAHEAD}"
    ),
)

_FROM_HEADER_RE: Final[re.Pattern[str]] = re.compile(r"(?im)^\s*from\s*:\s*.+?\s*$")
_TO_HEADER_RE: Final[re.Pattern[str]] = re.compile(r"(?im)^\s*to\s*:\s*.+?\s*$")
_EMAIL_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"(?i)\be-?mail\b|\bemail\b")
_LETTER_TOKEN_RE: Final[re.Pattern[str]] = re.compile(
    r"\bletter\b|^\s*dear\s+\S", re.IGNORECASE | re.MULTILINE
)
_MEMO_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"(?i)\bmemorandum\b|\bmemo\b")
_MESSAGE_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"(?i)\bmessage\b")


class EvidenceReferenceResolutionError(RuntimeError):
    """Raised when reference reconciliation cannot be proved coherently."""


@dataclass(frozen=True, slots=True)
class _CandidateTarget:
    document_id: str
    filename: str
    evidence_key: str
    text: str
    role: EvidenceRole


@dataclass(frozen=True, slots=True)
class _ExtractedReference:
    start: int
    raw_text: str
    kind: EvidenceReferenceKind
    appendix_label: str | None = None
    communication_type: str | None = None
    person_text: str | None = None
    date_text: str | None = None
    canonical_date: str | None = None


def resolve_evidence_references(
    search_result: CaseEvidenceSearchResult,
) -> CaseEvidenceReferenceResolution:
    """Extract and reconcile explicit references in one complete U8D result."""

    _validate_search_result(search_result)
    targets = _candidate_targets(search_result)
    appendix_documents = _appendix_document_index(search_result)

    resolutions: list[EvidenceReferenceResolution] = []
    for document in search_result.documents:
        filename = document.document.original_filename
        document_id = document.document.source_document_instance_id
        for page in document.pages:
            for role_chunk in page.chunks:
                chunk = role_chunk.chunk
                for ordinal, item in enumerate(_extract_references(chunk.text)):
                    reference = _build_reference(
                        document_id=document_id,
                        filename=filename,
                        evidence_key=chunk.evidence_key,
                        page_number=chunk.page_number,
                        chunk_ordinal=chunk.chunk_ordinal,
                        source_reference_ordinal=ordinal,
                        item=item,
                    )
                    resolutions.append(
                        _resolve_reference(
                            reference=reference,
                            source_evidence_key=chunk.evidence_key,
                            targets=targets,
                            appendix_documents=appendix_documents,
                            case_corpus_complete=search_result.receipt.case_corpus_complete,
                        )
                    )

    counts = Counter(item.status for item in resolutions)
    receipt = EvidenceReferenceResolutionReceipt(
        schema_version=_RECEIPT_SCHEMA_VERSION,
        case_id=search_result.case_id,
        search_mode=search_result.search_mode,
        searched_document_ids=search_result.receipt.searched_document_ids,
        documents_completely_expanded=search_result.receipt.documents_completely_expanded,
        pages_inspected=search_result.receipt.pages_inspected,
        chunks_inspected=search_result.receipt.chunks_inspected,
        case_corpus_complete=search_result.receipt.case_corpus_complete,
        possible_not_located_permitted=search_result.receipt.case_corpus_complete,
        reference_count=len(resolutions),
        resolved_count=counts[EvidenceReferenceResolutionStatus.RESOLVED],
        ambiguous_count=counts[EvidenceReferenceResolutionStatus.AMBIGUOUS],
        possible_not_located_count=counts[
            EvidenceReferenceResolutionStatus.POSSIBLE_REFERENCED_BUT_NOT_LOCATED
        ],
        unresolved_count=counts[EvidenceReferenceResolutionStatus.UNRESOLVED_REFERENCE],
    )
    return CaseEvidenceReferenceResolution(
        case_id=search_result.case_id,
        resolutions=tuple(resolutions),
        receipt=receipt,
    )


def _validate_search_result(search_result: CaseEvidenceSearchResult) -> None:
    receipt = search_result.receipt
    if receipt.case_id != search_result.case_id:
        raise EvidenceReferenceResolutionError("U8D search result and receipt case_id differ.")
    if receipt.completion is not EvidenceSearchCompletion.COMPLETE:
        raise EvidenceReferenceResolutionError(
            "Reference reconciliation requires a COMPLETE U8D evidence search."
        )
    if len(search_result.documents) != receipt.documents_completely_expanded:
        raise EvidenceReferenceResolutionError(
            "Reference reconciliation requires every receipted document surface."
        )

    document_ids = tuple(
        document.document.source_document_instance_id for document in search_result.documents
    )
    if document_ids != receipt.searched_document_ids:
        raise EvidenceReferenceResolutionError(
            "U8D searched_document_ids do not match the supplied document surfaces."
        )

    pages = sum(len(document.pages) for document in search_result.documents)
    chunks = sum(
        len(page.chunks)
        for document in search_result.documents
        for page in document.pages
    )
    if pages != receipt.pages_inspected:
        raise EvidenceReferenceResolutionError("U8D page coverage does not reconcile.")
    if chunks != receipt.chunks_inspected:
        raise EvidenceReferenceResolutionError("U8D chunk coverage does not reconcile.")

    if receipt.case_corpus_complete:
        if receipt.negative_finding_scope is not NegativeFindingScope.CASE_CORPUS:
            raise EvidenceReferenceResolutionError(
                "Case-corpus completeness must carry CASE_CORPUS negative-finding authority."
            )
        if not receipt.negative_finding_permitted:
            raise EvidenceReferenceResolutionError(
                "Case-corpus completeness must permit scoped negative findings."
            )


def _candidate_targets(search_result: CaseEvidenceSearchResult) -> tuple[_CandidateTarget, ...]:
    items: list[_CandidateTarget] = []
    for document in search_result.documents:
        for page in document.pages:
            for role_chunk in page.chunks:
                items.append(
                    _CandidateTarget(
                        document_id=document.document.source_document_instance_id,
                        filename=document.document.original_filename,
                        evidence_key=role_chunk.chunk.evidence_key,
                        text=role_chunk.chunk.text,
                        role=role_chunk.classification.role,
                    )
                )
    return tuple(items)


def _appendix_document_index(
    search_result: CaseEvidenceSearchResult,
) -> dict[str, tuple[str, ...]]:
    # The governed filename is the deterministic document-level appendix cue.
    # Do not index arbitrary page text here: a sentence such as "see Appendix
    # H4" inside Appendix H5 is a *reference*, not evidence that H5 itself is H4.
    pairs: list[tuple[str, str]] = []
    for document in search_result.documents:
        for label in _appendix_labels(document.document.original_filename):
            pairs.append((label, document.document.source_document_instance_id))

    result: dict[str, tuple[str, ...]] = {}
    for label in tuple(dict.fromkeys(label for label, _ in pairs)):
        result[label] = tuple(
            dict.fromkeys(document_id for item_label, document_id in pairs if item_label == label)
        )
    return result


def _extract_references(text: str) -> tuple[_ExtractedReference, ...]:
    if not isinstance(text, str):
        raise EvidenceReferenceResolutionError("Governed evidence text must be a string.")

    extracted: list[_ExtractedReference] = []
    for match in _APPENDIX_REFERENCE_RE.finditer(text):
        extracted.append(
            _ExtractedReference(
                start=match.start(),
                raw_text=match.group(0),
                kind=EvidenceReferenceKind.APPENDIX,
                appendix_label=_canonical_appendix_label(match.group("label")),
            )
        )

    occupied: list[tuple[int, int]] = []
    for pattern in _COMMUNICATION_PATTERNS:
        for match in pattern.finditer(text):
            span = match.span()
            if any(_overlaps(span, prior) for prior in occupied):
                continue
            communication_type = _canonical_communication_type(
                match.group("communication_type")
            )
            person = _clean_optional(match.groupdict().get("person"))
            date_text = _clean_optional(match.groupdict().get("date"))
            canonical_date = _canonical_date(date_text) if date_text else None
            extracted.append(
                _ExtractedReference(
                    start=match.start(),
                    raw_text=match.group(0),
                    kind=EvidenceReferenceKind.COMMUNICATION,
                    communication_type=communication_type,
                    person_text=person,
                    date_text=date_text,
                    canonical_date=canonical_date,
                )
            )
            occupied.append(span)

    extracted.sort(key=lambda item: (item.start, item.kind.value, item.raw_text.casefold()))
    return tuple(extracted)


def _build_reference(
    *,
    document_id: str,
    filename: str,
    evidence_key: str,
    page_number: int,
    chunk_ordinal: int,
    source_reference_ordinal: int,
    item: _ExtractedReference,
) -> EvidenceReference:
    if item.kind is EvidenceReferenceKind.APPENDIX:
        normalized_target = f"appendix:{item.appendix_label}"
    else:
        person = _normalise_person(item.person_text) if item.person_text else ""
        date_value = item.canonical_date or _normalise(item.date_text or "")
        normalized_target = (
            f"communication:{item.communication_type}|person:{person}|date:{date_value}"
        )

    identity_material = "\0".join(
        (
            evidence_key,
            str(source_reference_ordinal),
            item.kind.value,
            normalized_target,
            _normalise(item.raw_text),
        )
    ).encode("utf-8")
    reference_id = "sha256:" + hashlib.sha256(identity_material).hexdigest()

    return EvidenceReference(
        reference_id=reference_id,
        source_document_instance_id=document_id,
        source_filename=filename,
        source_evidence_key=evidence_key,
        source_page_number=page_number,
        source_chunk_ordinal=chunk_ordinal,
        source_reference_ordinal=source_reference_ordinal,
        kind=item.kind,
        raw_reference_text=item.raw_text,
        normalized_target=normalized_target,
        appendix_label=item.appendix_label,
        communication_type=item.communication_type,
        person_text=item.person_text,
        date_text=item.date_text,
        canonical_date=item.canonical_date,
    )


def _resolve_reference(
    *,
    reference: EvidenceReference,
    source_evidence_key: str,
    targets: tuple[_CandidateTarget, ...],
    appendix_documents: dict[str, tuple[str, ...]],
    case_corpus_complete: bool,
) -> EvidenceReferenceResolution:
    if reference.kind is EvidenceReferenceKind.APPENDIX:
        return _resolve_appendix_reference(
            reference=reference,
            source_evidence_key=source_evidence_key,
            targets=targets,
            appendix_documents=appendix_documents,
            case_corpus_complete=case_corpus_complete,
        )

    matched = tuple(
        target
        for target in targets
        if target.evidence_key != source_evidence_key
        and _communication_candidate(target)
        and _communication_target_matches(reference, target)
    )
    if len(matched) == 1:
        return EvidenceReferenceResolution(
            reference=reference,
            status=EvidenceReferenceResolutionStatus.RESOLVED,
            matched_document_ids=(matched[0].document_id,),
            matched_evidence_keys=(matched[0].evidence_key,),
            basis=(
                "One governed communication-shaped/primary evidence chunk matched "
                "all explicit communication reference cues."
            ),
        )
    if len(matched) > 1:
        return EvidenceReferenceResolution(
            reference=reference,
            status=EvidenceReferenceResolutionStatus.AMBIGUOUS,
            matched_document_ids=tuple(dict.fromkeys(item.document_id for item in matched)),
            matched_evidence_keys=tuple(item.evidence_key for item in matched),
            basis=(
                "Multiple governed communication-shaped/primary evidence chunks matched "
                "all explicit communication reference cues."
            ),
        )
    return _unlocated(
        reference,
        case_corpus_complete=case_corpus_complete,
        basis=(
            "No governed communication-shaped/primary evidence chunk matched all "
            "explicit communication reference cues."
        ),
    )


def _resolve_appendix_reference(
    *,
    reference: EvidenceReference,
    source_evidence_key: str,
    targets: tuple[_CandidateTarget, ...],
    appendix_documents: dict[str, tuple[str, ...]],
    case_corpus_complete: bool,
) -> EvidenceReferenceResolution:
    document_ids = appendix_documents.get(reference.appendix_label or "", ())
    if len(document_ids) == 1:
        document_targets = tuple(
            target
            for target in targets
            if target.document_id == document_ids[0]
            and target.evidence_key != source_evidence_key
        )
        communication_keys = tuple(
            target.evidence_key for target in document_targets if _communication_shaped(target.text)
        )
        primary_keys = tuple(
            target.evidence_key
            for target in document_targets
            if target.role in {EvidenceRole.PRIMARY_SOURCE, EvidenceRole.MIXED}
        )
        keys = communication_keys or primary_keys or tuple(
            target.evidence_key for target in document_targets
        )
        if not keys:
            return _unlocated(
                reference,
                case_corpus_complete=case_corpus_complete,
                basis=(
                    "The referenced appendix identity was present but no distinct governed "
                    "evidence item could be used as its drill-down target."
                ),
            )
        return EvidenceReferenceResolution(
            reference=reference,
            status=EvidenceReferenceResolutionStatus.RESOLVED,
            matched_document_ids=(document_ids[0],),
            matched_evidence_keys=(keys[0],),
            basis="Exact governed appendix label matched one searched document.",
        )

    if len(document_ids) > 1:
        first_key_by_document: list[tuple[str, str]] = []
        for document_id in document_ids:
            document_targets = tuple(
                target
                for target in targets
                if target.document_id == document_id
                and target.evidence_key != source_evidence_key
            )
            communication_keys = tuple(
                target.evidence_key
                for target in document_targets
                if _communication_shaped(target.text)
            )
            primary_keys = tuple(
                target.evidence_key
                for target in document_targets
                if target.role in {EvidenceRole.PRIMARY_SOURCE, EvidenceRole.MIXED}
            )
            keys = communication_keys or primary_keys or tuple(
                target.evidence_key for target in document_targets
            )
            if keys:
                first_key_by_document.append((document_id, keys[0]))
        if len(first_key_by_document) >= 2:
            return EvidenceReferenceResolution(
                reference=reference,
                status=EvidenceReferenceResolutionStatus.AMBIGUOUS,
                matched_document_ids=tuple(item[0] for item in first_key_by_document),
                matched_evidence_keys=tuple(item[1] for item in first_key_by_document),
                basis="The same governed appendix label matched multiple searched documents.",
            )
        return _unlocated(
            reference,
            case_corpus_complete=case_corpus_complete,
            basis=(
                "Multiple documents carried the referenced appendix label but no unique "
                "governed target could be established."
            ),
        )

    return _unlocated(
        reference,
        case_corpus_complete=case_corpus_complete,
        basis="No searched governed document carried the referenced appendix label.",
    )


def _unlocated(
    reference: EvidenceReference,
    *,
    case_corpus_complete: bool,
    basis: str,
) -> EvidenceReferenceResolution:
    status = (
        EvidenceReferenceResolutionStatus.POSSIBLE_REFERENCED_BUT_NOT_LOCATED
        if case_corpus_complete
        else EvidenceReferenceResolutionStatus.UNRESOLVED_REFERENCE
    )
    suffix = (
        " The complete governed case corpus was searched, so a possible "
        "referenced-but-not-located finding is permitted."
        if case_corpus_complete
        else " The searched scope was not the complete governed case corpus, so absence cannot be asserted."
    )
    return EvidenceReferenceResolution(
        reference=reference,
        status=status,
        matched_document_ids=(),
        matched_evidence_keys=(),
        basis=basis + suffix,
    )


def _communication_shaped(text: str) -> bool:
    return bool(_FROM_HEADER_RE.search(text) and _TO_HEADER_RE.search(text))


def _communication_candidate(target: _CandidateTarget) -> bool:
    if target.role in {EvidenceRole.PRIMARY_SOURCE, EvidenceRole.MIXED}:
        return True
    return _communication_shaped(target.text)


def _communication_target_matches(
    reference: EvidenceReference,
    target: _CandidateTarget,
) -> bool:
    text = target.text
    normalised = _normalise(text)

    if reference.person_text:
        person_tokens = _person_tokens(reference.person_text)
        if not person_tokens or not all(token in normalised for token in person_tokens):
            return False

    if reference.date_text:
        if reference.canonical_date:
            if reference.canonical_date not in set(_canonical_dates_in_text(text)):
                return False
        elif _normalise(reference.date_text) not in normalised:
            return False

    if not _communication_type_compatible(reference.communication_type or "", text):
        return False

    # Communication type alone is too weak to identify a specific target.
    return bool(reference.person_text or reference.date_text)


def _communication_type_compatible(communication_type: str, text: str) -> bool:
    if communication_type == "email":
        return bool(
            _EMAIL_TOKEN_RE.search(text)
            or (_FROM_HEADER_RE.search(text) and _TO_HEADER_RE.search(text))
        )
    if communication_type == "letter":
        return bool(_LETTER_TOKEN_RE.search(text))
    if communication_type == "memorandum":
        return bool(_MEMO_TOKEN_RE.search(text))
    if communication_type == "message":
        return bool(
            _MESSAGE_TOKEN_RE.search(text)
            or (_FROM_HEADER_RE.search(text) and _TO_HEADER_RE.search(text))
        )
    if communication_type == "correspondence":
        return True
    return False


def _appendix_labels(value: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            _canonical_appendix_label(match.group("label"))
            for match in _APPENDIX_LABEL_RE.finditer(value)
        )
    )


def _canonical_appendix_label(value: str) -> str:
    return re.sub(r"\s+", "", value).upper()


def _canonical_communication_type(value: str) -> str:
    normalised = re.sub(r"-", "", value.casefold())
    if normalised == "email":
        return "email"
    if normalised in {"memorandum", "memo"}:
        return "memorandum"
    return normalised


def _canonical_date(value: str) -> str | None:
    stripped = value.strip()
    iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", stripped)
    if iso:
        return _safe_iso(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))

    named = re.fullmatch(
        rf"(?i)(\d{{1,2}})\s+({_MONTH_PATTERN})\s+(\d{{4}})",
        stripped,
    )
    if named:
        month = _MONTHS[named.group(2).casefold()]
        return _safe_iso(int(named.group(3)), month, int(named.group(1)))

    # Numeric day/month references remain exact text.  U8F-C1 does not silently
    # reinterpret an ambiguous numeric date ordering.
    return None


def _canonical_dates_in_text(text: str) -> tuple[str, ...]:
    pattern = re.compile(rf"(?i)\b({_NAMED_DATE_PATTERN}|{_ISO_DATE_PATTERN})\b")
    values = tuple(
        canonical
        for match in pattern.finditer(text)
        if (canonical := _canonical_date(match.group(1))) is not None
    )
    return tuple(dict.fromkeys(values))


def _safe_iso(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _person_tokens(value: str) -> tuple[str, ...]:
    tokens = re.findall(r"[a-z0-9]+", value.casefold())
    ignored = {"mr", "mrs", "ms", "miss", "dr", "prof", "sir", "lady"}
    return tuple(token for token in tokens if token not in ignored)


def _normalise_person(value: str) -> str:
    return " ".join(_person_tokens(value))


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split()).strip(" ,.;:")
    return cleaned or None


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def _overlaps(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


__all__ = [
    "EvidenceReferenceResolutionError",
    "resolve_evidence_references",
]
