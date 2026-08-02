# Sprint 2.3 Milestone 5 — Evidence-Key Traceability Acceptance Fix

## Scope

This is a narrow M5-only acceptance fix. It does not modify Sprint 2.2 or Sprint 2.3 M1–M4.

The real-case M5 acceptance run exposed that one frozen M3 `EvidenceMapping.evidence_key` may legitimately recur across legal elements with `EvidenceReference` objects that differ in non-identity descriptive/runtime fields while still referring to the same underlying chunk.

## Corrected invariant

M5 now canonicalises duplicate evidence keys when their stable evidence identity is compatible:

- `chunk_id`
- `document_name`
- `page`
- `citation`
- `document_id` when both occurrences provide one

M5 no longer requires full `EvidenceReference` equality.

M5 still fails closed where one evidence key resolves to incompatible stable source identity, including a different document, page, citation, chunk ID, or conflicting non-empty document IDs.

The first compatible occurrence becomes the canonical traceability record used only for evidence-key-to-citation/source resolution. Frozen M3 mappings remain unchanged.

## Regression coverage

The fix adds tests for:

1. Same key + compatible identity + different non-identity fields.
2. Same key + incompatible document/page identity raises.
3. One chunk reused across multiple elements renders successfully.
4. Citation traceability remains stable after canonicalisation.
5. Frozen M4 input remains unchanged.

## Non-goals

No changes to:

- M1–M4 models or logic
- `EvidenceMapping.evidence_key`
- retrieval
- case isolation
- provenance
- evidence semantics
- element mapping
- M4 assessment
- M5 legal-significance profiles or provisional-status rules
