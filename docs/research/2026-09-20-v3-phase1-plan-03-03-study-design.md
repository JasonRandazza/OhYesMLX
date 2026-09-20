# Plan 03-03 Study Design: Expert Streaming under High Memory Pressure

**Status:** PRE-REGISTERED  
**Date:** 2026-09-20  
**Phase:** Milestone v3 Phase 1 (Large-Model Scaling: 35B MoE Class on Apple Silicon)  
**Author:** Antigravity (Coordinator)  
**Target Hardware:** Apple Silicon M2 Max (12 CPU cores, 38 GPU cores, 64 GB unified memory, 400 GB/s bandwidth)  
**Subject Model:** `mlx-community/Qwen3.6-35B-A3B-4bit` (40 layers, 256 experts, 8 active per token, 19.03 GiB safetensors)  

---

## 1. Abstract & Scope

In MoE architectures, parameter count is decoupled from compute cost: while `Qwen3.6-35B-A3B` contains 256 experts per layer across 40 layers, each token activates only 8 routed experts plus shared attention and expert blocks. Under resident serving, the entire 19.03 GiB weight matrix must reside continuously in unified memory, demanding ~20.5 GB of RAM. On memory-constrained Apple Silicon hardware (16 GB, 24 GB, or 36 GB Macs), or under high memory pressure on 64 GB Macs, fully resident serving causes memory exhaustion (OOM) or catastrophic swap paging.

To address this ceiling, runtimes implement SSD-based expert offloading:
1. **OptiQ (`mlx-optiq` 0.5.6):** Implements dynamic SSD expert streaming via `StreamingQuantizedSwitchLinear` and concurrent `os.pread` (queue depth 24), streaming active expert weight rows on demand from safetensors while keeping backbone weights resident. Features an optional in-RAM LRU cache (`--stream-experts-cache`) and an auto-activation threshold (`model_disk_bytes > 0.70 * total_RAM`).
2. **vMLX (1.6.59):** Implements dynamic SSD streaming via **FlashMoE** (`--flash-moe`), which swaps MoE blocks for `FlashMoEBlock` with an LRU slot bank (`--flash-moe-slot-bank 64`) and multi-worker `pread` I/O. In parallel, vMLX offers **Smelt** (`--smelt`), a static partial-expert loading mechanism that keeps only top $N\%$ of experts resident in RAM (`--smelt-experts 50`).

This study is the single-variable benchmark evaluating the exact trade-offs of SSD-based expert streaming vs resident serving on a 35B MoE model. We measure memory footprint reduction, decode throughput collapse, prefill latency scaling, LRU cache effectiveness, and output coherence.

---

## 2. Pre-Registered Hypotheses

### H1: Backbone-Only Resident Memory Floor (75–80% Footprint Reduction)
Under full SSD expert streaming (OptiQ `--stream-experts`, vMLX `--flash-moe`), the process physical memory footprint (`phys_footprint_mb`) will drop from **~20.5 GB** down to **~3.5–5.0 GB**, matching the static 2.28 GB backbone (attention, embeddings, shared experts, layer norms) plus allocator headroom. Expert streaming achieves an ~75% to 80% unified memory reduction, enabling 35B MoE models to execute on 8 GB–16 GB memory ceilings.

### H2: Decode Throughput Collapse (6× to 10× Disk-Bound Penalty)
Fetching active expert weights on demand over NVMe APFS introduces random read latency and kernel dispatch overhead for 320 expert slices per token (40 layers × 8 active experts). Steady-state decode throughput will collapse from resident baseline levels (**56–62 tok/s**) down to **6–10 tok/s**, directly constrained by NVMe random I/O latency and Metal buffer staging rather than unified memory bandwidth.

### H3: In-RAM Expert Cache Ineffectiveness Under High Routing Entropy
In a 256-expert architecture with 8 active experts per token, routing distributions exhibit high entropy across natural language sequences. Introducing an in-RAM LRU cache (OptiQ `--stream-experts-cache 64`, vMLX `--flash-moe-slot-bank 64`) will yield a low cache hit rate (<15%) on standard generation, resulting in negligible throughput improvement (<5%) while adding LRU synchronization overhead.

