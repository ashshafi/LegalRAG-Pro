"""Tests for evidential-status prompt construction."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from evidence_reasoning import (  # noqa: E402
    EVIDENCE_STATUS_LABELS,
    build_evidence_context,
    build_legal_prompt,
)


class EvidenceReasoningTests(unittest.TestCase):
    def test_context_exposes_source_classification_to_model(self) -> None:
        results = {
            "documents": [["The claimant states that no contact occurred."]],
            "metadatas": [[{
                "file": "Witness Statement.pdf",
                "page": 2,
                "evidence_source_type": "claimant_witness_statement",
                "evidence_source_label": "Claimant evidence",
            }]],
        }

        context = build_evidence_context(results)

        self.assertIn("Evidence ID: E1", context)
        self.assertIn("Source classification: Claimant evidence", context)
        self.assertIn("Source type: claimant_witness_statement", context)
        self.assertIn("Document: Witness Statement.pdf", context)
        self.assertIn("Page: 2", context)

    def test_prompt_requires_all_evidential_status_labels(self) -> None:
        prompt = build_legal_prompt(
            question="What does the evidence show?",
            context="Evidence ID: E1",
        )

        for label in EVIDENCE_STATUS_LABELS:
            self.assertIn(label, prompt)

    def test_prompt_prevents_witness_statement_becoming_documented_fact(self) -> None:
        prompt = build_legal_prompt(
            question="What happened?",
            context="Evidence ID: E1",
        )

        compact = " ".join(prompt.split())
        self.assertIn("A claimant witness statement is claimant evidence", compact)
        self.assertIn('"Mr Shafi states..."', compact)
        self.assertIn("Do not convert retrospective witness evidence", compact)

    def test_prompt_separates_record_access_from_actual_knowledge(self) -> None:
        prompt = build_legal_prompt(
            question="What did the employer know?",
            context="Evidence ID: E1",
        )

        compact = " ".join(prompt.split())
        self.assertIn('Do not say that an employer "knew"', compact)
        self.assertIn("records may have been accessible", compact)
        self.assertIn("do not by themselves prove actual knowledge", compact)

    def test_prompt_requires_conflicts_to_be_identified(self) -> None:
        prompt = build_legal_prompt(
            question="Is this disputed?",
            context="Evidence ID: E1",
        )

        compact = " ".join(prompt.split())
        self.assertIn("Where evidence conflicts", compact)
        self.assertIn("silently choosing one account", compact)

    def test_source_assertion_is_an_allowed_status_label(self) -> None:
        prompt = build_legal_prompt(
            question="What did CACI know?",
            context="Evidence ID: E1",
        )
        compact = " ".join(prompt.split())

        self.assertIn("Documented fact | Source assertion | Claimant evidence", compact)
        self.assertIn("This label establishes that the assertion was made", compact)


if __name__ == "__main__":
    unittest.main()
