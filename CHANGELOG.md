# Changelog

## Sprint 2.1 – Case Management

- Added persistent SQLite-backed legal case metadata.
- Added Streamlit case creation, selection, editing, and active-case state.
- Added case-aware Chroma ingestion metadata and collision-safe chunk IDs.
- Added strict case-isolated RAG retrieval.
- Added controlled legacy-document assignment without re-embedding.
- Scoped document selection, counts, and tribunal-tool availability to the
  active case.
- Added regression tests covering case persistence, ingestion metadata,
  retrieval isolation, migration safety, and document listing.

Existing OCR, embeddings, Chroma collection, evidence rendering, and timeline
behaviour have been retained.

## Sprint 2.2 – Retrieval Quality & Evidence Reliability

### Milestone 1 – Duplicate Suppression & Retrieval Diversification

- Over-retrieve four times the requested evidence count before quality filtering.
- Remove exact duplicate chunks and conservative near-duplicates from the same
  source document.
- Return at most one evidence chunk from the same document page.
- Limit a dominant document to two results during the first selection pass,
  then relax that cap when additional independent documents are unavailable.
- Preserve existing case and selected-document Chroma filters before any
  quality processing, so Sprint 2.1 case isolation remains unchanged.
- Preserve Chroma result-field alignment and original case metadata.
- Added regression tests for duplicate suppression, source diversity,
  corroborating-document preservation, result alignment, and case-scope wiring.

### Milestone 2 – Evidence Source Classification & Evidence Status Labelling

- Added stable evidence-source metadata for claimant/witness, employer,
  independent medical, occupational-health, insurer, tribunal, party
  submissions, legal authorities, secondary summaries, mixed correspondence,
  and unclassified material.
- New indexing persists source type, human-readable label, and classification
  method in Chroma metadata.
- Existing indexes do not require re-indexing: retrieved legacy chunks receive
  conservative compatibility classification before Milestone 1 quality
  filtering.
- Stored or explicit classifications take precedence over automatic inference.
- Added explicit `--source-type` support when indexing one PDF from the CLI.
- Added evidence provenance to the Evidence panel.
- Reworked answer prompting so material propositions are separated into:
  Documented fact, Claimant evidence, Independent medical evidence, Employer
  evidence, Inference, Legal argument, or Disputed matter.
- Added safeguards preventing witness assertions, record accessibility, or
  leadership continuity from being silently upgraded into proof of employer
  knowledge.
- Preserved Sprint 2.1 case isolation and Sprint 2.2 Milestone 1 duplicate
  suppression/diversification unchanged.
- Regression suite expanded from 42 to 58 passing tests.

## Sprint 2.2 Milestone 3 - Chunk Provenance and Primary-Source Reranking

- Added chunk-level provenance so mixed/composite PDFs can distinguish the local
  author/source of individual evidence excerpts from the document/container
  classification.
- Added conservative mixed-correspondence handling for ambiguous bundles such as
  employer/insurer email chains.
- Added bounded primary-source reranking that preserves Chroma's top semantic hit
  while allowing nearby direct records to move ahead of retrospective or
  secondary sources.
- Preserved Sprint 2.2 Milestone 1 duplicate suppression/diversification and
  Milestone 2 evidence classification/reasoning unchanged.
- Added provenance-aware answer context and Evidence panel labels.
- Existing indexes remain compatible; chunk provenance is added at retrieval
  time and is persisted for newly indexed chunks.
