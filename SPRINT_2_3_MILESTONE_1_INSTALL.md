# Sprint 2.3 Milestone 1 — Patch Installation

Apply this patch only to the `feature/legal-analysis` branch created from the frozen `sprint-2.2-milestone-4` checkpoint.

The patch is additive. It contains only:

- the new `src/legal_analysis/` package;
- new Sprint 2.3 Milestone 1 tests;
- Milestone 1 documentation.

It does not contain or replace `db`, `docs`, `.env`, `.venv`, retrieval modules, chat/UI modules, or Sprint 2.2 evidence modules.

After extracting the patch into the project root, run:

```powershell
python -m pytest -q
```

If legacy root-level smoke scripts are configured separately in your environment, the maintained regression suite can also be targeted explicitly with:

```powershell
python -m pytest -q tests
```

Do not commit/tag Milestone 1 until the live regression suite is green and the controlled definitions/serialization have been inspected.
