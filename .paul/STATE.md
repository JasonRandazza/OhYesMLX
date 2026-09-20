---
description: "OhYesMLX — current position and accumulated context"
type: ProjectState
about: "OhYesMLX"
---

# Project State

## Project Reference

See: .paul/PROJECT.md (updated 2026-09-14)

**Core value:** A Mac user can find out whether their serving runtime or their quantization is what's actually costing them speed and memory.
**Current focus:** Milestone v3 Phase 2: Context Scaling & Conversational Dynamics (entering Plan 03-04 planning)

## Current Position

Milestone: v3 — Large-Model Scaling, Context Dynamics & Public Release (0.3.0) — IN PROGRESS
Phase: 3 (Speculative Decoding & Acceleration Architectures) — COMPLETE & CLOSED (2/2 plans complete)
Plan: Plan 03-07 (Speculative Draft-Model Decoding in mlx-lm) — COMPLETE & PUBLISHED
Status: Plan 03-07 executed and published (`docs/research/2026-09-20-speculative-draft-decoding.md`). Diagnosed stock `mlx_lm.server --draft-model` refusal on hybrid linear-attention models (`ValueError: Speculative decoding requires a trimmable prompt cache (got {'ArraysCache'})`). Evaluated 7 configurations across 3 semantic workloads via exact recurrent state-rollback adapter. Confirmed H1–H5: dual-model speculative drafting with a dense 4B draft model on a 35B MoE target causes a severe throughput collapse (64.3 -> 24.5 tok/s, 0.38x at K=1; down to 12.0 tok/s, 0.19x at K=4) and consumes +3,072 MB RAM overhead; proved that 35B MoE sparsity (1.98 GB active bytes/step) renders dense drafting (2.54 GB/step) counterproductive on unified memory; demonstrated 100.000% generative fidelity; established Native MTP (Plan 03-06) as structurally superior to draft-model speculation on Apple Silicon. Phase 3 closed. Ready for Phase 4 (Public Distribution & Packaging).
Last activity: 2026-09-20 — **Plan 03-07 Executed & Published (Speculative Draft-Model Decoding in mlx-lm)**. H1–H5 confirmed. Phase 3 Complete & Closed. 496 tests pass.

Progress:
- Milestone: [███████░░░] 75%
- Phase: [██████████] 100%

## Loop Position

Current loop state:
```
PLAN ──▶ APPLY ──▶ UNIFY
  ○        ○        ◉     [Plan 03-07 Complete & Unified; Milestone v3 Phase 3 Closed; entering Phase 4 planning]
```

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: —
- Total execution time: —

## Accumulated Context

### Decisions

