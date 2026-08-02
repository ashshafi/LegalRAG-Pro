# Sprint 2.3 Milestone 5 — Install and Acceptance

## Baseline

Apply this patch only to the clean `feature/legal-analysis` branch frozen at:

- tag: `sprint-2.3-milestone-4`
- commit recorded in the project checkpoint: `e7b9aad`

Verify locally before applying:

```powershell
git status
git branch --show-current
git log -1 --oneline
git tag --list "sprint-2.3-milestone-4"
python -m pytest -q
```

## Added runtime files

```text
src/legal_analysis/legal_analysis.py
src/legal_analysis/legal_analysis_rules.py
src/legal_analysis/legal_analysis_renderer.py
```

No M1–M4 runtime module is replaced or modified.

## Regression test

After applying the patch:

```powershell
python -m pytest -q
```

Do not commit or tag M5 until the real-case acceptance diagnostics have been reviewed.

## Real-case acceptance

Set the local import path if required:

```powershell
$env:PYTHONPATH="$PWD\src"
```

Then run M2 → M3 → M4 → M5 for the four frozen questions:

```powershell
@'
from case_management.repository import CaseRepository
from legal_analysis.selector import DeterministicIssueSelector
from legal_analysis.evidence_mapper import ElementEvidenceMapper
from legal_analysis.element_assessor import ElementEvidenceAssessor
from legal_analysis.legal_analysis_renderer import (
    StructuredLegalAnalysisRenderer,
    format_legal_analysis_diagnostics,
)

case = next(
    c for c in CaseRepository().list_all()
    if c.name.casefold() == "shafi v caci ltd".casefold()
)

questions = [
    "What evidence shows CACI knew about my disability?",
    "Should CACI have allowed me to work from home because of my disability?",
    "Is my claim out of time if the failures continued?",
    "Was I treated unfavourably because of something arising from my disability?",
]

selector = DeterministicIssueSelector()
mapper = ElementEvidenceMapper()
assessor = ElementEvidenceAssessor()
renderer = StructuredLegalAnalysisRenderer()

print("CASE:", case.name)
print("CASE ID:", case.case_id)

for number, question in enumerate(questions, 1):
    print("\n" + "=" * 100)
    print(f"ACCEPTANCE QUERY {number}")
    print(question)
    print("=" * 100)

    selection = selector.select(question, case_id=case.case_id)
    mapped = mapper.map_primary_issue(
        case_id=case.case_id,
        user_question=question,
        selection=selection,
    )
    assessed = assessor.assess(mapped)
    analysed = renderer.render(assessed)
    print(format_legal_analysis_diagnostics(analysed))
'@ | python -
```

## Acceptance review

Confirm that the diagnostic:

- separates evidence state from legal significance;
- retains M4 source assertions, adverse evidence, disputes and gaps;
- does not upgrade unresolved propositions;
- keeps documentary citations attached to factual propositions rather than legal conclusions;
- does not state that CACI had legal knowledge;
- does not state that home working was legally reasonable or that CACI breached the adjustment duty;
- does not decide a continuing act existed or that the claim is in/out of time;
- does not declare section 15 liability established;
- uses only the five M5 provisional non-merits statuses;
- does not output prospects percentages or credibility findings.

Only after those checks pass should M5 be committed/tagged.
