# Sprint 2.3 Milestone 1 — Structured Analysis Foundation

Version: 1.0

## Objective

Introduce a durable, typed legal-analysis domain model without changing the frozen Sprint 2.2 retrieval/evidence pipeline, chat workflow, or UI.

## Implemented domain foundation

- `IssueAnalysis` with stable `case_id`, issue-definition ID/version, schema version, status, legal framework and ordered element analyses.
- `ElementAnalysis` with propositions, supporting/adverse/corroborative/neutral/conflicting evidence, disputes, inferences, evidential gaps, respondent position and later-analysis placeholders.
- `EvidenceReference` carrying forward Sprint 2.2 `EvidenceSourceType` plus provenance basis/confidence, evidence status and issue-specific analytical role.
- `Proposition`, `DisputedMatter` and `EvidentialGap` typed records.
- Explicit controlled enums for analysis status, analytical role, confidence, provenance basis/confidence, evidence status, materiality and issue-definition lifecycle.

## Controlled issue definitions

The following legal-domain definitions are explicit versioned data rather than prompt text:

- `RA-001 / 1.0` — Reasonable adjustments
- `DA-001 / 1.0` — Discrimination arising from disability
- `EK-001 / 1.0` — Employer knowledge of disability
- `LIM-001 / 1.0` — Limitation / continuing act / just and equitable extension

A substantive future change must be introduced under a new definition version; an existing ID/version pair is immutable domain meaning.

## Registry

`IssueDefinitionRegistry` supports:

- exact ID/version retrieval;
- current active-version retrieval;
- deterministic listing;
- version listing;
- duplicate ID/version rejection;
- prevention of multiple active versions for the same issue ID;
- validation of registered definitions.

The registry never silently substitutes a different issue or unknown version.

## Serialization

`IssueAnalysis` supports deterministic JSON-compatible serialization and deserialization, preserving:

- schema version;
- issue-definition ID/version;
- case ID;
- nested evidence metadata;
- evidence status and analytical role;
- propositions, disputes and gaps;
- timestamps and dates.

## Architectural boundary

Milestone 1 does **not** implement or modify:

- question-to-issue LLM classification;
- retrieval or reranking;
- element-specific evidence retrieval;
- automatic evidence-role classification;
- conflict/gap detection from real documents;
- prose legal analysis;
- Streamlit UI/chat behavior;
- chronology or work-product generation.

Sprint 2.2 remains a dependency and is not refactored by this milestone.

## Verification

The packaged Milestone 4 application snapshot contained 113 maintained regression tests. Milestone 1 adds 45 tests; the isolated `tests/` suite passes 158/158 in the build environment.

The user's live `sprint-2.2-milestone-4` checkpoint contains 120 tests, so a clean application of this additive patch would normally produce approximately 165 passing tests. The live local result is authoritative.
