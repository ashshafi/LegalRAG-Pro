# Sprint 2.3 Milestone 4 — Acceptance Hardening

This narrow patch addresses three defects exposed by the first live M4 acceptance run.

1. **Established proposition specificity** — a high-confidence direct source no longer causes a raw chunk excerpt to be promoted into `PRESENTLY ESTABLISHED`. Establishment now additionally requires a deterministic, element-specific factual signal. Otherwise the proposition remains supported/unresolved.
2. **Conflict specificity** — `CONFLICTING` now requires explicit incompatible positions on the same identifiable factual proposition. Party labels, different context, silence, or loose token overlap are insufficient.
3. **Gap specificity** — gap generation now inspects mapped source presence. Where an ET3/respondent pleading or ACAS/procedural source is already present but the required fact is absent from the mapped excerpt, the gap identifies the missing fact rather than claiming the source category is missing.

No Sprint 2.2 or Sprint 2.3 M1–M3 module is modified. No retrieval, search profile, evidence mapping, provenance, or issue selection behavior is changed.
