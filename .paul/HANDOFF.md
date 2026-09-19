---
description: "OhYesMLX — session handoff, 2026-09-19 (Milestone v2 Complete: JANG Study and Accuracy Scoring)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-19 (Milestone v2 Complete: JANG Study & Accuracy Scoring)

> **This file is short by design and is rewritten each session, never appended to.** It holds
> *state*: where things stand now and what is next. Durable rules live in `AGENTS.md`;
> decisions live in `.paul/STATE.md`; findings live in `docs/research/`. Previous handoffs are
> in `.paul/archive/` and are not required reading.

Read this, then `.paul/STATE.md`, then `AGENTS.md`.

---

## Where the project is

- **v1 Milestone (0.1.0) is 100% closed and published.**
- **v2 Milestone (0.2.0: JANG Study & Accuracy Scoring) is 100% COMPLETE & PUBLISHED.**
  - **Phase 1 (Track 1: The JANG Study) Complete:**
    - Plan 01-01: Dense JANG Study (`docs/research/2026-09-17-dense-jang-study.md`).
    - Plan 01-02: MoE JANG Study (`docs/research/2026-09-17-moe-jang-study.md`).
    - Plan 01-03: Cross-Runtime JANG Synthesis (`docs/research/2026-09-17-jang-cross-runtime.md`).
  - **Phase 2 (Track 2: Accuracy Scoring) Complete:**
    - Plan 02-01: Accuracy Harness Spike (`docs/research/2026-09-18-accuracy-spike-report.md`).
    - Plan 02-02: Dense Accuracy Study (`docs/research/2026-09-18-accuracy-dense.md`).
    - Plan 02-03: MoE Accuracy Study (`docs/research/2026-09-19-accuracy-moe.md`).
    - Plan 02-04: Accuracy Pareto Tradeoff Synthesis (`docs/research/2026-09-19-accuracy-pareto.md`).
- **Core Findings of Milestone v2:**
  - **The Evaluation Trilogy is Complete:** Speed, Memory, and Accuracy joined across 10 artifacts, 2 models, and 2 runtimes.
  - **JANG Duality Confirmed with Quality:**
    - *Dense (`Qwen3.5-4B`):* `JANG_4S` delivers +14–22% decode speedup with zero quality penalty (MMLU parity, $\Delta = +0.53\text{ pp}$ [95% CI: $-0.38, +1.43\text{ pp}$], replicate-confirmed at 0.0000 pp drift).
    - *MoE (`LFM2.5-8B-A1B`):* `JANG_2L` preserves instruction following at 2.37 bits (IFEval 56.8% vs 52.0%) with 36% disk savings and 30% footprint reduction.
  - **OptiQ Strictly Dominated:** Eliminated across all frontiers (-3.1 to -4.4 pp on dense, -7.3 to -8.0 pp on MoE, +14% to +78% disk penalty).
  - **Outlier Protection:** Recipe-dependent; mandatory on MoE (`oQ4e` +14.30 pp over `oQ4`).
  - **Loader Offset:** Runtime is a live confound for accuracy (3–4 pp loader offset on identical weights; Study 2C).
- **All Ports Free:** 8000, 1337, 8080, 8081, 8100 verified released. Stale Osaurus CLI process cleanly swept; `osaurus mcp` preserved.
- **Test Suite:** 495 tests pass (`pytest -q` in 32.21s).

---

## What is next

Milestone v2 is fully discharged and unified. Awaiting user direction on the next objective:
1. **vMLX JIT A/B experiment:** Single-variable test of `--enable-jit` vs `--no-jit` on identical JANG weights.
2. **Thinking-off arm:** Dedicated small arm testing MMLU with thinking disabled to isolate reasoning channel contributions.
3. **v3 Roadmap Planning:** New candidate models, longer sweeps, or external publishing.

---

## Standing Invariants

- **Quiet Machine:** Nothing else runs while a cell is measured.
- **Vary one thing at a time:** The defining rule of the project.
- **Single-variable framing:** Column is format axis (runtime constant); row is runtime axis (format constant).
- **Never infer capability from absence of a flag.**
