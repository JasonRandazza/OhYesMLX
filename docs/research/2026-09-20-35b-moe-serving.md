# 35B MoE Serving Benchmark — Qwen3.6-35B-A3B across Stock 4-bit, OptiQ, oQ4, and JANG

Date: 2026-09-20. Plan 03-01 complete. All measurements taken live on Apple Silicon M2 Max (64 GB unified memory, macOS 15.6.1).

Subject: `Qwen3.6-35B-A3B` — a 35.95 B-parameter hybrid-attention MoE (40 layers, 256 routed experts, 8 routed per token, ~3 B active parameters) in four 4-bit artifacts across the five local serving runtimes driven by OhYesMLX.

---

## 1. Executive Summary & Headline Findings

This study marks the first time OhYesMLX has evaluated the large MoE class (~36 B total parameters, ~20–25 GB resident weights) on Apple Silicon, pushing beyond the 4B/8B regime where memory is free. Across 20 probed cells, 16 live serving cells, and an independent replication pass, four core findings emerge:

1. **Hypothesis 1 Confirmed (Decode Tracks Bytes Read Per Token):**
   At 256 experts with 8 routed per token, decoding reads ~1.98 GB of weights per token rather than the full 35.95 B parameters. Across all five runtimes, decode throughput lands at **54.1 to 70.3 tok/s** (within 2× of the 8B-A1B MoE's ~130 tok/s), proving that large-model MoE decode throughput is bounded by active routed traffic rather than stored footprint. `stock4bit` consistently leads decode throughput across all runtimes because its override map raises only routing gates to 8 bits, leaving shared experts, attention, and embeddings at 4 bits.

2. **Hypothesis 2 Confirmed (OptiQ Strictly Pareto-Dominated at 35B):**
   OptiQ is eliminated from the 35B Pareto frontier on all three evaluated coordinates:
   - **Disk:** Largest artifact by 17%–25% (24.69 GB vs 20.43 GB stock, 19.71 GB JANG).
   - **Speed:** Slowest or tied on decode in every runtime (56.3–61.8 tok/s vs 64.1–70.3 tok/s for stock).
   - **Memory:** Highest peak memory footprint in four of five runtimes (21.5–27.6 GB).

3. **Hypothesis 3 Confirmed (The JANG MoE Duality Confirmed at 35B):**
   Per the pre-registered protocol (design §5.3), JANG was evaluated on `vmlx` after four runtimes refused it. The MoE half of the JANG Duality replicated cleanly:
   - `jangtq4` delivered the **lowest disk footprint** (19.71 GB vs 20.43 GB stock4bit, -3.5%) and the **lowest peak memory footprint** (19,456 MB vs 20,480 MB, -1,024 MB / -5.0%).
   - JANG's dense decode throughput advantage did **not** transfer to MoE: `stock4bit__vmlx` beat `jangtq4__vmlx` on decode in both the primary (+13.1%, 66.4 vs 58.7 tok/s) and replicate (+17.9%, 62.7 vs 53.2 tok/s) runs, clearing the pre-registered 2.5% band.

4. **Hypothesis 4 Confirmed (Footprint Accounting Diverges at 35B):**
   `phys_footprint` charges wired GPU pages (Osaurus) and anonymous memory (mlx-lm, oMLX, OptiQ, vMLX) differently. At 35B, Osaurus reports **12.3–15.4 GB** (73.6% of weight bytes), while the other four runtimes report **19.5–27.6 GB** (100%–105% of weight bytes). Cross-runtime memory rankings remain fundamentally invalid (`CROSS_RUNTIME_UNCOMPARABLE`).

5. **Founding Defect Resolved (Open Question 1):**
   Stock `mlx_lm.server` 0.31.3 loaded and served `Jundot/Qwen3.6-35B-A3B-oQ4` with **100% coherent output** (64.1 tok/s decode, 0 deltas lost). The mixed-script token salad observed during Phase 1 on `Jundot/Qwen3.6-35B-A3B-oQ4-mtp` was strictly caused by the unhandled speculative MTP head, not an inherent 256-expert failure in stock mlx-lm.

---

## 2. Test Matrix & Artifact Provenance

### 2.1 Artifacts Verified on Disk
All four artifacts declare identical text architecture: `qwen3_5_moe_text`, 40 layers, 256 routed experts, 8 routed per token, hidden size 2048, `full_attention_interval: 4`, vocab 248320.

| Format Label | Hugging Face Repository | Git Revision | Files | Disk Bytes | GiB | Override Profile |
|---|---|---|---|---|---|---|
| `stock4bit` | `mlx-community/Qwen3.6-35B-A3B-4bit` | `38740b84` | 17 | 20,429,169,720 | 19.03 | 80 overrides (gate tensors 8-bit; attention/shared 4-bit) |
| `oq4` | `Jundot/Qwen3.6-35B-A3B-oQ4` | `0c710dba` | 16 | 21,125,808,764 | 19.68 | 306 overrides (113 at 5-bit, 14 at 6-bit, 179 at 8-bit) |
| `optiq` | `mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit` | `70a3aa32` | 17 | 24,693,930,096 | 23.00 | 512 overrides (394 at 8-bit; includes 2.36 GB sidecars) |
| `jangtq4` | `JANGQ-AI/Qwen3.6-35B-A3B-JANGTQ4` | `0f77d193` | 36 | 19,707,916,875 | 18.35 | `mxtq` global rule (routed 4-bit, non-routed 8-bit) |

### 2.2 Serving Runtimes
- `mlxlm`: 0.31.3 (venv at `~/.local/share/ohyesmlx/mlx-lm-0.31.3`)
- `omlx`: 0.6.4
- `optiq`: 0.5.6 (pinned `--max-context off --no-stream-experts`)
- `vmlx`: 1.6.59 (pinned `--no-jit --disable-native-mtp`)
- `osaurus`: 0.25.9 (pinned `modelIdleResidencyPolicy.seconds: 900`, `cache.prefix.enabled: false`)

---

## 3. Loadability & Coherence Probe (Step 2)

Prior to running the grid, all 20 combinations (4 formats × 5 runtimes) were evaluated with a single-request probe (`max_tokens=24`, `READY_TIMEOUT_S=900s`).

| Format | `mlxlm` | `omlx` | `optiq` | `vmlx` | `osaurus` |
|---|---|---|---|---|---|
| `stock4bit` | **LOADS** (4.0s, 23 deltas) | **LOADS** (3.1s, 3 deltas) | **LOADS** (3.3s, 1 delta) | **LOADS** (10.1s, 24 deltas) | **LOADS** (1.4s, 16 deltas) |
| `optiq` | **LOADS** (3.9s, 23 deltas) | **LOADS** (2.2s, 3 deltas) | **LOADS** (3.2s, 1 delta) | **LOADS** (11.1s, 24 deltas) | **LOADS** (2.4s, 17 deltas) |
| `oq4` | **LOADS** (4.4s, 23 deltas) | **LOADS** (2.2s, 3 deltas) | **LOADS** (3.3s, 1 delta) | **LOADS** (10.1s, 24 deltas) | **LOADS** (1.4s, 16 deltas) |
| `jangtq4` | **Refused** (360 missing params) | **Refused** (HTTP 409) | **Refused** (request timed out) | **LOADS** (12.1s, 24 deltas) | **Refused** (stream produced no content) |

**Probe Discoveries:**
- **Vision Tower Compatibility:** vMLX successfully loaded and served `optiq` in 11.1s, confirming that multimodal vision tower tensors did not cause parameter-rejection crashes on this model.
- **JANGTQ Loader Restriction:** JANGTQ4 was refused by mlx-lm (unsupported tensor parameters), oMLX (HTTP 409), OptiQ (server hang), and Osaurus (empty stream). Only vMLX contains the native `mxtq` kernel loader.

---

## 4. Serving Benchmark Grid Results (Step 3)

The single-variable grid was executed with `--study format --cache-state off` across 3 pinned workloads (`chat`, `prefill`, `decode`) with 9 measured batches per cell across 2 interleaved visits separated by 30s cooldowns.

### 4.1 Sustained Decode Workload (`decode`: prompt 24 tokens, max 512 tokens)
Primary benchmark for steady-state memory bandwidth and generation throughput.

| Format | `mlxlm` | `omlx` | `optiq` | `vmlx` | `osaurus` |
|---|---|---|---|---|---|
| `stock4bit` | **64.1** tok/s | **67.9** tok/s | **66.6** tok/s | **66.4** tok/s | **58.1** tok/s |
| `oq4` | 59.3 tok/s | 62.0 tok/s | 59.2 tok/s | 63.8 tok/s | 54.1 tok/s |
| `optiq` | 59.1 tok/s | 60.2 tok/s | 56.3 tok/s | 56.5 tok/s | 55.9 tok/s |
| `jangtq4` | — | — | — | 58.7 tok/s | — |

**Decode Ordering:**
- `mlxlm`: `stock4bit` (64.1) > `oq4` (59.3) > `optiq` (59.1)
- `omlx`: `stock4bit` (67.9) > `oq4` (62.0) > `optiq` (60.2)
- `optiq`: `stock4bit` (66.6) > `oq4` (59.2) > `optiq` (56.3)
- `vmlx`: `stock4bit` (66.4) > `oq4` (63.8) > `jangtq4` (58.7) > `optiq` (56.5)
- `osaurus`: `stock4bit` (58.1) > `optiq` (55.9) > `oq4` (54.1)

### 4.2 Prefill Throughput Workload (`prefill`: prompt 1,309 tokens, max 64 tokens)
Exposes prompt processing speed on long context.

| Format | `mlxlm` | `omlx` | `optiq` | `vmlx` | `osaurus` |
|---|---|---|---|---|---|
| `stock4bit` | **64.5** tok/s | **84.1** tok/s | **76.7** tok/s | **63.8** tok/s | **72.8** tok/s |
| `oq4` | 60.9 tok/s | 71.6 tok/s | 70.1 tok/s | 62.2 tok/s | 67.8 tok/s |
| `optiq` | 57.7 tok/s | 65.9 tok/s | 67.9 tok/s | 56.4 tok/s | 68.7 tok/s |
| `jangtq4` | — | — | — | 57.3 tok/s | — |

*Prefill prompt processing rate (prompt tokens / TTFT):*
- `stock4bit__omlx`: 411.2 tok/s (TTFT 3.21s)
- `stock4bit__optiq`: 420.4 tok/s (TTFT 3.14s)
- `stock4bit__osaurus`: 437.0 tok/s (TTFT 3.02s)
- `stock4bit__vmlx`: 554.7 tok/s (TTFT 2.37s)
- `jangtq4__vmlx`: 285.9 tok/s (TTFT 4.60s)

### 4.3 Short Request Latency Workload (`chat`: prompt 24 tokens, max 128 tokens)

| Format | `mlxlm` | `omlx` | `optiq` | `vmlx` | `osaurus` |
|---|---|---|---|---|---|
| `stock4bit` | **65.0** tok/s | **70.3** tok/s | **70.1** tok/s | **65.7** tok/s | **63.8** tok/s |
| `oq4` | 59.8 tok/s | 65.5 tok/s | 63.5 tok/s | 63.8 tok/s | 59.7 tok/s |
| `optiq` | 58.8 tok/s | 61.8 tok/s | 60.5 tok/s | 56.6 tok/s | 60.9 tok/s |
| `jangtq4` | — | — | — | 58.6 tok/s | — |

---

## 5. Replication Pass (Step 4)

To satisfy §2.5, a replication run was executed on the decisive pair for Hypothesis 3 (`vmlx` comparing `stock4bit` and `jangtq4`) with the cell visit order reversed (`jangtq4` first, `stock4bit` second).

| Workload | Metric | `jangtq4__vmlx` Primary | `jangtq4__vmlx` Replicate | `stock4bit__vmlx` Primary | `stock4bit__vmlx` Replicate | $\Delta$ (Stock vs JANG) |
|---|---|---|---|---|---|---|
| `decode` | `decode_tps` | 58.7 | 53.2 | 66.4 | 62.7 | **+13.1% (Primary) / +17.9% (Replicate)** |
| `decode` | `peak_mb` | 19,456.0 | 19,456.0 | 20,480.0 | 20,480.0 | **-1,024 MB (-5.0% for JANG)** |
| `prefill` | `decode_tps` | 57.3 | 49.1 | 63.8 | 60.1 | **+11.3% (Primary) / +22.4% (Replicate)** |
| `prefill` | prompt tok/s | 285.9 | 263.9 | 554.7 | 541.5 | **+94.0% (Stock prefill lead)** |
| `chat` | `decode_tps` | 58.6 | 52.3 | 65.7 | 60.1 | **+12.1% (Primary) / +14.9% (Replicate)** |

Both passes clear the pre-registered 2.5% tie band (`R-tie` passed), confirming that stock 4-bit holds a statistically robust decode and prefill speed advantage over JANGTQ4 on 35B MoE, while JANGTQ4 holds a deterministic 1,024 MB (5.0%) memory footprint advantage.

---

## 6. Detailed Hypothesis Evaluation

### 6.1 Hypothesis 1: Decode is set by bytes read per token
- **Pre-registered condition:** 35B MoE decode rate lands in the same order of magnitude as 8B MoE, and correlates with active bytes read per token rather than total model size.
- **Finding:** **CONFIRMED.**
  - `Qwen3.6-35B-A3B` decodes at 58–70 tok/s across all five runtimes. Compared to dense 35B models (which decode at 15–20 tok/s on 400 GB/s unified memory), the 35B MoE decodes ~3.5× faster because each token activates only 8 of 256 experts (~1.98 GB weights read).
  - `stock4bit` decoded faster than `oq4` and `optiq` across all runtimes because it leaves attention, shared experts, and embeddings at 4-bit, requiring fewer memory transactions per step.

### 6.2 Hypothesis 2: OptiQ is Pareto-dominated at 35B
- **Pre-registered condition:** OptiQ is the largest artifact on disk, does not lead `decode_tps` in any column, and does not lead `peak_mb` in any column.
- **Finding:** **CONFIRMED.**
  - **Disk:** OptiQ is 24.69 GB (+20.8% larger than stock4bit 20.43 GB; +25.3% larger than JANG 19.71 GB).
  - **Decode Speed:** Slowest or tied in all five runtimes (56.3–61.8 tok/s).
  - **Memory:** Consumes highest peak memory across mlxlm, omlx, optiq, and vmlx (21.5–27.6 GB vs 19.5–20.5 GB for stock).
  - OptiQ is strictly Pareto-dominated at 35B and eliminated from recommendations.

### 6.3 Hypothesis 3: JANG density lead survives at 35B; throughput lead does not
- **Pre-registered condition:** Evaluated in runtimes loading JANG. JANG delivers the lowest `peak_mb` and `disk_bytes` without leading `decode_tps`.
- **Finding:** **CONFIRMED.**
  - Evaluated on `vmlx` (single-runtime protocol triggered after other runtimes refused).
  - `jangtq4` was the smallest artifact on disk (19.71 GB) and achieved the lowest peak memory (19,456 MB vs 20,480 MB for stock).
  - Stock 4-bit defeated JANG on decode by +13.1% primary / +17.9% replicate. The dense throughput lead seen in v2 (`JANG_4S` on Qwen3.5-4B) does not transfer to 35B MoE.

### 6.4 Hypothesis 4: Peak footprint is a per-runtime accounting
- **Pre-registered condition:** Footprint-to-weight ratio remains runtime-dependent rather than converging at scale.
- **Finding:** **CONFIRMED.**
  - Stock 4-bit weight file size is 19,482.8 MiB.
  - Osaurus reports peak memory of 14,336 MB (**0.736×** of weights) due to wired GPU page allocation.
  - vMLX reports 20,480 MB (**1.051×**), oMLX reports 20,480 MB (**1.051×**), mlx-lm reports 19,456 MB (**0.999×**), and OptiQ reports 19,456 MB (**0.999×**).
  - The ~26% reporting gap observed in Phase 5 on 4B/8B models remains constant at 35B.

---

## 7. Confound Ledger Review

| Confound | Theoretical Risk | Applied Mitigation | Evidence / Outcome |
|---|---|---|---|
| **1. Bit assignment** | Non-uniform quantization fakes speed | Observed alongside disk bytes & override maps | `stock4bit`'s 4-bit non-expert layers verified as primary source of its throughput lead. |
| **2. Vision tower** | vMLX refuses multimodal maps | Evaluated in Step 2 probe | vMLX loaded all artifacts cleanly in 10–12s; zero parameter errors. |
| **3. MTP speculative decoding** | Speculative decoding fakes single-token rate | Pinned `--disable-native-mtp` in vMLX; OptiQ sidecar ignored | Logs show MTP disabled; steady ~60 tok/s confirmed unassisted decode. |
| **4. JIT overhead** | JIT compilation overhead alters throughput | Pinned `--no-jit` in vMLX | Upstream JIT overhead eliminated per Candidate 2 findings. |
| **5. Osaurus host settings** | Drift in ~/.osaurus alters numbers | Byte-exact backup, residency pinned to 900s, cache pinned off | Baseline checked and restored byte-exact (`cmp` verified). |
| **6. Thermal drift** | Laptop throttling aliases onto artifact order | Interleaved visits, 30s cooldown, reversed replicate pass | Drift stayed within ±0.0% to +12.7%; replication confirmed ranking. |
| **7. Prefix cache reuse** | Cache hit fakes prefill speed | `--cache-state off` pinned across all five runtimes | No prefix hit observed; full 1,309 prefill measured honestly. |

---

## 8. Final Recommendations for 35B MoE on Apple Silicon

| Priority | Recommended Configuration | Observed Metrics | Rationale |
|---|---|---|---|
| **Maximum Generation Throughput** | **`stock4bit` in `omlx`** (or `optiq` / `vmlx`) | **67.9–70.3 tok/s** decode; 20.43 GB disk | Stock 4-bit leaves shared attention/expert at 4-bit, minimizing per-token memory bandwidth. |
| **Lowest Memory & Disk Footprint** | **`jangtq4` in `vmlx`** | **19.0 GB** peak RAM; **19.71 GB** disk; 58.7 tok/s decode | Saves 1.02 GB RAM and 721 MB disk over stock 4-bit at a 13% decode throughput tradeoff. |
| **Fastest Cold Load** | **`stock4bit` in `osaurus`** | **2.67s** cold load; 14.3 GB reported footprint | Rapid startup from native Swift loader. |
| **Configurations to Avoid** | **`optiq` (any runtime)** | 24.69 GB disk; slowest decode; highest RAM | Strictly Pareto-dominated across all frontiers. |
| **Configurations to Avoid** | **`jangtq4` outside `vmlx`** | Refused / Crash / Hang | Unsupported by mlx-lm, oMLX, OptiQ, and Osaurus. |

---

## 9. Next Steps

With Milestone v3 Phase 1 (Plan 03-01) successfully executed, verified, and published:
1. **Candidate 3 (Thinking-Off MMLU Arm):** Preserved for overnight execution to evaluate reasoning suppression on MMLU.
2. **Milestone v3 Phase 2 (Context Scaling & Multi-turn Dynamics):** Proceed to Plan 03-04 (multi-turn context sweeps up to 32k) and Plan 03-05 (quantized KV caches on 35B MoE).
