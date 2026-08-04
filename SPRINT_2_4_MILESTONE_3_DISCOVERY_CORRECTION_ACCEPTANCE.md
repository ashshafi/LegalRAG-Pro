# Sprint 2.4 Milestone 3 — Calibrated Discovery Correction Live Acceptance

Do not commit or tag M3 before this procedure is reviewed.

## 1. Verify the fixture is unchanged

From the repository root in PowerShell:

```powershell
Get-FileHash .\tests\fixtures\shafi_chronology_live_v1_0.json -Algorithm SHA256
```

Required SHA-256:

```text
833124866a8afec8d071d94c6c973890cf45a4a8c26c9451706d51cc3c18965c
```

Do not recapture or edit the fixture before this acceptance run.

## 2. Run regression

```powershell
python -m pytest tests -q
```

All tests must pass.

## 3. Run the corrected four-issue Shafi chronology

```powershell
$env:PYTHONPATH="$PWD\src;$PWD\tests"

@'
import copy
import hashlib
from pathlib import Path

from case_management.repository import CaseRepository
from legal_analysis.selector import DeterministicIssueSelector
from legal_analysis.evidence_mapper import ElementEvidenceMapper
from legal_analysis.element_assessor import ElementEvidenceAssessor
from legal_analysis.legal_analysis_renderer import StructuredLegalAnalysisRenderer

from case_analysis.foundation import build_case_analysis_foundation
from case_analysis.m2.matrices import build_case_matrices
from case_analysis.m3.chronology import build_case_chronology, format_chronology_diagnostics
from case_analysis.m3.chronology_serialization import dumps_case_chronology, loads_case_chronology
from case_analysis.m3.event_extraction import CHRONOLOGY_EXTRACTION_POLICY_VERSION
from case_analysis.m3.models import (
    CASE_CHRONOLOGY_BUILDER_VERSION,
    CHRONOLOGY_PROFILE_VERSION,
    EventStatus,
    TimingStatus,
)

EXPECTED_FIXTURE_SHA = "833124866a8afec8d071d94c6c973890cf45a4a8c26c9451706d51cc3c18965c"
fixture_path = Path("tests/fixtures/shafi_chronology_live_v1_0.json")
fixture_before = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
assert fixture_before == EXPECTED_FIXTURE_SHA, (fixture_before, EXPECTED_FIXTURE_SHA)

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
chronology_reversed = build_case_chronology(foundation, matrices, tuple(reversed(results)))
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
            assert not assertion.description.casefold().startswith("the source records an assertion")
        if assertion.temporal_extent is None:
            assert assertion.timing_status is TimingStatus.UNKNOWN

fixture_after = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
assert fixture_after == fixture_before == EXPECTED_FIXTURE_SHA

print("CASE:", case.name)
print("CASE ID:", chronology.case_id)
print("FOUNDATION SYNTHESIS ID:", chronology.synthesis_id)
print("CHRONOLOGY SCHEMA:", chronology.schema_version)
print("CHRONOLOGY BUILDER:", CASE_CHRONOLOGY_BUILDER_VERSION)
print("PROFILE VERSION:", CHRONOLOGY_PROFILE_VERSION)
print("EXTRACTION POLICY:", CHRONOLOGY_EXTRACTION_POLICY_VERSION)
print("LIVE FIXTURE SHA256:", fixture_after)
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

## 4. Required automated gates

```text
ORDER INDEPENDENT: True
ROUND TRIP IDENTICAL: True
SOURCE M5 INPUT UNCHANGED: True
FOUNDATION UNCHANGED: True
MATRICES UNCHANGED: True
LIVE FIXTURE SHA256: 833124866a8afec8d071d94c6c973890cf45a4a8c26c9451706d51cc3c18965c
```

## 5. Required manual chronology review

Where supported by the unchanged fixture, confirm:

- 11 May 2005 RTW remains present;
- 14 June 2005 H4/VF work communication is present and uses only actual DA/EK/RA M2 links;
- 1 July 2005 relapse is present and remains source-qualified/supported, not established;
- August 2025 payslip request is present through the existing `EK-UNRESOLVED` relationship only;
- 4 September 2025 payroll material is present only if exceptional projection qualifies through its exact frozen use;
- 6 September 2025 payroll response is present; event content may be supported while timing is established;
- 10 September 2025 ACAS remains present and factual;
- 24 July 2026 does not appear as an Alison Brooks automatic-reply-derived substantive event;
- 28 June remains conditional on actual canonical source evidence, not a cross-reference alone;
- 17 July 2026 remains absent unless safely available upstream;
- no LIM relationship is invented for H4 or Appendix D p.1;
- 4 and 6 September are not silently reconciled;
- no headings, disclaimers, automatic replies, legal argument, long document lists, or clipped `update the` fragments are reintroduced.

## 6. Working-tree gate

Run:

```powershell
git status
git diff -- src/case_analysis/m3/event_extraction.py
git diff -- tests/test_case_analysis_m3_discovery_correction.py
```

Do not commit and do not create `sprint-2.4-milestone-3` until the complete live output has been reviewed and marked PASS.
