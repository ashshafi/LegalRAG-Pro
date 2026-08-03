# LegalRAG Pro — Sprint 2.4 Milestone 1
## Case Analysis Foundation
### Implementation Specification v1.0

**Starting checkpoint:** `dd17212 / sprint-2.3-milestone-5`

## Objective

Create the minimum durable case-wide foundation over one or more frozen Sprint 2.3 `StructuredLegalAnalysisResult` objects without implementing any case-wide substantive analysis.

## Governing rule

Sprint 2.4 M1 identifies and validates the immutable analytical source set. It does not aggregate, reinterpret, canonicalise or synthesise the underlying legal analysis.

## Runtime surface

Only:

```text
src/case_analysis/
    __init__.py
    models.py
    validation.py
    serialization.py
    foundation.py
```

## Durable records

### SourceAnalysisReference

Preserves only durable Sprint 2.3 lineage:

- `case_id`
- `issue_analysis_id`
- issue-definition ID/version
- issue name
- issue-analysis schema version
- original issue-analysis `created_at`
- exact element IDs/order
- M3 mapper version
- M4 assessor version
- M5 analyser version

The complete M3–M5 object graph is not embedded or serialized.

### CaseAnalysisFoundation

Contains:

- `case-synthesis-schema/1.0`
- deterministic `synthesis_id`
- `case_id`
- sorted `SourceAnalysisReference` records
- metadata `created_at`
- `case-synthesiser/1.0`

## Deterministic identity

`synthesis_id` is UUIDv5 derived from:

1. case-synthesis schema version;
2. case-synthesiser version;
3. case ID;
4. sorted source `issue_analysis_id` values.

Input order does not affect identity.

`created_at` does not participate in identity.

For byte-stable default rebuilds, the foundation builder derives its default metadata `created_at` from the latest immutable source analysis creation timestamp. A caller may supply another timezone-aware metadata timestamp without changing `synthesis_id`.

## Validation

M1 fails closed on:

- no source analyses;
- mixed `case_id` input;
- duplicate `issue_analysis_id` input;
- invalid UUID/version/schema lineage;
- changed M3/M4 identity fields;
- changed M3/M4/M5 element order;
- tampered `synthesis_id` during deserialization.

## Explicit non-goals

M1 does **not** implement:

- Issue Matrix;
- Evidence Matrix;
- evidence canonicalisation;
- chronology or `CaseEvent`;
- date/event extraction;
- gap consolidation;
- conflict consolidation;
- dependency analysis;
- final `CaseAnalyticalSynthesis`;
- retrieval, Chroma, OpenAI or Streamlit integration.

## Acceptance baseline

Packaged baseline:

- frozen M5 tests: 322
- new M1 tests: 21
- total: **343 passed**
- pre-existing files changed: **0**
- pre-existing files missing: **0**
