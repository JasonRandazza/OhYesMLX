---
description: "OhYesMLX — session handoff, 2026-09-20 (Milestone v3 Phase 1 Complete [Plans 03-01, 03-02, 03-03])"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-20 (Milestone v3 Phase 1 Complete)

> **This file is short by design and is rewritten each session, never appended to.** It holds
> *state*: where things stand now and what is next. Durable rules live in `AGENTS.md`;
> decisions live in `.paul/STATE.md`; findings live in `docs/research/`.

Read this, then `.paul/STATE.md`, then `AGENTS.md`.

---

## Where the project is

- **v1 (0.1.0) & v2 (0.2.0) Milestones:** 100% COMPLETE & PUBLISHED.
- **Milestone v3 Phase 1 (Large-Model Scaling: 35B MoE Class):** 100% COMPLETE (3/3 plans complete):
  - **Plan 03-01 (35B MoE Serving Benchmark):** 100% COMPLETE & PUBLISHED (`docs/research/2026-09-20-35b-moe-serving.md`). 16 live cells executed; H1–H4 confirmed.
  - **Plan 03-02 (Cold vs Warm Page Cache Load & Memory Residency Attribution):** 100% COMPLETE & PUBLISHED (`docs/research/2026-09-20-cold-warm-load-attribution-35b.md`). APFS NVMe cold read throughput at 5.40 GB/s; lazy load penalties quantified; Osaurus 0.74x memory gap solved via `IOAccelerator` region accounting.
  - **Plan 03-03 (Expert Streaming under High Memory Pressure):** 100% COMPLETE & PUBLISHED (`docs/research/2026-09-20-expert-streaming-high-memory-pressure.md`).
    - Full SSD streaming achieves 75–88% memory reduction (footprint drops from ~20.5 GB down to 3.2–3.9 GB, isolating the 2.28 GB non-expert backbone).
    - Decode throughput collapses 9× to 16× (from 67–75 tok/s to 4.3–8.2 tok/s) due to NVMe random `os.pread` latency for 320 slices/token.
    - In-RAM LRU caching yields <5% speedup under 256-expert routing entropy.
    - Smelt maintains near-native decode (62.5 tok/s) at risk of semantic degradation on omitted experts; FlashMoE preserves exact fidelity at disk-bound speed.
    - OptiQ's static 70% RAM auto-threshold (44.8 GB on 64 GB Mac) never triggers for 35B models, making explicit flag pinning mandatory under memory pressure.
- **Machine & Ports:** All ports (8000, 8080, 8081, 8100, 1337) free and verified swept. 105 GiB free disk.
- **Test Suite:** 496 passed (`pytest -q`).

---

## What is next in fresh session

1. **Enter Planning for Milestone v3 Phase 2 (Context Scaling & Conversational Dynamics):**
   - **Plan 03-04 (Multi-Turn Conversation Sweep: 1 to 10 turns):** Measure turn-by-turn ITL degradation, cumulative prefix-cache retention, and latency progression across successive conversation turns.
   - **Plan 03-05 (Quantized KV Caches: FP8, INT4 vs FP16):** Unified memory savings vs accuracy retention at 16k and 32k context lengths across runtimes supporting KV cache quantization.
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
