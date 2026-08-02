# Sprint 2.3 Milestone 4 — Installation / Validation

Apply the Milestone 4 code patch over the frozen `sprint-2.3-milestone-3` working tree on `feature/legal-analysis`.

The patch is additive. It adds:

```text
src/legal_analysis/evidence_assessment.py
src/legal_analysis/assessment_rules.py
src/legal_analysis/element_assessor.py

tests/test_legal_analysis_evidence_assessment.py
tests/test_legal_analysis_assessment_rules.py
tests/test_legal_analysis_element_assessor.py
tests/test_legal_analysis_element_assessor_integration.py
tests/test_legal_analysis_element_assessor_architecture.py
tests/test_legal_analysis_element_assessor_acceptance.py

SPRINT_2_3_MILESTONE_4_ELEMENT_ASSESSMENT.md
SPRINT_2_3_MILESTONE_4_INSTALL.md
```

No frozen M1–M3 or Sprint 2.2 source file should be replaced by the patch.

## Regression test

From the repository root with the virtual environment active:

```powershell
python -m pytest -q
```

If a standalone diagnostic command imports `src` directly, set:

```powershell
$env:PYTHONPATH="$PWD\src"
```

## Acceptance

Do not commit/tag Milestone 4 until:

1. the complete local regression suite passes;
2. the four frozen real-case M3 queries are mapped using the frozen M3 mapper;
3. each `MappedIssueAnalysis` is passed to `ElementEvidenceAssessor().assess(...)`;
4. `format_assessment_diagnostics(...)` is reviewed for supporting/adverse/corroborative/neutral/conflicting evidence, source assertions, disputes, unresolved matters and material gaps;
5. no output determines statutory-element satisfaction or final legal merits.
