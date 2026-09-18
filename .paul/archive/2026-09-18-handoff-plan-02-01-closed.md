---
description: "OhYesMLX — session handoff, 2026-09-18 (Phase 2 Track 2 Accuracy Scoring: Plan 02-01 Complete, Plan 02-02 Ready)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-18 (v2 Phase 2 Track 2 Accuracy Scoring: Plan 02-01 Complete, Plan 02-02 Ready)

> **This file is short by design and is rewritten each session, never appended to.** It holds
> *state*: where things stand now and what is next. Durable rules live in `AGENTS.md`;
> decisions live in `.paul/STATE.md`; findings live in `docs/research/`. Previous handoffs are
> in `.paul/archive/` and are not required reading.

Read this, then `.paul/STATE.md`, then `AGENTS.md`.

---

## Where the project is

- **v1 is 100% closed and published.**
- **v2 Milestone active (0.2.0):** JANG Study and Accuracy Scoring.
- **v2 Phase 1 (Track 1: The JANG Study) is 100% COMPLETE & PUBLISHED** across all three plans (`docs/research/2026-09-17-dense-jang-study.md`, `docs/research/2026-09-17-moe-jang-study.md`, `docs/research/2026-09-17-jang-cross-runtime.md`).
- **v2 Phase 2 (Track 2: Accuracy Scoring) Plan 02-01 is 100% COMPLETE & PUBLISHED:**
  - **Spike Report published:** [`docs/research/2026-09-18-accuracy-spike-report.md`](file:///Users/jrazz/Dev/active/OhYesMLX/docs/research/2026-09-18-accuracy-spike-report.md) (973 lines).
  - Decision 102 recorded in `.paul/STATE.md`.
  - Upstream `vmlx_engine` scheduler deadlock on string stop sequences isolated and patched in both copies (`match_idx`, `sha256 9710d2b9…`).
  - Reasoning channel trap resolved via `--gen_kwargs enable_thinking=false` (3.27s/it on GSM8K, 100% extractable scores).
  - Presentation priced and frozen: `fewshot_as_multiturn: true` (0.60 vs 0.00 on MMLU 5-shot).
  - Execution budget validated: ~1.2–1.9h per cell with `enable_thinking=false` (well inside §6.1's 5–7h estimate; §3.3 downward budget dial not triggered).
- **Tests:** 495 tests pass (`/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`).
- **Ports & Processes:** All ports (1337, 8080, 8081, 8100, 8000) are free. No background runtimes active.
- **Osaurus State:** Jason's host Osaurus settings verified byte-exact (`cmp` verified, `config/osaurus-settings-baseline.json` is git-clean).
- **Deep Wiki:** Updated with Plan 02-01 findings (`10 Wiki/Projects/OhYesMLX/OhYesMLX.md`).

---

## Active Plan: Plan 02-02 (Dense Accuracy Study: `Qwen3.5-4B`)

**Objective:**
Execute the Dense Accuracy Study across both runtimes (`vMLX` and `Osaurus`) on `Qwen3.5-4B` over the 4 target tasks (MMLU, GSM8K, ARC-Challenge, IFEval):
- Column A: `vMLX` across the 4 dense formats (`jang4s`, `stock4bit`, `oq4`, `oq4e`), `cache_state="off"`.
- Column B: `Osaurus` across the 4 dense formats (`jang4s`, `oq4`, `oq4e`, `optiq`), host settings toggled per §4.4 and restored byte-exact.
- Replicate: `jang4s` + `stock4bit` on `vMLX` and `jang4s` on `Osaurus` (MMLU).
- Study 2C dense half: per-item agreement rate across shared formats.
- Author and publish `docs/research/2026-09-18-accuracy-dense.md`.

**Gates before Plan 02-02's first cell (from Spike Report §10.3):**
1. Verify vMLX engine file hash per block (`shasum -a 256 …/mllm_scheduler.py` == `9710d2b9…`).
2. Pass `--gen_kwargs enable_thinking=false` on all runs.
3. Pass `--fewshot_as_multiturn true` on all runs.
4. Pass `--num_fewshot 5` for MMLU (generative default is 0).
5. Capture runtime stdout/stderr log alongside `results.json` to preserve reconciliation and token counts.

---

## Standing Invariants

- **Vary one thing at a time:** The defining rule of the project.
- **Zero repository dependencies:** Run `lm-eval` exclusively via isolated `uv run --isolated --with lm-eval`.
- **Osaurus KV Cache Guarantee:** Restore host config byte-exact upon completion (`cmp` verified).
- **Process Safety:** Never sweep using bare name `osaurus`. Sweep by full executable path `^/Applications/osaurus.app/Contents/MacOS/osaurus`.
- **Thermal & Contention:** Exactly one model resident in memory at a time. Never run background jobs, tests, git operations, or downloads while measuring a cell.
- **Prompt Cache Preservation:** Always dispatch cc-agent via `.paul/orders/dispatch.sh <role> <order-file>`, preserving byte-identical `PREAMBLE.md` for $0.003/M cache read hit rate.
