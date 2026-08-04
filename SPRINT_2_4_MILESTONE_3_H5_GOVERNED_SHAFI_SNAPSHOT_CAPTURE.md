# Sprint 2.4 Milestone 3 — H5 Governed Shafi Analytical Snapshot Capture

Status: **H5 — NOT PASSED**

## What is complete

H5 harness-only governed capture infrastructure is implemented and tested.

It provides:

- exact verification of the immutable legacy fixture SHA before capture;
- truthful provenance classification (`ORIGINAL_CAPTURE_STATE` or `NEW_GOVERNED_FROZEN_STATE`);
- fail-closed rejection of `ORIGINAL_CAPTURE_STATE` unless exact complete original-state recovery is independently verified;
- exact four-question scope enforcement;
- H2 in-memory snapshot construction and validation;
- H3 exact native reconstruction and cross-component validation;
- repeated in-memory Gate 1 determinism verification;
- legacy partial-fixture semantic compatibility observation;
- canonical write-once snapshot creation;
- post-write H2 reload/H3 reconstruction/Gate 1 rerun;
- legacy fixture SHA verification after capture;
- overwrite protection.

Harness files added:

- `tests/case_analysis_m3_governed_snapshot_capture.py`
- `tests/case_analysis_m3_h5_shafi_capture.py`
- `tests/test_case_analysis_m3_governed_snapshot_capture.py`

No production/runtime file is modified.

## Provenance determination

The exact complete M5/M1/M2 state from the historical
`shafi_chronology_live_v1_0.json` capture is not available in the persisted
project artifacts inspected for H5. The historical fixture is a partial M2/M4
boundary snapshot and cannot reconstruct the full original native state.

Therefore a future successful H5 capture must be classified:

`NEW_GOVERNED_FROZEN_STATE`

unless an independently persisted complete original M5/M1/M2 state is later
located and proven exact.

## Why the real governed snapshot is not included in this package

The authorised H5 target is:

`tests/fixtures/shafi_m3_frozen_analytical_snapshot_v1_0.json`

It must be created from one atomic live four-question run using the user's local
LegalRAG case repository/retrieval/OpenAI/Chroma state. That state is not present
in this packaging environment. Creating a synthetic or reconstructed substitute
would violate the H5 provenance rules.

Accordingly, no governed Shafi snapshot has been created here.

## Local governed capture

After applying H1-H5 to the current experimental tree and confirming the legacy
fixture SHA, run from the repository root:

```powershell
$env:PYTHONPATH="$PWD\src;$PWD\tests"
python .\tests\case_analysis_m3_h5_shafi_capture.py
```

The script runs exactly the four approved questions, captures one atomic
M5/M1/M2 state, classifies it as `NEW_GOVERNED_FROZEN_STATE`, validates it fully
in memory, and only then writes the target snapshot once.

If the target snapshot already exists, the script refuses to overwrite it.

## Required local output before H5 can pass

The capture must report:

- snapshot provenance classification;
- snapshot path;
- snapshot file SHA-256;
- `analytical_state_sha256`;
- M5 SHA-256;
- M1 SHA-256;
- M2 SHA-256;
- legacy fixture SHA before and after;
- legacy fixture semantic compatibility/drift observation;
- Gate 1 reconstruction PASS;
- Gate 1 deterministic PASS;
- chronology round-trip PASS;
- event count;
- dated-event count;
- multi-issue-event count.

## Automated verification in this package

- Dedicated H5 tests: 11 passed
- H1-H5 harness tests: 63 passed
- Complete packaged suite: 534 passed

Boundary:

- existing files changed: 0
- new harness/test files: 3
- production/runtime files changed: 0
- new fixture files: 0
- `event_extraction.py` changed: NO
- legacy fixture changed: NO
- Gate 2 live regeneration implemented by H5: NO
- M3 commit/tag: NONE

The correct gate remains:

**H5 — NOT PASSED**

H6 must not begin until the governed Shafi snapshot has actually been captured,
reloaded and reviewed from the user's local case state.
