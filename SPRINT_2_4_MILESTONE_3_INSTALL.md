# Sprint 2.4 Milestone 3 — Install and Live Acceptance

## 1. Verify the frozen starting checkpoint

From the repository root:

```powershell
git status
git branch --show-current
git log -1 --oneline
git tag --list "sprint-2.4-milestone-2"
```

Required baseline:

```text
feature/legal-analysis
4e906b3 ... Sprint 2.4 Milestone 2 ...
sprint-2.4-milestone-2
nothing to commit, working tree clean
```

## 2. Apply the additive code patch

Extract the Milestone 3 Code Patch into the repository root, preserving paths.

Do not commit or tag yet.

## 3. Run the maintained regression suite

```powershell
python -m pytest tests -q
```

## 4. Run the live four-issue Shafi v CACI chronology acceptance

```powershell
$env:PYTHONPATH="$PWD\src"

@'
import copy

from case_management.repository import CaseRepository

from legal_analysis.selector import DeterministicIssueSelector
from legal_analysis.evidence_mapper import ElementEvidenceMapper
from legal_analysis.element_assessor import ElementEvidenceAssessor
from legal_analysis.legal_analysis_renderer import StructuredLegalAnalysisRenderer

from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.m2.matrices import build_case_matrices
from case_analysis.m3.chronology import (
    build_case_chronology,
    format_chronology_diagnostics,
)
from case_analysis.m3.chronology_serialization import (
    dumps_case_chronology,
    loads_case_chronology,
)
from case_analysis.m3.models import (
    CHRONOLOGY_PROFILE_VERSION,
    EventStatus,
    TimingStatus,
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

results = tuple(results)
results_before = copy.deepcopy(results)

foundation = build_case_analysis_foundation(results)
foundation_before = copy.deepcopy(foundation)

matrices = build_case_matrices(foundation, results)
matrices_before = copy.deepcopy(matrices)

chronology = build_case_chronology(foundation, matrices, results)
chronology_reversed = build_case_chronology(
    foundation,
    matrices,
    tuple(reversed(results)),
)

payload = dumps_case_chronology(chronology)
restored = loads_case_chronology(payload)

assert chronology == chronology_reversed
assert restored == chronology
assert results == results_before
assert foundation == foundation_before
assert matrices == matrices_before

m2_keys = {item.evidence_key for item in matrices.evidence_matrix}
m2_use_identities = {
    use.identity
    for record in matrices.evidence_matrix
    for use in record.uses
}

for event in chronology.events:
    assert set(event.evidence_keys) <= m2_keys
    for assertion in event.assertions:
        assert assertion.profile_version == CHRONOLOGY_PROFILE_VERSION
        assert (
            assertion.issue_analysis_id,
            assertion.element_id,
            assertion.evidence_key,
        ) in m2_use_identities
        if assertion.event_status is EventStatus.ESTABLISHED:
            assert not assertion.description.casefold().startswith(
                "the source records an assertion"
            )
        if assertion.temporal_extent is None:
            assert assertion.timing_status is TimingStatus.UNKNOWN

print("CASE:", case.name)
print("CASE ID:", chronology.case_id)
print("FOUNDATION SYNTHESIS ID:", chronology.synthesis_id)
print("CHRONOLOGY SCHEMA:", chronology.schema_version)
print("CHRONOLOGY BUILDER:", chronology.chronology_builder_version)
print("PROFILE VERSION:", CHRONOLOGY_PROFILE_VERSION)
print("EVENTS:", len(chronology.events))
print("ASSERTIONS:", sum(len(item.assertions) for item in chronology.events))
print("DATED EVENTS:", sum(item.canonical_temporal_extent is not None for item in chronology.events))
print("UNKNOWN-DATE EVENTS:", sum(item.timing_status is TimingStatus.UNKNOWN for item in chronology.events))
print("DISPUTED-TIMING EVENTS:", sum(item.timing_status is TimingStatus.DISPUTED for item in chronology.events))
print("MULTI-ISSUE EVENTS:", sum(len(item.related_issue_definition_ids) > 1 for item in chronology.events))
print("MULTI-EVIDENCE EVENTS:", sum(len(item.evidence_keys) > 1 for item in chronology.events))
print("ORDER INDEPENDENT:", chronology == chronology_reversed)
print("ROUND TRIP IDENTICAL:", restored == chronology)
print("SOURCE M5 INPUT UNCHANGED:", results == results_before)
print("FOUNDATION UNCHANGED:", foundation == foundation_before)
print("MATRICES UNCHANGED:", matrices == matrices_before)
print("JSON BYTES:", len(payload.encode("utf-8")))
print()
print(format_chronology_diagnostics(chronology))
'@ | python -
```

## 5. Acceptance review

Confirm:

```text
ORDER INDEPENDENT: True
ROUND TRIP IDENTICAL: True
SOURCE M5 INPUT UNCHANGED: True
FOUNDATION UNCHANGED: True
MATRICES UNCHANGED: True
EVENTS: > 0
```

Then manually inspect representative entries and verify:

1. A later witness statement or pleading does not replace a historical event date with the document date.
2. Claimant/source assertions are not rendered as established events.
3. Exact, month and year precision are displayed without invented components.
4. Conflicting dates remain disputed rather than selecting one.
5. Shared events retain all canonical M2 evidence and issue/element links.
6. Chronology language is factual and does not decide reasonableness, continuing act, limitation or section 15 liability.
7. No date exists merely because a legal authority, case number or unrelated metadata contains a year.

A sparse chronology is acceptable if the frozen M4 propositions do not safely anchor additional events. Do not expand the extraction policy during acceptance merely to increase event count.

## 6. Verify additive working tree

```powershell
git status
```

Only the new `src/case_analysis/m3/`, M3 tests, and the two M3 documents should be untracked.

Do not commit or create `sprint-2.4-milestone-3` until the live output has been reviewed and marked PASS.
