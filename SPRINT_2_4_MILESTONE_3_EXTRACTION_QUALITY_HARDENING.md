# Sprint 2.4 Milestone 3 — Extraction Quality Hardening

## Purpose

The live chronology acceptance run passed all automated invariants but exposed
non-event headings, document labels and footer boilerplate being emitted as
unknown-date events. It also showed a generic request for documents could be
misclassified as an adjustment proposal.

This hardening pass changes only the M3 controlled extraction layer. It does
not change chronology models, event/assertion identity functions, ordering,
serialization, date parsing, M2 evidence identity, M4/M5 status semantics or
input validation.

## Changes

- Suppress structural headings, section titles, policy/background labels and
  short heading-like text when they contain no factual event predicate.
- Suppress common email confidentiality/footer text and Acas footer slogans.
- Require an event-type-specific factual action before raw frozen evidence text
  can enrich a proposition into an event assertion.
- Remove generic `request` / `proposal` matching from the reasonable-adjustment
  extraction profile; an actual adjustment object such as home working,
  phased return, flexible hours or reduced hours must be present.
- Use word-boundary signal matching so terms such as `act` do not match
  `factual`, and `sent` does not match `presented`.
- Preserve factual all-capital source sentences when they contain an explicit
  event action.

## Regression coverage

Targeted tests reproduce:

- `MEDICAL BACKGROUND`;
- `Section 3 – Factual Background`;
- `Documents Relevant to the Capability Review`;
- `The Company's Long-Term Sickness Absence Policy`;
- `Catastrophic Relapse and Permanent Incapacity`;
- email-transmission/footer boilerplate;
- `Acas working for everyone`;
- generic requests for records/documents/payslips;
- noun-only medical labels;
- signal-substring collisions;
- preservation of genuine adjustment requests, ET1 presentation and factual
  all-capital communication events.

## Boundary

No Sprint 2.2, Sprint 2.3, Sprint 2.4 M1 or Sprint 2.4 M2 file is modified.
