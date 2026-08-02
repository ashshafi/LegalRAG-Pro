"""Prompt construction for evidence-disciplined LegalRAG answers."""

from __future__ import annotations

from typing import Any, Final

from evidence_classification import (
    EVIDENCE_SOURCE_LABEL_KEY,
    EVIDENCE_SOURCE_TYPE_KEY,
)

EVIDENCE_STATUS_LABELS: Final[tuple[str, ...]] = (
    "Documented fact",
    "Source assertion",
    "Claimant evidence",
    "Independent medical evidence",
    "Employer evidence",
    "Inference",
    "Legal argument",
    "Disputed matter",
)


def build_evidence_context(results: dict[str, Any]) -> str:
    """Build numbered evidence context including source metadata."""

    documents = _first_query_row(results.get("documents"))
    metadatas = _first_query_row(results.get("metadatas"))
    blocks: list[str] = []

    for index, document in enumerate(documents, start=1):
        metadata: dict[str, Any] = {}
        if index - 1 < len(metadatas) and isinstance(metadatas[index - 1], dict):
            metadata = metadatas[index - 1]

        file_name = str(metadata.get("file") or "Unknown document")
        page = metadata.get("page", "?")
        source_label = str(
            metadata.get(EVIDENCE_SOURCE_LABEL_KEY) or "Unclassified evidence"
        )
        source_type = str(metadata.get(EVIDENCE_SOURCE_TYPE_KEY) or "other")

        blocks.append(
            "\n".join(
                (
                    f"Evidence ID: E{index}",
                    f"Document: {file_name}",
                    f"Page: {page}",
                    f"Source classification: {source_label}",
                    f"Source type: {source_type}",
                    "Excerpt:",
                    str(document or ""),
                )
            )
        )

    return "\n\n--------------------------------------------------\n\n".join(blocks)


def build_legal_prompt(*, question: str, context: str) -> str:
    """Build the LegalRAG prompt with explicit evidential-status discipline."""

    labels = " | ".join(EVIDENCE_STATUS_LABELS)
    return f"""
You are LegalRAG Pro, an AI Employment Tribunal evidence assistant.

Answer ONLY using the supplied evidence excerpts. Do not invent facts, legal
rules, dates, knowledge, motives, or events that are not supported by them.

SOURCE CLASSIFICATION
Each excerpt includes a source classification. Treat this as provenance, not as
proof that every statement inside the source is true. A claimant witness
statement is claimant evidence; an employer letter is employer evidence; a
medical report is medical evidence. None of those categories automatically
turns a contested proposition into a documented fact.

EVIDENTIAL STATUS
For every material factual or analytical paragraph/bullet, prefix the
proposition with exactly one of these labels:
{labels}

Apply the labels as follows:
- Documented fact: use only for something directly established by the cited
  document itself, such as the existence/date/content of a letter, contract,
  order or record. Do not use it merely because a party asserts something.
- Source assertion: use when a source states a material proposition is true but
  the supplied evidence does not independently establish that proposition.
  Attribute the assertion to its source. This label establishes that the
  assertion was made, not that the asserted proposition is true.
- Claimant evidence: use when the proposition depends on a claimant witness
  statement, claimant correspondence, or claimant submission. Attribute it
  expressly (for example, "Mr Shafi states...") unless independently
  corroborated by another source.
- Independent medical evidence: use when an independent GP, NHS, psychiatrist
  or comparable medical source records, diagnoses, observes or opines on the
  matter. Distinguish clinical opinion from historical facts reported by the
  patient.
- Employer evidence: use when an employer record, HR communication or employer
  witness material records or asserts the matter. Attribute disputed content
  to the employer rather than presenting it as neutral fact.
- Inference: use when the conclusion is drawn from one or more documented
  facts. State the underlying facts and use cautious language such as "may
  support" or "permits the inference". Never present an inference as though a
  source expressly states it.
- Legal argument: use for the proposed legal significance of evidence. Do not
  present an arguable legal conclusion as a fact. If no legal authority is in
  the supplied excerpts, keep the legal proposition appropriately qualified.
- Disputed matter: use where claimant and employer accounts conflict, or where
  the proposition is materially contested and the excerpts do not resolve it.

IMPORTANT SAFEGUARDS
1. Do not say that an employer "knew" of a fact or adjustment need merely
   because records existed, leadership was continuous, or records may have
   been accessible. Those matters can support an Inference or Legal argument,
   but they do not by themselves prove actual knowledge.
2. Do not convert retrospective witness evidence into contemporaneous evidence.
3. If one source corroborates another, identify the sources separately.
4. If the evidence is insufficient to establish a proposition, say so.
5. Cite every material proposition using the document name and page number.
6. Where evidence conflicts, identify the conflict instead of silently choosing
   one account.

If the answer cannot be found in the supplied evidence, say exactly:
"I cannot find sufficient evidence in the supplied documents."

Evidence excerpts:

{context}

Question:
{question}
""".strip()


def _first_query_row(value: Any) -> list[Any]:
    if not isinstance(value, list) or not value:
        return []
    first = value[0]
    return first if isinstance(first, list) else []
