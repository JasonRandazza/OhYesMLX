# Study Design: Milestone v3 Phase 3 Plan 03-07 — Speculative Draft-Model Decoding in mlx-lm

**Author:** Antigravity Coordinator  
**Date:** 2026-09-20  
**Target Milestone:** v3 (Phase 3: Speculative Decoding & Acceleration Architectures)  
**Status:** PRE-REGISTERED  

---

## 1. Executive Summary & Core Motivation

Milestone v3 Phase 3 evaluates speculative decoding and acceleration architectures on Apple Silicon unified memory.
In Plan 03-06, we evaluated **Native Multi-Token Prediction (MTP)** in vMLX, discovering that a single dedicated MTP layer inside the primary model achieved a **+31.0% decode speedup** (78.7 -> 103.1 tok/s) at **85.3% acceptance** with negligible memory overhead (+73 MB RAM).

Plan 03-07 targets the traditional alternative: **Speculative Draft-Model Decoding** using a separate, smaller drafter model. In `mlx-lm`, this is supported via `--draft-model` and `--num-draft-tokens`.

We evaluate the hero model pair:
- **Target Model:** `mlx-community/Qwen3.6-35B-A3B-4bit` (19.03 GiB on-disk; ~20.5 GB resident; 40 layers, 256 experts, 8 active per token)
- **Draft Model:** `mlx-community/Qwen3.5-4B-4bit` (2.54 GiB on-disk; ~2.8 GB resident; dense hybrid architecture)
- **Vocabulary Alignment:** Byte-identical tokenizer (100% vocabulary match).

### The Primary Question
Does running a secondary 4B draft model in unified memory yield a net decode speedup on Apple Silicon, or does dual-model memory bandwidth contention wipe out draft acceptance gains?

---

## 2. Upstream Architectural Refusal Discovery

During pre-flight validation of stock `mlx-lm` 0.31.3 (`mlx_lm.server --model <35B> --draft-model <4B>`), we identified a fundamental engine boundary:
- Both `Qwen3.6-35B-A3B` and `Qwen3.5-4B` are hybrid linear-attention models using GatedDeltaNet recurrent layers.
- In `mlx_lm.models.cache`, linear layers allocate `ArraysCache`, which holds recurrent state matrices ($S_t$) rather than offset-sliced token sequences.
- Because `ArraysCache` does not implement `trim()`, `mlx_lm.generate.speculative_generate_step` deliberately refuses execution:
  `ValueError: Speculative decoding requires a trimmable prompt cache (got {'ArraysCache'}).` (tracked in upstream `mlx-lm` Issue #1446).

Plan 03-07 resolves this via **Option A**:
1. Empirically verify and document the stock `mlx_lm.server` boundary refusal.
2. Implement an in-memory recurrent state-snapshot rollback adapter in `scripts/probe_speculative_draft.py` that preserves 100.000% bit-exact parity with greedy autoregressive generation while enabling speculative drafting across $K \in \{1, 2, 3, 4\}$.
3. Benchmark the actual unified memory decode speedup vs memory bus contention.

---

## 3. Pre-Registered Hypotheses

- **H1 (Stock Runtime Incompatibility):** Stock `mlx_lm.server` with `--draft-model` will reject execution on hybrid linear-attention models (`Qwen3.5` and `Qwen3.6`), raising `ValueError: Speculative decoding requires a trimmable prompt cache`.
- **H2 (Dual-Model Bandwidth Contention Inversion):** Unlike Native MTP (+31% speedup), speculative drafting with a dense 4B model will produce a **net decode throughput collapse** (<0.50× of base AR decode) on Apple Silicon unified memory. Because 35B MoE activates only 8/256 experts (~1.98 GB active bytes/step), drafting with a dense 4B model (reading 2.54 GB every draft token) consumes more memory bandwidth per token than running the 35B target model directly.
- **H3 (Monotonic Throughput Degradation with Draft Depth):** As draft depth $K$ increases from 1 to 4, decode throughput will degrade monotonically ($K=1 > K=2 > K=3 > K=4$) due to diminishing acceptance rates compounding memory bus contention.
- **H4 (Bit-Exact Generative Fidelity):** The recurrent state-snapshot rollback adapter will achieve 100.000% token-by-token parity with standalone non-speculative greedy AR decode.
- **H5 (Memory Residency Overhead):** Co-locating both the 35B target (~20.5 GB) and the 4B draft model (~2.8 GB) in unified memory will increase resident physical footprint by +2.5 to +3.2 GB without memory leaks.

---

## 4. Experimental Configurations (Arms)

| Arm ID | Description | Target Model | Draft Model | Speculative Parameters |
|---|---|---|---|---|
| **Arm 0** | Stock Server Control | `Qwen3.6-35B-A3B-4bit` | `Qwen3.5-4B-4bit` | Stock `mlx_lm.server --draft-model` (Refusal Check) |
| **Arm 1** | Target Standalone AR | `Qwen3.6-35B-A3B-4bit` | None | Greedy AR decode baseline |
| **Arm 2** | Draft Standalone AR | `Qwen3.5-4B-4bit` | None | Greedy AR decode baseline |
| **Arm 3** | Speculative $K=1$ | `Qwen3.6-35B-A3B-4bit` | `Qwen3.5-4B-4bit` | $K=1$ draft token per step, exact rollback |
| **Arm 4** | Speculative $K=2$ | `Qwen3.6-35B-A3B-4bit` | `Qwen3.5-4B-4bit` | $K=2$ draft tokens per step, exact rollback |
| **Arm 5** | Speculative $K=3$ | `Qwen3.6-35B-A3B-4bit` | `Qwen3.5-4B-4bit` | $K=3$ draft tokens per step, exact rollback |
| **Arm 6** | Speculative $K=4$ | `Qwen3.6-35B-A3B-4bit` | `Qwen3.5-4B-4bit` | $K=4$ draft tokens per step, exact rollback |

---

## 5. Workloads & Evaluation Prompts

Evaluated against the identical 3 semantic workloads from Plan 03-06 (max 64 output tokens):
1. **Workload A (Structured Code / Low Entropy):**
   *Prompt:* `"Write a Python function `fibonacci_memo(n: int) -> int` that computes the nth Fibonacci number using recursion and an explicit dictionary memoization cache. Include docstring and type hints."*
2. **Workload B (Reasoning & Philosophy / High Entropy):**
   *Prompt:* `"Analyze the Ship of Theseus paradox from the perspective of mereological essentialism versus four-dimensionalism (worm theory). Summarize the key metaphysical distinction."*
3. **Workload C (Technical Architecture / Medium Entropy):**
   *Prompt:* `"Explain how Apple Silicon unified memory architecture eliminates redundant PCIe transfers between the CPU and GPU during LLM decode steps."*

---

## 6. Metrics & Verification Protocol

1. **Quiet Machine Protocol:** All candidate ports (8000, 8080, 8081, 8100, 1337) swept; no background processes.
2. **Decode Throughput (tok/s):** Generated tokens divided by decode generation span.
3. **Draft Acceptance Rate:** Ratio of accepted draft tokens to total drafted tokens ($N_{\text{accepted}} / N_{\text{drafted}}$).
4. **Speedup Ratio:** $\text{Throughput}_{\text{spec}} / \text{Throughput}_{\text{AR}}$.
5. **Exact Match Parity:** Bit-exact token array match with standalone AR decode.
6. **Coherence Gate:** Clean semantic output free of repetition or token salad.
