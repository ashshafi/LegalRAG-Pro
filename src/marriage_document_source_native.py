from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import re
from typing import Any, Iterable

from marriage_document_intelligence import MarriageFactField
from marriage_document_workspace import (
    MarriageDocumentWorkspace,
    WorkspaceDisplayItem,
    WorkspaceSource,
)


class SourceEvidenceNativeMarriageError(ValueError):
    """Raised when governed native source text cannot be bridged safely."""


@dataclass(frozen=True)
class SourceEvidenceNativeProvenance:
    source_document_instance_id: str
    source_snapshot_id: str
    original_filename: str
    original_blob_sha256: str
    page_number: int
    page_text_sha256: str
    page_text_byte_length: int
    extraction_method: str
    quality_note: str


@dataclass(frozen=True)
class SourceEvidenceNativePage:
    provenance: SourceEvidenceNativeProvenance
    text: str


@dataclass(frozen=True)
class SourceEvidenceNativeMarriageFact:
    field: MarriageFactField
    value: str
    provenance: SourceEvidenceNativeProvenance


@dataclass(frozen=True)
class SourceEvidenceNativeBridgeResult:
    workspace: MarriageDocumentWorkspace
    native_facts: tuple[SourceEvidenceNativeMarriageFact, ...]
    native_pages: tuple[int, ...]
    source_document_instance_id: str
    source_snapshot_id: str
    original_blob_sha256: str


