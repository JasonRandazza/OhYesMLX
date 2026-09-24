---
description: "OhYesMLX — milestone and phase structure"
type: Roadmap
about: "OhYesMLX"
---

# Roadmap: OhYesMLX

## Overview

Three studies, each varying exactly one thing, each publishable on its own. The format
axis leads because research found it is the genuinely unoccupied ground: every published
format comparison either changes the runtime too, is vendor self-reported, or measures
perplexity instead of task accuracy. The runtime axis follows, and cites `mlx-Chronos`
rather than pretending to be first. The third study is the one our own first spike handed
us.

## Current Milestone

**v3 — Large-Model Scaling, Context Dynamics & Public Release** (0.3.0)
Status: In Progress
Phases: 4 of 4 complete (Milestone v3 Complete)

| Phase | Name | Plans | Status | Completed |
|---|---|---|---|---|
| 1 | Large-Model Scaling (35B MoE Class) | 3 | **Complete** | 2026-09-20 |
| 2 | Context Scaling & Conversational Dynamics | 2 | **Complete** | 2026-09-20 |
| 3 | Speculative Decoding & Acceleration | 2 | **Complete** | 2026-09-20 |
| 4 | Public Distribution & Packaging (v1.0) | 2 | **Complete** | 2026-09-20 |

## Completed Milestones

**v2 — JANG Study and Accuracy Scoring** (0.2.0)
Status: Complete (2026-09-19)
Phases: 2 of 2 complete

| Phase | Name | Plans | Status | Completed |
|---|---|---|---|---|
| 1 | Track 1: The JANG Study | 3 | **Complete** | 2026-09-17 |
| 2 | Track 2: Accuracy Scoring (lm-evaluation-harness) | 4 | **Complete** | 2026-09-19 |

**v1 — Format axis on small models** (0.1.0)
Status: Complete (2026-09-16)
Phases: 7 of 7 complete

## v1 Phases (Archive)

| Phase | Name | Plans | Status | Completed |
|-------|------|-------|--------|-----------|
| 1 | Portability spike | 1 | **Complete** | 2026-09-15 |
| 2 | Measurement core | 5 | **Complete** | 2026-09-15 |
| 2.1 | Coherence gate [INSERTED] | 1 | **Complete** | 2026-09-15 |
| 3 | The sparse grid — format axis per runtime | 2 | **Complete** | 2026-09-16 |
| 4 | The 256-expert question | 1 | **Complete** | 2026-09-15 |
| 5 | The joined grid (runtime axis falls out of it) | 2 | **Complete** | 2026-09-16 |
| 6 | Sweeps | 2 | **Complete** | 2026-09-16 |

## v2 Phase Details

### Phase 1: Track 1 — The JANG Study (v2)

**Goal:** Single-variable study of the JANG proprietary quantization family (`JANG_4S`, `JANG_2L`) on the two runtimes that load it (`vMLX 1.6.59` and `Osaurus 0.25.x`), holding runtime constant against portable formats, and holding format constant across both runtimes.

**Study Design:** `docs/research/2026-09-17-v2-track1-jang-study-design.md`

**Plans:**
- [x] 01-01: Dense JANG Study (`Qwen3.5-4B`) — **Complete 2026-09-17** (`docs/research/2026-09-17-dense-jang-study.md`)
- [x] 01-02: MoE JANG Study (`LFM2.5-8B-A1B`) — **Complete 2026-09-17** (`docs/research/2026-09-17-moe-jang-study.md`)
- [x] 01-03: Cross-Runtime JANG Synthesis — **Complete 2026-09-17** (`docs/research/2026-09-17-jang-cross-runtime.md`)

### Phase 2: Track 2 — Accuracy Scoring (v2)

**Goal:** Complete the evaluation trilogy (Speed, Memory, Accuracy) by pricing the quality trade for JANG and portable quantization formats on Apple Silicon, directly testing vendor claims (e.g. 2-bit JANG matching 4-bit MMLU), and constructing the 2D Pareto frontier across throughput, footprint, and accuracy.

**Study Design:** `docs/research/2026-09-17-v2-track2-accuracy-study-design.md`

