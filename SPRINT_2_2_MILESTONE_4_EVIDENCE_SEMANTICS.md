# Sprint 2.2 Milestone 4 - Evidence Semantics & Assertion Safety

## Objective

Improve LegalRAG Pro's distinction between source identity, what a source
asserts, and what the evidence substantively establishes, without modifying the
frozen retrieval/reranking pipeline from Milestones 1-3.

## Governing principle

**Source identity != source assertion != substantive truth.**

## Scope

1. Add post-retrieval provenance basis and confidence metadata.
2. Prevent weak container/content classification from being presented as
   reliable authorship.
3. Add `Source assertion` as an explicit evidential-status category.
4. Apply special safeguards to knowledge/awareness propositions.
5. Surface semantic provenance, basis, confidence, and cautions in the Evidence
   panel.
6. Add targeted regression tests for Appendix L5, H4/H5/H6, Appendix J, and
   claimant-authored July 2026 correspondence.

## Out of scope

Milestone 4 must not change:

- vector retrieval or query expansion;
- case or selected-document filters;
- over-retrieval;
- duplicate suppression;
- evidence diversification;
- primary-source tiers or reranking coefficients;
- Milestone 3 chunk-provenance classification used during reranking.

The semantic layer is applied only after the final evidence set has been
returned by `retrieve()`.

## Provenance basis

- `manual`
- `explicit_sender`
- `signature`
- `known_document_author`
- `container_fallback`
- `mixed`
- `unknown`

## Provenance confidence

- `high` - explicit/manual authorship, sender, signature, or reliable known
  document authorship.
- `medium` - mixed source or filename-supported container provenance.
- `low` - weak inherited container provenance or unknown authorship.

## Source assertion

Use `Source assertion` when a source states that a material proposition is true
but the supplied evidence does not independently establish it. The answer must
attribute the assertion and must not silently convert it into substantive fact.

Example:

> Source assertion: Appendix H5 states that CACI was aware of the proposed
> adjustments.

This establishes that the assertion was made, not that CACI's awareness has
been independently proved.

## Knowledge/awareness guard

Words such as `knew`, `aware`, `fully aware`, `knowledge`, `notice`,
`understood`, `accepted`, and `recognised` are guarded propositions.

Direct receipt, acknowledgement, discussion, or communication in a direct
record may support a documented knowledge proposition. Otherwise LegalRAG must
use `Source assertion`, `Inference`, or `Disputed matter` as appropriate.

## Frozen acceptance queries

1. `What evidence shows that CACI knew about my disability and my attempts to return to work, and what happened after the 2005 relapse?`
2. `What evidence establishes what CACI actually knew about my disability, proposed adjustments and return-to-work recommendations, and distinguish direct evidence of knowledge from assertions and inference?`

Milestone 4 passes only when both the regression suite and these end-to-end
outputs preserve the distinction between source identity, assertion and truth.