| Decision | Phase | Impact |
|----------|-------|--------|
| Two single-variable studies replace LMRE's native diagonal | Pre-phase | Every run declares which axis it varies; nothing varies both. |
| PAUL is the only process spine | Pre-phase | No CONTEXT.md, no ADRs, no handoff docs, no wayfinder. This file is the only state store. |
| Speed + memory only in v1 | Pre-phase | Accuracy work is refused until v1 ships, however tempting. |
| ~~Hero model is `gemma-4-12B-it-qat`~~ **Superseded Phase 1** | Pre-phase | Zero downloads; 36 GiB free disk forbade more. Replaced by the Qwen3.5-4B + LFM2.5-8B-A1B row below. |
| `--cells a,b,c` is the only cell selector | Pre-phase | Any second mechanism gets deleted on sight. |
| Implementation delegated to `cc-agent` (deepseek-v4.1-flash, max effort) | Pre-phase | Opus reviews every diff and every test run personally; worker prose is not evidence. |
| Hero models are `Qwen3.5-4B` + `LFM2.5-8B-A1B` | Phase 1 | `gemma4_unified` is not shipped by mlx-lm, so that family can carry no stock-mlx control. 33.7 GB for both, all four formats each. |
| Format axis ships before runtime axis | Phase 1 | `mlx-Chronos` already published a runtime-axis protocol; nobody has done the format axis properly. |
| A cell emitting garbage FAILS, however fast | Phase 1 | Stock mlx-lm loaded a 256-expert oQ4 MoE, hit full throughput, and returned token salad with nothing raised. |
| JANG is a runtime+format bundle, not an axis point | Phase 1 | No runtime loads JANG and the other formats both. Own study, after v1. |
| A grid contains both axes as its slices | Phase 3 | Rows (one format, many runtimes) are the runtime axis; columns (one runtime, many formats) are the format axis; the best cell is a recommendation. Attribute within a row or column, recommend across the whole. The two axes were never alternatives to the diagonal — they are readings of one measurement. |
| Three workloads, never averaged | Phase 3 | chat/prefill/decode. One shape measures one corner and prefill-heavy and decode-heavy work can have different winners. A richer suite is v2's. |
| Floors then one ordering metric, never a blended score | Phase 3 | Weighting speed against memory has no objective answer, so a single number would encode an arbitrary trade-off as though it were measured. Full metric card behind every ranking. |
| Osaurus prefill was a cache hit: 8.3x cache, 1.15x version | Phase 3 | Three runs isolated it. Its KV cache cannot be disabled from any command line, only from ~/.osaurus/config, and the settings drift guard already watches both keys. |
| cold_load_s is not one quantity across runtimes | Phase 3 | oMLX loads lazily and hides 3.08-3.85 s in request #1. first_request_s now records it. A cross-runtime load comparison uses the sum. |
| The reasoning channel is the output stream when there is no content | Phase 3 | mlx-lm and vMLX answer entirely in it; all 24 of their grid rows failed before this. |
| Every runtime advertises models it cannot serve | Phase 3 | mlx-lm, oMLX and Osaurus all list a model in /v1/models and then refuse it. oMLX published a 2.15 s cold load for weights it had already failed to load. Readiness is not the port, and not the model list either. |
| Osaurus and vMLX are two independent JANG runtimes, both kept | Phase 3 | JANG cannot be a format-axis row, but JANG-on-Osaurus vs JANG-on-vMLX is the runtime axis with format held constant. Two implementations are what make a single-variable JANG study possible at all. |
| The 256-expert failure is runtime-specific, not format-specific | Phase 4 | oMLX 0.6.4 answers coherently from the same bytes stock mlx-lm turns into salad. The format axis is not built on a corrupting quantizer. |
| Drift annotates, never fails | Phase 3 | A cell still moving is a result, and the row saying the window was too short is the row that must not be dropped. DRIFT_ANNOTATION_PCT=5.0 separates the columns, not every row. |
| Warmup is a per-runtime property, not a universal constant | Phase 3 | mlx-lm drifts +17.0% median across a whole column; oMLX, mlx-optiq, vMLX and Osaurus settle at +2.6/-0.0/+0.5/+1.0%. One warmup budget cannot be right for all five. |
| A server's self-reported tok/s is not a measurement | Phase 4 | oMLX reports 15,286 tok/s from a generation_duration of 0.0. The harness measures; it does not relay. |
| Warmup is measured per cell, not pinned per run | Phase 5 | Two windows of five rates, medians compared at 3%, floor 10, cap 20. A trend test and never a variance test: a noisy workload is not an unwarmed one. `warmup_count` publishes what each cell needed. |
| A run is discarded only for a stated defect in its conditions | Phase 5 | The first oMLX column was thrown away because the machine was not quiet while it ran, and is kept and named with that reason. A run discarded without such a defect is discarded for its number. |
| Nothing else runs on this machine while a cell is measured | Phase 5 | Not a test suite, not a git operation, not "lightweight" background work. It cost one column: a cell warmed at 68-73 measured 40-60 and would have inverted the format ordering. The harness cannot detect this, so the discipline holds without enforcement. |
| A sweep is a run pin, never a third `--study` axis | Phase 6 | `--study` names which of a *cell's* two variables may vary, and a cell is (format, runtime). Concurrency, prompt length and cache state are properties of how the run drove the cells. Each sweep is N runs differing in one header pin, joined with Phase 5's machinery. |
| `measured` counts batches, not requests | Phase 6 | At concurrency 1 a batch is one request, so every number measured so far stays comparable. |
| None of the five runtimes batch | Phase 6 | Measured at N=8 on the one format all five serve: aggregate gains 0.99–1.15x, spans ~8x, TTFT in proportion. Concurrency on any of them is pure latency cost. A gain without a per-request *slowdown* is not batching. |
| At N>1, positive drift means per-request rate was still moving | Phase 6 | Not "under-warmed" — the warmup window closed on aggregate. `measured_drift` is unchanged and correct about what it computes; the diagnosis a reader draws is what changes. Any sweep table printing drift needs that sentence beside it. |
| A concurrency sweep warms on aggregate throughput | Phase 6 | Measured at N=8: the per-request series swings ±11% with no trend and never settles; aggregate settles at batch 12. Same rule, same constants, different series. |
| `footprint` counts different page classes, measured | Phase 5/6 | Osaurus's weights are wired GPU pages (+1064 MB wired on load, IOAccelerator 581 MB); oMLX's are anonymous (+752 MB active, IOAccelerator 3334 MB). The file-backed explanation was wrong and is deleted. |
| Adjacent cells within a few percent are ties, not a ranking | Phase 5 | Five runtime-axis pairs sit within 2.5% and swap under a late-window re-rank. The renderer still prints them as an order; marking unresolvable ties is the next improvement. |
| Phase 5 is a join, not a measurement campaign | Phase 5 | The runtime axis was measured in full by Phase 3's five columns and read by nobody. Re-measuring it would have re-run 67 minutes of data already on disk. |
| A grid is assembled from named directories, never a glob | Phase 5 | `results/grid/` holds thirteen run dirs from three sessions; a wildcard would silently join columns that never belonged together. |
| The runtime axis is not publishable until warmup is per-runtime | Phase 5 | mlx-lm is last in 11 of 14 orderings on the published median and 1st/3rd/3rd/4th on the late-window median. The cross-runtime ordering is measuring warmup and calling it speed. The format axis is unaffected — within a column the shortfall lands on every format equally. |
| `peak_mb` and `cold_load_s` carry no runtime-axis ranking | Phase 5 | `footprint` counts different pages per runtime: four columns report within a few percent of their weight bytes, Osaurus roughly half of its. `CROSS_RUNTIME_UNCOMPARABLE` prints the reason above any runtime-axis ordering by them. Format-axis orderings are untouched. |
| Sweep prompts are cut from a frozen fixture, `ohyesmlx/longtext.md` | Phase 6 | The 09-14/09-15 research docs concatenated once (60,701 tokens, sha256 3ed2c160…a8a3), after the MS-7 excerpt. Chosen by Jason over a downloaded book and authored text. Never regenerated from `docs/`. |
| Osaurus runs the prompt-length sweep with its prefix and block-disk caches off | Phase 6 | With them on every repeat is a 0.27 s lookup. Authorised by Jason 2026-09-16; `scripts/run_sweep_prompt.sh` toggles, restores byte-exact and requires drift NONE. |
| OptiQ is started with `--max-context off` | Phase 6 | An integer cap rotates the KV window instead of refusing. No-op on Qwen3.5/LFM2 (both define `make_cache`), so no grid number moves. Jason's call, 2026-09-16. |
| The prompt-length sweep ranks on TTFT, never `prefill_tps` | Phase 6 | Osaurus's `usage.prompt_tokens` is chars/4, so `prefill_tps` from usage understates it ~20% on this text. TTFT, or locally counted `achieved` / TTFT, is comparable. |
| vMLX at 32k is published as FAIL | Phase 6 | Jason, 2026-09-16. Not a refusal (`—`): the macOS GPU watchdog (`kIOGPUCommandBufferCallbackErrorImpactingInteractivity`) kills its prefill; 28/49 in the sweep, 43/49 on rerun. Whether a prefill chunk setting avoids it is Jason's call. |
| A short measured window is annotated, not failed | Phase 6 | `(n=K of N)` beside the entry, and a lost visit keeps its reason on a PASS row. Same rule as drift: dropping the row deletes the only evidence the window was short. |
| Osaurus runs pin idle residency to 900 s and restore the host's 30 | Phase 6 | Jason, 2026-09-16. 0.25.5 set 30, which unloads the model inside the 30 s cooldown. Restore is verified with `cmp`, not drift NONE. Only `run_sweep_cache.sh` does it so far. |
| v1 closed on paper 2026-09-17; 05-02 superseded | Phase 6 | The "6 of 7" count included inserted Phase 2.1; there is no Phase 7. 05-02 (per-runtime warmup column re-run) is superseded by per-cell measured warmup (Phase 5 decision) — no re-run needed, runtime-axis caveat stands. |
| v2 leads with cheap closeouts: non-hybrid cache-split repeat, vMLX 32k re-test | v2 | Jason, 2026-09-17. Both candidates closed 2026-09-17. Next: JANG study, accuracy last. |
| Non-hybrid KV cache hit on all five runtimes (Candidate 3) | v2 | Measured 2026-09-17 on Llama-3.1-8B-oQ4: 25x–142x speedup. Proves hybrid ArraysCache was the cause of 1.00x on Qwen3.5. `docs/research/2026-09-17-cache-state-split-nonhybrid.md` |
| vMLX 32k chunked prefill enabled by VMLX_ALLOW_HYBRID_CHUNKED_PREFILL=1 (Candidate 4) | v2 | Shipped source audit + live probe 2026-09-17: one-shot default bypassed --prefill-step-size. Env var unlocks chunked prefill, eliminating Metal watchdog failure (88.76s TTFT). `docs/research/2026-09-17-vmlx-32k-chunked-prefill.md` |
| The cold/warm split is pinned at 4,096 tokens, block-disk caches off in both states | Phase 6 | One variable per pair. It is why vMLX shows no hit on the hybrid model — its prefix cache has no RAM backend for hybrids. |
| v2 Track 1 JANG Study formulated as two format-axis columns and one runtime-axis row reading | v2 Phase 1 | Single-variable problem solved; 10 artifacts verified on disk; zero downloads; pre-registers 2.5% tie band and R1-R4 readings. `docs/research/2026-09-17-v2-track1-jang-study-design.md` |
| Plan 01-01 Dense JANG Study confirms R1 on decode: JANG_4S leads portable formats in both vMLX (+13.9%/+16.8%) and Osaurus (+9.5%/+9.0%) on near-equal precision (4.15 bits); vMLX is +28% faster than Osaurus on identical JANG bytes | v2 Phase 1 | Eliminated size/bitwidth as cause; custom Metal tensor unpacking confirmed. docs/research/2026-09-17-dense-jang-study.md |
| Plan 01-02 MoE JANG Study triggers R4 (Split by Model): JANG_2L ties stock4bit in vMLX (+0.87% / −0.50% repl → R3) and loses to stock4bit in Osaurus (−5.12% / −9.80% repl); dense lead does not transfer to MoE; JANG delivers 36% disk savings and 16-31% memory reduction | v2 Phase 1 | Proves JANG decode advantage is model/profile specific; Osaurus prefix cache off toggle verified clean; docs/research/2026-09-17-moe-jang-study.md |
| Plan 01-03 Cross-Runtime JANG Synthesis establishes the JANG Duality: dense throughput winner vs MoE density/footprint winner; Phase 1 closed | v2 Phase 1 | Direct answers to design §6.4; vMLX JIT A/B framed as next single-variable experiment; docs/research/2026-09-17-jang-cross-runtime.md |
| Decision 101: Track 2 Accuracy Study Design formulated with zero-dependency uv isolation, pinned sample budget, McNemar paired intervals, and 2D Pareto frontier | v2 Phase 2 | Establishes test protocol for vendor parity claims (JANG_2L vs 4-bit MMLU), quality cost of JANG_4S decode lead, and Pareto status of OptiQ; docs/research/2026-09-17-v2-track2-accuracy-study-design.md |
| Decision 102: Plan 02-01 Accuracy Spike validates local endpoint, patches vMLX stop deadlock, and resolves reasoning trap via enable_thinking=false | v2 Phase 2 | Upstream scheduler deadlock in vmlx_engine/mllm_scheduler.py:3527 patched (match_idx); canary verified; --gen_kwargs enable_thinking=false eliminates 502/null-content trap; fewshot_as_multiturn: true priced & frozen (0.60 vs 0.00); budget verified (~1.2-1.9h per cell); 495 tests pass; docs/research/2026-09-18-accuracy-spike-report.md |
| Decision 103: ARC-Challenge dropped due to upstream extraction filter defect; Plan 02-02 runs on 3 validated tasks (MMLU 5-shot, GSM8K 5-shot, IFEval 0-shot; 2,780 items/cell) | v2 Phase 2 | Upstream arc_challenge_chat mandates "The best answer is [X]" while filter only strips outer whitespace, failing right answers; Jason chose to drop ARC-Challenge; Plan 02-02 executes across 8 primary + 3 replicate cells on 3 clean tasks |
| Decision 104: Dense Accuracy Study confirms Outcome P1 (Quality Parity) for JANG_4S vs stock4bit (+0.53 pp MMLU [95% CI: -0.38, +1.43 pp]) and establishes OptiQ as strictly Pareto-dominated (-3.1 to -4.4 pp MMLU, +28% disk) | v2 Phase 2 | Q2 confirmed (zero quality loss for +14–17% decode speedup); Q3 confirmed (OptiQ eliminated from Pareto frontier); 100.0% replicate determinism observed; Study 2C shows ~3–4 pp loader offset, proving cross-runtime accuracy rankings invalid; docs/research/2026-09-18-accuracy-dense.md |
| Decision 105: Plan 02-03 MoE Accuracy Study activates pre-registered budget dial (§3.3) and pins --no-disable-thinking due to vMLX LFM2 supports_instruct_mode=False | v2 Phase 2 | vMLX rejects enable_thinking=false with HTTP 400 for LFM2; reasoning trace active; MMLU dialed 40 -> 20 items/subject (1,140 items) to keep 8-cell campaign within ~18.5h budget; docs/research/2026-09-17-v2-track2-accuracy-study-design.md §3.3 |
| Decision 106: Plan 02-03 MoE Accuracy Study confirms 100.0% replicate determinism, rules out collapse at 2.37 bits (IFEval 56.8% vs 52.0%), strictly eliminates OptiQ (-7.3 pp MMLU, +14-78% disk), proves outlier protection mandatory (oQ4e +14.3 pp over oQ4), and diagnoses vMLX reasoning truncation trap (HTTP 502) | v2 Phase 2 | Closes Q1-Q4 on MoE; confirms within-runtime determinism on MoE; proves 2.37-bit quantization preserves instruction following; docs/research/2026-09-19-accuracy-moe.md |
| Decision 107: Plan 02-04 Pareto Tradeoff Synthesis completes evaluation trilogy (Speed, Memory, Accuracy); confirms JANG Duality (dense throughput lead at parity, MoE density/footprint lead with preserved IFEval); eliminates OptiQ across all frontiers; closes Milestone v2 | v2 Phase 2 | Establishes 3-coordinate recommendation table for Apple Silicon; closes Track 2 (Plan 02-04) and Milestone v2 (0.2.0); docs/research/2026-09-19-accuracy-pareto.md |
| Decision 108: Plan 03-01 35B MoE Serving Benchmark confirms routing-bound decode scaling (H1), OptiQ strictly Pareto-dominated (H2), JANG density lead on MoE without decode advantage (H3), and Osaurus 0.74x memory reporting gap (H4); stock4bit leads decode across all 5 runtimes; Phase 1 closed | Milestone v3 Phase 1 | Confirms 35B MoE decodes at 58–70 tok/s (~1.98 GB active bytes/step, within 2x of 8B MoE); OptiQ is +20.8% larger and slowest/tied; JANG_TQ4 provides 19.71 GB disk vs 20.43 GB stock, but loses decode to stock4bit (-13.1% primary, -17.9% replicate); Osaurus reports ~12.3-15.4 GB due to wired GPU page allocation; mlx-lm coherence on oQ4 confirmed (MTP head was root cause of Phase 1 salad); docs/research/2026-09-20-35b-moe-serving.md |
| Decision 109: Plan 03-02 Cold vs Warm Page Cache Load & Memory Residency Attribution confirms APFS sequential read throughput at 5.40 GB/s (H1), quantifies lazy loading penalties in oMLX (+4.92s) and OptiQ (+8.92s) inverting startup rankings (H2), and solves the 0.74x Osaurus footprint gap via IOAccelerator region accounting (H3) | Milestone v3 Phase 1 | Verified via mincore: true cold APFS load takes 5.61s vs 2.09s warm (2.68x speedup); True Time to First Output shows Osaurus (3.42s) > mlxlm (4.64s) > omlx (7.45s) > vmlx (8.66s) > optiq (12.44s); vmmap proves Osaurus caps IOAccelerator at 12.18 GB with remaining ~7 GB allocated into wired driver pages; docs/research/2026-09-20-cold-warm-load-attribution-35b.md |
| Decision 110: Plan 03-03 Expert Streaming under High Memory Pressure establishes the trade-offs of SSD expert streaming vs resident serving on 35B MoE: streaming achieves 75–88% memory reduction (footprint drops from ~20.5 GB to 3.2–3.9 GB, isolating the 2.28 GB backbone) at a 9× to 16× decode collapse (from 67–75 tok/s to 4.3–8.2 tok/s); LRU caching yields <5% speedup under 256-expert routing entropy; OptiQ 70% RAM auto-threshold never triggers on 64 GB Macs; Milestone v3 Phase 1 complete | Milestone v3 Phase 1 | Establishes memory floor vs NVMe random pread latency trade-off; confirms that streaming enables 35B MoE on 16 GB Macs (~3.9 GB footprint); proves in-RAM LRU caching cannot overcome MoE routing entropy; proves unpinned auto-streaming on 64 GB Mac risks sudden OOM under pressure; closes Milestone v3 Phase 1 (Plans 03-01, 03-02, 03-03 complete); docs/research/2026-09-20-expert-streaming-high-memory-pressure.md |
| Decision 111: Plan 03-04 Multi-Turn Conversation Sweep confirms hybrid linear-attention prefill scaling ($O(N)$ growth from ~0.4s to 1.6–2.2s across 10 turns) and establishes decode throughput (55–75 tok/s) and ITL (13–18 ms/tok) invariance to conversational context depth | Milestone v3 Phase 2 | 50/50 turns PASS; proves hybrid attention prevents cross-request prefix reuse under stateless chat completions; confirms Apple Silicon decode memory bandwidth saturation keeps tok/s invariant to KV cache size up to 1k tokens; docs/research/2026-09-20-multiturn-conversation-sweep.md |
| Decision 112: Plan 03-05 Quantized KV Caches establishes 72% incremental KV memory compression at 32k (saving 4.73 GB RAM, enabling 32k context on 16 GB Macs) and diagnoses ALU dequantization decode penalty on 8B models (20.0 -> 8.0 tok/s in OptiQ); Milestone v3 Phase 2 complete | Milestone v3 Phase 2 | Confirms INT4 KV cache drops 32k peak RAM from 11.26 GB to 6.54 GB in OptiQ/mlx-lm; proves ALU overhead of runtime dequantization outweighs memory bandwidth savings on 8B batch-1 decode; confirms vMLX SSD block-disk maintains flat ~5.09 GB RAM at 17.6 tok/s; 14/14 runs PASS coherence; closes Milestone v3 Phase 2; docs/research/2026-09-20-quantized-kv-caches.md |
| Decision 113: Plan 03-06 Native Multi-Token Prediction (MTP) in vMLX establishes fixed D=1 as the optimal speculative configuration on Apple Silicon (+31.0% decode speedup at 85% acceptance, +73 MB memory overhead); proves monotonic acceptance degradation across depths (H1); demonstrates over-speculation penalty at D>=2 (-15.5% at D=3); diagnoses 35B MoE MTP artifact failure mode (0.0% acceptance, 41% decode collapse, token salad) | Milestone v3 Phase 3 | Evaluates 8 configurations across 3 semantic workloads; confirms H1-H5; proves single-layer MTP drafts yield high returns (+31% speedup, 103 tok/s) while multi-draft chains compound rejection churn on memory-bandwidth bound M2 Max; proves uncalibrated heads produce 0% acceptance and 41% throughput collapse; docs/research/2026-09-20-native-mtp-vmlx.md |
| Decision 114: Plan 03-07 Speculative Draft-Model Decoding reveals dual-model memory bandwidth inversion on Apple Silicon unified memory (64.3 -> 24.5 tok/s, 0.38x collapse at K=1; down to 12.0 tok/s at K=4) and diagnoses stock mlx-lm ArraysCache trimmability refusal; proves Native MTP is structurally superior to draft models; Milestone v3 Phase 3 complete | Milestone v3 Phase 3 | Diagnoses stock mlx-lm refusal on hybrid models (ValueError: Speculative decoding requires a trimmable prompt cache); evaluates 7 configurations across 3 workloads via exact recurrent state-rollback adapter (100.000% generative fidelity); proves 35B MoE active sparsity (1.98 GB/step) renders dense 4B drafting (2.54 GB/step) counterproductive (4.52 GB/cycle vs 1.98 GB standalone AR); adds +3,072 MB RAM overhead; closes Milestone v3 Phase 3; docs/research/2026-09-20-speculative-draft-decoding.md |