**Plans:**
- [x] 02-01: Harness Spike & Local Endpoint Validation — **Complete 2026-09-18** (`docs/research/2026-09-18-accuracy-spike-report.md`)
- [x] 02-02: Dense Accuracy Study (`Qwen3.5-4B`) — **Complete 2026-09-18** (`docs/research/2026-09-18-accuracy-dense.md`)
- [x] 02-03: MoE Accuracy Study (`LFM2.5-8B-A1B`) — **Complete 2026-09-19** (`docs/research/2026-09-19-accuracy-moe.md`)
- [x] 02-04: Accuracy vs Throughput Pareto Tradeoff Synthesis — **Complete 2026-09-19** (`docs/research/2026-09-19-accuracy-pareto.md`)

## v1 Phase Details

### Phase 1: Portability spike — COMPLETE

Answered, twice, and the second answer redirected the project.

- `gemma-4-12B-it-qat-oQ4` is `model_type: gemma4_unified`, which **mlx-lm 0.31.3 does not
  ship**. That family cannot have a stock-mlx control and was dropped as hero model.
- `Jundot/Qwen3.6-35B-A3B-oQ4-mtp` (`qwen3_5_moe`, 256 experts) **loads** in 4s, returns
  HTTP 200, generates 64/64 tokens at full speed — and emits mixed-script token salad.

The second result is the finding the project now exists to chase, and it produced Phase 2.1
and Phase 4.

### Phase 2: Measurement core — COMPLETE

`transport.py`, `token_counter.py`, `runtimes.py`, `osaurus_settings.py`, `sample.py`,
`measure.py`, `report.py`, `cli.py`. 183 tests. Built by five concurrent Command Code
sessions against `docs/interfaces.md`.

### Phase 2.1: Coherence gate [INSERTED] — COMPLETE

**Goal:** a cell that emits garbage fails, however fast it was.
**Reason for insertion:** Phase 1 proved a runtime can load, answer HTTP 200, hit full
throughput, and return unusable text with nothing raised anywhere. Every speed number in
this project is worthless without this gate, so it precedes all measurement.

**Plans:**
- [x] 02.1-01: `coherence.py` and its call site in `measure.py` — issue #7

### Phase 3: The sparse grid — COMPLETE

**Goal, as built:** the grid, not a single column. `ohyesmlx run --study format` was invoked
once per runtime, five times, holding that runtime constant and varying the format. Five run
directories, twelve cells each: **60 of 60 PASS**, 353 tests.

The grid contains both axes as its slices — columns (one runtime, many formats) are the format
axis, rows (one format, many runtimes) are the runtime axis. That is why Phase 5 became the
join rather than a separate runtime-axis measurement campaign: the runtime-axis data already
exists, unread.

**Subject:** `Qwen3.5-4B` at stock-4bit, oQ4, oQ4e, OptiQ, plus JANG_4S where the runtime
loads it. `LFM2.5-8B-A1B` (MoE) is not yet run and carries into v1's remaining work.

**What it answered.** `stock4bit > oQ4 > oQ4e > OptiQ` on decode tok/s, identically in mlx-lm,
oMLX and mlx-optiq — three codebases that share nothing — with zero inversions in five columns.
OptiQ is last in every column that carries it and largest on disk (4.04 GB against stock-4bit's
3.06 GB). JANG_4S is fastest in both runtimes that can load it, which is a legal reading only
because two independent runtimes agree with the format held constant.

**Seven measurement-validity defects were found and fixed across this phase**, the last being
`measured_drift` — computed into every row and read by nothing. Drift now annotates and never
fails: a cell still moving is a result, and the row saying the window was too short is the row
that must not be dropped.

**Open, carried into Phase 5's write-up:** warmup is a per-runtime property and the harness
treats it as universal (mlx-lm drifts +17.0% median across a whole column; the other four
settle at +2.6/-0.0/+0.5/+1.0%), and a column-entry effect puts ~+15% on the first cell
measured in 3 of 5 columns. Both are recorded in `.paul/HANDOFF.md`.

**Standing caveat, carried in every table this phase produces:** LFM2.5 has 32 experts; the
checkpoint that failed has 256. A clean result here validates the machinery and does **not**
exonerate stock mlx-lm on high-expert-count MoE.

**Plans:**
- [x] 03-01: Format axis, dense (`Qwen3.5-4B`) — five columns, 60/60 PASS
- [x] 03-02: Format axis, MoE (`LFM2.5-8B-A1B`) — 59/60 PASS, `docs/research/2026-09-16-moe-format-axis.md`. The dense tail ordering does NOT transfer: stock wins by 11-17% and oq4/oq4e/OptiQ are tied.

### Phase 4: The 256-expert question — COMPLETE