### H4: Smelt vs FlashMoE Architectural Trade-off
In vMLX, static partial loading (`--smelt --smelt-experts 50`) will maintain near-resident decode throughput (**45–55 tok/s**) at a 50% memory reduction (~10–11 GB RAM), because resident experts bypass SSD reads entirely. However, queries that route to omitted experts will suffer output degradation or fallback behavior. Conversely, dynamic streaming (`--flash-moe`) will preserve 100% numerical and lexical coherence identical to resident serving, at the expense of disk-bound throughput.

### H5: Static 70% RAM Heuristic Fragility
OptiQ's `--stream-experts auto` condition (`model_disk_bytes > 0.70 * total_RAM`) is statically evaluated at startup against total installed RAM rather than free/available RAM. On a 64 GB Mac, the auto threshold is $0.70 \times 64 = 44.8\text{ GB}$. Because `Qwen3.6-35B-A3B-4bit` occupies 19.03 GiB (42.5% of threshold), OptiQ will **never** automatically engage expert streaming on 64 GB hardware, even when background memory pressure leaves < 5 GB of free RAM. When memory is constrained by concurrent host workloads, unpinned OptiQ will suffer sudden OS SIGKILL (OOM) rather than gracefully falling back to streaming.

---

## 3. Experimental Matrix

All cells test the identical model checkpoint: `mlx-community/Qwen3.6-35B-A3B-4bit` (19.03 GiB safetensors, verified streamable by both OptiQ's `moe_stream` and vMLX's `ExpertIndex`).

| Cell ID | Runtime | Execution Mode | Key Flags | Expected RAM | Expected Decode | Coherence Target |
|:---|:---|:---|:---|:---:|:---:|:---:|
| `C1` | **OptiQ** | Resident Control | `--max-context off --no-stream-experts` | ~20.5 GB | ~56–58 tok/s | Baseline PASS |
| `C2` | **OptiQ** | SSD Streaming | `--max-context off --stream-experts` | ~3.8–4.8 GB | ~6–10 tok/s | Bit-exact PASS |
| `C3` | **OptiQ** | Streaming + LRU Cache | `--max-context off --stream-experts --stream-experts-cache 64` | ~4.5–6.0 GB | ~6–10 tok/s | Bit-exact PASS |
| `C4` | **vMLX** | Resident Control | `--no-jit --disable-native-mtp` | ~20.5 GB | ~61–63 tok/s | Baseline PASS |
| `C5` | **vMLX** | FlashMoE Streaming | `--no-jit --disable-native-mtp --flash-moe --flash-moe-slot-bank 64` | ~4.0–5.5 GB | ~7–11 tok/s | Bit-exact PASS |
| `C6` | **vMLX** | Smelt Partial Load | `--no-jit --disable-native-mtp --smelt --smelt-experts 50` | ~10.5–12.0 GB | ~45–55 tok/s | Semantic check |

---

## 4. Controlled Parameters & Standing Rules

1. **Vary One Thing at a Time:**
   - Within OptiQ (Cells C1–C3): Runtime, weights, and sampling parameters are held constant; only the expert streaming / cache configuration varies.
   - Within vMLX (Cells C4–C6): Runtime, weights, and sampling parameters are held constant; only the memory offload mode (Resident vs FlashMoE vs Smelt) varies.
2. **Fixed Sampling:**
   - `temperature = 0.0`, `seed = 0`, greedy decoding.
   - Standard fixed prompt: `"Explain the architecture of Mixture of Experts (MoE) neural networks in 50 words."` (50–64 tokens generated).
3. **Port & Process Isolation:**
   - Exactly one server process resident at any time.
   - Ports swept and verified free between runs (OptiQ: 8080, vMLX: 8000).
   - 10-second quiet cooldown between cells.
4. **Residency Attribution:**
   - `phys_footprint_mb` sampled via `footprint -p <pid>`.
   - `vmmap` per-region accounting separating `IOAccelerator (graphics)` from anonymous heap and mapped file pages.

---

## 5. Artifacts & Deliverables

1. **Probe Script:** `scripts/probe_expert_streaming_35b.py` executing all 6 cells with automated memory sampling, latency measurement, and coherence verification.
2. **Raw Evidence:** `results/plan-03-03/streaming_results.json`.
3. **Research Report:** `docs/research/2026-09-20-expert-streaming-high-memory-pressure.md` analyzing findings across H1–H5 and establishing operational serving guidance for memory-constrained Apple Silicon environments.
