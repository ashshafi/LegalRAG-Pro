# Sprint 2.4 Milestone 3 — Calibrated Extraction Implementation v1.1

Status: implementation candidate; do not commit or tag before live Shafi acceptance.

## Versions

- chronology schema: `case-chronology-schema/1.0`
- chronology builder: `case-chronology-builder/1.1`
- chronology profile: `chronology-profile/1.1`
- extraction policy: `chronology-extraction-policy/1.1`

## Runtime change surface

Only:

- `src/case_analysis/m3/event_extraction.py`
- `src/case_analysis/m3/event_identity.py`
- `src/case_analysis/m3/models.py`

Frozen Sprint 2.3, Sprint 2.4 M1 and Sprint 2.4 M2 runtime files remain byte-identical.

## Calibrated pipeline

`CaseEvidenceRecord` → deterministic canonical `EvidenceReference` → proposition-constrained source-event discovery → stable source-event ordinal → existing M2 `EvidenceUse` projection → `EventAssertion` → conservative `CaseEvent` grouping.

Key behavioural changes:

- source events are discovered once per canonical evidence item, not independently per legal element;
- `EventAssertion.extraction_ordinal` is the stable source-event ordinal within canonical evidence;
- body-derived substantive events precede header fallback;
- a later communication header cannot re-date a historical body event;
- profiles constrain projection rather than independently generating event identities;
- conflicting dates in different evidence records remain separate by default;
- cross-evidence automatic grouping requires specific identical factual core plus compatible explicit timing;
- M4 proposition status remains the event-status ceiling;
- no new legal-use relationship is created outside M2.

## Live fixture dependency

The actual current Shafi M2/M5 result state is not present in the packaged application snapshot used to build this candidate. The patch therefore includes a deterministic test-only fixture-capture helper:

`tests/case_analysis_m3_live_fixture_capture.py`

Capture the live fixture from the exact four-issue `results` and `matrices` objects used for local acceptance and write it to:

`tests/fixtures/shafi_chronology_live_v1_0.json`

Do not manually clean or rewrite the captured summaries.
