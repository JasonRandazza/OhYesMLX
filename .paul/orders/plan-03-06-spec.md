# Work Order: Plan 03-06 — Native Multi-Token Prediction (MTP) in vMLX (`--enable-native-mtp`)

## Objective
Measure real decode speedup, speculative acceptance rates, ITL distributions, TTFT impact, and memory footprint across Native Multi-Token Prediction (MTP) configurations in vMLX on `Qwen3.6-35B-A3B-oQ4-mtp` vs non-MTP autoregressive baselines.

## Pre-Registered Hypotheses
- **H1 (Acceptance Rate Monotonic Degradation):** Speculative token acceptance rate ($\alpha$) will degrade monotonically with draft depth ($D=1 > D=2 > D=3$) due to error compounding across speculative draft steps.
- **H2 (Decode Speedup on Structured Code vs Prose):** On structured code tasks (low entropy), Native MTP (D=1 and D=2) will achieve a positive decode throughput speedup (>1.15× over base AR decode). On high-entropy reasoning/prose, speculative acceptance will drop, narrowing the decode advantage.
- **H3 (TTFT Invariance):** Because Native MTP operates strictly during autoregressive token generation and not during initial prompt prefill, TTFT will remain invariant ($\pm 5\%$) across all MTP depths and policies vs baseline AR decode.
- **H4 (Draft Head Memory Residency):** The dedicated MTP transformer layer (~600 MB of safetensors) and associated speculative draft state will introduce a small, bounded memory footprint increase (<1.0 GB RAM) over baseline non-MTP serving.
- **H5 (Adaptive Safety Valve Protection):** The adaptive depth policy (`--native-mtp-depth-policy adaptive`) will dynamically regulate draft depth and prevent throughput degradation below the base AR decode floor under variable entropy.

## Configurations to Measure
All runs hosted on `vmlx` 1.6.59, port 8000, `--stream-interval 1 --continuous-batching --no-jit`.
- **Arm 1: Baseline AR Decode (No MTP)**:
  `--disable-native-mtp` on `Jundot/Qwen3.6-35B-A3B-oQ4-mtp`.
- **Arm 2: Native MTP Depth 1 (D=1, fixed)**:
  `--native-mtp-depth 1 --native-mtp-depth-policy fixed --native-mtp-sampling-policy greedy-only`.
- **Arm 3: Native MTP Depth 2 (D=2, fixed)**:
  `--native-mtp-depth 2 --native-mtp-depth-policy fixed --native-mtp-sampling-policy greedy-only`.
- **Arm 4: Native MTP Depth 3 (D=3, fixed)**:
  `--native-mtp-depth 3 --native-mtp-depth-policy fixed --native-mtp-sampling-policy greedy-only`.
- **Arm 5: Native MTP Default Adaptive (D=3, adaptive)**:
  `--native-mtp-depth 3 --native-mtp-depth-policy adaptive --native-mtp-sampling-policy greedy-only`.
- **Arm 6: Non-MTP Model Control (`Jundot/Qwen3.6-35B-A3B-oQ4`)**:
  Running base artifact without MTP weights to confirm base AR performance parity.

## Workloads / Prompts
1. **Workload A (Structured Code):** Python function implementation (Fibonacci with memoization and type annotations; deterministic grammar, low entropy).
2. **Workload B (Reasoning / Creative Prose):** Philosophical analysis of the ship of Theseus (higher lexical entropy, abstract vocabulary).
3. **Workload C (Multi-turn Technical Summarization):** Architectural summary of Apple Silicon Unified Memory architecture.

Output length: 128 tokens per prompt. Temperature: 0.0 pinned (greedy).

## Metrics Recorded
- TTFT (ms / s)
- Decode throughput (tok/s)
- ITL (ms/tok) P50, P90, P99
- Cold load time (s)
- Peak memory footprint via `footprint -p <pid>` (MB)
- MTP acceptance statistics: total cycles, drafted tokens, accepted tokens, acceptance rate (%), cycles by depth (d1, d2, d3)
- Coherence gate status (PASS/FAIL)

## Deliverables
- `scripts/probe_native_mtp_35b.py`
- `results/plan-03-06/mtp_results.json`
- `docs/research/2026-09-20-v3-phase3-plan-03-06-study-design.md`
- `docs/research/2026-09-20-native-mtp-vmlx.md`
