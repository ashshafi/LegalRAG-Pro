# Sprint 2.3 Milestone 3 — Installation and Validation

## Baseline

Apply this patch only to the clean Sprint 2.3 Milestone 2 branch/checkpoint:

- branch: `feature/legal-analysis`
- tag: `sprint-2.3-milestone-2`
- baseline commit: `6d59843`

Do not modify the Sprint 2.2 rollback tags.

## Added runtime files

- `src/legal_analysis/search_profiles.py`
- `src/legal_analysis/evidence_mapping.py`
- `src/legal_analysis/evidence_mapper.py`
- `src/legal_analysis_retrieval_adapter.py`

No pre-existing runtime file is replaced by this patch.

## Added tests

- `tests/test_legal_analysis_search_profiles.py`
- `tests/test_legal_analysis_evidence_mapping.py`
- `tests/test_legal_analysis_evidence_mapper.py`
- `tests/test_legal_analysis_evidence_mapper_integration.py`
- `tests/test_legal_analysis_evidence_mapper_architecture.py`

## Run the maintained regression suite

From the repository root with the virtual environment active:

```powershell
python -m pytest -q
```

If a standalone Python acceptance script cannot import `legal_analysis`, set:

```powershell
$env:PYTHONPATH="$PWD\src"
```

## Real-case acceptance

Milestone 3 is not accepted solely because unit tests pass.

Run the four frozen questions through:

1. `DeterministicIssueSelector`
2. `ElementEvidenceMapper`
3. `format_mapping_diagnostics`

and inspect whether the real CACI evidence is attached to appropriate controlled elements.

Do not commit/tag until that real-case output has been reviewed.
