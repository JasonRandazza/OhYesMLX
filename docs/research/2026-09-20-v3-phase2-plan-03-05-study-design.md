# Plan 03-05 Study Design: Quantized KV Caches (FP8, INT4 vs FP16 at 16k and 32k Context)

**Status:** PRE-REGISTERED  
**Date:** 2026-09-20  
**Phase:** Milestone v3 Phase 2 (Context Scaling & Conversational Dynamics)  
**Author:** Antigravity (Coordinator)  
**Target Hardware:** Apple Silicon M2 Max (12 CPU cores, 38 GPU cores, 64 GB unified memory, 400 GB/s bandwidth)  
**Subject Model:** `brainworkup/Llama-3.1-8B-oQ4` (32 layers, 32 query heads, 8 KV heads, head dimension 128, 128k native context window, 4.60 GB safetensors)  
**Prompt Fixture:** `ohyesmlx/longtext.md` (60,701 tokens, sha256 `3ed2c160...a8a3`) cut to 16,384 and 32,768 tokens via `cli.sized_prompt`  

---

## 1. Abstract & Scope

At long context lengths (16,384 and 32,768 tokens), the Key-Value (KV) cache becomes a dominant consumer of both physical unified memory and memory bus bandwidth on Apple Silicon:
- For an 8B GQA architecture (32 layers, 8 KV heads, head dimension 128):
  $$\text{KV Bytes per Token} = 32 \times 2 \times 8 \times 128 \times 2 \text{ bytes (FP16)} = 131,072\text{ bytes} = 128\text{ KiB/token}$$
- At **16,384 tokens**, an unquantized FP16 KV cache consumes **2.147 GB** ($2.00\text{ GiB}$) of memory.
- At **32,768 tokens**, an unquantized FP16 KV cache consumes **4.295 GB** ($4.00\text{ GiB}$) of memory.

On unified memory architectures like Apple Silicon, where GPU compute shares memory bandwidth (400 GB/s on M2 Max) with KV cache and weight transfers, reading 4.3 GB of KV cache on every decode step introduces severe memory bandwidth contention:
- Model weights: ~4.6 GB (read every token step at batch size 1).
- FP16 KV Cache at 32k: 4.3 GB (read every token step).
- Total bandwidth demand per token: $\approx 8.9\text{ GB/step}$, roughly **doubling the memory traffic of generation** and cutting decode throughput significantly compared to short context.

To resolve this bandwidth and memory bottleneck, serving runtimes introduce online KV cache quantization:
1. **OptiQ (`optiq serve`):** Implements uniform `QuantizedKVCache` supporting `--kv-bits 8` (FP8) and `--kv-bits 4` (INT4) with streaming per-layer conversion and fused quantized SDPA (FlashAttention-2 N-tiling, avoiding score matrix materialization).
2. **vMLX (`vmlx serve`):** Implements `--kv-cache-quantization {none, q8, q4}` with group size 64.
3. **mlx-lm (`mlx_lm.server`):** Acts as the canonical stock FP16 control reference.

Plan 03-05 evaluates the exact single-variable trade-offs of KV cache quantization across 16k and 32k context windows, measuring physical memory reduction, decode throughput acceleration vs prefill overhead, and output coherence.

---

## 2. Pre-Registered Hypotheses

### H1: Exact Theoretical KV Memory Compression (50% and 75% Reduction)
Physical process footprint (`phys_footprint_mb`) at 32k context will accurately reflect theoretical KV tensor compression:
- FP16 Baseline: Model footprint (~5.2 GB) + ~4.3 GB KV $\approx$ **9.5 GB**.
- FP8 (q8 / bits=8): Model footprint + ~2.15 GB KV $\approx$ **7.35 GB** (~2.15 GB unified memory savings, 50% KV reduction).
- INT4 (q4 / bits=4): Model footprint + ~1.07 GB KV $\approx$ **6.27 GB** (~3.22 GB unified memory savings, 75% KV reduction).

### H2: Decode Throughput Acceleration at 32k Context Length (+10% to +25%)
At 32k context length, decode throughput (tok/s) under INT4 KV cache will be significantly **faster (+10% to +25% tok/s)** than under FP16 KV cache. Because reading the KV cache at 32k requires transferring 4.29 GB per step in FP16, compressing the KV cache to 1.07 GB per step reduces total memory bus traffic from ~8.9 GB/step to ~5.7 GB/step, directly relieving memory bandwidth saturation on Apple Silicon decode.

### H3: Prefill Latency Quantization Tax (+3% to +10% TTFT)
Time to First Token (TTFT) at 16k and 32k will incur a modest prefill tax (+3% to +10%) in INT4 and FP8 relative to unquantized FP16, caused by online quantization kernel execution and scale-factor computation during prompt prefill processing.

