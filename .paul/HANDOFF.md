---
description: "OhYesMLX — session handoff, 2026-09-19 (Plan 03-01 Specified: 35B MoE Serving Benchmark Ready)"
type: Handoff
about: "OhYesMLX"
---

# Handoff — 2026-09-19 (Ready for Plan 03-01 Execution)

> **This file is short by design and is rewritten each session, never appended to.** It holds
> *state*: where things stand now and what is next. Durable rules live in `AGENTS.md`;
> decisions live in `.paul/STATE.md`; findings live in `docs/research/`.

Read this, then `.paul/STATE.md`, then `AGENTS.md`.

---

## Where the project is

- **v1 Milestone (0.1.0) and v2 Milestone (0.2.0) are 100% COMPLETE & PUBLISHED.**
- **Post-v2 Candidates Complete:**
  - *Candidate 1 (Osaurus MoE MMLU):* 42.19% recovered offline, 0 baseline hits lost (`docs/research/2026-09-19-osaurus-moe-mmlu-extraction.md`).
  - *Candidate 2 (vMLX JIT A/B):* JIT decode penalty (-2.7% to -11.3%) confirmed; `--no-jit` pin validated (`docs/research/2026-09-19-vmlx-jit-ab.md`).
- **Milestone v3 Phase 1: Plan 03-01 Specified & Ready:**
  - Study design: `docs/research/2026-09-19-v3-phase1-35b-study-design.md` (35B MoE `Qwen3.6-35B-A3B`).
  - Architecture verified: 40 layers, 256 experts, 8 routed per token, 2048 hidden size.
  - Model lineup: Stock 4-bit (`mlx-community/Qwen3.6-35B-A3B-4bit`), OptiQ (`mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit`), oQ4 (`Jundot/Qwen3.6-35B-A3B-oQ4`), and JANG (`JANGQ-AI/Qwen3.6-35B-A3B-JANGTQ4`).
  - Fetch script: `scripts/fetch_35b.sh`.
- **Candidate 3 (Thinking-Off MMLU Arm):** Preserved in `ROADMAP.md` and `STATE.md` for overnight run.
- **Machine & Ports:** All ports (8000, 8080, 8081, 8100, 1337) free and verified swept. 187 GiB free disk.
- **Test Suite:** 496 passed (`pytest -q` in 32.73s).

---

## What is next in fresh session

Execute Plan 03-01:
1. **Download 35B models:** Run `scripts/fetch_35b.sh` (~80 GB download across the 4 verified models).
2. **Pre-flight loadability & coherence probe:** Validate that each candidate runtime (`vmlx`, `osaurus`, `optiq`, `mlxlm`, `omlx`) can bind, serve, and clear the coherence floor (preventing token salad).
3. **Execute 35B MoE serving benchmark:** Single-variable grid run across chat, prefill, and decode workloads.

---

## Standing Invariants

- **Quiet Machine:** Nothing else runs while a cell is measured.
- **Vary one thing at a time:** The defining rule of the project.
- **Single-variable framing:** Column is format axis; row is runtime axis.
- **Never infer capability from absence of a flag.**
