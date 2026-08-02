# Sprint 2.3 Milestone 2 — Issue Identification & Definition Selection

## Status

Implementation candidate for acceptance testing.

## Scope

Milestone 2 routes a user legal question to one or more controlled issue definitions created in Sprint 2.3 Milestone 1. It does not retrieve evidence, populate `IssueAnalysis`, assess merits, construct chronology, detect evidence conflicts/gaps, or generate legal conclusions.

## New modules

- `src/legal_analysis/selection.py`
  - `IssueSelection`
  - `SelectedIssue`
  - `IssueSelectionAmbiguity`
  - `IssueSelectionRole`
  - deterministic JSON serialization/deserialization
  - registry validation
  - selector version constant `issue-selector/1.0`
- `src/legal_analysis/selector.py`
  - `DeterministicIssueSelector`
  - registry-constrained, focus-sensitive rules
  - explicit unsupported and ambiguous outcomes
  - convenience function `select_issues()`

## Controlled outputs

The selector can reference only registered definitions:

- `RA-001 / 1.0` — Reasonable adjustments
- `DA-001 / 1.0` — Discrimination arising from disability
- `EK-001 / 1.0` — Employer knowledge of disability
- `LIM-001 / 1.0` — Limitation / continuing act / just and equitable extension

No legal definition is created by the selector.

## Selection roles

- `PRIMARY`
- `RELATED`
- `NOT_SELECTED`
- ambiguity is represented explicitly by `IssueSelectionAmbiguity`

The structured result also records issue-matching rationale, routing confidence and selector version. Confidence concerns routing only and never merits or prospects.

## Routing design

The first selector is deterministic. It does not use an LLM or a keyword-count score. Explicit focus patterns take precedence over broader topic signals. For example:

> Did CACI know that I wanted a reasonable adjustment?

routes to `EK-001 / 1.0` as primary and `RA-001 / 1.0` as related, because the grammatical focus is employer knowledge rather than the adjustment merits.

Unsupported topics such as breach of contract are not forced into one of the four registered disability definitions. Broad questions such as "Was what happened to me discriminatory?" remain explicitly ambiguous.

## Architectural boundary

Milestone 2 adds no dependency on:

- OpenAI or any external API
- Chroma or embeddings
- retrieval/re-ranking
- Streamlit/UI
- evidence analysis
- Sprint 2.2 runtime retrieval objects

The Milestone 1 definition, model, registry, validation and serialization modules remain unchanged.

## Acceptance queries

1. `What evidence shows CACI knew about my disability?`
   - Primary: `EK-001 / 1.0`
   - Related: `RA-001 / 1.0`
2. `Is my claim out of time if the failures continued?`
   - Primary: `LIM-001 / 1.0`
3. `Should CACI have allowed me to work from home because of my disability?`
   - Primary: `RA-001 / 1.0`
   - Related: `EK-001 / 1.0`
4. `Was I treated unfavourably because of something arising from my disability?`
   - Primary: `DA-001 / 1.0`
5. `Did CACI fail to make reasonable adjustments and is that claim still in time because the failure continued?`
   - Primary: `RA-001 / 1.0`
   - Related: `EK-001 / 1.0`, `LIM-001 / 1.0`
6. `Did CACI breach my employment contract?`
   - No primary; unsupported current-registry issue
7. `Was what happened to me discriminatory?`
   - No primary; explicit `RA-001`/`DA-001` ambiguity

## Packaged verification

The maintained `tests/` suite passes with the M2 additions applied to the packaged frozen M1 application snapshot.

Milestone 2 is not considered frozen until the user's live `feature/legal-analysis` branch passes its full regression suite and the seven acceptance queries produce the required routing structure.
