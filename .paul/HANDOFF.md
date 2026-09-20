---
description: "OhYesMLX — session handoff, 2026-09-20 (Phase 3 Closed; Phase 4 Ready)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-20 (Phase 3 Closed; Phase 4 Ready)

> **This file is the single session-transfer note for the incoming agent.**
> Read this, then `.paul/STATE.md`, then `AGENTS.md`.

---

## Current Project Position

- **Milestone v1 (0.1.0) & Milestone v2 (0.2.0):** 100% COMPLETE & CLOSED.
- **Milestone v3 Phase 1 (Large-Model Scaling: 35B MoE):** 100% COMPLETE & CLOSED (Plans 03-01, 03-02, 03-03).
- **Milestone v3 Phase 2 (Context Scaling & Dynamics):** 100% COMPLETE & CLOSED (Plans 03-04, 03-05).
- **Milestone v3 Phase 3 (Speculative Decoding & Acceleration):** 100% COMPLETE & CLOSED (Plans 03-06, 03-07):
  - `[x]` **Plan 03-06:** Native Multi-Token Prediction (MTP) in vMLX (`docs/research/2026-09-20-native-mtp-vmlx.md`). Proved fixed D=1 delivers +31% decode speedup (78.7 -> 103.1 tok/s) at 85% acceptance with +73 MB memory overhead; confirmed monotonic acceptance degradation (D1 [85%] > D2 [71%] > D3 [64%]); diagnosed 35B MoE MTP artifact defect.
  - `[x]` **Plan 03-07:** Speculative Draft-Model Decoding in mlx-lm (`docs/research/2026-09-20-speculative-draft-decoding.md`). Diagnosed stock `mlx_lm.server --draft-model` refusal on hybrid linear-attention models (`ValueError: Speculative decoding requires a trimmable prompt cache (got {'ArraysCache'})`). Evaluated 7 configurations via exact recurrent state-rollback adapter. Proved dual-model speculative drafting on Apple Silicon unified memory produces a 0.19× to 0.38× throughput collapse (64.3 -> 24.5 tok/s, 62% slowdown) and +3,072 MB RAM overhead because 35B MoE sparsity (1.98 GB active bytes/step) makes dense 4B drafting (2.54 GB/step) counterproductive (4.52 GB/cycle vs 1.98 GB AR). Established Native MTP as structurally superior to draft models on Apple Silicon.
- **Milestone v3 Phase 4 (Public Distribution & Packaging):** NEXT IN QUEUE.

---

## Immediate Next Objective: Phase 4 (Public Distribution & Packaging)

**Goal:** Package OhYesMLX for public consumption and provide automated interactive visualizations.

1. **Plan 03-08: Distributable Package & Clean CLI:**
   - Package OhYesMLX for public distribution (pip/uv installable, clean entry points, zero hardcoded host paths, self-contained dependencies).
   - Harden CLI and ensure full regression test coverage.
2. **Plan 03-09: Automated Interactive Pareto Visualization:**
   - Standalone interactive HTML/SVG Pareto frontier charts connecting Speed (tok/s, TTFT), Memory Footprint (phys_footprint), and Quality (Accuracy benchmarks) across all evaluated models and runtimes.

---

## Standing Invariants

- **Quiet Machine:** Exactly one model resident at a time. Sweep ports `8000, 8080, 8081, 8100, 1337` before starting.
- **Python Environment:** Prepend `PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"` so python resolves to the venv with `mlx_lm` and `tokenizers`.
- **Test Suite:** `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q` must remain 496+ green.
- **Deep Wiki:** Update `/Users/jrazz/Documents/ObsidianNotes/10 Wiki/Projects/OhYesMLX/OhYesMLX.md` and run `validate_vault.py` after verified runs. Never commit/push the vault.
