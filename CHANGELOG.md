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
