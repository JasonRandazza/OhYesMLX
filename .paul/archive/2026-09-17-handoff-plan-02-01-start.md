---
description: "OhYesMLX — session handoff, 2026-09-17 (Phase 2 Track 2 Accuracy Scoring Active: Plan 02-01)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-17 (v2 Phase 2 Track 2 Accuracy Scoring Active: Plan 02-01)

> **This file is short by design and is rewritten each session, never appended to.** It holds
> *state*: where things stand now and what is next. Durable rules live in `AGENTS.md`;
> decisions live in `.paul/STATE.md`; findings live in `docs/research/`. Previous handoffs are
> in `.paul/archive/` and are not required reading.

Read this, then `.paul/STATE.md`, then `AGENTS.md`.

---

## Where the project is

- **v1 is 100% closed and published.**
- **v2 Milestone active (0.2.0):** JANG Study and Accuracy Scoring.
- **v2 Phase 1 (Track 1: The JANG Study) is 100% COMPLETE & PUBLISHED across all three plans:**
  1. **Plan 01-01 (Dense JANG Study: Qwen3.5-4B):** [`docs/research/2026-09-17-dense-jang-study.md`](file:///Users/jrazz/Dev/active/OhYesMLX/docs/research/2026-09-17-dense-jang-study.md)
  2. **Plan 01-02 (MoE JANG Study: LFM2.5-8B-A1B):** [`docs/research/2026-09-17-moe-jang-study.md`](file:///Users/jrazz/Dev/active/OhYesMLX/docs/research/2026-09-17-moe-jang-study.md)
  3. **Plan 01-03 (Cross-Runtime JANG Synthesis):** [`docs/research/2026-09-17-jang-cross-runtime.md`](file:///Users/jrazz/Dev/active/OhYesMLX/docs/research/2026-09-17-jang-cross-runtime.md)
- **v2 Phase 2 (Track 2: Accuracy Scoring) is IN PROGRESS:**
  - **Study Design Document authored & published:** [`docs/research/2026-09-17-v2-track2-accuracy-study-design.md`](file:///Users/jrazz/Dev/active/OhYesMLX/docs/research/2026-09-17-v2-track2-accuracy-study-design.md) (1,313 lines).
  - Decision 101 recorded in `.paul/STATE.md`.
  - Phase 2 plans defined:
    * **02-01: Harness Spike & Local Endpoint Validation** (*Active*)
    * **02-02: Dense Accuracy Study (`Qwen3.5-4B`)**
    * **02-03: MoE Accuracy Study (`LFM2.5-8B-A1B`)**
    * **02-04: Accuracy vs Throughput Pareto Tradeoff Synthesis**
- **Tests:** 495 tests pass (`/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`).
- **Ports & Processes:** All ports (1337, 8080, 8081, 8100, 8000) are free. No background runtimes active.
- **Osaurus State:** Jason's host Osaurus settings verified byte-exact (`cmp` verified, `config/osaurus-settings-baseline.json` is git-clean).
- **Deep Wiki:** Up-to-date with Track 1 findings; next update upon Plan 02-01 / Phase 2 execution.

---

## Active Plan: Plan 02-01 (Harness Spike & Local Endpoint Validation)

**Immediate Objective:**
1. Pin `lm-eval` version in isolated environment (`uv run --isolated --with lm-eval lm_eval --version`).
2. Validate task registry identifiers and generative task configurations (MMLU, GSM8K, ARC-Challenge, IFEval).
3. Start candidate runtime (`runtimes.RUNTIMES[...]`), issue canary requests via `--model local-chat-completions --model_args base_url=http://localhost:<port>/v1`, verify answer channel extraction and `<think>` reasoning token stripping.
4. Establish item-identity hashing, evaluate `fewshot_as_multiturn` setting, and measure wall-clock seconds per item to validate the Phase 2 budget.

---

## Standing Invariants

- **Vary one thing at a time:** The defining rule of the project.
- **Zero repository dependencies:** Run `lm-eval` exclusively via isolated `uv run --isolated --with lm-eval`.
- **Osaurus KV Cache Guarantee:** Restore host config byte-exact upon completion (`cmp` verified).
- **Process Safety:** Never sweep using bare name `osaurus`. Sweep by full executable path `^/Applications/osaurus.app/Contents/MacOS/osaurus`.
- **Thermal & Contention:** Exactly one model resident in memory at a time. Never run background jobs, tests, git operations, or downloads while measuring a cell.
- **Prompt Cache Preservation:** Always dispatch cc-agent via `.paul/orders/dispatch.sh <role> <order-file>`, preserving byte-identical `PREAMBLE.md` for $0.003/M cache read hit rate.