One format (`Jundot/Qwen3.6-35B-A3B-oQ4-mtp`, already cached), two runtimes, coherence as the
measured outcome, zero downloads.

**Answered: the failure is runtime-specific, not format-specific.** oMLX 0.6.4 answers
coherently from the same bytes stock mlx-lm turns into token salad. The format axis is not
built on a corrupting quantizer, and the gate catches the failure.
See `docs/research/2026-09-15-phase4-256-expert.md`.

**Plans:**
- [x] 04-01: Two-runtime coherence comparison on 256 experts

### Phase 5: The joined grid

**Goal:** the five Phase 3 run directories become one grid, and the runtime axis — which was
measured and never read — falls out of it as the grid's rows.
**Depends on:** Phase 3
**Scope change from the original plan:** this phase was written as a separate runtime-axis
measurement campaign. Phase 3 built the grid instead of a single column, so the runtime-axis
data already exists in `results/grid/`. Phase 5 is therefore a **join, not a measurement** —
nothing here starts a server.

`mlx-Chronos` already publishes a runtime-axis protocol. Our contribution is the specific
runtime set and the format-held-constant discipline, not the idea. Say so in the write-up.

Shapes pinned in `docs/interfaces.md`, section "Phase 5 — the joined grid": `measure.load_run`
reads a `results.jsonl` back, `report.render_grid` renders the grid with three distinguishable
entry states, four join guards refuse a grid whose columns never belonged together, and
`ohyesmlx grid <run-dir>...` takes explicit directories rather than a glob.

**Plans:**
- [x] 05-01: `load_run`, `render_grid`, the `grid` command, and the write-up —
      `docs/research/2026-09-16-phase5-joined-grid.md`
- [ ] 05-02: per-runtime warmup, re-run the mlx-lm column, re-join. **SUPERSEDED
      2026-09-16 by per-cell measured warmup** (two windows of five rates, medians
      compared at 3%, floor 10, cap 20 — STATE.md Decisions): warmup is measured per
      cell, not pinned per run, so no column re-run is needed. The runtime-axis
      caveat stands: mlx-lm's published-median ordering still measures warmup as
      much as speed.

### Phase 6: Sweeps — COMPLETE

**Goal, as built:** two single-variable sweeps joined with Phase 5's machinery, plus the
concurrency finding that fell out along the way.

- **06-01 (concurrency + prompt length):** N=8 aggregate gains 0.99–1.15× — none of the
  five runtimes batch. Prompt sweep at 128/1k/4k/16k/32k ranks on TTFT (Osaurus's
  `usage.prompt_tokens` is chars/4, so `prefill_tps` is not comparable); mlx-lm leads
  from 1k up; vMLX 32k is published FAIL (macOS GPU watchdog on a one-shot hybrid
  prefill, 28/49 in the sweep, 43/49 on rerun). See
  `docs/research/2026-09-16-prompt-length-sweep.md` and
  `docs/research/2026-09-16-concurrency-omlx.md`.
- **06-02 (cold/warm KV split):** at 4,096 tokens, only oMLX (17.4×) and Osaurus (23.3×)
  serve a warm hit on Qwen3.5; mlx-lm/OptiQ cannot (hybrid `ArraysCache` not trimmable),
  vMLX declines its own prefix cache for hybrids without block-disk. See
  `docs/research/2026-09-17-cache-state-split.md`.

**Plans:**
- [x] 06-01: Concurrency and prompt-length sweeps
- [x] 06-02: Cold/warm KV-cache split

## Milestone v2: JANG Study & Accuracy Scoring (0.2.0) — COMPLETE

### Phase 1: Track 1 — The JANG Study (COMPLETE 2026-09-17)
- [x] 01-01: Dense JANG Study (`Qwen3.5-4B`) — `docs/research/2026-09-17-dense-jang-study.md` (R1 confirmed: JANG_4S leads portable formats by +14–17% in vMLX and +9–10% in Osaurus on sustained decode).
- [x] 01-02: MoE JANG Study (`LFM2.5-8B-A1B`) — `docs/research/2026-09-17-moe-jang-study.md` (R4 triggered: JANG_2L ties stock4bit in vMLX and loses in Osaurus, but saves 36% disk and 16–31% memory).
- [x] 01-03: Cross-Runtime JANG Synthesis — `docs/research/2026-09-17-jang-cross-runtime.md` (JANG Duality established: dense throughput leader vs MoE footprint/density leader).

