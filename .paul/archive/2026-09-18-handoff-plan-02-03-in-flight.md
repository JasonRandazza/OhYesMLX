---
description: "OhYesMLX — session handoff, 2026-09-18 (Phase 2 Track 2 Accuracy Scoring: Plan 02-03 MoE Campaign In Flight)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-18 (v2 Phase 2 Track 2 Accuracy Scoring: Plan 02-03 MoE Campaign In Flight)

> **This file is short by design and is rewritten each session, never appended to.** It holds
> *state*: where things stand now and what is next. Durable rules live in `AGENTS.md`;
> decisions live in `.paul/STATE.md`; findings live in `docs/research/`. Previous handoffs are
> in `.paul/archive/` and are not required reading.

Read this, then `.paul/STATE.md`, then `AGENTS.md`.

---

## Where the project is

- **v1 is 100% closed and published.**
- **v2 Milestone active (0.2.0):** JANG Study and Accuracy Scoring.
- **v2 Phase 1 (Track 1: The JANG Study) is 100% COMPLETE & PUBLISHED.**
- **v2 Phase 2 (Track 2: Accuracy Scoring) Plan 02-01 & 02-02 COMPLETE & PUBLISHED:**
  - Dense Accuracy Study published: [`docs/research/2026-09-18-accuracy-dense.md`](file:///Users/jrazz/Dev/active/OhYesMLX/docs/research/2026-09-18-accuracy-dense.md).
- **v2 Phase 2 (Track 2: Accuracy Scoring) Plan 02-03 IS CURRENTLY IN FLIGHT:**
  - Launched: 2026-09-18 at 17:27:12 local.
  - Runner log: [`results/accuracy-moe/runner.log`](file:///Users/jrazz/Dev/active/OhYesMLX/results/accuracy-moe/runner.log).
  - Target matrix: 8 cells total (Column A: 5 cells on vMLX; Replicate: 2 cells on vMLX; Study 2C: 1 cell on Osaurus).
  - Configuration: Pre-registered budget dial activated (MMLU 20 items/subject = 1,140 items; GSM8K 250; IFEval 250); `--no-disable-thinking` pinned due to vMLX `supports_instruct_mode=False` for LFM2.
  - Projected runtime: ~18.5 hours total.
- **Machine State:** Quiet. **DO NOT run tests, downloads, or git operations while measurements are in flight.**

---

## What is next (Upon Campaign Completion)

1. Verify all 8 cells in [`results/accuracy-moe/`](file:///Users/jrazz/Dev/active/OhYesMLX/results/accuracy-moe) report `status: PASS` and release ports.
2. Run statistical analysis via `python scripts/analyze_accuracy_moe.py`.
3. Dispatch Command Code worker (`cc-agent`) to author `docs/research/2026-09-18-accuracy-moe.md` reporting:
   - Q1 answer: JANG_2L (2.37 bits avg) vs stock 4-bit on MMLU.
   - P3 collapse check: GSM8K and IFEval reasoning retention.
   - Q3 answer: OptiQ Pareto status on MoE.
   - Replicate stability (within-runtime determinism).
   - Study 2C: Cross-runtime agreement on JANG_2L (`vmlx` vs `osaurus`).
4. Update `.paul/STATE.md` and close Plan 02-03.
5. Proceed to Plan 02-04 (Accuracy vs Throughput Pareto Tradeoff Synthesis — 0 measurement hours).

---

## Standing Invariants

- **Quiet Machine:** Nothing else runs while a cell is measured.
- **Vary one thing at a time:** The defining rule of the project.
- **Zero repository dependencies:** Runs exclusively via isolated `uv`.
- **Osaurus Host Settings:** Byte-exact restoration verified with `cmp` after Osaurus execution.
