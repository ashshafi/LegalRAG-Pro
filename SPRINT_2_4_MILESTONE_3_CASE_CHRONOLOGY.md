# Sprint 2.4 Milestone 3 — Case Chronology

## Implementation status

Milestone 3 implements a deterministic, evidence-traceable chronology over the frozen Sprint 2.4 M1/M2 and Sprint 2.3 M4/M5 analytical records.

Versions:

- `case-chronology-schema/1.0`
- `case-chronology-builder/1.0`
- `chronology-profile/1.0`

## Frozen boundary

The implementation is entirely additive under `src/case_analysis/m3/`.

It does not:

- retrieve documents;
- call OpenAI or Chroma;
- import the legacy timeline feature;
- remap evidence;
- alter M4 proposition status or evidential role;
- alter M5 legal-analysis status;
- create case-level gap/conflict registers;
- produce case-level merits synthesis.

## Runtime modules

```text
src/case_analysis/m3/
    models.py
    date_parsing.py
    event_extraction.py
    event_identity.py
    chronology.py
    chronology_validation.py
    chronology_serialization.py
```

## Governing extraction rule

Chronology is M4-proposition-led and frozen-evidence-enriched.

Every event assertion must originate from an existing M2 `EvidenceUse` plus `EvidencePropositionLink`. Frozen evidence summary text may only enrich that proposition under an exact, deterministic profile keyed by:

```text
(issue_definition_id, issue_definition_version, element_id)
```

Every profile records `chronology-profile/1.0`. Raw dates in evidence text do not independently create events.

## Occurrence and timing

Occurrence status and timing status are separate:

```text
EventStatus:
    ESTABLISHED
    SUPPORTED
    DISPUTED
    UNRESOLVED

TimingStatus:
    ESTABLISHED
    SUPPORTED
    DISPUTED
    UNKNOWN
```

An event may therefore be established while its precise timing remains disputed.

## Partial dates and periods

Dates preserve only the precision actually evidenced:

```text
EXACT
MONTH
YEAR
```

`TemporalExtent` separately represents:

```text
POINT
PERIOD
```

Range boundaries preserve their own precision. Open-ended periods retain `end=None`. No missing day or month is invented for display.

## Identity and deduplication

`EventAssertion` identity is derived deterministically from:

```text
issue_analysis_id
+ element_id
+ source proposition index
+ evidence_key
+ extraction ordinal
+ profile version
```

`CaseEvent` identity is derived from:

```text
case_id
+ controlled event type
+ normalized event core
+ sorted assertion IDs
+ schema/builder version
```

Grouping is conservative. Assertions from the same evidence item merge only when they represent the same extracted occurrence. Cross-evidence grouping requires an exact, sufficiently specific controlled event core. No fuzzy or LLM deduplication is used.

## Date safeguards

- `EvidenceReference.date` is treated as source-date metadata of unknown semantic type.
- It can become event timing only when the represented event is the source communication/document itself.
- Historical dates explicitly stated within a later document remain the event dates.
- A communication clause may borrow a header/summary date only when exactly one temporal expression exists in that frozen summary.
- Bare four-digit tokens, case numbers and authority years do not become chronology dates.

## Acceptance boundary

Milestone 3 passes when chronology is deterministic, round-trippable, immutable with respect to all source objects, and every event resolves to canonical M2 evidence and an exact M4 proposition coordinate without upgrading evidential status.
