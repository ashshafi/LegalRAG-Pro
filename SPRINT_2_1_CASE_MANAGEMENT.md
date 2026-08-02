# Sprint 2.1 – Case Management

## Purpose

Evolve LegalRAG Pro from a document-centric RAG application into a case-centric
legal workspace without replacing working retrieval, indexing, OCR or Streamlit
components.

## Minimal case contract

A case has:

- an internal stable `case_id` independent of tribunal/court references;
- a required human-readable name;
- an optional tribunal/court case number;
- optional claimant and respondent names;
- a lightweight status (default: `active`);
- creation and last-updated timestamps.

## Milestones

1. **Case model and persistence** – domain model, SQLite repository and tests.
2. **Case selection UI** – create/select/edit an active case in Streamlit.
3. **Case-aware ingestion** – attach `case_id` metadata to newly indexed chunks.
4. **Case-isolated retrieval** – restrict document lists and RAG retrieval to the active case.
5. **Legacy migration** – assign existing unscoped Chroma documents to a case safely.
6. **Case-aware tribunal tools** – scope timeline/evidence/people/compare/report tools to the active case.

## Backward-compatibility rule

No milestone may make existing unscoped Chroma documents unreachable until a
migration path exists. Milestone 1 therefore makes no changes to Chroma,
retrieval, indexing or current UI behaviour.

## Milestone 2 – Case Selection UI

Milestone 2 introduces case management into the Streamlit interface without
changing document indexing or retrieval behaviour.

Implemented behaviour:

- list persisted cases in the sidebar;
- create a case from the sidebar;
- select one active case;
- preserve the active case in Streamlit session state;
- edit the active case's metadata and status;
- display the active case in the main application;
- leave existing document selection, Chroma retrieval, RAG, timeline and OCR
  behaviour unchanged.

Case-aware document ownership and retrieval isolation are explicitly deferred to
later milestones.

## Milestone 3 – Case-Aware Document Ingestion

Milestone 3 extends the existing PDF indexing path without changing retrieval.

Implemented behaviour:

- `index_pdf()` accepts an optional stable internal `case_id`;
- case-aware chunks store `case_id` alongside the existing `file`, `page`, and
  `chunk` metadata;
- case-aware Chroma IDs include the case ID so identically named PDFs in
  different cases cannot collide;
- legacy indexing remains available when no case ID is supplied and preserves
  the historic metadata and ID formats;
- the command-line indexer accepts `--case-id` and optional `--pdf`;
- strict case-filtered retrieval is deferred to Milestone 4.

Examples:

```powershell
python src/index_documents.py --case-id "<internal-case-uuid>"
python src/index_documents.py --case-id "<internal-case-uuid>" --pdf docs/ET1.pdf
```

Existing Chroma records are not migrated or deleted by this milestone.

## Milestone 4 – Case-Isolated Retrieval

Milestone 4 scopes RAG retrieval to the active legal case.

Implemented behaviour:

- the active internal `case_id` is passed from Streamlit into the chat service
  and retriever;
- Chroma vector queries are strictly filtered by `case_id` whenever a case is
  active;
- filename selections are combined with the case constraint using `$and`;
- switching cases clears the previous case's displayed answer and timeline so
  stale evidence is not shown under a different case;
- `document_manager.get_documents(case_id)` can return case-specific indexed
  filenames;
- callers that do not provide a case ID retain the historic global/legacy
  retrieval path.

### Legacy compatibility

Existing Chroma chunks created before Milestone 3 do not contain `case_id`.
They remain available to legacy/global callers but are deliberately excluded
from strict active-case searches. They are not silently assigned to a case.
A controlled migration/assignment workflow is required before those historic
chunks appear in case-isolated RAG results.

## Milestone 5 – Legacy Document Assignment & Migration

Milestone 5 provides a controlled path for pre-case-management Chroma chunks.

Implemented behaviour:

- identify filenames containing chunks without `case_id`;
- preview exactly how many legacy chunks will be assigned;
- require an explicit UI confirmation before assignment;
- update metadata only, retaining the existing document text and embeddings;
- never move chunks that already belong to another case;
- expose the workflow under the active case in the Streamlit sidebar;
- make successfully assigned legacy chunks immediately eligible for the
  case-isolated retrieval introduced in Milestone 4.

This migration is intentionally document-by-document. Bulk automatic assignment
is avoided because filename presence alone is not sufficient evidence that a
document belongs to a particular legal case.

## Milestone 6 – Case Management Integration & Polish

Milestone 6 completes Sprint 2.1.

Implemented behaviour:

- the Documents sidebar now lists Chroma-indexed documents belonging to the
  active case rather than every PDF present in the filesystem;
- document selection keys are case-specific, preventing Streamlit checkbox
  state from leaking between cases;
- document counts refer to the active case;
- Tribunal Tool controls are disabled when an active case has no indexed
  evidence;
- the chat prevents a case-specific query when no case documents are selected;
- active-case name, case number, and status are displayed consistently;
- empty-case and no-document states provide actionable guidance;
- legacy/global behaviour remains available when no case is active.

## Sprint 2.1 completion criteria

Sprint 2.1 is complete when:

1. cases can be created, selected, edited, and persisted;
2. new indexed chunks can carry a stable case ID;
3. active-case RAG retrieval cannot return chunks from another case;
4. historic chunks can be deliberately assigned without re-embedding;
5. the document UI and status information are scoped to the active case;
6. automated regression tests pass.

All six criteria are implemented by Milestones 1–6.
