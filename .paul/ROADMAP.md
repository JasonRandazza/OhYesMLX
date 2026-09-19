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

## Completed Milestone

**v1 — Format axis on small models** (0.1.0)
Status: Complete
Phases: 7 of 7 complete

## Current Milestone

**v2 — JANG Study and Accuracy Scoring** (0.2.0)
Status: In Progress
Phases: 1 of 2 complete

| Phase | Name | Plans | Status | Completed |
|-------|------|-------|--------|-----------|
| 1 | Track 1: The JANG Study | 3 | **Complete** | 2026-09-17 |
| 2 | Track 2: Accuracy Scoring (lm-evaluation-harness) | 4 | **In Progress** | — |

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
- [ ] 02-04: Accuracy vs Throughput Pareto Tradeoff Synthesis — *Next*

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

## Milestone v2: JANG Study & Accuracy Scoring (0.2.0) — IN PROGRESS

### Phase 1: Track 1 — The JANG Study (COMPLETE 2026-09-17)
- [x] 01-01: Dense JANG Study (`Qwen3.5-4B`) — `docs/research/2026-09-17-dense-jang-study.md` (R1 confirmed: JANG_4S leads portable formats by +14–17% in vMLX and +9–10% in Osaurus on sustained decode).
- [x] 01-02: MoE JANG Study (`LFM2.5-8B-A1B`) — `docs/research/2026-09-17-moe-jang-study.md` (R4 triggered: JANG_2L ties stock4bit in vMLX and loses in Osaurus, but saves 36% disk and 16–31% memory).
- [x] 01-03: Cross-Runtime JANG Synthesis — `docs/research/2026-09-17-jang-cross-runtime.md` (JANG Duality established: dense throughput leader vs MoE footprint/density leader).

### Phase 2: Track 2 — Accuracy Scoring (IN PROGRESS)
- [x] 02-01: Harness Spike & Local Endpoint Validation — `docs/research/2026-09-18-accuracy-spike-report.md` (vMLX stop-deadlock patched, reasoning trap resolved via `enable_thinking=false`, `fewshot_as_multiturn: true` frozen).
- [x] 02-02: Dense Accuracy Study (`Qwen3.5-4B`) — `docs/research/2026-09-18-accuracy-dense.md` (P1 Parity confirmed for JANG_4S vs stock4bit at +0.53 pp MMLU [95% CI: -0.38, +1.43 pp]; OptiQ strictly Pareto-dominated at -3.8 to -4.4 pp MMLU and +28% disk).
- [ ] 02-03: MoE Accuracy Study (`LFM2.5-8B-A1B`) — 5 formats on vMLX plus 2C MoE check.
- [ ] 02-04: Accuracy vs Throughput Pareto Tradeoff Synthesis.

---
*Roadmap created: 2026-09-14*
*Last updated: 2026-09-18 (Plan 02-02 complete)*
