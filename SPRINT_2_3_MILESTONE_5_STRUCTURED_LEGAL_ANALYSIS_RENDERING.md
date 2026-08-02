# Sprint 2.3 — Milestone 5
## Structured Legal Analysis Rendering
### Specification v1.0

## Objective

Sprint 2.3 Milestone 5 converts the immutable Milestone 4 evidential assessment into structured, citation-traceable provisional legal analysis.

The governing invariant is:

> **M5 may interpret the frozen evidential state. It must never rewrite it.**

M5 is the first Sprint 2.3 layer permitted to explain legal significance, but it does not make final liability, limitation, credibility, prospects or statutory-satisfaction decisions.

## Frozen dependencies

M5 consumes the checkpoint frozen at `sprint-2.3-milestone-4` and treats all earlier layers as immutable dependencies:

- Sprint 2.2 retrieval, case isolation, deduplication, provenance, reranking and evidence semantics;
- Sprint 2.3 M1 durable analysis models and versioned issue definitions;
- Sprint 2.3 M2 issue selection;
- Sprint 2.3 M3 evidence-to-element mappings;
- Sprint 2.3 M4 evidential roles, proposition assessments, disputes, unresolved matters and gaps.

M5 does not retrieve, remap, reassess or mutate any of those objects.

## Input

The only analytical input is a valid M4 `EvidenceAssessmentResult`.

M5 uses:

- `ElementEvidenceAssessment.assessed_propositions` as the primary traceable proposition source;
- M4 `EvidenceAssessment` roles;
- M4 disputed matters;
- M4 unresolved matters;
- M4 evidential gaps;
- M4 assessment confidence;
- M3 stable evidence keys and M1 `EvidenceReference.citation` for traceability.

The string-only `presently_established` field is diagnostic convenience and is not the primary source for proposition-level rendering.

## Output

M5 produces an additive `StructuredLegalAnalysisResult` containing one `ElementLegalAnalysis` for every exact controlled element and a mechanical issue-level synthesis.

For each element the output contains:

1. legal question;
2. current evidential position;
3. established factual matters with evidence keys/citations;
4. supported-but-not-established matters with evidence keys/citations;
5. source assertions, explicitly qualified;
6. adverse/countervailing material;
7. corroborative and contextual material;
8. disputes/conflicting material;
9. legal significance;
10. limitations;
11. unresolved matters;
12. frozen M4 evidential gaps;
13. provisional non-merits analytical status;
14. provisional analysis;
15. analysis confidence.

## M5-local provisional statuses

M5 owns `ElementAnalysisStatus` with exactly these values:

- `WELL_SUPPORTED_ON_CURRENT_RECORD`
- `PARTIALLY_SUPPORTED`
- `DISPUTED`
- `INSUFFICIENTLY_EVIDENCED`
- `UNRESOLVED`

These describe the analytical state of the current record. They are not equivalent to `SATISFIED`, `PROVEN`, `FAILED`, `CLAIM_SUCCEEDS` or `CLAIM_FAILS`.

## Status constraints

M5 status is mechanically constrained by M4:

- genuine M4 disputes produce `DISPUTED`;
- no meaningful mapped/assessed support produces `INSUFFICIENTLY_EVIDENCED`;
- strong established factual material with high M4 confidence and no material unresolved limitation may produce `WELL_SUPPORTED_ON_CURRENT_RECORD`;
- established or supported factual material with limitations produces `PARTIALLY_SUPPORTED`;
- otherwise the analysis remains `UNRESOLVED`.

M5 never upgrades an M4 proposition assessment.

## Confidence constraints

M5 analysis confidence may never exceed M4 assessment confidence.

Status ceilings are:

- `WELL_SUPPORTED_ON_CURRENT_RECORD`: maximum HIGH;
- `PARTIALLY_SUPPORTED`: maximum MEDIUM;
- `DISPUTED`: maximum MEDIUM;
- `INSUFFICIENTLY_EVIDENCED`: LOW;
- `UNRESOLVED`: LOW.

## Exact versioned legal-significance profiles

Legal significance must not be inferred from element names or generated generically.

M5 v1.0 therefore contains exact profiles keyed by:

`(issue_definition_id, issue_definition_version, element_id)`

All 34 elements of the four current definitions must have explicit coverage:

- RA-001/1.0 — 8 elements;
- DA-001/1.0 — 7 elements;
- EK-001/1.0 — 9 elements;
- LIM-001/1.0 — 10 elements.