### Phase 2: Track 2 — Accuracy Scoring (COMPLETE 2026-09-19)
- [x] 02-01: Harness Spike & Local Endpoint Validation — `docs/research/2026-09-18-accuracy-spike-report.md` (vMLX stop-deadlock patched, reasoning trap resolved via `enable_thinking=false`, `fewshot_as_multiturn: true` frozen).
- [x] 02-02: Dense Accuracy Study (`Qwen3.5-4B`) — `docs/research/2026-09-18-accuracy-dense.md` (P1 Parity confirmed for JANG_4S vs stock4bit at +0.53 pp MMLU [95% CI: -0.38, +1.43 pp]; OptiQ strictly Pareto-dominated at -3.8 to -4.4 pp MMLU and +28% disk).
- [x] 02-03: MoE Accuracy Study (`LFM2.5-8B-A1B`) — `docs/research/2026-09-19-accuracy-moe.md` (100% replicate determinism, 2.37-bit instruction following preserved, OptiQ eliminated, outlier protection mandatory).
- [x] 02-04: Accuracy vs Throughput Pareto Tradeoff Synthesis — `docs/research/2026-09-19-accuracy-pareto.md` (unified 3-coordinate recommendation table across Apple Silicon).

---

## Post-v2 / Candidate Experiments

### Candidate 1: Osaurus MoE MMLU Extraction Resolution (Offline Analysis)
- **Status:** COMPLETE (2026-09-19).
- **Artifact:** `docs/research/2026-09-19-osaurus-moe-mmlu-extraction.md`, `scripts/rescore_moe_mmlu.py`.
- **Finding:** lm-eval 3.77% was first-line regex truncation (`^(.*?)(?=\n|$)`). Five-pattern cascade on full completion recovers **42.19%** (481/1,140, 95% Wilson CI: [39.36%, 45.08%]) with 0 baseline hits lost. Strict equality reconciles exactly to 43/1,140. Outscores stock4bit (35.53%) and OptiQ (28.25%).

### Candidate 2: vMLX JIT A/B Study (Single-Variable Speed Benchmark)
- **Status:** COMPLETE (2026-09-19).
- **Artifact:** `docs/research/2026-09-19-vmlx-jit-ab.md`, `scripts/run_vmlx_jit_ab.sh`.
- **Finding:** Across all 6 cell-workload pairs, `--enable-jit` carries a **-2.7% to -11.3% decode throughput penalty** (-1.5 to -8.7 tok/s) on Apple Silicon M2 Max. On 4B/8B models at batch size 1, memory bandwidth dominates and JIT compilation overhead hurts decode speed. TTFT and prefill throughput are indifferent ($\pm1-2\%$). Confirms that Track 1's choice to pin `--no-jit` was not only methodologically pure, but optimal for throughput.

### Candidate 3: Thinking-Off MMLU Arm (Deferred)
- **Status:** Deferred in favor of Milestone v3 development. Blocked by vMLX endpoint rejecting `enable_thinking=false` (HTTP 400 `supports_instruct_mode=False`). Preserved here across AGY session boundaries.
- **Goal:** Dedicated ablation study testing MMLU with reasoning channel explicitly suppressed (dense via API `enable_thinking=false`, MoE via prompt template / system prompt) to:
  1. Isolate the exact accuracy contribution of the `<think>` reasoning trace vs raw knowledge retrieval.
  2. Resolve the vMLX reasoning truncation trap (HTTP 502 `reasoning_only_no_content` observed on MoE item 80/1,140).
- **Budget:** ~3.5 to 8 hours quiet machine time.

---

## Milestone v3: Large-Model Scaling, Context Dynamics & Public Release (0.3.0) — ACTIVE

