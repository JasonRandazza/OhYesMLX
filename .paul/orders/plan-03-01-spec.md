GOAL: Specify Plan 03-01 (35B MoE Serving Benchmark) study design and fetch script.

CONTEXT:
Milestone v3 Phase 1 scales OhYesMLX from sub-10B models to 35B MoE (`Qwen3.6-35B-A3B`).
Total parameter count is ~35B, active parameters per token is ~3B (40 layers, 256 experts, 8 routed per token, 2048 hidden size, hybrid attention).
At 4-bit, weights consume ~18.3 to 20.6 GB on disk, occupying ~35-45% of 64GB unified memory.
We need:
1. `scripts/fetch_35b.sh` — standalone script downloading the 4 verified models.
2. `docs/research/2026-09-19-v3-phase1-35b-study-design.md` — comprehensive single-variable study design.

MODELS (All verified 100% architecture-identical: 40 layers, 256 experts, 8 routed per tok, hidden 2048):
1. Stock 4-bit: `mlx-community/Qwen3.6-35B-A3B-4bit` (19.03 GB)
2. OptiQ 4-bit: `mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit` (20.63 GB)
3. oQ4: `Jundot/Qwen3.6-35B-A3B-oQ4` (19.67 GB)
4. JANG 4-bit: `JANGQ-AI/Qwen3.6-35B-A3B-JANGTQ4` (18.35 GB)

Total disk: ~77.7 GB (187 GiB free on host).

FILES TO TOUCH:
- scripts/fetch_35b.sh
- docs/research/2026-09-19-v3-phase1-35b-study-design.md

SPECIFICATION:
1. Create `scripts/fetch_35b.sh`:
   - Standalone executable bash script (`chmod +x`).
   - Sets:
     `HF=/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/hf`
   - Iterates through the 4 repos:
     - `mlx-community/Qwen3.6-35B-A3B-4bit`
     - `mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit`
     - `Jundot/Qwen3.6-35B-A3B-oQ4`
     - `JANGQ-AI/Qwen3.6-35B-A3B-JANGTQ4`
   - Logs timestamp for each download and reports failure or success.
   - Outputs `FETCHDONE` at exit.
   - Carries comment: "Do not run while a benchmark is measuring."

2. Create `docs/research/2026-09-19-v3-phase1-35b-study-design.md`:
   - Structure follows `docs/research/2026-09-17-v2-track1-jang-study-design.md`.
   - Title: "Milestone v3 Phase 1 — 35B MoE Serving Benchmark Study Design: Qwen3.6-35B-A3B across Stock 4-bit, OptiQ, oQ4, and JANG"
   - Marked "Design only. No measurements in this document."
   - §1: Executive summary & problem statement (why 35B scale matters, memory residency on Apple Silicon 64GB M2 Max).
   - §2: Architecture parity table (40 layers, 256 experts, 8 per token, 2048 hidden, hybrid attention) across all 4 repos with verified disk sizes.
   - §3: Candidate Serving Runtimes & compatibility matrix (`vmlx`, `osaurus`, `optiq`, `mlxlm`, `omlx`).
   - §4: Coherence Gate & Floor rules (referencing stock mlx-lm token salad on 256-expert oQ4-mtp in v1).
   - §5: Pre-registered Hypotheses (H1 through H4: active routing decode speed, OptiQ Pareto domination at 35B, JANG density/throughput lead, peak footprint accounting).
   - §6: Workload shapes (`chat`, `prefill`, `decode`), pins (temp 0, seed 0, concurrency 1, plateau warmup, 30s cooldown).
   - §7: Execution protocol and next steps (fetch -> probe -> grid run -> report).

VERIFICATION:
- Check syntax: `bash -n scripts/fetch_35b.sh`
- Run test suite: `/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python -m pytest -q`
- Touch nothing else. Do NOT execute the download script (download execution is reserved for coordinator).
