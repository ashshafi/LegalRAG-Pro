"""Evidence-grounded answer generation for LegalRAG Pro."""

from __future__ import annotations

from collections.abc import Sequence

from config import openai_client
from evidence_classification import (
    EVIDENCE_CLASSIFICATION_METHOD_KEY,
    EVIDENCE_SOURCE_LABEL_KEY,
    EVIDENCE_SOURCE_TYPE_KEY,
)
from evidence_reasoning import build_evidence_context, build_legal_prompt
from models import CHAT_MODEL
from retriever import retrieve


def ask(
    question: str,
    selected_documents: Sequence[str] | None = None,
    *,
    case_id: str | None = None,
) -> dict:
    """Ask a legal question using evidence from the requested case."""

    results = retrieve(
        question,
        selected_documents,
        n_results=10,
        case_id=case_id,
    )

    context = build_evidence_context(results)
    prompt = build_legal_prompt(question=question, context=context)

    response = openai_client.responses.create(
        model=CHAT_MODEL,
        input=prompt,
    )

    sources = []

    for i in range(len(results["documents"][0])):
        metadata = results["metadatas"][0][i]

        sources.append(
            {
                "file": metadata["file"],
                "page": metadata["page"],
                "text": results["documents"][0][i],
                "source_type": metadata.get(
                    EVIDENCE_SOURCE_TYPE_KEY,
                    "other",
                ),
                "source_label": metadata.get(
                    EVIDENCE_SOURCE_LABEL_KEY,
                    "Unclassified evidence",
                ),
                "classification_method": metadata.get(
                    EVIDENCE_CLASSIFICATION_METHOD_KEY,
                    "unknown",
                ),
            }
        )

    return {
        "answer": response.output_text,
        "sources": sources,
        "search_results": results,
    }
