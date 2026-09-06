from dataclasses import dataclass
from types import SimpleNamespace
from pathlib import Path

from explicit_document_location import resolve_explicit_document_location
from new_ai_finding import wrap_source_comparison_new_ai_finding_prompt


@dataclass(frozen=True)
class Entry:
    source_document_instance_id: str
    original_filename: str


@dataclass(frozen=True)
class Chunk:
    page_number: int
    chunk_ordinal: int
    chunk_id: str
    evidence_key: str
    text: str


@dataclass(frozen=True)
class Page:
    page_number: int
    text: str
    chunks: tuple


@dataclass(frozen=True)
class Inspection:
    case_id: str
    source_document_instance_id: str
    source_snapshot_id: str
    original_filename: str
    pages: tuple


def catalog(_case_id):
    return (Entry("et3", "ET3.220441.2025. Grounds of Resistance - FINAL.pdf"),)


def inspection_complete(*, case_id, source_document_instance_id):
    return Inspection(
        case_id, source_document_instance_id, "snap",
        "ET3.220441.2025. Grounds of Resistance - FINAL.pdf",
        (
            Page(4, "27. Denial\n28. Response", (
                Chunk(4, 0, "c27", "e27", "27. Denial"),
                Chunk(4, 1, "c28", "e28", "28. Response"),
            )),
            Page(5, "29. Further\n30. Denied", (
                Chunk(5, 0, "c29", "e29", "29. Further"),
                Chunk(5, 1, "c30", "e30", "30. Denied"),
            )),
        ),
    )


def inspection_partial(*, case_id, source_document_instance_id):
    return Inspection(
        case_id, source_document_instance_id, "snap",
        "ET3.220441.2025. Grounds of Resistance - FINAL.pdf",
        (
            Page(4, "27. Denial\n28. Response", (
                Chunk(4, 0, "c27", "e27", "27. Denial"),
                Chunk(4, 1, "c28", "e28", "28. Response"),
            )),
            Page(5, "45. Later\n46. Later", (
                Chunk(5, 0, "c45", "e45", "45. Later"),
            )),
        ),
    )


def test_complete_requested_paragraph_range_has_exact_page_map():
    result = resolve_explicit_document_location(
        question="Compare paragraphs 27-30 of the Grounds of Resistance.",
        case_id="case",
        catalog_service=catalog,
        inspection_service=inspection_complete,
    )
    assert result is not None
    assert result.verified_location_pages == ((27, 4), (28, 4), (29, 5), (30, 5))
    assert result.missing_locations == ()
    assert result.ambiguous_locations == ()
    assert result.location_verification_complete is True


def test_partial_requested_range_is_retained_but_not_marked_complete():
    result = resolve_explicit_document_location(
        question="Compare paragraphs 27-30 of the Grounds of Resistance.",
        case_id="case",
        catalog_service=catalog,
        inspection_service=inspection_partial,
    )
    assert result is not None
    assert result.verified_location_pages == ((27, 4), (28, 4))
    assert result.missing_locations == (29, 30)
    assert result.location_verification_complete is False


def test_wrapper_exposes_verified_and_unverified_coordinates():
    explicit = SimpleNamespace(
        matched_filename="Grounds.pdf",
        location_kind="paragraph",
        requested_locations=(27, 28, 29, 30),
        verified_location_pages=((27, 4), (28, 4)),
        missing_locations=(29, 30),
        ambiguous_locations=(),
    )
    prompt = wrap_source_comparison_new_ai_finding_prompt(
        base_prompt="LEGALRAG GOVERNED LARGE-MATTER FINAL SYNTHESIS",
        question="Compare paragraphs 27-30.",
        explicit_location=explicit,
    )
    assert "paragraph 27: VERIFIED_PAGE=4" in prompt
    assert "paragraph 28: VERIFIED_PAGE=4" in prompt
    assert "paragraph 29: NOT_VERIFIED" in prompt
    assert "paragraph 30: NOT_VERIFIED" in prompt
    assert "verification_complete: no" in prompt
    assert "sole authority for assigning" in prompt
    assert "do not invent or" in prompt


def test_legalrag_binds_verification_into_direct_and_bounded_wrapper():
    source = Path("src/legalrag.py").read_text(encoding="utf-8-sig")
    assert "new_ai_prompt_wrapper = lambda" in source
    assert "explicit_location=governed_evidence.explicit_location" in source
    assert "base_prompt = new_ai_prompt_wrapper(" in source
    assert "prompt_wrapper=(" in source
    assert "new_ai_prompt_wrapper" in source


def test_governed_evidence_retains_explicit_location_record():
    source = Path("src/evidence_answer/governed_retrieval.py").read_text(encoding="utf-8-sig")
    assert "explicit_location: ExplicitDocumentLocationResult | None = None" in source
    assert "explicit_location=explicit_location" in source
