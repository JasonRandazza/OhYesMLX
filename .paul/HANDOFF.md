---
description: "OhYesMLX — session handoff, 2026-09-20 (Phase 3 Plan 03-07 Ready)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-20 (Phase 3 Plan 03-07 Ready)

> **This file is the single session-transfer note for the incoming agent.**
> Read this, then `.paul/STATE.md`, then `AGENTS.md`.

---

## Current Project Position

- **Milestone v1 (0.1.0) & Milestone v2 (0.2.0):** 100% COMPLETE.
- **Milestone v3 Phase 1 (Large-Model Scaling: 35B MoE):** 100% COMPLETE (Plans 03-01, 03-02, 03-03).
- **Milestone v3 Phase 2 (Context Scaling & Dynamics):** 100% COMPLETE & CLOSED (Plans 03-04, 03-05).
- **Milestone v3 Phase 3 (Speculative Decoding & Acceleration):** IN PROGRESS (1/2 plans complete):
  - `[x]` **Plan 03-06:** Native Multi-Token Prediction (MTP) in vMLX (`docs/research/2026-09-20-native-mtp-vmlx.md`). Proved fixed D=1 delivers +31% decode speedup (78.7 -> 103.1 tok/s) at 85% acceptance with +73 MB memory overhead; confirmed monotonic acceptance degradation (D1 [85%] > D2 [71%] > D3 [64%]); diagnosed 35B MoE MTP artifact defect (0% acceptance, 41% collapse, token salad).
  - `[ ]` **Plan 03-07:** Speculative Draft-Model Decoding in mlx-lm (`--draft-model` / `--speculative-model`). **NEXT IN QUEUE.**

---

## Immediate Next Objective: Plan 03-07

**Goal:** Benchmark speculative draft-model decoding in `mlx-lm` (`--draft-model` and `--num-draft-tokens`) on Apple Silicon unified memory.

1. **Target Model Pair:**
   - **Target Model:** `mlx-community/Qwen3.6-35B-A3B-4bit` (~20 GB resident)
   - **Draft Model:** `mlx-community/Qwen3.5-4B-4bit` (~2.5 GB resident)
   - *Verification:* Verified byte-identical tokenizer (`tokenizer.json` and `vocab.json` match 100%).
2. **Key Comparisons:**
   - Baseline standalone target (`mlx_lm.server --model <35B>`)
   - Speculative draft decoding at draft tokens $K \in \{1, 2, 3, 4\}$ (`--draft-model <4B> --num-draft-tokens <K>`)
   - Non-speculative draft model baseline (`mlx_lm.server --model <4B>`)
3. **Primary Question:**
   Does running a secondary 4B draft model in unified memory yield a net decode speedup on Apple Silicon, or does dual-model memory bandwidth contention wipe out draft acceptance gains?
4. **Deliverables:**
   - `scripts/probe_speculative_draft.py`
   - `results/plan-03-07/speculative_results.json`
   - `docs/research/2026-09-20-speculative-draft-decoding.md`

---

## Standing Invariants

- **Quiet Machine:** Exactly one model resident at a time. Sweep ports `8000, 8080, 8081, 8100, 1337` before starting.
- **Python Environment:** Prepend `PATH="$HOME/.local/share/ohyesmlx/mlx-lm-0.31.3/bin:$PATH"` so python resolves to the venv with `mlx_lm` and `tokenizers`.
- **Test Suite:** `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q` must remain 496+ green.
- **Deep Wiki:** Update `/Users/jrazz/Documents/ObsidianNotes/10 Wiki/Projects/OhYesMLX/OhYesMLX.md` and run `validate_vault.py` after verified runs. Never commit/push the vault.
