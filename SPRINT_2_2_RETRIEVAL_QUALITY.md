# LegalRAG Pro – Sprint 2.2 Retrieval Quality & Evidence Reliability

## Milestone 1: Duplicate Suppression & Retrieval Diversification

### Objective

Improve the evidence set supplied to the answer-generation model without
changing Sprint 2.1 case isolation, document ingestion, embeddings, OCR, or the
Streamlit case-management workflow.

### Retrieval flow

1. Expand the user's question as before.
2. Create the query embedding as before.
3. Build the existing case/document Chroma `where` filter.
4. Ask Chroma for four times the requested final result count.
5. Remove exact duplicate text.
6. Conservatively remove near-duplicate chunks only within the same source
   document, preserving similar wording from independent documents as possible
   corroboration.
7. Allow only one final chunk per document/page.
8. On the first pass, allow at most two results from one document so other
   relevant sources can surface.
9. If fewer results are available, relax the per-document cap while retaining
   the one-result-per-page safeguard.
10. Return at most the originally requested result count in Chroma-compatible
    response shape.

### Backwards compatibility

- Case scoping is applied by Chroma before quality filtering.
- Selected-document filtering is unchanged.
- No database migration is required.
- No re-indexing is required.
- Existing callers continue receiving the same result dictionary structure.
- The answer-generation and Evidence-panel interfaces are unchanged.

### Tests

Regression coverage includes:

- exact duplicate suppression;
- near-duplicate suppression within one document;
- preservation of similar evidence from different documents;
- one-result-per-document-page behaviour;
- diversification away from a dominant document;
- fallback when only one document is available;
- preservation of `case_id` metadata;
- Chroma result-field alignment;
- verification that the case filter is sent to Chroma before quality filtering.