### H4: Complete Output Coherence Floor (100% PASS)
All quantized configurations (FP8, INT4) across 16k and 32k contexts will pass the coherence floor (`coherence.is_coherent()`, 100% PASS, 0 token salad failures, 0 repetition collapse), confirming that 4-bit and 8-bit KV quantization preserves attention dynamics and lexical integrity at 32k context on Apple Silicon.

### H5: OptiQ Fused SDPA Advantage Over Generic Dequantization
In OptiQ, fused quantized SDPA (FlashAttention-2 N-tiling) will achieve higher decode throughput at 32k in INT4 mode compared to non-fused dequantization paths, verifying the advantage of specialized Metal kernel tiling for quantized KV states.

---

## 3. Experimental Matrix

All configurations evaluate `brainworkup/Llama-3.1-8B-oQ4` (128k native context window, 4.60 GB safetensors, verified GQA architecture) across two pinned context lengths: **16,384 tokens** and **32,768 tokens**.

| Cell ID | Runtime | KV Precision | CLI Flags | Target Context | Expected KV RAM | Expected Decode | Coherence |
|:---|:---|:---|:---|:---:|:---:|:---:|:---:|
| `C1-16k` | **OptiQ** | FP16 (Baseline) | `--max-context off` | 16,384 | ~2.15 GB | Baseline | PASS |
| `C1-32k` | **OptiQ** | FP16 (Baseline) | `--max-context off` | 32,768 | ~4.29 GB | Baseline (slow) | PASS |
| `C2-16k` | **OptiQ** | FP8 (8-bit) | `--max-context off --kv-bits 8` | 16,384 | ~1.07 GB | +5–10% | PASS |
| `C2-32k` | **OptiQ** | FP8 (8-bit) | `--max-context off --kv-bits 8` | 32,768 | ~2.15 GB | +10–15% | PASS |
| `C3-16k` | **OptiQ** | INT4 (4-bit) | `--max-context off --kv-bits 4` | 16,384 | ~0.54 GB | +10–15% | PASS |
| `C3-32k` | **OptiQ** | INT4 (4-bit) | `--max-context off --kv-bits 4` | 32,768 | ~1.07 GB | +15–25% | PASS |
| `C4-16k` | **vMLX** | FP16 (Baseline) | `--kv-cache-quantization none` | 16,384 | ~2.15 GB | Baseline | PASS |
| `C4-32k` | **vMLX** | FP16 (Baseline) | `--kv-cache-quantization none` | 32,768 | ~4.29 GB | Baseline (slow) | PASS |
| `C5-16k` | **vMLX** | FP8 (q8) | `--kv-cache-quantization q8` | 16,384 | ~1.07 GB | +5–10% | PASS |
| `C5-32k` | **vMLX** | FP8 (q8) | `--kv-cache-quantization q8` | 32,768 | ~2.15 GB | +10–15% | PASS |
| `C6-16k` | **vMLX** | INT4 (q4) | `--kv-cache-quantization q4` | 16,384 | ~0.54 GB | +10–15% | PASS |
| `C6-32k` | **vMLX** | INT4 (q4) | `--kv-cache-quantization q4` | 32,768 | ~1.07 GB | +15–25% | PASS |
| `C7-16k` | **mlxlm** | FP16 (Control) | Standard stock `mlx_lm.server` | 16,384 | ~2.15 GB | Reference | PASS |
| `C7-32k` | **mlxlm** | FP16 (Control) | Standard stock `mlx_lm.server` | 32,768 | ~4.29 GB | Reference | PASS |

---

## 4. Controlled Parameters & Standing Rules

1. **Vary One Thing at a Time:** Model weights (`Llama-3.1-8B-oQ4`), prompt cut source (`longtext.md`), and sampling parameters are held strictly identical; only the KV cache precision (FP16 vs FP8 vs INT4) varies within each runtime.
2. **Fixed Sampling Parameters:** `temperature = 0.0`, `seed = 0`, greedy decoding, `max_tokens = 64`.
3. **Quiet Machine Rule:** Exactly one serving runtime process resident at any time.
4. **Port Sweep & Verification:** Ports 8000, 8080, 8081, 8100, 1337 swept and verified clean before and after every cell.
5. **Memory & Coherence Disciplines:**
   - Physical memory sampled via `sample.phys_footprint_mb(pid)` at pre-load, post-load, and peak execution.
   - Text output validated via `coherence.is_coherent()`.

---

## 5. Artifacts & Deliverables

1. **Order Specification:** `.paul/orders/plan-03-05-spec.md`
2. **Study Design:** `docs/research/2026-09-20-v3-phase2-plan-03-05-study-design.md`
3. **Probe Script:** `scripts/probe_kv_quant.py`
4. **Raw Benchmark Data:** `results/plan-03-05/kv_quant_results.json`
5. **Research Report:** `docs/research/2026-09-20-quantized-kv-caches.md`
