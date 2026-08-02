# LegalRAG Pro – Sprint 2.2 Milestone 2

## Evidence Source Classification & Evidence Status Labelling

### Objective

Give the retrieval and answer-generation layers reliable provenance metadata
before asking the LLM to make legal/evidential distinctions.

Milestone 1 remains unchanged: case-scoped Chroma retrieval still over-fetches,
deduplicates, and diversifies evidence before the final ten evidence slots are
returned.

### Source metadata

Each classified chunk can carry these Chroma metadata fields:

- `evidence_source_type`
- `evidence_source_label`
- `evidence_classification_method`

Supported source types are:

- `claimant_witness_statement`
- `respondent_witness_statement`
- `witness_statement`
- `claimant_correspondence`
- `employer_record`
- `independent_medical`
- `occupational_health`
- `insurer_record`
- `tribunal_record`
- `claimant_submission`
- `respondent_submission`
- `legal_authority`
- `secondary_summary`
- `mixed_correspondence`
- `other`

Classification is deliberately conservative. Ambiguous material is left as a
generic, mixed, or unclassified source rather than being upgraded to a stronger
provenance category.

### Existing documents

No re-indexing is required for the current case database.

For chunks indexed before Milestone 2, the retriever adds source metadata to a
copy of the Chroma result after the existing case/document filter has already
been applied. The Chroma database is not rewritten by this compatibility path.

Newly indexed PDFs persist the same source metadata at ingestion time.

Stored or explicit source metadata always takes precedence over automatic
classification.

### Evidence status in generated answers

Source provenance and proposition status are separate concepts.

The model is instructed to use one of these statuses for each material
factual/analytical proposition:

- **Documented fact**
- **Claimant evidence**
- **Independent medical evidence**
- **Employer evidence**
- **Inference**
- **Legal argument**
- **Disputed matter**

Examples of the intended discipline:

- A claimant witness statement should normally be expressed as
  **Claimant evidence: Mr Shafi states ...**, not as an established fact.
- A GP or consultant psychiatrist report may be labelled **Independent medical
  evidence**, while facts merely reported by the patient remain attributed.
- Leadership continuity, record retention, or possible access to historical
  records may support an **Inference** or **Legal argument**, but do not by
  themselves prove actual employer knowledge.
- Conflicting claimant/respondent evidence should be identified as a
  **Disputed matter**, not silently resolved by the model.

### Evidence panel

The Streamlit Evidence panel now shows the source classification and whether it
was obtained automatically, explicitly, or from stored metadata.

### Explicit classification for new PDFs

A single PDF may be indexed with an explicit source type:

```powershell
python src/index_documents.py --case-id <CASE_UUID> --pdf "docs\\document.pdf" --source-type employer_record
```

This is optional. Omitting `--source-type` uses conservative automatic
classification.

### Backwards compatibility

- Sprint 2.1 `case_id` filtering is unchanged.
- Selected-document filtering is unchanged.
- Milestone 1 over-fetch, duplicate suppression, one-result-per-page and
  diversification are unchanged.
- Existing result dictionary structure is retained; metadata gains additional
  fields only.
- Existing databases do not require migration or re-embedding.

### Regression tests

The suite now contains 58 passing tests, including coverage for:

- claimant witness-statement provenance;
- ambiguous witness statements remaining neutral;
- independent medical vs occupational-health classification;
- insurer and employer evidence classification;
- conservative handling of mixed correspondence;
- explicit/stored classification precedence;
- legacy retrieval enrichment without re-indexing;
- propagation of source metadata through case-scoped retrieval;
- all seven answer-level evidential statuses;
- prevention of witness assertions becoming documented fact;
- separation of record access from actual knowledge;
- explicit treatment of conflicting evidence;
- all existing Sprint 2.1 and Milestone 1 regression tests.

### Acceptance test

Use the same question used for the original and Milestone 1 comparison.
Milestone 2 passes when the answer:

1. retains Milestone 1 duplicate suppression and source diversity;
2. attributes claimant witness evidence as claimant evidence rather than
   presenting it as neutral fact;
3. separately identifies independent medical/employer evidence where present;
4. labels inferential conclusions as inferences;
5. does not treat leadership continuity or record availability as proof of
   actual knowledge;
6. identifies conflicts as disputed matters;
7. continues to cite document name and page for material propositions.
