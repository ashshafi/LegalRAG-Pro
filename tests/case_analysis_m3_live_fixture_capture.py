from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable

from case_analysis.m2.matrices import CaseMatrices
from case_analysis.m3.event_extraction import _canonical_evidence_lookup
from legal_analysis.legal_analysis import StructuredLegalAnalysisResult

FIXTURE_VERSION = "shafi-chronology-live-fixture/1.0"
SOURCE_CHECKPOINT = "4e906b3"


def _link_payload(link):
    return {
        "source_proposition_index": link.source_proposition_index,
        "text": link.text,
        "status": link.status.value,
        "confidence": link.confidence.value,
        "rationale": link.rationale,
        "evidence_keys": list(link.evidence_keys),
    }


def _use_payload(use):
    return {
        "issue_analysis_id": use.issue_analysis_id,
        "issue_definition_id": use.issue_definition_id,
        "issue_definition_version": use.issue_definition_version,
        "element_id": use.element_id,
        "element_ordinal": use.element_ordinal,
        "analytical_role": use.analytical_role.value,
        "mapping_relevance": use.mapping_relevance.value,
        "mapping_confidence": use.mapping_confidence.value,
        "assessment_confidence": use.assessment_confidence.value,
        "proposition_links": [_link_payload(link) for link in use.proposition_links],
    }


def build_live_fixture_payload(
    matrices: CaseMatrices,
    results: Iterable[StructuredLegalAnalysisResult],
    *,
    evidence_keys: Iterable[str] | None = None,
    fixture_version: str = FIXTURE_VERSION,
    source_checkpoint: str = SOURCE_CHECKPOINT,
) -> dict:
    """Build a deterministic static live-shaped fixture from frozen M2/M5 state."""

    frozen_results = tuple(results)
    canonical = _canonical_evidence_lookup(frozen_results)
    selected = set(evidence_keys) if evidence_keys is not None else None
    records = []
    for record in matrices.evidence_matrix:
        if selected is not None and record.evidence_key not in selected:
            continue
        evidence = canonical[record.evidence_key]
        summary = evidence.summary
        records.append(
            {
                "evidence_key": record.evidence_key,
                "document_id": record.document_id,
                "document_name": record.document_name,
                "page": record.page,
                "chunk_id": record.chunk_id,
                "citation": record.citation,
                "summary": summary,
                "summary_sha256": sha256(summary.encode("utf-8")).hexdigest(),
                "date": evidence.date.isoformat() if evidence.date is not None else None,
                "author": evidence.author,
                "parties": list(evidence.parties),
                "uses": [_use_payload(use) for use in record.uses],
            }
        )
    return {
        "fixture_version": fixture_version,
        "source_checkpoint": source_checkpoint,
        "case_id": matrices.case_id,
        "synthesis_id": matrices.synthesis_id,
        "source_analysis_ids": list(matrices.source_analysis_ids),
        "evidence": records,
    }


def dumps_live_fixture(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_live_fixture(
    path: str | Path,
    matrices: CaseMatrices,
    results: Iterable[StructuredLegalAnalysisResult],
    *,
    evidence_keys: Iterable[str] | None = None,
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = build_live_fixture_payload(matrices, tuple(results), evidence_keys=evidence_keys)
    destination.write_text(dumps_live_fixture(payload) + "\n", encoding="utf-8")
    return destination


__all__ = [
    "FIXTURE_VERSION",
    "SOURCE_CHECKPOINT",
    "build_live_fixture_payload",
    "dumps_live_fixture",
    "write_live_fixture",
]
