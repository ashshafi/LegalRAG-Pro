"""M3-local evidence-to-element relationship models.

These types deliberately do not modify the frozen Sprint 2.3 M1 durable schema.
They preserve why an EvidenceReference was attached to an element and which
mapper version made that relationship.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .enums import Confidence
from .models import EvidenceReference, IssueAnalysis
from .search_profiles import ELEMENT_MAPPER_VERSION


class EvidenceRelevance(StrEnum):
    """Describe evidence relevance to one controlled legal element."""

    RELEVANT = "relevant"
    POTENTIALLY_RELEVANT = "potentially_relevant"
    NOT_RELEVANT = "not_relevant"


@dataclass(frozen=True, slots=True)
class EvidenceMapping:
    """Trace one evidence item to one exact issue element."""

    evidence: EvidenceReference
    issue_definition_id: str
    issue_definition_version: str
    element_id: str
    relevance: EvidenceRelevance
    mapping_confidence: Confidence
    mapping_rationale: str
    mapper_version: str = ELEMENT_MAPPER_VERSION

    def __post_init__(self) -> None:
        for field_name in (
            "issue_definition_id",
            "issue_definition_version",
            "element_id",
            "mapping_rationale",
            "mapper_version",
        ):
            value = str(getattr(self, field_name)).strip()
            if not value:
                raise ValueError(f"{field_name} must not be empty.")
            object.__setattr__(self, field_name, value)
        if not isinstance(self.relevance, EvidenceRelevance):
            raise ValueError("relevance must be an EvidenceRelevance.")
        if not isinstance(self.mapping_confidence, Confidence):
            raise ValueError("mapping_confidence must be a Confidence.")

    @property
    def evidence_key(self) -> str:
        """Return a stable identity key for cross-element reuse."""

        if self.evidence.chunk_id:
            return self.evidence.chunk_id
        page = self.evidence.page or 0
        return f"{self.evidence.document_id or self.evidence.document_name}|{page}|{self.evidence.citation}"


@dataclass(frozen=True, slots=True)
class ElementMappingResult:
    """Trace all candidate mapping decisions for one element."""

    element_id: str
    search_query: str
    mappings: tuple[EvidenceMapping, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "element_id", self.element_id.strip())
        object.__setattr__(self, "search_query", self.search_query.strip())
        object.__setattr__(self, "mappings", tuple(self.mappings))
        if not self.element_id or not self.search_query:
            raise ValueError("element_id and search_query must not be empty.")
        if any(mapping.element_id != self.element_id for mapping in self.mappings):
            raise ValueError("All mappings must belong to ElementMappingResult.element_id.")

    @property
    def relevant(self) -> tuple[EvidenceMapping, ...]:
        return tuple(
            item for item in self.mappings if item.relevance is EvidenceRelevance.RELEVANT
        )

    @property
    def potentially_relevant(self) -> tuple[EvidenceMapping, ...]:
        return tuple(
            item
            for item in self.mappings
            if item.relevance is EvidenceRelevance.POTENTIALLY_RELEVANT
        )


@dataclass(frozen=True, slots=True)
class MappedIssueAnalysis:
    """M3 result wrapper around the unchanged M1 IssueAnalysis schema."""

    analysis: IssueAnalysis
    element_results: tuple[ElementMappingResult, ...]
    mapper_version: str = ELEMENT_MAPPER_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "element_results", tuple(self.element_results))
        object.__setattr__(self, "mapper_version", self.mapper_version.strip())
        if not self.mapper_version:
            raise ValueError("mapper_version must not be empty.")
        expected = tuple(element.element_id for element in self.analysis.elements)
        actual = tuple(item.element_id for item in self.element_results)
        if actual != expected:
            raise ValueError("Element mapping results must match IssueAnalysis element order exactly.")


__all__ = [
    "ElementMappingResult",
    "EvidenceMapping",
    "EvidenceRelevance",
    "MappedIssueAnalysis",
]


def format_mapping_diagnostics(result: MappedIssueAnalysis) -> str:
    """Return a deterministic human-readable M3 acceptance representation."""

    lines = [
        f"Issue: {result.analysis.issue_definition_id}/{result.analysis.issue_definition_version} — {result.analysis.issue_name}",
        f"Mapper: {result.mapper_version}",
        f"Case: {result.analysis.case_id}",
        "",
    ]
    element_by_id = {element.element_id: element for element in result.analysis.elements}
    for element_result in result.element_results:
        element = element_by_id[element_result.element_id]
        lines.append(f"Element: {element.element_id} — {element.element_name}")
        relevant = element_result.relevant
        potential = element_result.potentially_relevant
        if not relevant:
            lines.append("  Relevant mapped evidence: none")
        for mapping in relevant:
            evidence = mapping.evidence
            page = f", p.{evidence.page}" if evidence.page is not None else ""
            lines.extend(
                (
                    f"  [{evidence.evidence_status.value}] {evidence.document_name}{page}",
                    f"  Mapping confidence: {mapping.mapping_confidence.value.upper()}",
                    f"  Rationale: {mapping.mapping_rationale}",
                )
            )
        if potential:
            lines.append(f"  Potentially relevant candidates: {len(potential)}")
        lines.append("")
    return "\n".join(lines).rstrip()


__all__.append("format_mapping_diagnostics")
