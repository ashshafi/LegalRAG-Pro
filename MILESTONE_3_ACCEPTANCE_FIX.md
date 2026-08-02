# Sprint 2.2 Milestone 3 — Acceptance Fix

This narrow patch addresses the two issues identified in the Milestone 3 acceptance test.

## Changes

1. Evidence-panel provenance is now included in the always-visible Streamlit expander heading.
   - Matching provenance: `Document — Page N | Employer evidence`
   - Mixed container: `Document — Page N | Employer evidence | container: Insurer evidence`

2. The provenance-aware answer prompt now prohibits strong knowledge/awareness wording unless the cited excerpt expressly records receipt, communication, acknowledgement, discussion, or awareness by the relevant CACI personnel.

## Preserved behaviour

No changes were made to:
- Milestone 1 retrieval quality / deduplication / diversification
- Milestone 2 evidence classification or reasoning module
- Milestone 3 chunk provenance classifier
- Milestone 3 primary-source reranker
- case-scoped retrieval

## Verification

The isolated packaged test suite passes 82 tests after this patch (78 previous + 4 new/extended tests). The user's live repository contains additional tests, so the local live result is authoritative.
