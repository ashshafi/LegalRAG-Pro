"""Index PDF documents into the LegalRAG Pro Chroma collection."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI
from pypdf import PdfReader

from chunk_provenance import add_chunk_provenance_to_metadata
from evidence_classification import EvidenceSourceType, classify_evidence_source

from case_management.document_context import (
    build_chunk_metadata,
    build_document_id,
    normalise_case_id,
)
from ocr import extract_text

LOGGER = logging.getLogger(__name__)

load_dotenv()

client = OpenAI()
chroma_client = chromadb.PersistentClient(path="db")
collection = chroma_client.get_or_create_collection(name="legal_documents")

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
)


def index_pdf(
    pdf_path: str | Path,
    case_id: str | None = None,
    evidence_source_type: EvidenceSourceType | str | None = None,
) -> int:
    """Index one PDF and optionally associate every chunk with a case.

    Args:
        pdf_path: PDF file to index.
        case_id: Stable internal case ID. When omitted, the historic global
            indexing behaviour and document-ID format are preserved.
        evidence_source_type: Optional explicit source classification for this
            PDF. When omitted, each chunk is classified conservatively.

    Returns:
        Number of chunks successfully added to Chroma.
    """

    path = Path(pdf_path)
    cleaned_case_id = normalise_case_id(case_id)

    LOGGER.info(
        "Indexing %s%s",
        path.name,
        f" for case {cleaned_case_id}" if cleaned_case_id else "",
    )

    reader = PdfReader(path)
    document_hint = _build_document_hint(reader)
    total_chunks = 0
    ocr_text: str | None = None
    ocr_used = False

    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text()

        if not text or not text.strip():
            LOGGER.info("Page %s has no text; using OCR.", page_number)

            if not ocr_used:
                try:
                    ocr_text = extract_text(path)
                    ocr_used = True
                    LOGGER.info("OCR completed successfully for %s.", path.name)
                except Exception:
                    LOGGER.exception("OCR failed for %s.", path.name)
                    continue

            text = ocr_text
            if not text or not text.strip():
                LOGGER.warning("OCR found no text for page %s.", page_number)
                continue

        chunks = splitter.split_text(text)

        for chunk_number, chunk in enumerate(chunks):
            try:
                response = client.embeddings.create(
                    model="text-embedding-3-small",
                    input=chunk,
                )
                embedding = response.data[0].embedding

                document_id = build_document_id(
                    pdf_path=path,
                    page_number=page_number,
                    chunk_number=chunk_number,
                    case_id=cleaned_case_id,
                )
                classification = classify_evidence_source(
                    file_name=path.name,
                    text=chunk,
                    document_hint=document_hint,
                    explicit_source_type=evidence_source_type,
                )
                metadata = build_chunk_metadata(
                    pdf_path=path,
                    page_number=page_number,
                    chunk_number=chunk_number,
                    case_id=cleaned_case_id,
                    evidence_source_type=classification.source_type.value,
                    evidence_source_label=classification.label,
                    evidence_classification_method=classification.method,
                )
                metadata = add_chunk_provenance_to_metadata(
                    metadata,
                    text=chunk,
                )

                collection.add(
                    ids=[document_id],
                    embeddings=[embedding],
                    documents=[chunk],
                    metadatas=[metadata],
                )
                total_chunks += 1
            except Exception:
                LOGGER.exception(
                    "Error adding chunk %s from %s page %s.",
                    chunk_number,
                    path.name,
                    page_number,
                )

    LOGGER.info("Finished indexing %s (%s chunks).", path.name, total_chunks)
    return total_chunks


def _build_document_hint(reader: PdfReader, max_chars: int = 6000) -> str:
    """Return limited opening text used to resolve document-level provenance.

    The classifier currently uses this hint only for conservative party
    attribution of witness statements. It is not supplied to the LLM and does
    not affect embeddings.
    """

    parts: list[str] = []
    for page in reader.pages[:3]:
        try:
            text = page.extract_text() or ""
        except Exception:
            LOGGER.debug(
                "Unable to extract evidence-classification hint.",
                exc_info=True,
            )
            continue
        if text.strip():
            parts.append(text.strip())
        if sum(len(part) for part in parts) >= max_chars:
            break

    return "\n".join(parts)[:max_chars]


def index_all_documents(case_id: str | None = None) -> int:
    """Index every PDF in ``docs/`` and return the total chunks added."""

    docs_folder = Path("docs")
    pdf_files = sorted(docs_folder.glob("*.pdf"))

    if not pdf_files:
        LOGGER.warning("No PDF files found in %s.", docs_folder.resolve())
        return 0

    total_chunks = 0
    for pdf_file in pdf_files:
        total_chunks += index_pdf(pdf_file, case_id=case_id)

    LOGGER.info("Finished indexing all documents (%s chunks).", total_chunks)
    return total_chunks


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Index LegalRAG Pro PDFs into Chroma."
    )
    parser.add_argument(
        "--case-id",
        dest="case_id",
        help=(
            "Stable internal case UUID to store in Chroma metadata. "
            "Omit to preserve legacy/global indexing behaviour."
        ),
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        help="Index one PDF instead of every PDF in docs/.",
    )
    parser.add_argument(
        "--source-type",
        choices=[source_type.value for source_type in EvidenceSourceType],
        help=(
            "Optional explicit evidence source type for --pdf. "
            "Omit to use conservative automatic classification."
        ),
    )
    args = parser.parse_args()
    if args.source_type and args.pdf is None:
        parser.error("--source-type can only be used together with --pdf")
    return args


def main() -> None:
    """Run the command-line indexing entry point."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    args = _parse_args()

    if args.pdf is not None:
        index_pdf(
            args.pdf,
            case_id=args.case_id,
            evidence_source_type=args.source_type,
        )
    else:
        index_all_documents(case_id=args.case_id)


if __name__ == "__main__":
    main()
