---
description: "OhYesMLX — session handoff, 2026-09-20 (Milestone v3 Overnight Autonomous Execution Directive)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-20 (Milestone v3 Overnight Autonomous Execution Directive)

> **This file is the single session-transfer note for the incoming agent.**
> Read this, then `.paul/STATE.md`, then `AGENTS.md`.

---

## 🚨 AUTONOMOUS OVERNIGHT DIRECTIVE

**Jason is asleep. Do NOT pause, wait, or ask questions between plans.**
Your mission is to **autonomously execute as many remaining Milestone v3 plans as possible overnight** until the milestone is fully completed or all work is exhausted.

For every plan you execute, follow the established **PAUL workflow (`PLAN ──▶ APPLY ──▶ UNIFY`)**:
1. **PLAN:** Formulate order spec (`.paul/orders/plan-03-XX-spec.md`) and pre-registered single-variable study design (`docs/research/2026-09-20-v3-...-study-design.md`) with explicit hypotheses (H1–H4/H5).
2. **APPLY:** Implement the dedicated probe script (`scripts/probe_...py`), sweep ports (`8000, 8080, 8081, 8100, 1337`), execute the benchmark under the Quiet Machine rule, and save raw evidence to `results/plan-03-XX/`.
3. **UNIFY:**
   - Author the comprehensive research report (`docs/research/2026-09-20-...md`).
   - Update `.paul/ROADMAP.md` (mark plan `[x] Complete`).
   - Update `.paul/STATE.md` (record Decision `111+`, update Loop Position & Current Position).
   - Update Deep Wiki (`/Users/jrazz/Documents/ObsidianNotes/10 Wiki/Projects/OhYesMLX/OhYesMLX.md`) with finding and roadmap checkbox, then run vault validator: `python3 "00 System/Automation/validate_vault.py" "/Users/jrazz/Documents/ObsidianNotes"` (never commit/push vault).
   - Verify test suite: `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q` (must remain 496+ green).
   - Commit all repo changes to git with a clear `feat(v3): ...` commit message.
   - **Immediately proceed to the next plan in sequence.**

---

## Where the Project Stands Right Now

- **v1 (0.1.0) & v2 (0.2.0):** 100% COMPLETE.
- **Milestone v3 Phase 1 (Large-Model Scaling: 35B MoE Class):** **100% COMPLETE & CLOSED**
  - `[x]` **Plan 03-01:** 35B MoE Serving Benchmark (`docs/research/2026-09-20-35b-moe-serving.md`).
  - `[x]` **Plan 03-02:** Cold vs Warm Page Cache Load & Memory Residency Attribution (`docs/research/2026-09-20-cold-warm-load-attribution-35b.md`). APFS 5.40 GB/s cold read; lazy-load penalties; Osaurus 0.74x memory gap solved via `IOAccelerator` accounting.
  - `[x]` **Plan 03-03:** Expert Streaming under High Memory Pressure (`docs/research/2026-09-20-expert-streaming-high-memory-pressure.md`). 75–88% memory reduction (footprint down to 3.2–3.9 GB, 2.28 GB backbone floor); 9×–16× decode collapse (4.3–8.2 tok/s); LRU caching <5% gain; OptiQ 70% RAM auto-threshold fragility.
- **All Ports Free:** 8000, 8080, 8081, 8100, 1337 verified swept and clean.
- **Working Tree:** Clean, all commits ahead of origin on `main`. 496 tests passing.

---

## Exact Sequential Plan Queue for Tonight

### Phase 2: Context Scaling & Conversational Dynamics
1. **Plan 03-04: Multi-Turn Conversation Sweep (1 to 10 turns)**
   - **Goal:** Quantify turn-by-turn ITL degradation, cumulative KV / prefix-cache retention speedup, and latency progression across successive conversational turns.
   - **Target Model:** `mlx-community/Qwen3.6-35B-A3B-4bit` (and/or `Qwen3.5-4B`).
   - **Candidate Runtimes:** `omlx`, `osaurus`, `vmlx`, `mlxlm`.
   - **Deliverables:** `scripts/probe_multiturn_sweep.py`, `results/plan-03-04/multiturn_results.json`, `docs/research/2026-09-20-multiturn-conversation-sweep.md`.

2. **Plan 03-05: Quantized KV Caches (FP8, INT4 vs FP16 KV Caches)**
   - **Goal:** Measure unified memory savings vs TTFT/decode latency and perplexity/accuracy retention at 16k and 32k context lengths across runtimes supporting KV cache quantization (`vmlx`, `optiq`, `mlxlm`).
   - **Deliverables:** `scripts/probe_kv_quant.py`, `results/plan-03-05/kv_quant_results.json`, `docs/research/2026-09-20-quantized-kv-caches.md`.

### Phase 3: Speculative Decoding & Acceleration Architectures
3. **Plan 03-06: Native Multi-Token Prediction (MTP) in vMLX (`--enable-native-mtp`)**
   - **Goal:** Measure real decode speedup, acceptance rate, and TTFT impact vs non-MTP baselines on MTP-equipped models (`Jundot/Qwen3.6-35B-A3B-oQ4-mtp`).
   - **Deliverables:** `scripts/probe_native_mtp_35b.py`, `results/plan-03-06/mtp_results.json`, `docs/research/2026-09-20-native-mtp-vmlx.md`.

4. **Plan 03-07: Speculative Draft-Model Decoding in mlx-lm (`--speculative-model`)**
   - **Goal:** Quantify draft-model speculation speedup, token acceptance rate, and memory overhead on memory-bandwidth bound Apple Silicon decode.
   - **Deliverables:** `scripts/probe_speculative_draft.py`, `results/plan-03-07/speculative_results.json`, `docs/research/2026-09-20-speculative-draft-decoding.md`.

### Phase 4: Public Distribution & Packaging (v1.0 Release)
5. **Plan 03-08: Distributable Package & Clean CLI**
   - Package OhYesMLX for public consumption (`pyproject.toml`, clean CLI ergonomics, zero hardcoded host paths, self-contained).
6. **Plan 03-09: Automated Interactive Pareto Visualization**
   - Standalone interactive HTML/SVG Pareto frontier charts linking Speed, Memory, and Quality coordinates across tested configurations.

---

## Standing Invariants

- **Quiet Machine:** Exactly one model resident at a time. No other tasks or downloads while measuring.
- **Vary one thing at a time:** The core rule of the project.
- **Never infer capability from absence of a flag.**
- **Never report bare mean for latency:** Report P50 / P90 / P99.
- **Memory Metric Discipline:** Memory has no cross-runtime ranking (`CROSS_RUNTIME_UNCOMPARABLE`). `peak_mb` is strictly within-runtime via `footprint -p <pid>`.
- **Zero New Dependencies:** Maintain flat, lean stdlib-first architecture.
