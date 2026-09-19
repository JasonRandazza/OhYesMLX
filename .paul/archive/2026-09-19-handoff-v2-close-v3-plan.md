---
description: "OhYesMLX — session handoff, 2026-09-19 (Milestone v2 Complete; Candidates 1 & 2 Complete; Candidate 3 Queued for Overnight; Milestone v3 Horizon Planned)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-19 (v2 Complete, JIT A/B Closed, Candidate 3 Queued)

> **This file is short by design and is rewritten each session, never appended to.** It holds
> *state*: where things stand now and what is next. Durable rules live in `AGENTS.md`;
> decisions live in `.paul/STATE.md`; findings live in `docs/research/`.

Read this, then `.paul/STATE.md`, then `AGENTS.md`.

---

## Where the project is

- **v1 Milestone (0.1.0) and v2 Milestone (0.2.0) are 100% COMPLETE & PUBLISHED.**
- **Candidate 1: Osaurus MoE MMLU Extraction Resolution (COMPLETE):**
  - Offline re-scoring tool (`scripts/rescore_moe_mmlu.py`) recovered true MMLU score from untouched sample rows: **42.19% (481/1,140)** with 0 baseline hits lost (reconciled exactly to lm-eval's 43/1,140 under first-line truncation). Outscores stock4bit (35.53%) and OptiQ (28.25%).
  - Research note: `docs/research/2026-09-19-osaurus-moe-mmlu-extraction.md`.
- **Candidate 2: vMLX JIT A/B Study (COMPLETE):**
  - Single-variable speed benchmark measuring `--no-jit` vs `--enable-jit` via `OHYESMLX_VMLX_ENABLE_JIT` on identical JANG weights (`Qwen3.5-4B-JANG_4S` and `LFM2.5-8B-A1B-JANG_2L`).
  - Runner: `scripts/run_vmlx_jit_ab.sh`. Results: `results/vmlx-jit-ab/`.
  - Research note: `docs/research/2026-09-19-vmlx-jit-ab.md`.
  - **Key Finding:** JIT does NOT accelerate decode on 4B/8B models on Apple Silicon; across all 6 cell-workloads, `--enable-jit` carries a **-2.7% to -11.3% decode throughput penalty** (-1.5 to -8.7 tok/s). TTFT and prefill throughput are indifferent ($\pm1-2\%$). Confirms that Track 1's choice to pin `--no-jit` was not only methodologically sound, but delivered optimal decode throughput.
- **Candidate 3: Thinking-Off MMLU Arm (PRESERVED FOR OVERNIGHT):**
  - Documented in `.paul/ROADMAP.md` and `.paul/STATE.md`.
  - Ready for overnight dispatch before sleep.
- **Milestone v3 Horizon Plan:**
  - 4 Tracks defined in `.paul/ROADMAP.md`: Large-Model Scaling (30B–70B on internal vs external NVMe), Context Scaling (multi-turn sweeps & quantized KV caches), Speculative Decoding (MTP & draft models), and Public Distribution (v1.0 packaging & interactive Pareto charts).
- **All Ports Free:** 8000, 1337, 8080, 8081, 8100 verified released.
- **Test Suite:** 496 tests pass (`pytest -q` in 32.43s).

---

## What is next

1. **Option 3 Overnight Execution:**
   - Launch the Thinking-Off MMLU Arm before going to sleep:
     ```sh
     nohup scripts/run_accuracy_moe.sh > results/accuracy-moe/overnight-thinking-off.log 2>&1 &
     ```
2. **Milestone v3 Kickoff:**
   - Proceed with Phase 1 of Milestone v3 (Large-Model Scaling: 35B MoE / storage tiering).

---

## Standing Invariants

- **Quiet Machine:** Nothing else runs while a cell is measured.
- **Vary one thing at a time:** The defining rule of the project.
- **Single-variable framing:** Column is format axis (runtime constant); row is runtime axis (format constant).
- **Never infer capability from absence of a flag.**
