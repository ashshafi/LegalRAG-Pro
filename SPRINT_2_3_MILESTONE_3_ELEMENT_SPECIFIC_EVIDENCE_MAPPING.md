# Sprint 2.3 — Milestone 3
## Element-Specific Evidence Mapping
### Specification v1.0

## Objective

Connect the controlled issue architecture from Sprint 2.3 M1/M2 to the frozen Sprint 2.2 evidence pipeline without changing retrieval semantics.

Milestone 3 answers one question only:

> Which retrieved evidence is relevant to which controlled legal element of the selected primary issue?

It does **not** decide whether an element is legally satisfied, resolve conflicts, identify formal evidential gaps, decide limitation/reasonableness, or generate merits conclusions.

## Frozen dependency direction

The dependency is one-way:

`Sprint 2.3 M3 -> frozen Sprint 2.2 retriever/evidence semantics`

Sprint 2.2 does not acquire knowledge of legal issues or elements.

The Milestone 2 checkpoint `6d59843 / sprint-2.3-milestone-2` remains the rollback point.

## Pipeline

User question
→ M2 `IssueSelection`
→ exact registered primary `IssueDefinition`
→ controlled element search profiles
→ frozen Sprint 2.2 retrieval/evidence pipeline
→ Sprint 2.2 semantic enrichment
→ `EvidenceReference` conversion
→ deterministic element relevance mapping
→ M1 `IssueAnalysis`

## New M3-local structures

### `ElementSearchProfile`

Version-linked mapping configuration containing:

- exact issue definition ID/version;
- exact element ID;
- factual search objective;
- search terms/strong phrases;
- optional required factual signals;
- optional source-type hints.

Profiles are mapping configuration, not legal definitions.

### `EvidenceMapping`

An M3-local trace record containing:

- `EvidenceReference`;
- issue definition ID/version;
- element ID;
- relevance (`RELEVANT`, `POTENTIALLY_RELEVANT`, `NOT_RELEVANT`);
- mapping confidence;
- mapping rationale;
- mapper version.

This relationship remains M3-local in v1.0 and does not modify the frozen M1 schema.

### `MappedIssueAnalysis`

An M3-local wrapper containing:

- the valid frozen M1 `IssueAnalysis`;
- ordered per-element mapping decisions;
- `element-mapper/1.0`.

This resolves mapper-version traceability without modifying the M1 `IssueAnalysis` schema.

## Controlled profiles

All 34 elements across the four registered v1.0 definitions have an exact search profile:

- RA-001/1.0 — Reasonable adjustments (8 elements)
- DA-001/1.0 — Discrimination arising from disability (7 elements)
- EK-001/1.0 — Employer knowledge of disability (9 elements)
- LIM-001/1.0 — Limitation / continuing act / just and equitable extension (10 elements)

Profile coverage and ordering are validated against the M1 registry.

## Retrieval boundary

M3 does not implement:

- embeddings;
- Chroma querying;
- case filters;
- over-retrieval;
- deduplication;
- diversification;
- primary-source reranking;
- chunk provenance;
- source classification;
- semantic provenance.

A separate additive bridge, `src/legal_analysis_retrieval_adapter.py`, composes the existing frozen `retriever.retrieve()` with the existing frozen `enrich_evidence_semantics()` function.

The bridge sits outside `src/legal_analysis/` so the frozen M1 domain package remains importable without OpenAI/Chroma configuration.

## Case isolation

The same `case_id` is supplied to every element-specific retrieval call. M3 rejects a case ID that conflicts with a case-bound M2 `IssueSelection`.

## Evidence conversion

M3 preserves durable Sprint 2.2 metadata where available:

- document identity/name;
- page;
- chunk ID;
- source type;
- semantic provenance type;
- provenance basis;
- provenance confidence;
- evidence status;
- date;
- author;
- parties;
- citation.

Temporary ranking/vector scores are not copied into the M1 durable domain record.

## Analytical roles

All M3-mapped evidence is stored as `NEUTRAL` in the M1 `ElementAnalysis`.

That is deliberate. M3 establishes element relevance only. Supporting/adverse/conflicting legal evaluation belongs to Sprint 2.3 M4.

## Source assertion safety

A Sprint 2.2 knowledge assertion remains `SOURCE_ASSERTION` when mapped to a knowledge element. Mapping evidence to an element cannot upgrade an assertion into a documented substantive fact.

## Empty elements

An element may legitimately contain no mapped evidence. M3 does not automatically create an `EvidentialGap`; formal gap analysis belongs to M4.

## Evidence reuse

The same stable chunk may map to multiple legal elements where its content is genuinely relevant. Within one element, duplicate evidence identities are suppressed.

## Bounded retrieval

Version 1.0 uses explicit configuration constants:

- candidate limit per element: 8;
- retained relevant items per element: 5;
- mapper version: `element-mapper/1.0`.

## Deterministic relevance mapping

M3 v1.0 uses deterministic profile matching. No LLM is required.

Each candidate receives:

- relevance state;
- mapping confidence (`HIGH`, `MEDIUM`, `LOW`);
- a short rationale explaining only element relevance.

Required factual gates prevent broad contextual material from becoming direct evidence. For example, an item cannot become directly relevant to `EK-DIRECT-KNOWLEDGE` merely because it mentions disability; it must also contain a controlled receipt/acknowledgement/discussion/awareness signal.

## Diagnostic output

`format_mapping_diagnostics()` provides a deterministic human-readable acceptance representation grouped by legal element. It is not a final legal-analysis UI and contains no merits conclusion.

## Acceptance queries

The four frozen real-case acceptance questions remain:

1. `What evidence shows CACI knew about my disability?`
2. `Should CACI have allowed me to work from home because of my disability?`
3. `Is my claim out of time if the failures continued?`
4. `Was I treated unfavourably because of something arising from my disability?`

The acceptance requirement is not merely successful retrieval. Evidence must be distributed among appropriate controlled elements without contaminating unrelated elements or upgrading source assertions into facts.

## Non-goals

M3 does not implement:

- merits analysis;
- element satisfaction decisions;
- final supporting/adverse classification;
- conflict resolution;
- evidential-gap generation;
- respondent-position synthesis;
- legal conclusions;
- chronology generation;
- evidence matrices;
- final prose analysis;
- Streamlit analysis UI;
- work-product generation.
