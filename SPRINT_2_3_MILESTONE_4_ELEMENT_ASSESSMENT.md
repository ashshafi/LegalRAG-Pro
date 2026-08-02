# Sprint 2.3 — Milestone 4
## Element Assessment & Evidential Gap Analysis
### Specification v1.0 — Implementation checkpoint

## Objective

Consume immutable Sprint 2.3 Milestone 3 evidence mappings and produce deterministic, traceable evidential assessments for each controlled legal element.

Milestone 4 classifies mapped evidence as supporting, adverse, corroborative, neutral/contextual, or conflicting; preserves Source assertion semantics; identifies disputed factual propositions; records what the current evidence can establish at source-record level; identifies unresolved matters and specific material evidential gaps; and assigns evidential assessment confidence.

Milestone 4 does **not** retrieve evidence, alter M3 mappings, determine statutory element satisfaction, or produce final legal merits analysis.

## Frozen dependencies

M4 consumes but does not modify:

- Sprint 2.2 retrieval, case isolation, reranking, provenance and evidence semantics;
- Sprint 2.3 M1 durable analysis models and issue definitions;
- Sprint 2.3 M2 issue selection;
- Sprint 2.3 M3 search profiles, `EvidenceMapping`, mapping confidence/rationale and mapper result.

## M4-local models

- `PropositionAssessmentStatus`
  - `ESTABLISHED_BY_CURRENT_EVIDENCE`
  - `SUPPORTED_BUT_NOT_ESTABLISHED`
  - `DISPUTED`
  - `UNRESOLVED`
  - `NOT_SUPPORTED_BY_CURRENT_EVIDENCE`
- `EvidenceAssessment`
- `AssessedProposition`
- `ElementEvidenceAssessment`
- `EvidenceAssessmentResult`
- assessor version `element-assessor/1.0`

`PropositionAssessmentStatus` is intentionally separate from the frozen M1 `EvidenceStatus`.

## Assessment rules

1. Only M3 `RELEVANT` mappings enter M4 assessment automatically.
2. M3 evidence/mappings are never mutated.
3. M4 creates role-adjusted copies of `EvidenceReference` for the assessed M1 `ElementAnalysis` buckets.
4. Source assertions may support a proposition but cannot establish the asserted proposition by themselves.
5. Direct high-confidence records may establish only their own documented/source-level content; M4 does not turn that into legal element satisfaction.
6. Respondent/employer material containing an explicit denial may be adverse.
7. Silence is not treated as contradiction.
8. Genuine conflict requires explicit contrary material plus sufficient factual overlap; M4 records a `DisputedMatter` and does not resolve credibility.
9. Independent evidence becomes corroborative only when it materially overlaps another supporting source from a different source family. Independence alone does not equal corroboration.
10. Evidential gaps are generated only for controlled material elements with a specific missing evidence target. Empty elements do not automatically create generic gaps.
11. Absence of mapped evidence is never converted into evidence that an event did not occur.
12. `legal_analysis` remains empty for Milestone 5.

## Status handling

The assessed `IssueAnalysis` preserves:

- `issue_analysis_id`;
- `case_id`;
- issue-definition ID/version;
- schema version;
- element IDs/order;
- `created_at`.

M4 normally sets `analysis_status` to `EVIDENCE_INCOMPLETE`, or `CONFLICTING_EVIDENCE` where a genuine explicit conflict is detected.

## Non-goals

No retrieval, remapping, chronology, evidence matrix, statutory-element decision, legal conclusion, prospects assessment, final prose analysis, pleading or submission generation is implemented in M4.

## Acceptance

M4 passes when all earlier tests remain green, M3 mappings remain immutable, all four controlled issue definitions can be assessed, source assertions remain assertions, genuine conflicts and specific gaps are handled conservatively, and the four fixed real-case queries produce per-element evidential assessments without merits conclusions.