### Phase 1: Large-Model Scaling (35B MoE Class on Apple Silicon)
- [x] 03-01: 35B MoE Serving Benchmark (`Qwen3.6-35B-A3B`) — **Complete 2026-09-20** (`docs/research/2026-09-20-35b-moe-serving.md`). Confirmed H1–H4 across 16 live cells in 5 runtimes: routing-bound decode scaling (58–70 tok/s), OptiQ strictly Pareto-dominated (+20.8% disk, slowest/tied decode), JANG MoE duality (density savings without decode advantage), Osaurus 0.74x memory reporting gap (`CROSS_RUNTIME_UNCOMPARABLE`). Resolved Phase 1 founding defect: stock mlx-lm serves 256-expert oQ4 with 100% coherence; MTP head was root cause of Phase 1 salad.
- [x] 03-02: Cold vs Warm Page Cache Load & Memory Residency Attribution — **Complete 2026-09-20** (`docs/research/2026-09-20-cold-warm-load-attribution-35b.md`). Verified via `mincore`: true cold APFS load (0% cache) achieves 5.40 GB/s sequential throughput (5.61s cold vs 2.09s warm, a 2.68x speedup); lazy loading hides +4.92s in oMLX and +8.92s in OptiQ, inverting startup rankings; `vmmap` per-region accounting proves Osaurus 0.74x footprint gap is an allocation class artifact (`IOAccelerator` capped at 12.18 GB vs 18.75–19.87 GB in other runtimes).
- [x] 03-03: Expert Streaming under High Memory Pressure — **Complete 2026-09-20** (`docs/research/2026-09-20-expert-streaming-high-memory-pressure.md`). Evaluated OptiQ SSD streaming and vMLX FlashMoE/Smelt across 6 cells on `Qwen3.6-35B-A3B-4bit`. Confirmed H1–H5: Full streaming achieves 75–88% memory reduction (footprint drops from ~20.5 GB to 3.2–3.9 GB, hitting the 2.28 GB backbone floor); decode throughput collapses by 9× to 16× (from 67–75 tok/s to 4.3–8.2 tok/s) due to NVMe random pread latency (320 slices/token); 64-slot LRU caching yields <5% throughput improvement under 256-expert routing entropy; Smelt maintains near-native speed (62.5 tok/s) at risk of routing degradation; OptiQ's static 70% RAM auto-threshold (44.8 GB on 64 GB Mac) never fires for 35B models, making explicit flag pinning mandatory under memory pressure.

### Phase 2: Context Scaling & Conversational Dynamics
- [x] 03-04: Multi-Turn Conversation Sweep (1 to 10 turns) — **Complete 2026-09-20** (`docs/research/2026-09-20-multiturn-conversation-sweep.md`). Evaluated 50 dialogue turns across all 5 runtimes on `Qwen3.6-35B-A3B-4bit`. Confirmed H1–H5: hybrid attention prevents cross-turn stateless prefix-cache reuse, causing TTFT to scale linearly with dialogue depth (3.4×–4.2× growth from ~0.4s to 1.6–2.2s); decode throughput (55–75 tok/s) and ITL (13–18 ms/tok) remain rock-solid invariant to context length; memory footprint is flat in steady state; 100% coherence pass rate.
- [x] 03-05: Quantized KV Caches (FP8, INT4 vs FP16 KV Caches at 16k and 32k) — **Complete 2026-09-20** (`docs/research/2026-09-20-quantized-kv-caches.md`). Evaluated 14 configurations across OptiQ, vMLX, and mlx-lm on `Llama-3.1-8B-oQ4`. Confirmed H1–H5: INT4 KV cache compresses peak footprint from 11.26 GB to 6.54 GB (saving 4.73 GB RAM, a 72% incremental KV reduction), enabling 32k context on 16 GB Macs; dynamic dequantization on 8B in OptiQ incurs an ALU decode penalty (20.0 tok/s -> 8.0 tok/s) while vMLX maintains steady decode (17.6 tok/s); 100% coherence pass rate; Phase 2 closed.

