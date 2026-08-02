# Sprint 2.2 Milestone 4 - Patch Installation

Apply the Milestone 4 code patch over the frozen Sprint 2.2 Milestone 3 working
tree. Do not replace `docs`, `db`, `.env`, `.venv`, or Git metadata.

Then run:

```powershell
python -m pytest -q
```

Restart LegalRAG Pro and run the two frozen Milestone 4 acceptance queries.
Do not commit/tag the milestone until both end-to-end outputs are reviewed.

No re-indexing is required. The semantic layer runs after retrieval and does
not alter the Milestone 3 ranking order.
