# Work Order: Plan 03-07 — Speculative Draft-Model Decoding in mlx-lm (`--draft-model`)

## Objective
Benchmark speculative draft-model decoding in `mlx-lm` using `mlx-community/Qwen3.6-35B-A3B-4bit` as the target model and `mlx-community/Qwen3.5-4B-4bit` as the draft model on Apple Silicon unified memory. Document the upstream `ArraysCache` trimmability boundary in stock `mlx-lm` and measure real decode throughput, acceptance rates, and memory contention across draft tokens $K \in \{1, 2, 3, 4\}$ via an exact recurrent state-rollback adapter.

## Pre-Registered Hypotheses
- **H1 (Stock Runtime Incompatibility):** Stock `mlx_lm.server` with `--draft-model` will reject execution on hybrid linear-attention models (`Qwen3.5` and `Qwen3.6`), raising `ValueError: Speculative decoding requires a trimmable prompt cache`.
- **H2 (Dual-Model Bandwidth Contention Inversion):** Unlike Native MTP (+31% speedup), speculative drafting with a dense 4B model will produce a **net decode throughput collapse** (<0.50× of base AR decode) on Apple Silicon unified memory. Because 35B MoE activates only 8/256 experts (~1.98 GB active bytes/step), drafting with a dense 4B model (reading 2.54 GB every draft token) consumes more memory bandwidth per token than running the 35B target model directly.
- **H3 (Monotonic Throughput Degradation with Draft Depth):** As draft depth $K$ increases from 1 to 4, decode throughput will degrade monotonically ($K=1 > K=2 > K=3 > K=4$) due to diminishing acceptance rates compounding memory bus contention.
- **H4 (Bit-Exact Generative Fidelity):** The recurrent state-snapshot rollback adapter will achieve 100.000% token-by-token parity with standalone non-speculative greedy AR decode.
- **H5 (Memory Residency Overhead):** Co-locating both the 35B target (~20.5 GB) and the 4B draft model (~2.8 GB) in unified memory will increase resident physical footprint by +2.5 to +3.2 GB without memory leaks.

## Configurations to Measure
Environment: Python 3.14 via `~/.local/share/ohyesmlx/mlx-lm-0.31.3` with MLX 0.32.2.
- **Arm 0: Stock Server Control (`stock_refusal_control`)**:
  Stock `mlx_lm.server` with `--model <35B> --draft-model <4B>` confirming the `ArraysCache` trimmability refusal.
- **Arm 1: Standalone Target AR Baseline (`standalone_35b_ar`)**:
  Autoregressive greedy decode on `Qwen3.6-35B-A3B-4bit`.
- **Arm 2: Standalone Draft AR Baseline (`standalone_4b_ar`)**:
  Autoregressive greedy decode on `Qwen3.5-4B-4bit`.
- **Arm 3: Speculative Draft Decoding $K=1$ (`speculative_k1`)**:
  Target 35B MoE + Draft 4B Dense, 1 draft token per step, exact recurrent rollback.
- **Arm 4: Speculative Draft Decoding $K=2$ (`speculative_k2`)**:
  Target 35B MoE + Draft 4B Dense, 2 draft tokens per step, exact recurrent rollback.
- **Arm 5: Speculative Draft Decoding $K=3$ (`speculative_k3`)**:
  Target 35B MoE + Draft 4B Dense, 3 draft tokens per step, exact recurrent rollback.
- **Arm 6: Speculative Draft Decoding $K=4$ (`speculative_k4`)**:
  Target 35B MoE + Draft 4B Dense, 4 draft tokens per step, exact recurrent rollback.

## Workloads / Prompts
1. **Workload A (Structured Code / Low Entropy):** Python Fibonacci function with memoization and type annotations.
2. **Workload B (Reasoning & Philosophy / High Entropy):** Ship of Theseus paradox analysis.
3. **Workload C (Technical Architecture / Medium Entropy):** Apple Silicon Unified Memory architecture explanation.

Output length: 64 tokens per prompt. Temperature: 0.0 pinned (greedy).

## Metrics Recorded
- TTFT (ms / s)
- Decode throughput (tok/s)
- Speedup ratio vs Target Standalone AR
- Draft acceptance rate ($N_{\text{accepted}} / N_{\text{drafted}}$)
- Generative exact match agreement (% token match vs Standalone AR)
- Resident memory footprint via `footprint -p <pid>` (MB)
- Coherence gate status (PASS/FAIL)

## Deliverables
- `scripts/probe_speculative_draft.py`
- `results/plan-03-07/speculative_results.json`
- `docs/research/2026-09-20-v3-phase3-plan-03-07-study-design.md`
- `docs/research/2026-09-20-speculative-draft-decoding.md`
