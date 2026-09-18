---
description: "OhYesMLX — session handoff, 2026-09-18 (Phase 2 Track 2 Accuracy Scoring: Plan 02-02 Complete, Plan 02-03 Ready)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-18 (v2 Phase 2 Track 2 Accuracy Scoring: Plan 02-02 Complete, Plan 02-03 Ready)

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
- **v2 Phase 2 (Track 2: Accuracy Scoring) Plan 02-02 is 100% COMPLETE & PUBLISHED:**
  - **Research Report published:** [`docs/research/2026-09-18-accuracy-dense.md`](file:///Users/jrazz/Dev/active/OhYesMLX/docs/research/2026-09-18-accuracy-dense.md) (11 cells, 30,580 evaluations, all PASS).
  - **Q2 Answered (Outcome P1: Quality Parity):** `JANG_4S` delivers its +14–17% decode speedup with zero accuracy penalty vs uniform 4-bit (`stock4bit`) on MMLU (+0.53 pp [95% CI: -0.38, +1.43 pp], strictly inside ±1.5 pp band).
  - **Q3 Answered (OptiQ Strictly Pareto-Dominated):** OptiQ is 28% larger on disk, slower/tied on decode, and scores lowest across all benchmarks (-3.1 to -4.4 pp on MMLU, $p < 10^{-6}$).
  - **Replicate Stability:** 100.000% within-runtime agreement (0 discordant items across 6,840 MMLU replicate evaluations).
  - **Study 2C:** Cross-runtime agreement 88–94% on constrained reasoning with ~3–4 pp loader offset, confirming that cross-runtime accuracy rankings are invalid.
- **Tests:** 495 tests pass (`pytest -q`).
- **Ports & Processes:** All ports (1337, 8080, 8081, 8100, 8000) are free. No background runtimes active.
- **Osaurus State:** Restored byte-exact (`cmp -s` verified).

---

## Active Plan: Plan 02-03 (MoE Accuracy Study: `LFM2.5-8B-A1B`)

**Objective:**
Execute the MoE Accuracy Study across the 5 MoE formats on `vMLX` (`jang2l`, `stock4bit`, `oq4`, `oq4e`, `optiq`) plus the Q1 replicate (`jang2l` + `stock4bit` on `vMLX`, MMLU) and Study 2C MoE row (`jang2l__osaurus`):
- Test vendor claim for `JANG_2L` (2.37 bits avg) vs uniform 4-bit on MMLU (Q1).
- Detect whether 2.37-bit MoE triggers quality collapse (P3) on multi-step math (GSM8K) or distractor reasoning.
- Author and publish `docs/research/2026-09-18-accuracy-moe.md`.

---

## Standing Invariants

- **Vary one thing at a time:** The defining rule of the project.
- **Zero repository dependencies:** Run `lm-eval` exclusively via isolated `uv run --isolated --with lm-eval`.
- **Osaurus KV Cache Guarantee:** Restore host config byte-exact upon completion (`cmp` verified).
- **Process Safety:** Never sweep using bare name `osaurus`. Sweep by full executable path `^/Applications/osaurus.app/Contents/MacOS/osaurus`.
- **Thermal & Contention:** Exactly one model resident in memory at a time. No local GPU models or repo modifications while measuring.