### Phase 3: Speculative Decoding & Acceleration Architectures — COMPLETE & CLOSED
- [x] 03-06: Native Multi-Token Prediction (MTP) in vMLX (`--enable-native-mtp`) — **Complete 2026-09-20** (`docs/research/2026-09-20-native-mtp-vmlx.md`). Evaluated 8 configurations across 3 semantic workloads in vMLX 1.6.59. Confirmed H1–H5: Native MTP at Fixed Depth 1 achieves a +31.0% decode speedup (78.7 -> 103.1 tok/s, confirmed 107.6 tok/s) on structured code and +27.9% (78.4 -> 100.3 tok/s) on philosophy at high acceptance (81.4%–85.3%); acceptance degrades monotonically with depth (D=1 [85%] > D=2 [71%] > D=3 [64%]); over-speculation beyond D=1 produces net throughput degradation (-15.5% at D=3 on architecture); memory overhead is negligible (+73 MB RAM); diagnosed upstream `Qwen3.6-35B-A3B-oQ4-mtp` artifact failure (0.0% acceptance, 41% decode collapse, token salad), contrasting with 100% clean non-MTP control.
- [x] 03-07: Speculative Draft-Model Decoding in mlx-lm (`--draft-model`) — **Complete 2026-09-20** (`docs/research/2026-09-20-speculative-draft-decoding.md`). Diagnosed stock `mlx_lm.server --draft-model` refusal on hybrid linear-attention models (`ValueError: Speculative decoding requires a trimmable prompt cache (got {'ArraysCache'})`). Evaluated 7 configurations across 3 semantic workloads via exact recurrent state-rollback adapter. Confirmed H1–H5: dual-model speculative drafting with a dense 4B draft model on a 35B MoE target causes a severe throughput collapse (64.3 -> 24.5 tok/s, 0.38x at K=1; down to 12.0 tok/s, 0.19x at K=4) and consumes +3,072 MB RAM overhead; proved that 35B MoE sparsity (1.98 GB active bytes/step) renders dense drafting (2.54 GB/step) counterproductive on unified memory; demonstrated 100.000% generative fidelity; established Native MTP (Plan 03-06) as structurally superior to draft-model speculation on Apple Silicon; Phase 3 closed.

### Phase 4: Public Distribution & Packaging (v1.0 Release) — COMPLETE & CLOSED
- [x] 03-08: Distributable Package & Clean CLI — **Complete 2026-09-20**. Packaged OhYesMLX for public distribution (PEP 621, Hatchling, version 0.3.0, zero external dependencies, `longtext.md` bundled, `--version`/`-V` CLI flags, 504 passing tests).
- [~] 03-09: Automated Interactive Pareto Visualization — **REVERTED 2026-09-23 (Decision 117): ranked memory across runtimes from a hand-copied table; removed before release.** Superseded text follows. Built standalone zero-dependency interactive HTML5/SVG visualization (`ohyesmlx/pareto.py`, `results/pareto_frontier.html`) mapping Speed, Memory Footprint, and Quality frontiers across 18 verified configurations, added `ohyesmlx pareto` CLI subcommand, and expanded test suite to 509 passing tests. Phase 4 Closed. Milestone v3 Complete.

---

## Horizon Roadmap: Milestone v3.1 / v4 Candidates

- **Runtime Expansion:** Non-MLX runtime adapters (`llama.cpp` server, `Ollama`) to enable rigorous, single-variable GGUF vs MLX cross-runtime evaluation.
- **Architectural Coverage:** Support for updated MLX-LM backends (`gemma4_unified`), Vision-Language Models (VLMs), and native MTP heads.
- **Accuracy Pipeline Integration:** Automated zero-shot / thinking-off downstream task evaluations (MMLU, GSM8k) integrated into the core harness alongside speed and memory.

---
*Roadmap created: 2026-09-14*
*Last updated: 2026-09-20 (Plan 03-09 Complete; Phase 4 Closed; Milestone v3 Complete; Compatibility & Horizon Roadmap Updated)*

## Milestone v3.1: Hardening (0.3.1) — IN PROGRESS

Source: deep review 2026-09-23, `.paul/review/2026-09-23/SUMMARY.md`. IDs refer to it.

- [x] Phase 1 (COMPLETE 2026-09-23): Correctness & residency. A1 (no figures on FAIL rows), A2 (single-delta timestamps; delta domain in measure), B1–B4 (stale Osaurus sweep by executable path; lsof failure; swallowed cleanup; post-SIGKILL wait), C1–C4 (persist partial visits; start/try gap; unreadable baseline fails closed; sampler/scratch/tmp), A6 (OptiQ sampler flags pinned), D2 (harness revision in header), E1–E3 (tests that can fail).
- [x] Phase 2 (COMPLETE 2026-09-23, `17b3791`): Contract decisions. A5 label (Decision 119), A7 refusal (Decision 120), D1 end-to-end latency percentiles, D3 unknown versions refused by the join.
- [x] Phase 3 (COMPLETE 2026-09-24, `4279663`, `deb6189`): Research & docs integrity. Caveats on the script-based v3 papers (Decision 121); probe_grid LOADS requires coherence (A4); docs/interfaces.md and README drift (F).
- [~] Phase 4: Re-run the v3 script-based studies through the harness. **Code complete 2026-09-24** (Decisions 122–123): `--kv-quant`, `--mtp-depth`, `--stream-experts`, `--workloads multiturn`. Remaining: one overnight sweep per study, plus a third 35B replicate.

