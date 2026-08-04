# Sprint 2.4 Milestone 3 — Acceptance Fix

## Scope

This narrow acceptance fix corrects chronology profile dispatch after the live
four-issue Shafi v CACI Ltd run exposed a valid frozen legal element without a
registered chronology extraction profile:

```text
('LIM-001', '1.0', 'LIM-JE-FACTORS')
```

Milestone 3 remains uncommitted and untagged while this fix is tested.

## Corrected rule

Chronology extraction now distinguishes:

- a valid controlled element with a registered `chronology-profile/1.0`
  profile — run its controlled extraction rules;
- a valid controlled element with no chronology profile — treat it as
  non-event-capable for M3 v1.0 and skip it without creating an event;
- an unknown definition/version/element key — fail closed;
- a duplicate or registered profile for an unknown controlled element — fail
  closed as a profile-registry integrity error.

The strict `profile_for()` helper remains strict for callers explicitly
requiring a profile. The main extraction loop uses optional profile resolution.

No generic or dummy profile was added for `LIM-JE-FACTORS`.

## Files changed

```text
src/case_analysis/m3/event_extraction.py
tests/test_case_analysis_m3_extraction.py
tests/test_case_analysis_m3_acceptance.py
```

No Sprint 2.2, Sprint 2.3, Sprint 2.4 M1 or Sprint 2.4 M2 file changed.

## Regression coverage

The fix adds or strengthens tests proving:

1. `LIM-JE-FACTORS` is a valid controlled element but has no M3 v1.0 chronology profile;
2. optional lookup returns no profile while strict lookup still raises;
3. unknown controlled-element keys still fail closed;
4. a date and event words in an unprofiled element cannot create an event;
5. registered event-capable elements continue extracting normally;
6. the complete four-doctrine fixture succeeds with evidence under `LIM-JE-FACTORS` and creates no chronology event from it.

## Verification

Packaged maintained suite:

```text
418 passed
```

This is three tests beyond the pre-fix packaged M3 suite of 415 tests.
