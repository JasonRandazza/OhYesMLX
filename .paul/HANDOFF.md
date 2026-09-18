---
description: "OhYesMLX — session handoff, 2026-09-18 (Phase 2 Track 2 Accuracy Scoring: Plan 02-02 In Flight)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-18 (v2 Phase 2 Track 2 Accuracy Scoring: Plan 02-02 In Flight)

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
- **v2 Phase 2 (Track 2: Accuracy Scoring) Plan 02-01 is 100% COMPLETE & PUBLISHED.**
- **Plan 02-02 (Dense Accuracy Study: `Qwen3.5-4B`) is LAUNCHED & EXECUTING in background:**
  - Command: `caffeinate -dimsu sh scripts/run_accuracy_dense.sh all`
  - Runner log: `results/accuracy-dense/runner.log`
  - Decision 103 applied: ARC-Challenge dropped due to upstream extraction mismatch; evaluating across the 3 validated tasks (MMLU 5-shot multiturn, GSM8K 5-shot multiturn, IFEval 0-shot; 2,780 items/cell).
  - Scope: Column A (vMLX: 4 cells), Column B (Osaurus: 4 cells), Replicate (3 cells, MMLU only). Total: 11 cell runs.
- **Tests:** 495 tests pass (`pytest -q`).
- **Working Tree:** Clean on `main`.

---

## Next Steps When Run Completes

1. Verify run completion in `results/accuracy-dense/runner.log` and confirm all 11 cell manifests show `"status": "PASS"`.
2. Confirm host Osaurus settings were restored byte-exact (`cmp -s`).
3. Run analysis script:
   `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python scripts/analyze_accuracy_dense.py --results-dir results/accuracy-dense`
4. Evaluate paired difference intervals, Q2 (`JANG_4S` vs `stock4bit`), Q3/Q4, and Study 2C cross-runtime agreement rate.
5. Author and publish `docs/research/2026-09-18-accuracy-dense.md`.
6. Update Deep Wiki and `.paul/STATE.md`.

---

## Standing Invariants

- **Vary one thing at a time:** The defining rule of the project.
- **Zero repository dependencies:** Run `lm-eval` exclusively via isolated `uv run --isolated --with lm-eval`.
- **Osaurus KV Cache Guarantee:** Restore host config byte-exact upon completion (`cmp` verified).
- **Process Safety:** Never sweep using bare name `osaurus`. Sweep by full executable path `^/Applications/osaurus.app/Contents/MacOS/osaurus`.
- **Thermal & Contention:** Exactly one model resident in memory at a time. No local GPU models or repo modifications while measuring.
