"""Tests for always-visible evidence provenance headings."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from evidence_display import build_evidence_heading  # noqa: E402


class EvidenceDisplayTests(unittest.TestCase):
    def test_heading_shows_chunk_provenance_when_container_matches(self) -> None:
        heading = build_evidence_heading({
            "file": "Appendix H6.pdf",
            "page": 2,
            "chunk_source_label": "Employer evidence",
            "source_label": "Employer evidence",
        })

        self.assertEqual(
            heading,
            "📄 Appendix H6.pdf — Page 2 | Employer evidence",
        )

    def test_heading_shows_container_when_provenance_differs(self) -> None:
        heading = build_evidence_heading({
            "file": "Appendix H5.pdf",
            "page": 2,
            "chunk_source_label": "Employer evidence",
            "source_label": "Insurer evidence",
        })

        self.assertEqual(
            heading,
            "📄 Appendix H5.pdf — Page 2 | Employer evidence | container: Insurer evidence",
        )

    def test_heading_uses_safe_fallbacks(self) -> None:
        heading = build_evidence_heading({"file": "Unknown.pdf", "page": 4})

        self.assertEqual(
            heading,
            "📄 Unknown.pdf — Page 4 | Unclassified evidence",
        )


if __name__ == "__main__":
    unittest.main()
