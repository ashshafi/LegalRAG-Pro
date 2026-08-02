"""Tests for Milestone 4 semantic context and assertion-safety prompt."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from semantic_reasoning import (  # noqa: E402
    build_semantic_context,
    build_semantic_legal_prompt,
)


class SemanticReasoningTests(unittest.TestCase):
    def test_context_exposes_basis_confidence_and_knowledge_signal(self) -> None:
        results = {
            "documents": [["CACI was fully aware of the recommendation."]],
            "metadatas": [[{
                "file": "Appendix H5.pdf",
                "page": 2,
                "evidence_source_label": "Insurer evidence",
                "chunk_source_label": "Mixed / composite evidence",
                "semantic_source_label": "Mixed / composite evidence",
                "provenance_basis": "mixed",
                "provenance_confidence": "medium",
                "provenance_warning": "No single author is reliably attributable.",
                "knowledge_signal_label": "Knowledge/awareness assertion present",
                "primary_source_label": "Mixed direct correspondence",
                "retrieval_original_rank": 5,
                "retrieval_rerank_rank": 2,
            }]],
        }

        context = build_semantic_context(results)

        self.assertIn("Semantic provenance: Mixed / composite evidence", context)
        self.assertIn("Provenance basis: mixed", context)
        self.assertIn("Provenance confidence: medium", context)
        self.assertIn("Knowledge/awareness assertion present", context)
        self.assertIn("Provenance caution:", context)

    def test_prompt_defines_source_identity_assertion_and_truth_as_distinct(self) -> None:
        prompt = build_semantic_legal_prompt(
            question="What did CACI know?",
            context="Evidence ID: E1",
        )
        compact = " ".join(prompt.split())

        self.assertIn(
            "Source identity, source assertion, and substantive truth are three different things",
            compact,
        )
        self.assertIn('"Source assertion" is a required evidential-status label', compact)
        self.assertIn("It establishes that the assertion was made, not the truth", compact)

    def test_prompt_forbids_source_says_knew_becoming_established_knowledge(self) -> None:
        prompt = build_semantic_legal_prompt(
            question="What did CACI know?",
            context="Evidence ID: E1",
        )
        compact = " ".join(prompt.split())

        self.assertIn('Do NOT silently rewrite either as "CACI knew"', compact)
        self.assertIn("specially guarded propositions", compact)
        self.assertIn("only a cue to inspect the excerpt; it is not itself proof", compact)

    def test_prompt_protects_low_confidence_provenance(self) -> None:
        prompt = build_semantic_legal_prompt(
            question="Who authored this?",
            context="Evidence ID: E1",
        )
        compact = " ".join(prompt.split())

        self.assertIn("If semantic provenance is Unclassified evidence", compact)
        self.assertIn("do not guess the author from subject matter", compact)


if __name__ == "__main__":
    unittest.main()
