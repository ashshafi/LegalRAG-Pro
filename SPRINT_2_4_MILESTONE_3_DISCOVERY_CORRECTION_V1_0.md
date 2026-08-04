# Sprint 2.4 Milestone 3 — Calibrated Discovery Correction v1.0

Status: implementation candidate; do not commit or tag before corrected Shafi live acceptance.

## Frozen governing decisions

- M3 architecture: accepted
- Extraction Policy Calibration: `chronology-extraction-policy/1.1`
- Projection profile: `chronology-profile/1.1`
- Non-Event-Capable Projection Policy Decision v1.0: frozen
- Durable chronology schema: `case-chronology-schema/1.0`
- Builder: `case-chronology-builder/1.1`

## Runtime change surface

Only:

- `src/case_analysis/m3/event_extraction.py`

No behavioural change was made to:

- `event_identity.py`
- `models.py`
- `date_parsing.py`
- `chronology.py`
- `chronology_serialization.py`
- `chronology_validation.py`
- Sprint 2.4 M1/M2
- Sprint 2.3

## Corrected behaviour

1. Factual source-event discovery no longer depends on event-capable legal profiles.
2. Projection is evaluated afterwards as normal / exceptional / refused.
3. Exceptional projection is permitted only through the exact existing M2 `EvidenceUse`, never through a new issue or element.
4. Generic propositions may exceptionally project only where discovered events form one controlled factual subject family; they cannot whitelist unrelated multi-event content.
5. `NOT_SUPPORTED_BY_CURRENT_EVIDENCE` still refuses projection.
6. Split `Email N ... (date)` envelopes may supply their own date to nearby communication body text without inventing missing text.
7. A safe complete factual prefix may survive a clipped trailing continuation such as `, and then update the`; the missing continuation is never guessed.
8. Medical-deterioration grammar now recognises causal relapse constructions (`caused/resulted in/led to/triggered ... relapse`).
9. Payroll communication grammar now recognises response/reply/email-from and forwarded/passive-forwarding forms.
10. Payroll communication may use an unambiguous date in its containing factual block.
11. Timing-only M4 propositions can strengthen timing independently from event-content status when exactly one discovered event matches that date.
12. Source assertions remain visibly qualified in rendered assertion descriptions.
13. `Automatic reply` / out-of-office headers are rejected on the raw subject before sanitisation; substantive body text cannot rescue a rejected wrapper header.
14. Exhibit labels are treated as structural references so D1/D2/D3 lists do not become duplicate source events.

## New regression coverage

`tests/test_case_analysis_m3_discovery_correction.py` adds eight targeted cases:

- H4 14 June 2005 split envelope/body VF event, DA/EK/RA only;
- 1 July 2005 causal relapse, supported and source-qualified;
- August 2025 payslip request through existing `EK-UNRESOLVED` only;
- 4 September 2025 payroll event through existing `EK-UNRESOLVED` only;
- 6 September 2025 payroll response with supported content and established timing;
- generic non-event-capable projection does not whitelist unrelated events in one chunk;
- `NOT_SUPPORTED` non-event-capable use cannot project;
- 24 July automatic-reply header cannot be rescued by substantive body topic.

## Regression result in packaged snapshot

- Focused M3 suite: `94 passed`
- Complete maintained `tests` suite: `471 passed`

The user's local tree previously contained seven additional tests, so the local total may differ. The local result is authoritative.

## Fixture boundary

The captured live fixture remains external to this patch and must not be overwritten:

`tests/fixtures/shafi_chronology_live_v1_0.json`

Expected SHA-256:

`833124866a8afec8d071d94c6c973890cf45a4a8c26c9451706d51cc3c18965c`

Run the corrected four-issue live acceptance against that unchanged fixture before any commit/tag decision.
