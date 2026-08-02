"""Milestone 3 provenance-aware evidence context and prompt wrapper."""

from __future__ import annotations

from typing import Any

from chunk_provenance import (
    CHUNK_PROVENANCE_METHOD_KEY,
    CHUNK_SOURCE_LABEL_KEY,
    CHUNK_SOURCE_TYPE_KEY,
    PRIMARY_SOURCE_LABEL_KEY,
)
from evidence_classification import EVIDENCE_SOURCE_LABEL_KEY, EVIDENCE_SOURCE_TYPE_KEY
from evidence_reasoning import build_legal_prompt
from evidence_reranking import (
    RETRIEVAL_ORIGINAL_RANK_KEY,
    RETRIEVAL_RERANK_RANK_KEY,
)


def build_provenance_context(results: dict[str, Any]) -> str:
    """Build evidence context exposing container and chunk provenance."""

    documents = _first_query_row(results.get("documents"))
    metadatas = _first_query_row(results.get("metadatas"))
    blocks: list[str] = []

    for index, document in enumerate(documents, start=1):
        metadata: dict[str, Any] = {}
        if index - 1 < len(metadatas) and isinstance(metadatas[index - 1], dict):
            metadata = metadatas[index - 1]

        blocks.append(
            "\n".join(
                (
                    f"Evidence ID: E{index}",
                    f"Document: {metadata.get('file', 'Unknown document')}",
                    f"Page: {metadata.get('page', '?')}",
                    "Document classification: "
                    f"{metadata.get(EVIDENCE_SOURCE_LABEL_KEY, 'Unclassified evidence')}",
                    "Document source type: "
                    f"{metadata.get(EVIDENCE_SOURCE_TYPE_KEY, 'other')}",
                    "Chunk provenance: "
                    f"{metadata.get(CHUNK_SOURCE_LABEL_KEY, 'Unclassified evidence')}",
                    "Chunk source type: "
                    f"{metadata.get(CHUNK_SOURCE_TYPE_KEY, 'other')}",
                    "Chunk provenance method: "
                    f"{metadata.get(CHUNK_PROVENANCE_METHOD_KEY, 'unknown')}",
                    "Primary-source class: "
                    f"{metadata.get(PRIMARY_SOURCE_LABEL_KEY, 'Unclassified source')}",
                    "Vector rank / reranked rank: "
                    f"{metadata.get(RETRIEVAL_ORIGINAL_RANK_KEY, '?')} / "
                    f"{metadata.get(RETRIEVAL_RERANK_RANK_KEY, '?')}",
                    "Excerpt:",
                    str(document or ""),
                )
            )
        )

    return "\n\n--------------------------------------------------\n\n".join(blocks)


def build_provenance_legal_prompt(*, question: str, context: str) -> str:
    """Wrap the frozen Milestone 2 prompt with chunk-provenance safeguards."""

    provenance_rules = """
MILESTONE 3 CHUNK PROVENANCE
Each excerpt may come from a mixed/composite PDF. "Document classification"
describes the container as a whole; "Chunk provenance" describes the local
excerpt. When they differ, use Chunk provenance for attribution of that excerpt
and do not treat the container label as proof of authorship.

Primary-source class and reranked position are retrieval preferences only. They
do not make a proposition true and must never be described as evidential weight
or proof in the answer.

For party-authored correspondence, preserve provenance even when describing the
documented content of the letter/email. Prefer wording such as:
- "Claimant evidence: In his letter, the claimant requested..."
- "Employer evidence: The employer's letter records/states..."
rather than a bare "Documented fact" label that could obscure who authored the
material. Use "Documented fact" principally for neutral document properties or
facts directly established without converting a party's assertion into truth.

KNOWLEDGE / AWARENESS WORDING
Do not say that CACI, its management, or named personnel were "fully aware",
"aware of", "knew", "had knowledge of", or had received specific medical,
insurer, adjustment, or return-to-work recommendations unless the cited excerpt
expressly records receipt, communication, acknowledgement, discussion, or
awareness by the relevant CACI person(s). Mere participation in a return-to-work
plan, the existence of recommendations, or an insurer's involvement does not by
itself establish actual awareness of the recommendations. In that situation,
state the documented participation/content first and label any proposed
knowledge conclusion as an Inference using cautious wording such as "may
support an argument that...".
""".strip()

    base_prompt = build_legal_prompt(question=question, context=context)
    return f"{provenance_rules}\n\n{base_prompt}"


def _first_query_row(value: Any) -> list[Any]:
    if not isinstance(value, list) or not value:
        return []
    first = value[0]
    return first if isinstance(first, list) else []
