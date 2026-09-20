# Study Design: Milestone v3 Phase 3 Plan 03-06 — Native Multi-Token Prediction (MTP) in vMLX

**Author:** Antigravity Coordinator  
**Date:** 2026-09-20  
**Target Milestone:** v3 (Phase 3: Speculative Decoding & Acceleration Architectures)  
**Status:** PRE-REGISTERED  

---

## 1. Executive Summary & Core Motivation

Milestone v3 Phase 1 established serving dynamics, memory residency, and SSD streaming trade-offs for 35B MoE models (`Qwen3.6-35B-A3B`), while Phase 2 characterized conversational context scaling and quantized KV caches.

Phase 3 targets **Speculative Decoding & Acceleration Architectures**. DeepSeek-V3/V4 and Qwen3.6-35B introduce **Native Multi-Token Prediction (MTP)**, where an additional lightweight transformer layer predicts subsequent tokens during the main model's forward pass. While traditional speculative decoding requires a secondary draft model (which introduces independent memory bus traffic on Apple Silicon unified memory), Native MTP executes within the primary model's forward pass, reusing shared embeddings and representations.

vMLX 1.6.59 ships native runtime support for MTP on `qwen3_5_moe` (`native_mtp.py`, `mllm_batch_generator.py`), offering:
- Fixed draft depth configurations (`--native-mtp-depth <1..3> --native-mtp-depth-policy fixed`)
- Adaptive depth controller (`--native-mtp-depth-policy adaptive`)
- Autoregressive safety valve (`VMLX_NATIVE_MTP_AR_SAFETY=1`)
- Deterministic greedy enforcement (`--native-mtp-sampling-policy greedy-only`)

This pre-registered study executes the first rigorous single-variable benchmark of Native MTP on Apple Silicon, measuring real decode throughput speedup, token acceptance rates across depths, ITL distributions, prefill invariance, and memory residency.

---

## 2. Pre-Registered Hypotheses

- **H1 (Acceptance Rate Monotonic Degradation):** Speculative token acceptance rate ($\alpha$) will degrade monotonically with draft depth ($D=1 > D=2 > D=3$) due to error compounding across speculative draft steps:
  $$\alpha(D=1) > \alpha(D=2) > \alpha(D=3)$$
- **H2 (Decode Speedup on Structured Code vs Prose):** On structured code tasks (low lexical entropy), Native MTP (D=1 and D=2) will achieve a positive decode throughput speedup (>1.15× over base AR decode). On high-entropy reasoning/prose, speculative acceptance will drop, narrowing the decode advantage.
- **H3 (TTFT Invariance):** Because Native MTP operates strictly during autoregressive token generation and not during initial prompt prefill, TTFT will remain invariant ($\pm 5\%$) across all MTP depths and policies vs baseline AR decode on identical prompt tokens.
- **H4 (Draft Head Memory Residency):** The dedicated MTP transformer layer (~600 MB of safetensors) and associated speculative draft state will introduce a small, bounded memory footprint increase (<1.0 GB RAM) over baseline non-MTP serving.
- **H5 (Adaptive Safety Valve Protection):** The adaptive depth policy (`--native-mtp-depth-policy adaptive`) will dynamically regulate draft depth and prevent throughput degradation below the base AR decode floor under variable entropy.

---

## 3. Experimental Architecture & Single-Variable Isolation

In accordance with the project's inviolable rule—**Vary one thing at a time**:
- **Hardware Platform:** Apple M2 Max (12-core CPU, 30-core GPU, 64 GB Unified Memory, 400 GB/s bandwidth).
- **Model Artifact:** `Jundot/Qwen3.6-35B-A3B-oQ4-mtp` (40 base layers, 256 experts, 8 active, + 1 MTP transformer layer, 42 MTP safetensor keys).
- **Runtime:** `vmlx` 1.6.59 hosted on port 8000.
- **Fixed Flags:** `--port 8000 --stream-interval 1 --continuous-batching --no-jit`.
- **Sampling Parameters:** Temperature 0.0 pinned, seed pinned, greedy decoding.
- **Variable Axis:** Native MTP configuration.

### Tested Configurations (Arms)
| Arm ID | Configuration Name | Model | MTP Flags |
|---|---|---|---|
| **Arm 1** | Baseline AR (No MTP) | `Jundot/...-oQ4-mtp` | `--disable-native-mtp` |
| **Arm 2** | Native MTP Depth 1 (Fixed) | `Jundot/...-oQ4-mtp` | `--native-mtp-depth 1 --native-mtp-depth-policy fixed --native-mtp-sampling-policy greedy-only` |
| **Arm 3** | Native MTP Depth 2 (Fixed) | `Jundot/...-oQ4-mtp` | `--native-mtp-depth 2 --native-mtp-depth-policy fixed --native-mtp-sampling-policy greedy-only` |
| **Arm 4** | Native MTP Depth 3 (Fixed) | `Jundot/...-oQ4-mtp` | `--native-mtp-depth 3 --native-mtp-depth-policy fixed --native-mtp-sampling-policy greedy-only` |
| **Arm 5** | Native MTP Adaptive (D=3) | `Jundot/...-oQ4-mtp` | `--native-mtp-depth 3 --native-mtp-depth-policy adaptive --native-mtp-sampling-policy greedy-only` |
| **Arm 6** | Base Model Control | `Jundot/...-oQ4` (no MTP weights) | `--disable-native-mtp` |

---

## 4. Workloads & Evaluation Prompts

Each configuration is evaluated against 3 distinct prompt archetypes with max 128 output tokens:
1. **Workload A (Structured Code):**
   *Prompt:* `"Write a Python function `fibonacci_memo(n: int) -> int` that computes the nth Fibonacci number using recursion and an explicit dictionary memoization cache. Include docstring and type hints."*
   *Entropy:* Low. Grammar and Python syntax are highly constrained.
2. **Workload B (Reasoning & Philosophy):**
   *Prompt:* `"Analyze the Ship of Theseus paradox from the perspective of mereological essentialism versus four-dimensionalism (worm theory). Summarize the key metaphysical distinction."*
   *Entropy:* High. Abstract reasoning with diverse conceptual vocabulary.
3. **Workload C (Technical Architecture):**
   *Prompt:* `"Explain how Apple Silicon unified memory architecture eliminates redundant PCIe transfers between the CPU and GPU during LLM decode steps."*
   *Entropy:* Medium. Technical systems explanation.

---

## 5. Measurement Methodology & Metrics

For every cell run:
1. **Quiet Machine Protocol:** No background processes, downloads, or concurrent test runs. Ports 8000, 8080, 8081, 8100, 1337 swept prior to start.
2. **Memory Footprint:** Measured via `footprint -p <pid>` (Apple `phys_footprint`) during active generation.
3. **Time to First Token (TTFT):** Wall-clock duration from request dispatch to first received content token.
4. **Inter-Token Latency (ITL / TPOT):** Per-token delta timestamps recorded across streaming SSE deltas; P50, P90, P99 calculated.
5. **Decode Throughput:** Generation tokens divided by generation span (tok/s).
6. **MTP Telemetry Extraction:** Querying vMLX `/stats` and parsing batch generator MTP telemetry (`cycles`, `drafted_tokens`, `accepted_tokens`, `acceptance_rate`, `cycles_by_depth`).
7. **Coherence Gate:** Output verified for semantic coherence and free of repetitive degradation or token salad.
