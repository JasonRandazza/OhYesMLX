---
description: "OhYesMLX — session handoff, 2026-09-19 (Phase 2 Track 2 Accuracy Scoring: Plan 02-03 Complete, Plan 02-04 Next)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-19 (v2 Phase 2 Track 2 Accuracy Scoring: Plan 02-03 Complete, Plan 02-04 Next)

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
- **v2 Phase 2 (Track 2: Accuracy Scoring) Plans 02-01, 02-02, and 02-03 COMPLETE & PUBLISHED:**
  - Accuracy Spike published: [`docs/research/2026-09-18-accuracy-spike-report.md`](docs/research/2026-09-18-accuracy-spike-report.md).
  - Dense Accuracy Study published: [`docs/research/2026-09-18-accuracy-dense.md`](docs/research/2026-09-18-accuracy-dense.md).
  - MoE Accuracy Study published: [`docs/research/2026-09-19-accuracy-moe.md`](docs/research/2026-09-19-accuracy-moe.md).
- **Plan 02-03 Findings Summary:**
  - 100.000% replicate determinism confirmed on MoE (0 discordant items across 1,140 MMLU items).
  - Outcome P3 rejected: JANG_2L instruction following preserved at 2.37 bits (IFEval 56.8% vs 52.0%; Osaurus 60.4%).
  - Q3 answered: OptiQ strictly Pareto-dominated (-7.3 pp MMLU, +14% to +78% disk penalty).
  - Q4 answered: Outlier protection vital on MoE (oQ4e +14.3 pp over oQ4).
  - vMLX reasoning-truncation trap diagnosed (HTTP 502 when completion ends without closing `</think>`).
  - Study 2C extraction filter confound documented for Osaurus on MMLU (prose prefix vs regex filter).
- **All Ports Free:** 8000, 1337, 8080, 8081, 8100 verified released. Stale Osaurus CLI process cleanly swept; `osaurus mcp` preserved.
- **Test Suite:** 495 tests pass (`pytest -q` in 32.28s). Both self-tests pass.

---

## What is next (Plan 02-04: Accuracy vs Throughput Pareto Tradeoff Synthesis)

1. **Zero live measurement hours:** Pure analytical/synthesis joining Track 1 speed/memory coordinates with Track 2 accuracy coordinates.
2. **Execute Work Order for Plan 02-04:**
   - Compute Pareto frontiers per Study Design §5.5 (Qwen3.5-4B vMLX, Qwen3.5-4B Osaurus, LFM2.5-8B-A1B vMLX).
   - Compute trade rates (quality per speed, quality per memory, quality per disk) for pairs clearing the band.
   - Formally answer questions Q1–Q4 in order per Study Design §1.3 and §5.3.
   - Produce the 3-coordinate recommendation tables.
   - Author [`docs/research/2026-09-19-accuracy-pareto.md`](docs/research/2026-09-19-accuracy-pareto.md) via delegated Command Code worker (`cc-agent`).
3. **Close Phase 2 and Milestone v2:** Update state stores and Deep Wiki upon publication.

---

## Standing Invariants

- **Quiet Machine:** Nothing else runs while a cell is measured.
- **Vary one thing at a time:** The defining rule of the project.
- **Single-variable framing:** Column is format axis (runtime constant); row is runtime axis (format constant).
- **Never infer capability from absence of a flag.**