### Deferred Issues

| Issue | Origin | Effort | Revisit |
|-------|--------|--------|---------|
| LMRE not yet archived to ~/Dev/archive/ | Pre-phase | S | After Phase 4, once nothing more is needed from it |
| Disk audit incomplete — two workers hit the turn cap | Phase 2.1 | S | Low urgency: 238 GiB free, both hero models on disk. Worth doing only if disk tightens again |
| ~~LMRE's rubric/ruling design not ported~~ **PULLED FORWARD 2026-09-15** | Pre-phase | — | Floors + one ordering metric now pinned in docs/interfaces.md. The accuracy axis stays in v2; only the honest half moved. |
| No CI | Pre-phase | S | Before the repo gets its first outside contributor |
| ~~Tokenizer-unavailable should make a cell N/A~~ **ALREADY FIXED, entry was stale** | Phase 4 | — | `_visit` checks the counter before starting the runtime and writes N/A with the reason; `test_an_unavailable_tokenizer_is_na_rather_than_a_silent_fallback` covers it. Verified 2026-09-16. |
| Eight pre-`first_request_workload_id` run dirs cannot be loaded | Phase 5 | S | `load_run` refuses them by line number rather than defaulting the field. A schema migration, only if those columns are ever wanted |
| ~~mlx-optiq reports `"mlx-optiq, version 0.5.6"`~~ **FIXED on branch `defects`** | Phase 3 | — | `OptiqRuntime.parse_version` records the version and passes an unrecognised shape through whole. Merges to main once the in-flight grid lands. |
| `footprint` vs resident on Osaurus is inferred, not probed | Phase 5 | S | The file-backed-pages explanation needs a probe before any memory ranking is published |
| ~~`mlx-lm` 0.31.3 lives only in `/tmp/mlxspike`~~ **RESOLVED 2026-09-15** | Phase 4 | — | Reinstalled at `~/.local/share/ohyesmlx/mlx-lm-0.31.3` with the spike's exact pins (mlx 0.32.2, transformers 5.17.0, tokenizers 0.23.2, numpy 2.5.3). |
| Runner stdout logs come out 0 bytes | Phase 6 | S | **DIAGNOSED 2026-09-17, cause is launch-side, not in-repo.** Nothing in the repo ever names `runner.log`; both runners send progress to their own stdout and only per-cell logs are redirected in-script. The empty files are caller-side redirect targets created at launch (`cmd & > file` shape — redirect unbound from the command) that received zero bytes over the whole run; per-cell logs prove redirection itself works. Correct launch: `sh scripts/run_sweep_prompt.sh > results/sweep-prompt/runner.log 2>&1 &` (redirect before `&`). In-repo hardening proposed but NOT applied (behavior change — progress would reach only the file): `exec > "$OUT/runner.log" 2>&1` after `mkdir -p "$OUT"`. Jason's call. |
| Drift markers in a TTFT-ranked table are decode drift | Phase 6 | S | **FIXED 2026-09-17 in `render_sweep` and `render_grid`.** Entries carry the marker solely for decode-derived ranks (`DECODE_DERIVED_RANKS = {decode_tps}`); all other ranks print bare. Grids byte-identical, both TTFT sweeps and grids marker-free, decode renders keep markers, `CONCURRENCY_DRIFT_SENTENCE` scoped to decode ranks, 495 tests green. |
| ~~Grid TTFT-ranked entries carry decode drift (same latent mislabel, `render_grid`)~~ **FIXED 2026-09-17** | Phase 6 | — | `_grid_table` passes `drift_marker=rank in DECODE_DERIVED_RANKS`. Default decode-ranked grid byte-identical; non-decode grids marker-free. |
| ~~`CONCURRENCY_DRIFT_SENTENCE` now describes markers absent from non-decode tables~~ **FIXED 2026-09-17** | Phase 6 | — | Scoped to `rank in DECODE_DERIVED_RANKS` in `render_sweep`. |
| TTFT-ranked concurrent table carries no queueing caveat | Phase 6 | S | The design says concurrent TTFT is a queueing measurement; the render doesn't. Minor. |
| Thinking-Off MMLU Arm (Candidate 3) | Post-v2 | M | **Preserved for overnight execution.** Ablation study: isolate reasoning contribution on MMLU and resolve MoE HTTP 502 truncation trap. |

