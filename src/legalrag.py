"""Evidence-grounded answer generation for LegalRAG Pro."""

from __future__ import annotations

from collections.abc import Sequence

from config import openai_client
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

    context = ""

    for i in range(len(results["documents"][0])):
        metadata = results["metadatas"][0][i]

        context += f"""
Document: {metadata['file']}
Page: {metadata['page']}

{results["documents"][0][i]}

--------------------------------------------------

"""

    prompt = f"""
You are LegalRAG Pro, an AI Employment Tribunal assistant.

Answer ONLY using the supplied documents.

If the answer cannot be found in the supplied documents,
say:

"I cannot find sufficient evidence in the supplied documents."

Always cite the document name and page number where possible.

Documents:

{context}

Question:

{question}
"""

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
            }
        )

    return {
        "answer": response.output_text,
        "sources": sources,
        "search_results": results,
    }
