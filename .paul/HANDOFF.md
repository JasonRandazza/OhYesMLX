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
- **Milestone v3 Phase 1 (Large-Model Scaling: 35B MoE Class):**
  - **Plan 03-01 (35B MoE Serving Benchmark):** 100% COMPLETE & PUBLISHED (`docs/research/2026-09-20-35b-moe-serving.md`). 16 live cells executed; H1–H4 confirmed.
  - **Plan 03-02 (Cold vs Warm Page Cache Load & Memory Residency Attribution):** 100% COMPLETE & PUBLISHED (`docs/research/2026-09-20-cold-warm-load-attribution-35b.md`).
    - APFS NVMe cold read throughput: 5.40 GB/s (5.61s cold vs 2.09s warm, a 2.68x speedup).
    - Lazy loading quantified at 35B: oMLX hides +4.92s and OptiQ hides +8.92s in Request #1, inverting cold-load rankings. True Time to First Output: Osaurus (3.42s) > mlxlm (4.64s) > omlx (7.45s) > vmlx (8.66s) > optiq (12.44s).
    - Osaurus 0.74x memory gap solved: `IOAccelerator` allocations capped at 12.18 GB with remaining ~7 GB allocated into wired driver pages (`CROSS_RUNTIME_UNCOMPARABLE` validated).
    - Swap: 0.0 MB across all runs. Memory 100% cleanly reclaimed.
- **Machine & Ports:** All ports (8000, 8080, 8081, 8100, 1337) free and verified swept. 105 GiB free disk.
- **Test Suite:** 496 passed (`pytest -q`).

---

## What is next in fresh session

1. **Enter Planning for Milestone v3 Phase 1 Plan 03-03 (Expert Streaming under High Memory Pressure):**
   - Formulate study design measuring OptiQ's `--stream-experts auto` vs `--stream-experts off` behavior and vMLX block paging thresholds on 35B MoE under memory pressure.
2. **Backlog / Deferred Items:**
   - Candidate 3 (Thinking-Off MMLU Arm on LFM2.5-8B-A1B) remains in roadmap backlog.

---

## Standing Invariants

- **Quiet Machine:** Nothing else runs while a cell is measured.
- **Vary one thing at a time:** The defining rule of the project.
- **Single-variable framing:** Column is format axis; row is runtime axis.
- **Never infer capability from absence of a flag.**
- **Never report bare mean for latency:** Use P50 / P90 / P99.
- **Peak memory accounting:** `footprint -p <pid>`, never `ps` RSS. Memory carries no cross-runtime ranking.
