"""Fast provider-facing projection for ordinary governed legal questions.

This module does not retrieve evidence, mutate evidence, or weaken U8 admission.
The caller supplies only semantic rows that U8 has already reconciled against
their completely expanded governed source documents.
"""

from __future__ import annotations

from typing import Any

from semantic_reasoning import build_semantic_context


def build_interactive_governed_answer_prompt(
    *,
    question: str,
    enriched_results: dict[str, Any],
) -> str:
    """Build a bounded solicitor-facing prompt from governed semantic rows."""

    context = build_semantic_context(enriched_results)
    return f"""
U8 GOVERNED INTERACTIVE LEGAL ANSWER

This is a bounded semantic answer projection for an ordinary interactive
question. It is not an exhaustive whole-corpus report.

Every evidence row supplied below has already passed the governed U8 retrieval
boundary and has been reconciled to its governed source document. The provider
is intentionally shown only the semantically retrieved governed chunks, not
every chunk from every discovered document.

Rules:
1. Answer the user's legal/evidential question from the supplied evidence only.
2. Prefer primary and contemporaneous source evidence over later summaries.
3. Identify supporting, adverse, contradictory, and qualifying evidence where
   material.
4. Preserve the supplied file/page/evidence provenance in the answer.
5. Do not say or imply that evidence does not exist merely because it is absent
   from this bounded semantic projection.
6. Do not make a whole-document or whole-corpus negative finding from this
   interactive projection. If the question genuinely requires proof of absence
   or an exhaustive corpus conclusion, state that an explicit exhaustive search
   is required.
7. Use clear solicitor-facing language; do not expose internal governance jargon
   unless it is needed to explain a limitation.

QUESTION:
{question}

GOVERNED SEMANTIC EVIDENCE:
{context}
""".strip()


__all__ = ["build_interactive_governed_answer_prompt"]