### Blockers/Concerns

| Blocker | Impact | Resolution Path |
|---------|--------|-----------------|
| ~~Stock mlx-lm executes a 256-expert oQ4 MoE incorrectly~~ **RESOLVED Phase 4** | Was: invalidates any speed number taken without a coherence check | Runtime-specific, not format-specific. oMLX serves the same bytes coherently. Gate catches it. `docs/research/2026-09-15-phase4-256-expert.md` |
| ~~36 GiB free~~ **RESOLVED 2026-09-15** | Was: caps model choice | 312 GiB free after Jason cleared JANG models and deleted the Time Machine local snapshots that were pinning the blocks. Phase 3 is unconstrained. |

## Boundaries (Active)

- `.paul/STATE.md` is the only project state store. If a second appears, delete it.
- No new dependency without naming what it replaces.
- No governance layer: no plan hashing, no sealed evidence, no action grants, no workspace scaffolding.

## Session Continuity

Last session: 2026-09-20 (Antigravity coordinator)
Stopped at: Milestone v3 Phase 3 COMPLETE & CLOSED. Plan 03-07 executed, verified, and published (`docs/research/2026-09-20-speculative-draft-decoding.md`). Decision 114 recorded. Phase 3 (2/2 plans complete).
Next action: Enter planning for Milestone v3 Phase 4 (Public Distribution & Packaging: Plan 03-08 CLI & Packaging, Plan 03-09 Interactive Pareto Visualization).
Resume context: **Read `.paul/HANDOFF.md` first**, then this file's Decisions table.

---
*STATE.md — Updated after every significant action*
*Size target: <100 lines (digest, not archive)*
