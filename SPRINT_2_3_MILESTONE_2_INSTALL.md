# Sprint 2.3 Milestone 2 — Code Patch Installation

Apply this patch only to the clean `feature/legal-analysis` branch at the frozen Sprint 2.3 Milestone 1 checkpoint.

## Files added

```text
src/legal_analysis/selection.py
src/legal_analysis/selector.py
tests/test_legal_analysis_selection.py
tests/test_legal_analysis_selector.py
tests/test_legal_analysis_selector_architecture.py
SPRINT_2_3_MILESTONE_2_ISSUE_IDENTIFICATION.md
SPRINT_2_3_MILESTONE_2_INSTALL.md
```

The patch intentionally does not replace or modify any Milestone 1 source file or Sprint 2.2 module.

## Validation

From the project root with the virtual environment active:

```powershell
python -m pytest -q
```

If your shell does not already include `src` on Python's import path for direct command-line exercises, use:

```powershell
$env:PYTHONPATH="$PWD\src"
```

This environment variable is not a code change and does not need to be committed.

Do not commit or tag Milestone 2 until the full regression suite and the seven frozen behavioural acceptance queries have been checked.
