# Milestone v3 Phase 1 — Plan 03-02 Study Design: Cold vs Warm Page Cache Load & Memory Residency Attribution

Date: 2026-09-20. **Design only. No measurements in this document.** No runtime was started, no model was loaded, no tensor was read. Every figure below is either derived from the repository's verified baselines, computed from the local filesystem, or quoted from prior research artifacts.

Subject: `Qwen3.6-35B-A3B` in `stock4bit` (`mlx-community/Qwen3.6-35B-A3B-4bit`, 20,429,169,720 bytes = 19.026 GiB) across the five local serving runtimes driven by OhYesMLX (`mlxlm`, `omlx`, `optiq`, `vmlx`, `osaurus`).

---

## 1. Executive Summary & Problem Statement

### 1.1 The Problem

In Plan 03-01 ([`docs/research/2026-09-20-35b-moe-serving.md`](file:///Users/jrazz/Dev/active/OhYesMLX/docs/research/2026-09-20-35b-moe-serving.md)), OhYesMLX evaluated the 35B MoE class for the first time across 16 serving cells. While decode throughput, TTFT, and prefill scaling conformed cleanly to the routed architecture (H1–H3), two fundamental measurement questions remained un-attributed:

1. **Load Time Ambiguity (`cold_load_s` vs OS Page Cache vs Lazy Loading):**
   Reported `cold_load_s` across runtimes ranged from 1.4s (Osaurus) to 12.1s (vMLX). However, prior research on 4B models ([`2026-09-15-cold-load-is-not-one-quantity.md`](file:///Users/jrazz/Dev/active/OhYesMLX/docs/research/2026-09-15-cold-load-is-not-one-quantity.md)) established that:
   - A runtime loading weights lazily (such as oMLX) appears fast at startup because it only starts an HTTP listener, then hides the multi-gigabyte weight load inside Request #1.
   - A runtime loading weights after prior disk reads benefits silently from the macOS unified buffer cache, where clean file pages remain resident in RAM.
   At 35B scale (~19 GiB weights), we do not know how much of `cold_load_s` represents true APFS NVMe disk bandwidth versus OS buffer cache re-mapping, nor how many seconds lazy runtimes hide in the first inference request.

2. **Memory Residency Attribution (The 0.74× Osaurus Reporting Divergence):**
   In Plan 03-01, Osaurus reported a `phys_footprint` of **12.3–15.4 GB** (73.6% of weight bytes), while `mlxlm`, `omlx`, `optiq`, and `vmlx` reported **19.5–27.6 GB** (100%–105% of weight bytes).
   Phase 5 research ([`2026-09-16-footprint-is-not-one-quantity.md`](file:///Users/jrazz/Dev/active/OhYesMLX/docs/research/2026-09-16-footprint-is-not-one-quantity.md)) proved on small models that Osaurus places weights into **wired GPU pages** (`IOAccelerator`), which `phys_footprint` does not charge to anonymous process memory, while other runtimes allocate anonymous unified memory. At 35B scale, where weights consume 30% of unified memory, this discrepancy must be dissected and quantified with exact region accounting.

### 1.2 The `mincore` Breakthrough

Previous attempts to study page cache effects were constrained by macOS Sonoma/Sequoia restricting the `purge` command to root (`sudo purge`). 

In formulating Plan 03-02, we discovered that POSIX `libc.mincore` via Python `ctypes` can inspect the exact physical residency of memory-mapped file pages in the macOS unified buffer cache without requiring elevated permissions:
- For any file path, `mincore` inspects page-by-page residency (16 KiB pages on Apple Silicon).
- It reports the exact percentage ($0.00\%$ to $100.00\%$) of weight bytes resident in RAM before and after any runtime starts.
- Initial validation on `models--mlx-community--Qwen3.6-35B-A3B-4bit` confirms that after a quiet period, the 19.00 GiB weight files are currently at **0.00% residency** (322,766 of 322,766 pages cold).

This gives OhYesMLX an objective, non-invasive instrument to verify true cold vs warm page cache states.

---

## 2. Subject & Variables

### 2.1 The Constant: Format Held Constant
To isolate runtime behavior, the quantization format and model are held strictly constant:
- **Model:** `Qwen3.6-35B-A3B` (35.95 B total parameters, 256 routed experts, 8 routed/token, hybrid attention)
- **Artifact:** `mlx-community/Qwen3.6-35B-A3B-4bit` (revision `38740b84`, 20,429,169,720 bytes across 4 safetensors shards)
- **Status:** Verified 100% loadable and coherent across all 5 serving runtimes in Plan 03-01.

### 2.2 The Variables
1. **Runtime Variable (Primary Axis):**
   - `mlxlm`: Stock `mlx_lm.server` 0.31.3
   - `omlx`: oMLX 0.6.4
   - `optiq`: OptiQ 0.5.6 (pinned `--max-context off --no-stream-experts`)
   - `vmlx`: vMLX 1.6.59 (pinned `--no-jit --disable-native-mtp`)
   - `osaurus`: Osaurus 0.25.9 (pinned `modelIdleResidencyPolicy.seconds: 900`, `cache.prefix.enabled: false`)

2. **Cache Condition Variable (Secondary Axis):**
   - **Condition Cold:** `mincore` verifies $0.0\%$ weight pages in RAM prior to startup.
   - **Condition Warm:** `mincore` verifies $>95.0\%$ weight pages in RAM prior to startup (measured immediately following the cold run).

---

## 3. Pre-Registered Hypotheses

### H1: True Storage I/O vs Page-Table Remapping
When loading 19.026 GiB of weights:
- **Under Condition Cold (0% cache):** Load time is bounded by Apple Silicon internal APFS NVMe read throughput (~3.5–5.0 GB/s on M2 Max). True cold load time will require **$\ge 3.8\text{ s}$** across all runtimes that load weights eagerly. Any runtime reporting $<3.0\text{ s}$ under Condition Cold is exhibiting lazy loading.
- **Under Condition Warm (>95% cache):** Load time is bounded by virtual memory page-table creation and tensor graph initialization rather than disk I/O. Eager runtimes will see load time drop to **$1.0\text{--}2.5\text{ s}$** (a $2\times$ to $4\times$ speedup).

### H2: Lazy Load First-Request Penalty Scales with Parameters
oMLX reports an artificially low startup time by deferring model weight loading until the first HTTP completion request arrives:
- In v1 ([`docs/research/2026-09-15-cold-load-is-not-one-quantity.md`](file:///Users/jrazz/Dev/active/OhYesMLX/docs/research/2026-09-15-cold-load-is-not-one-quantity.md)), oMLX hid $+3.51\text{ s}$ inside request #1 on a 3.0 GiB model (~1.17 s/GB).
- On `Qwen3.6-35B-A3B-4bit` (19.03 GiB), oMLX will hide **$\ge 12.0\text{ s}$** inside Request #1 ($t_{\text{req1}} - t_{\text{req2}} \ge 12.0\text{ s}$).
- All other runtimes (`mlxlm`, `optiq`, `vmlx`, `osaurus`) load eagerly, exhibiting first-request deltas of $\le 1.0\text{ s}$ (representing one-shot Metal shader compilation / warmup).

### H3: Metal Wired Allocation Accounts for the 0.74× Footprint Divergence
Per-region `vmmap` analysis and system-wide `vm_stat` accounting will confirm:
- `osaurus` allocates the 19.03 GiB model into `IOAccelerator (graphics)` wired device memory pages (`wired_mb`). Because macOS `phys_footprint` treats wired device allocations differently from dirty anonymous memory, Osaurus reports a process footprint substantially below the weight bytes (~12–15 GB).
- `mlxlm`, `omlx`, `optiq`, and `vmlx` allocate weights into dirty anonymous memory, resulting in `phys_footprint` tracking weight bytes directly ($19.5\text{--}27.6\text{ GB}$).
- Total system wired memory (`vm_stat: Pages wired down`) will increase by $\approx 19\text{ GB}$ during the Osaurus residency, proving that the physical memory consumption is identical despite the lower reported process footprint.

### H4: Host Memory Headroom & Clean Reclamation
On a 64 GB unified memory host running in isolation:
- Loading the 19.03 GiB model will leave $\ge 35\text{ GB}$ of available unified memory headroom.
- Zero swapouts will occur during any test.
- Upon process termination and port sweep, all memory (both anonymous and wired `IOAccelerator` pages) will be completely reclaimed to the OS, with system available memory returning to baseline $\pm 1.0\text{ GiB}$.

---

## 4. Test Matrix & Protocol

### 4.1 Measurement Sequence per Runtime
For each of the 5 runtimes:
1. **Pre-flight Audit:**
   - Verify ports 8000, 8080, 8081, 8100, 1337 are free.
   - Run `mincore` over all 4 shards of `stock4bit`. Record baseline page cache residency percentage ($R_{\text{pre}}$).
   - Sample host `vm_stat` (free, wired, active, inactive, anonymous, file-backed).
2. **Cold Load & Execution:**
   - Launch runtime handle. Time $t_{\text{spawn}} \to t_{\text{ready}}$ as `cold_load_s`.
   - Send Request #1 (prompt: "Say the word ready.", `max_tokens=8`, temp=0.0). Record $t_{\text{req1}}$.
   - Send Request #2 (identical prompt). Record $t_{\text{req2}}$.
   - Send Request #3 (identical prompt). Record $t_{\text{req3}}$.
   - Sample process memory: `phys_footprint_mb`, `vmmap --summary`, and per-region `vmmap` breakdown (`IOAccelerator`, `mapped file`, `anonymous`).
   - Sample host `vm_stat` under full residency.
   - Stop runtime handle. Confirm port released.
   - Run `mincore` to record post-load cache residency ($R_{\text{post}}$).
3. **Warm Reload & Execution:**
   - Immediately restart runtime handle on the now-cached artifact ($R \approx 100\%$).
   - Record warm `cold_load_s`.
   - Send Request #1 and Request #2. Record latencies.
   - Stop runtime handle and confirm port released.

---

## 5. Artifacts and Deliverables

1. `scripts/probe_page_cache_35b.py`: Automated probe executing the protocol above across candidate runtimes.
2. `results/plan-03-02/`: Observation logs containing raw JSON observations and `vmmap` outputs.
3. `docs/research/2026-09-20-cold-warm-load-attribution-35b.md`: Published findings report addressing H1–H4.
4. `.paul/STATE.md`: Recording of Decision 109 and phase progress updates.
