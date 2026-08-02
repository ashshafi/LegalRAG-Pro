"""Tests for provenance-aware evidence context and prompt safeguards."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from provenance_reasoning import (  # noqa: E402
    build_provenance_context,
    build_provenance_legal_prompt,
)


class ProvenanceReasoningTests(unittest.TestCase):
    def test_context_exposes_document_and_chunk_provenance_separately(self) -> None:
        results = {
            "documents": [["From: HR Director\nEmployer email text."]],
            "metadatas": [[{
                "file": "Appendix H4.pdf",
                "page": 3,
                "evidence_source_label": "Insurer evidence",
                "evidence_source_type": "insurer_record",
                "chunk_source_label": "Employer evidence",
                "chunk_source_type": "employer_record",
                "chunk_provenance_method": "chunk-leading-sender",
                "primary_source_label": "Primary/direct record",
                "retrieval_original_rank": 6,
                "retrieval_rerank_rank": 3,
            }]],
        }

        context = build_provenance_context(results)

        self.assertIn("Document classification: Insurer evidence", context)
        self.assertIn("Chunk provenance: Employer evidence", context)
        self.assertIn("Primary-source class: Primary/direct record", context)
        self.assertIn("Vector rank / reranked rank: 6 / 3", context)

    def test_prompt_prefers_chunk_provenance_over_container_for_attribution(self) -> None:
        prompt = build_provenance_legal_prompt(
            question="What did the employer know?",
            context="Evidence ID: E1",
        )
        compact = " ".join(prompt.split())

        self.assertIn("When they differ, use Chunk provenance for attribution", compact)
        self.assertIn("do not treat the container label as proof of authorship", compact)

    def test_prompt_says_reranking_is_not_proof(self) -> None:
        prompt = build_provenance_legal_prompt(
            question="What does the evidence show?",
            context="Evidence ID: E1",
        )
        compact = " ".join(prompt.split())

        self.assertIn("retrieval preferences only", compact)
        self.assertIn("must never be described as evidential weight or proof", compact)

    def test_prompt_preserves_party_provenance_for_documented_content(self) -> None:
        prompt = build_provenance_legal_prompt(
            question="What was requested?",
            context="Evidence ID: E1",
        )
        compact = " ".join(prompt.split())

        self.assertIn("Claimant evidence: In his letter", compact)
        self.assertIn("Employer evidence: The employer's letter", compact)
        self.assertIn("could obscure who authored", compact)

    def test_prompt_requires_explicit_support_for_awareness_wording(self) -> None:
        prompt = build_provenance_legal_prompt(
            question="Was CACI fully aware of the recommendations?",
            context="Evidence ID: E1",
        )
        compact = " ".join(prompt.split())

        self.assertIn('were "fully aware"', compact)
        self.assertIn("expressly records receipt, communication, acknowledgement", compact)
        self.assertIn("does not by itself establish actual awareness", compact)
        self.assertIn("label any proposed knowledge conclusion as an Inference", compact)


if __name__ == "__main__":
    unittest.main()