Unknown definitions, versions or elements fail closed. M5 must not improvise legal reasoning.

Each profile records:

- legal relevance;
- the precise analytical subject;
- a safe provisional-analysis pattern;
- a key caveat;
- prohibited merits conclusions.

## Fixed reasoning pattern

For every element M5 follows:

**Evidence state → legal relevance → limitation/caveat → provisional analytical conclusion**

Example:

- Evidence state: CACI participation in RTW discussions is supported, while receipt of a specific medical recommendation is unresolved.
- Legal relevance: the participation may be relevant to actual or constructive knowledge.
- Limitation: participation does not establish receipt of the specific recommendation.
- Provisional analysis: the knowledge issue is partially supported on the current factual record but remains limited as to the precise information known by particular decision-makers.

M5 may not render the final proposition as “CACI had legal knowledge”.

## Source assertion rule

If M4 evidence status is `SOURCE_ASSERTION`, M5 must visibly retain that limitation.

A source assertion establishes that an assertion was made. It does not independently establish the truth of the asserted proposition.

## Adverse and conflicting evidence

M4 adverse evidence must remain visible in M5. Genuine M4 conflicts and disputes remain conflicts/disputes. M5 does not resolve credibility or choose a factual winner.

Silence or lack of corroboration is not converted into contradiction.

## Gaps and unresolved matters

M5 copies M4 gaps and unresolved matters. It may explain their legal significance, but it cannot regenerate, delete, repair or search around them.

Absence of evidence remains distinct from evidence of absence.

## Proposition-level traceability

Every material factual statement derived from an M4 assessed proposition must retain stable evidence keys and documentary citations.

Document citations support factual propositions. They must not be presented as if the source itself stated M5's legal conclusion.

## Doctrine safeguards

### Employer knowledge

M5 may say evidence is capable of supporting an actual- or constructive-knowledge argument. It may not declare that CACI had legal knowledge.

### Reasonable adjustments

M5 may identify that an adjustment was proposed and that evidence bears on practicability/effectiveness. It may not declare an adjustment legally reasonable or that the duty was breached.

### Discrimination arising from disability

M5 may identify factual material bearing on something arising, treatment and causation. It may not declare section 15 liability established or objective justification resolved.

### Limitation

M5 may identify factual material capable of supporting a continuing-conduct argument, dates, delay explanations and discretionary factors. It may not rule that a continuing act existed, that the claim is in/out of time, or that an extension should be granted.

## Issue-level synthesis

Issue-level synthesis mechanically aggregates M5 element statuses and limitations. It is not a scoring model and must never reason that a claim succeeds because a number of elements are supported.

## Versioning

M5 records:

`LEGAL_ANALYSER_VERSION = "legal-analyser/1.0"`

This is independent of the issue-analysis schema, issue-definition version, selector version, mapper version and assessor version.

## Package boundary

M5 v1.0 is additive and limited to:

```text
src/legal_analysis/
    legal_analysis.py
    legal_analysis_rules.py
    legal_analysis_renderer.py
```

It does not modify `legal_analysis/__init__.py` or any M1–M4 source module.

## No external runtime dependency

M5 v1.0 requires no OpenAI, Chroma, embeddings, retrieval service or Streamlit dependency. It is testable entirely from synthetic M4 objects.

## Acceptance queries

The four frozen real-case acceptance questions are:

1. `What evidence shows CACI knew about my disability?`
2. `Should CACI have allowed me to work from home because of my disability?`
3. `Is my claim out of time if the failures continued?`
4. `Was I treated unfavourably because of something arising from my disability?`

Acceptance requires structured legal significance while preserving all M4 limitations and avoiding final legal outcomes.

## Acceptance criteria

M5 passes when:

- it consumes M4 only;
- M4 is unchanged after rendering;
- all 34 exact profiles are covered;
- unknown legal definitions/versions/elements fail closed;
- evidence keys and citations remain traceable;
- source assertions remain qualified;
- adverse evidence remains visible;
- M4 disputes and gaps remain unchanged;
- M5 confidence never exceeds M4 confidence;
- no M4 proposition status is upgraded;
- no retrieval, remapping or reassessment occurs;
- no statutory element is finally declared satisfied;
- no liability, prospects, credibility or final limitation ruling is produced;
- all prior regression tests remain green;
- the four real-case questions produce disciplined provisional legal analyses.