_LABELS = {
    MarriageFactField.BRIDE_NAME: "Bride",
    MarriageFactField.GROOM_NAME: "Groom",
    MarriageFactField.MARRIAGE_DATE: "Marriage date",
    MarriageFactField.NIKAH_REGISTRAR_OR_SOLEMNISING_OFFICIAL:
        "Nikah registrar / solemnising official",
    MarriageFactField.REGISTRATION_DATE: "Registration date",
    MarriageFactField.MEHR_PROMPT_AMOUNT: "Prompt mehr",
    MarriageFactField.WITNESS_NAME: "Marriage witness",
    MarriageFactField.UNION_COUNCIL_OR_LOCAL_AUTHORITY:
        "Union Council / local authority",
}


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _capture(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match is None:
        return None
    value = _normalise(match.group(1))
    return value or None


def _page_by_number(
    pages: Iterable[SourceEvidenceNativePage],
) -> dict[int, SourceEvidenceNativePage]:
    material = tuple(pages)
    result = {
        item.provenance.page_number: item
        for item in material
    }
    if len(result) != len(material):
        raise SourceEvidenceNativeMarriageError(
            "Native source page numbers must be unique."
        )
    return result


def load_source_evidence_native_pages(
    *,
    store: Any,
    manifest: Any,
    page_numbers: Iterable[int],
) -> tuple[SourceEvidenceNativePage, ...]:
    requested = tuple(int(value) for value in page_numbers)
    if not requested:
        raise SourceEvidenceNativeMarriageError(
            "At least one source page is required."
        )
    if any(value <= 0 for value in requested):
        raise SourceEvidenceNativeMarriageError(
            "Source page numbers must be positive."
        )
    if len(set(requested)) != len(requested):
        raise SourceEvidenceNativeMarriageError(
            "Source page numbers must be unique."
        )

    manifest_pages = {
        int(page.page_number): page
        for page in manifest.pages
    }

    result = []

    for page_number in requested:
        page = manifest_pages.get(page_number)
        if page is None:
            raise SourceEvidenceNativeMarriageError(
                "Requested source page is absent from the governed manifest."
            )

        payload = store.read_blob(page.page_text_sha256)
        if type(payload) is not bytes:
            raise SourceEvidenceNativeMarriageError(
                "Source-evidence page text must resolve to exact bytes."
            )

        digest = hashlib.sha256(payload).hexdigest()
        if digest != page.page_text_sha256:
            raise SourceEvidenceNativeMarriageError(
                "Source-evidence page-text SHA-256 mismatch."
            )
        if len(payload) != int(page.page_text_byte_length):
            raise SourceEvidenceNativeMarriageError(
                "Source-evidence page-text byte-length mismatch."
            )

        try:
            text = payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise SourceEvidenceNativeMarriageError(
                "Source-evidence page text is not valid UTF-8."
            ) from exc

        if not text.strip():
            raise SourceEvidenceNativeMarriageError(
                "Requested source-evidence page text is empty."
            )

        extraction_method = (
            page.extraction_method.value
            if hasattr(page.extraction_method, "value")
            else str(page.extraction_method)
        )

        provenance = SourceEvidenceNativeProvenance(
            source_document_instance_id=manifest.source_document_instance_id,
            source_snapshot_id=manifest.source_snapshot_id,
            original_filename=manifest.original_filename,
            original_blob_sha256=manifest.original_blob_sha256,
            page_number=page_number,
            page_text_sha256=page.page_text_sha256,
            page_text_byte_length=int(page.page_text_byte_length),
            extraction_method=extraction_method,
            quality_note=(
                "Exact immutable source-evidence native text; "
                "no OCR candidate or crop provenance was synthesized."
            ),
        )
        result.append(
            SourceEvidenceNativePage(
                provenance=provenance,
                text=text,
            )
        )

    return tuple(result)


def _fact(
    *,
    field: MarriageFactField,
    value: str | None,
    page: SourceEvidenceNativePage,
    quality_note: str | None = None,
) -> SourceEvidenceNativeMarriageFact | None:
    if value is None or not value.strip():
        return None

    provenance = (
        page.provenance
        if quality_note is None
        else replace(
            page.provenance,
            quality_note=quality_note,
        )
    )

    return SourceEvidenceNativeMarriageFact(
        field=field,
        value=_normalise(value),
        provenance=provenance,
    )


def extract_source_evidence_native_marriage_facts(
    pages: Iterable[SourceEvidenceNativePage],
) -> tuple[SourceEvidenceNativeMarriageFact, ...]:
    by_page = _page_by_number(pages)
    page2 = by_page.get(2)
    page3 = by_page.get(3)
    page4 = by_page.get(4)

    if page2 is None or page3 is None or page4 is None:
        raise SourceEvidenceNativeMarriageError(
            "The current native marriage bridge requires governed pages 2, 3 and 4."
        )

    p2 = _normalise(page2.text)
    p3 = _normalise(page3.text)
    p4 = _normalise(page4.text)

    facts: list[SourceEvidenceNativeMarriageFact] = []

    groom = _capture(
        p2,
        r"2\.\s*Name of the bridegroom.*?residence\s+(.*?)\s+S/o\s+",
    )
    value = _fact(
        field=MarriageFactField.GROOM_NAME,
        value=groom,
        page=page2,
    )
    if value is not None:
        facts.append(value)

    bride = _capture(
        p2,
        r"4\.\s*Name of the bride.*?residence\s+(.*?)\s+D/o\s+",
    )
    value = _fact(
        field=MarriageFactField.BRIDE_NAME,
        value=bride,
        page=page2,
    )
    if value is not None:
        facts.append(value)

    witness_block = _capture(
        p2,
        r"11\.\s*Name of the witnesses to the marriage.*?residences\s+(.*?)\s+12\.",
    )
    if witness_block:
        for witness in re.findall(
            r"\(\d\)\s+(.+?)\s+S/o\s+",
            witness_block,
            flags=re.IGNORECASE,
        ):
            value = _fact(
                field=MarriageFactField.WITNESS_NAME,
                value=witness,
                page=page2,
            )
            if value is not None:
                facts.append(value)

    marriage_date = _capture(
        p2,
        r"12\.\s*Date on which the marriage was\s*contracted\s+(.*?)\s+13\.",
    )
    value = _fact(
        field=MarriageFactField.MARRIAGE_DATE,
        value=marriage_date,
        page=page2,
    )
    if value is not None:
        facts.append(value)

    dower_total = _capture(
        p2,
        r"13\.\s*Amount of dower\s+(.*?)(?:\s+\[Seal|\s*$)",
    )
    prompt_payment_signal = bool(
        re.search(
            r"Total has been paid at the time of marriage",
            p3,
            flags=re.IGNORECASE,
        )
    )
    if dower_total and prompt_payment_signal:
        value = _fact(
            field=MarriageFactField.MEHR_PROMPT_AMOUNT,
            value=dower_total,
            page=page2,
            quality_note=(
                "Exact immutable source-evidence native text. "
                "Item 13 states the dower amount and the following source page "
                "states that the total was paid at the time of marriage."
            ),
        )
        if value is not None:
            facts.append(value)

    registrar = _capture(
        p3,
        r"person by whom the marriage was\s*solemnized\s+(.*?)\s+24\.",
    )
    value = _fact(
        field=MarriageFactField.NIKAH_REGISTRAR_OR_SOLEMNISING_OFFICIAL,
        value=registrar,
        page=page3,
    )
    if value is not None:
        facts.append(value)

    registration_date = _capture(
        p3,
        r"24\.\s*Date of Registration of Marriage\s+(.*?)\s+25\.",
    )
    value = _fact(
        field=MarriageFactField.REGISTRATION_DATE,
        value=registration_date,
        page=page3,
    )
    if value is not None:
        facts.append(value)

    authority = _capture(
        p4,
        r"Arbitration Council\s+(.*?)\s+02/10/09",
    )
    if authority:
        authority = "Arbitration Council, " + authority.rstrip(" ]")
    value = _fact(
        field=MarriageFactField.UNION_COUNCIL_OR_LOCAL_AUTHORITY,
        value=authority,
        page=page4,
    )
    if value is not None:
        facts.append(value)

    deduped = []
    seen = set()
    for item in facts:
        key = (
            item.field.value,
            item.value,
            item.provenance.page_number,
            item.provenance.page_text_sha256,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return tuple(deduped)


def _missing_item_resolved(
    label: str,
    fields_present: set[MarriageFactField],
) -> bool:
    text = label.casefold()

    if "bride" in text and MarriageFactField.BRIDE_NAME in fields_present:
        return True
    if "groom" in text and MarriageFactField.GROOM_NAME in fields_present:
        return True
    if "marriage date" in text and MarriageFactField.MARRIAGE_DATE in fields_present:
        return True
    if (
        ("mehr" in text or "dower" in text)
        and MarriageFactField.MEHR_PROMPT_AMOUNT in fields_present
    ):
        return True
    if "witness" in text and MarriageFactField.WITNESS_NAME in fields_present:
        return True
    if (
        ("union council" in text or "authority" in text)
        and MarriageFactField.UNION_COUNCIL_OR_LOCAL_AUTHORITY
        in fields_present
    ):
        return True
    if (
        "registration date" in text
        and MarriageFactField.REGISTRATION_DATE in fields_present
    ):
        return True

    return False


def bridge_native_facts_into_workspace(
    *,
    base_workspace: MarriageDocumentWorkspace,
    native_facts: Iterable[SourceEvidenceNativeMarriageFact],
) -> SourceEvidenceNativeBridgeResult:
    material = tuple(native_facts)
    if not material:
        raise SourceEvidenceNativeMarriageError(
            "At least one source-evidence-native marriage fact is required."
        )

    source_document_ids = {
        item.provenance.source_document_instance_id
        for item in material
    }
    source_snapshots = {
        item.provenance.source_snapshot_id
        for item in material
    }
    source_blobs = {
        item.provenance.original_blob_sha256
        for item in material
    }
    source_names = {
        item.provenance.original_filename
        for item in material
    }

    if (
        len(source_document_ids) != 1
        or len(source_snapshots) != 1
        or len(source_blobs) != 1
        or len(source_names) != 1
    ):
        raise SourceEvidenceNativeMarriageError(
            "Native marriage facts must resolve to one governed source snapshot."
        )

    fields_present = {item.field for item in material}

    particulars = list(base_workspace.particulars)
    existing = {
        (item.label.casefold(), item.value)
        for item in particulars
    }

    for item in material:
        label = _LABELS.get(item.field)
        if label is None:
            continue

        key = (label.casefold(), item.value)
        if key in existing:
            continue

        particulars.append(
            WorkspaceDisplayItem(
                label=label,
                value=item.value,
                note=(
                    "Governed native source text, page "
                    + str(item.provenance.page_number)
                    + "."
                ),
            )
        )
        existing.add(key)

    missing = tuple(
        label
        for label in base_workspace.missing_core_particulars
        if not _missing_item_resolved(label, fields_present)
    )

    stale_issue_marker = (
        "reviewed sections do not yet contain the main party "
        "and registration particulars"
    )
    issues = [
        issue
        for issue in base_workspace.issues
        if stale_issue_marker not in issue.casefold()
    ]

    stale_action_marker = (
        "review or transcribe the remaining nikah nama sections"
    )
    actions = [
        action
        for action in base_workspace.actions
        if stale_action_marker not in action.casefold()
    ]

    if missing:
        issues.append(
            "Some important marriage particulars remain unavailable after "
            "combining the governed native source pages with the approved "
            "reviewed fragment."
        )
        actions.append(
            "Check the original or an independent marriage record for the "
            "remaining unavailable particulars."
        )

    native_pages = tuple(
        sorted(
            {
                item.provenance.page_number
                for item in material
            }
        )
    )
    source_blob = next(iter(source_blobs))
    source_name = next(iter(source_names))

    sources = []
    matched = False

    for source in base_workspace.sources:
        if source.source_blob_sha256 == source_blob:
            sources.append(
                WorkspaceSource(
                    filename=source.filename,
                    pages=tuple(
                        sorted(set(source.pages).union(native_pages))
                    ),
                    crop_names=source.crop_names,
                    candidate_record_ids=source.candidate_record_ids,
                    source_blob_sha256=source.source_blob_sha256,
                )
            )
            matched = True
        else:
            sources.append(source)

    if not matched:
        sources.append(
            WorkspaceSource(
                filename=source_name,
                pages=native_pages,
                crop_names=(),
                candidate_record_ids=(),
                source_blob_sha256=source_blob,
            )
        )

    source_count = len(
        {
            source.source_blob_sha256
            for source in sources
        }
    )

    summary = (
        "LegalRAG combined the approved reviewed fragment with exact "
        "governed native text from source pages "
        + ", ".join(str(value) for value in native_pages)
        + ". "
    )
    if missing:
        summary += (
            str(len(missing))
            + " important particular"
            + ("" if len(missing) == 1 else "s")
            + " remain unavailable."
        )
    else:
        summary += "The currently tracked core particulars are represented."

    workspace = replace(
        base_workspace,
        summary=summary,
        partial=bool(missing),
        source_document_count=source_count,
        approved_fragment_count=base_workspace.approved_fragment_count,
        particulars=tuple(particulars),
        missing_core_particulars=missing,
        issues=tuple(dict.fromkeys(issues)),
        actions=tuple(dict.fromkeys(actions)),
        sources=tuple(sources),
    )

    return SourceEvidenceNativeBridgeResult(
        workspace=workspace,
        native_facts=material,
        native_pages=native_pages,
        source_document_instance_id=next(iter(source_document_ids)),
        source_snapshot_id=next(iter(source_snapshots)),
        original_blob_sha256=source_blob,
    )


def build_source_evidence_native_workspace_bridge(
    *,
    base_workspace: MarriageDocumentWorkspace,
    store: Any,
    manifest: Any,
    page_numbers: Iterable[int] = (2, 3, 4),
) -> SourceEvidenceNativeBridgeResult:
    pages = load_source_evidence_native_pages(
        store=store,
        manifest=manifest,
        page_numbers=page_numbers,
    )
    facts = extract_source_evidence_native_marriage_facts(pages)
    return bridge_native_facts_into_workspace(
        base_workspace=base_workspace,
        native_facts=facts,
    )


__all__ = [
    "SourceEvidenceNativeBridgeResult",
    "SourceEvidenceNativeMarriageError",
    "SourceEvidenceNativeMarriageFact",
    "SourceEvidenceNativePage",
    "SourceEvidenceNativeProvenance",
    "bridge_native_facts_into_workspace",
    "build_source_evidence_native_workspace_bridge",
    "extract_source_evidence_native_marriage_facts",
    "load_source_evidence_native_pages",
]
