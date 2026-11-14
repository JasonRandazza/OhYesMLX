# Order: Standards review of Phase 5 wave 1 (read-only)

Diff: `.paul/review/2026-11-14-phase5-w1/diff.patch` (git diff 99d2a55...HEAD; commits 93d374c 05-01 Python "Stop now", 004171c 05-02 Swift app skeleton). Read it in ranges; it is ~5,500 lines.
Standards sources: `AGENTS.md` (esp. "One definition of everything", "Each rationale is written once", Style, "No new dependency"), `docs/threat-model.md` §10 rows P5-1..P5-12 (grep "## 10."), and this baseline:
Smell baseline (judgement calls, repo standards override): Mysterious Name; Duplicated Code; Feature Envy; Data Clumps; Primitive Obsession; Repeated Switches; Shotgun Surgery; Divergent Change; Speculative Generality; Message Chains; Middle Man; Refused Bequest.

Report — per file/hunk — (a) every place the diff violates a documented standard: cite file + rule; (b) any baseline smell: name it, quote the hunk. Mark each HARD (documented breach) or JUDGEMENT. Skip what tooling enforces. Give file:line for each. Under 500 words. You cannot run a shell; do not try.
