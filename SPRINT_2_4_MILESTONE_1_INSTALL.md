# Sprint 2.4 Milestone 1 — Install and Acceptance

Do not commit or tag Milestone 1 until both the local regression suite and the live case foundation exercise pass.

## 1. Verify frozen starting point

```powershell
git status
git branch --show-current
git log -1 --oneline
git tag --list "sprint-2.3-milestone-5"
```

Expected starting point:

```text
feature/legal-analysis
dd17212 ... Sprint 2.3 Milestone 5 ...
sprint-2.3-milestone-5
nothing to commit, working tree clean
```

## 2. Apply the additive M1 patch

Copy the patch contents into the repository root. The patch adds only:

```text
SPRINT_2_4_MILESTONE_1_CASE_ANALYSIS_FOUNDATION.md
SPRINT_2_4_MILESTONE_1_INSTALL.md
src/case_analysis/*
tests/case_analysis_m1_helpers.py
tests/test_case_analysis_m1_*.py
```

No Sprint 2.2 or Sprint 2.3 file should change.

## 3. Run regression tests

```powershell
python -m pytest tests -q
```

The packaged baseline is 343 passing tests. A live repository with additional local frozen tests may report a higher count.

## 4. Run live Shafi v CACI foundation acceptance

From the repository root:

```powershell
$env:PYTHONPATH="$PWD\src"

@'
from case_management.repository import CaseRepository
from legal_analysis.selector import DeterministicIssueSelector
from legal_analysis.evidence_mapper import ElementEvidenceMapper
from legal_analysis.element_assessor import ElementEvidenceAssessor
from legal_analysis.legal_analysis_renderer import StructuredLegalAnalysisRenderer
from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.serialization import (
    dumps_case_analysis_foundation,
    loads_case_analysis_foundation,
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

results = []
for question in questions:
    selection = selector.select(question, case_id=case.case_id)
    mapped = mapper.map_primary_issue(
        case_id=case.case_id,
        user_question=question,
        selection=selection,
    )
    assessed = assessor.assess(mapped)
    results.append(renderer.render(assessed))

foundation = build_case_analysis_foundation(results)
payload = dumps_case_analysis_foundation(foundation)
restored = loads_case_analysis_foundation(payload)

print("CASE:", case.name)
print("CASE ID:", foundation.case_id)
print("SCHEMA:", foundation.schema_version)
print("SYNTHESISER:", foundation.synthesiser_version)
print("SYNTHESIS ID:", foundation.synthesis_id)
print("SOURCE ANALYSES:", len(foundation.source_analyses))

for source in foundation.source_analyses:
    print(
        source.issue_definition_id,
        source.issue_definition_version,
        source.issue_analysis_id,
        source.mapper_version,
        source.assessor_version,
        source.analyser_version,
    )

print("ROUND TRIP IDENTICAL:", restored == foundation)
print("JSON BYTES:", len(payload.encode("utf-8")))
'@ | python -
```

## Acceptance requirements

The exercise passes if:

- all four M5 analyses have the same case ID;
- a foundation is constructed without retrieval/synthesis changes;
- four source references are present;
- source lineage reports M3/M4/M5 versions;
- serialization round-trip is identical;
- rerunning with the same four frozen issue analyses in a different order produces the same `synthesis_id` and serialized source order;
- no source M5 object is modified.

Do not expect the same `synthesis_id` across separate live runs that regenerate fresh Sprint 2.3 `issue_analysis_id` values. Determinism is defined over the same immutable source-analysis set.

## 5. Do not freeze yet

After the regression suite and live exercise pass, inspect:

```powershell
git status
git diff --name-only
```

Only the additive Sprint 2.4 M1 files should appear. Review acceptance before committing/tagging `sprint-2.4-milestone-1`.
