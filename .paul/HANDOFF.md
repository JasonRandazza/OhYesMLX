---
description: "OhYesMLX — session handoff, 2026-09-20 (Plan 03-01 Complete: 35B MoE Serving Benchmark Published)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-20 (Plan 03-01 Complete & Published)

> **This file is short by design and is rewritten each session, never appended to.** It holds
> *state*: where things stand now and what is next. Durable rules live in `AGENTS.md`;
> decisions live in `.paul/STATE.md`; findings live in `docs/research/`.

Read this, then `.paul/STATE.md`, then `AGENTS.md`.

---

## Where the project is

- **v1 (0.1.0) & v2 (0.2.0) Milestones:** 100% COMPLETE & PUBLISHED.
- **Milestone v3 Phase 1 (Plan 03-01: 35B MoE Serving Benchmark):** 100% COMPLETE & PUBLISHED.
  - Research report: `docs/research/2026-09-20-35b-moe-serving.md`.
  - Artifacts: 4 35B models downloaded cleanly into HF hub layout (~80 GB; 105 GiB free disk remaining).
  - Probe: 20-cell loadability & coherence probe executed (`scripts/probe_grid_35b.py`), 16 live cells identified, 4 refusals recorded verbatim.
  - Benchmark Grid: 16 live cells executed across 5 runtimes (`scripts/run_grid_35b.sh`), 100% PASS with zero failures (`results/grid-35b/grid.md`).
  - Replication: Decisive H3 pair (`jangtq4__vmlx` vs `stock4bit__vmlx`) replicated with reversed order; findings verified cleanly outside 2.5% tie band (`scripts/run_replicate_35b.sh`).
  - Key Findings:
    - **H1 Confirmed (Routing-bound decode scaling):** 35B MoE decodes at 58–70 tok/s across all runtimes (~1.98 GB active bytes/step), scaling strictly with active parameters (8/256 experts) rather than dense size. `stock4bit` won decode in all runtimes.
    - **H2 Confirmed (OptiQ strictly Pareto-dominated):** +20.8% larger disk footprint, slowest or tied on decode (56.3–61.8 tok/s), highest peak memory across all runtimes.
    - **H3 Confirmed (JANG MoE Duality):** JANG delivers density savings on MoE (19.71 GB vs 20.43 GB disk, 19.0 GB vs 20.0 GB RAM), but loses decode throughput to stock 4-bit (-13.1% primary, -17.9% replicate).
    - **H4 Confirmed (Memory reporting gap):** Osaurus reports ~12.3–15.4 GB (0.74x of weight bytes) due to wired GPU page allocation, while mlx-lm, oMLX, OptiQ, and vMLX report 19.5–27.6 GB. `CROSS_RUNTIME_UNCOMPARABLE` holds.
    - **Stock mlx-lm Coherence:** Stock mlx-lm 0.31.3 produced 100% coherent output on `oQ4`. The 256-expert salad in Phase 1 was strictly caused by the unhandled speculative MTP head in `-mtp`.
- **Runtime Fix:** `ohyesmlx/runtimes.py` patched to gracefully handle Osaurus CLI background launcher exit (`_listener_pids`).
- **Machine & Ports:** All ports (8000, 8080, 8081, 8100, 1337) free and verified swept. 105 GiB free disk.
- **Test Suite:** 496 passed (`pytest -q` in 32.35s).

---

## What is next in fresh session

1. **Enter Planning for Milestone v3 Phase 1 Plan 03-02 (Cold vs Warm Page Cache Load & Memory Residency Attribution):**
   - Formulate study design measuring internal APFS cold load times (`cold_load_s`) vs OS page cache hits, purge mechanisms, wired GPU allocations (`footprint -p`), and resident memory headroom on large models across all 5 serving runtimes.
2. **Backlog / Deferred Items:**
   - Candidate 3 (Thinking-Off MMLU Arm on LFM2.5-8B-A1B) remains in the roadmap backlog. Note: it requires designing prompt/system-prompt reasoning suppression for LFM2 in vMLX (which rejects `enable_thinking=false`) and budgeting 3.5–8 hours of uninterrupted quiet machine time.

---

## Standing Invariants

- **Quiet Machine:** Nothing else runs while a cell is measured.
- **Vary one thing at a time:** The defining rule of the project.
- **Single-variable framing:** Column is format axis; row is runtime axis.
- **Never infer capability from absence of a flag.**
- **Never report bare mean for latency:** Use P50 / P90 / P99.
- **Peak memory accounting:** `footprint -p <pid>`, never `ps` RSS. Memory carries no cross-runtime ranking.
