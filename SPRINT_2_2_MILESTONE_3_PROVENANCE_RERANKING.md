# Sprint 2.2 Milestone 3 - Chunk-Level Provenance and Primary-Source Reranking

## Objective

Improve evidence retrieval where a single PDF contains material from several
sources, and give nearby primary/direct records a controlled preference over
retrospective or secondary material without weakening semantic relevance.

## Frozen Baseline

Milestone 3 is designed to sit on top of the frozen Sprint 2.2 Milestone 2
checkpoint (`sprint-2.2-milestone-2`). It does not modify the implementation of:

- Milestone 1 duplicate suppression and document/page diversification;
- Milestone 2 document-level evidence classification; or
- Milestone 2 evidential-status prompt discipline.

## New Retrieval Pipeline

1. Apply case/document Chroma filter.
2. Over-retrieve candidates (Milestone 1).
3. Add Milestone 2 document classification.
4. Add chunk-level provenance.
5. Apply bounded primary-source reranking.
6. Apply the unchanged Milestone 1 duplicate/diversification filter.
7. Supply provenance-aware evidence context to the answer model.

## Chunk-Level Provenance

A retrieved chunk now carries both:

- **Document classification** - provenance of the PDF/container; and
- **Chunk provenance** - provenance of the local excerpt.

This avoids treating every page of a mixed appendix as insurer evidence merely
because the filename mentions Unum. A clear HR sender can classify an individual
chunk as Employer evidence while the containing PDF remains document-classified
as Insurer evidence or Mixed/composite evidence.

Where local authorship cannot be determined safely, mixed correspondence is
labelled **Mixed / composite evidence** rather than guessed.

## Primary-Source Preference

Each chunk receives a bounded source tier. Direct employer, medical,
occupational-health, insurer and tribunal records receive the strongest
retrieval preference; direct party correspondence receives a smaller
preference; witness statements/submissions and secondary summaries receive no
promotion.

The reranker:

- never displaces Chroma's number-one semantic result;
- limits promotion to a few rank positions;
- keeps vector relevance as the dominant signal; and
- does not treat retrieval priority as proof or legal weight.

## Answer-Layer Safeguards

The model is told that chunk provenance overrides container classification only
for attribution of that excerpt. Primary-source status/reranking must never be
presented as proof.

Party-authored correspondence should retain provenance when its documented
content is described, e.g. `Claimant evidence: In his letter, the claimant
requested...`, rather than using a bare `Documented fact` label that obscures
who authored the material.

## Backwards Compatibility

No re-indexing is required. Existing Chroma chunks receive chunk provenance at
retrieval time. Newly indexed chunks persist the new metadata.

No new Python dependency is introduced.

## Acceptance Test

Run the exact same CACI-knowledge question used for the original, Milestone 1
and Milestone 2 comparisons.

Milestone 3 passes if:

- Milestone 1 duplicate suppression remains intact;
- Milestone 2 evidence-status discipline remains intact;
- H4/H5 excerpts are attributed at chunk level where the local author/source is
  identifiable;
- ambiguous mixed excerpts are not incorrectly called insurer evidence;
- relevant contemporaneous/direct records appear earlier/more often without
  displacing clearly stronger semantic evidence;
- case isolation remains intact; and
- the answer does not equate primary-source preference with proof.
