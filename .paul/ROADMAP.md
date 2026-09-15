---
description: "OhYesMLX — milestone and phase structure"
type: Roadmap
about: "OhYesMLX"
---

# Roadmap: OhYesMLX

## Overview

Prove one assumption, build a ~1,000-line measurement core, publish four honest
numbers, then widen. Every phase after the first ends in something publishable, so
the project can stop at any phase boundary and still have given the community more
than it had. The predecessor project failed by making everything a prerequisite for
everything else; here, Phase 3 ships.

## Current Milestone

**v1 — Speed and memory, one model** (0.1.0)
Status: In progress
Phases: 0 of 5 complete

## Phases

| Phase | Name | Plans | Status | Completed |
|-------|------|-------|--------|-----------|
| 1 | Portability spike | 1 | Not started | - |
| 2 | Measurement core | 5 | Not started | - |
| 3 | Study A — runtime axis | 1 | Not started | - |
| 4 | Sweeps | 2 | Not started | - |
| 5 | Study B — format axis | 1 | Not started | - |

## Phase Details

### Phase 1: Portability spike

**Goal:** Answer one question that can invalidate Study A before any code is written:
can `mlx_lm.server` load an oQ4 artifact?
**Depends on:** Nothing (first phase)
**Research:** Unlikely (the answer is empirical, not documentary)

**Scope:**
- A fresh venv with `mlx-lm` installed.
- `mlx_lm.server` serving `avneetsb/gemma-4-12B-it-qat-oQ4-fp16` from the local HF cache.
- One valid completion returned over `/v1/chat/completions`.
- The answer recorded either way. If it fails, Study A's portable format falls back to an `mlx-community/*-4bit` artifact and the README says so.

**Plans:**
- [ ] 01-01: Prove or disprove oQ portability to stock mlx-lm

### Phase 2: Measurement core

**Goal:** A tool that starts each runtime, measures it honestly, samples its memory,
and writes one joined result file.
**Depends on:** Phase 1 (which format is portable decides what `runtimes.py` serves)
**Research:** Unlikely (LMRE already paid for the hard-won parts; they get ported)

**Scope:**
- `transport.py` vendored from LMRE near-verbatim — the SSE client with chunked-encoding handling, the `select()` loop, OptiQ keepalive tolerance, and reasoning-vs-content delta separation.
- `runtimes.py` — four runtime definitions carrying LMRE's pinned flag tuples, plus the Osaurus host-settings snapshot and baseline diff.
- `sample.py` — a `footprint -p <pid>` poller returning peak and timeseries, optional `powermetrics`, graceful without sudo. New; LMRE has no equivalent.
- `measure.py` — warmup of at least 3, fixed 256-token output, interleaved cell order, raw observations retained, persist after every cell.
- `report.py` — join transport, sampler, and `du` into `results.jsonl` and a markdown leaderboard.

**Plans:**
- [ ] 02-01: Vendor transport.py with its tests
- [ ] 02-02: runtimes.py — lifecycle for four runtimes
- [ ] 02-03: sample.py — macOS memory sampling
- [ ] 02-04: measure.py — the measurement loop
- [ ] 02-05: report.py and the results schema

### Phase 3: Study A — runtime axis

**Goal:** The first real numbers, and the first thing worth publishing.
**Depends on:** Phase 2
**Research:** Unlikely

**Scope:**
- One portable format served by `mlx_lm.server`, Osaurus, oMLX, and `optiq serve`.
- Concurrency 1, one prompt length. Deliberately narrow.
- README updated with the leaderboard and the runtime-axis caveat: format held constant, this compares serving and not quantization.
- **Ship it.**

**Plans:**
- [ ] 03-01: Run and publish Study A

### Phase 4: Sweeps

**Goal:** Find where continuous batching and mixed-precision KV cache actually pay off.
**Depends on:** Phase 3
**Research:** Likely (GuideLLM integration, and how each runtime's prefix cache is cleared)
**Research topics:** GuideLLM request-rate shaping against a local endpoint; oMLX SSD prefix cache location and eviction; whether Osaurus and OptiQ cache prefixes at all.

**Scope:**
- Concurrency sweep 1/2/4/8/16/32, sustained at least 60s each, per-request and aggregate throughput reported separately.
- Prompt-length sweep 128/1k/4k/16k/32k in, fixed 256 out.
- Cold vs warm KV-cache split: every config run twice, caches cleared between.

**Plans:**
- [ ] 04-01: Concurrency and prompt-length sweeps
- [ ] 04-02: Cold/warm KV-cache split

### Phase 5: Study B — format axis

**Goal:** Hold the runtime constant and vary the quantization — including JANG, which
means the first honest third-party look at the "2-bit destroys 4-bit" claim.
**Depends on:** Phase 4
**Research:** Likely (whether oMLX loads all four target formats in one install)

**Scope:**
- oMLX serving mlx-lm 4-bit, oQ4, OptiQ-4bit, and JANG_4M of the same base model, one at a time.
- On-disk size including sidecars, so JANGTQ's runtime sidecar counts against it.
- Published with the format-axis caveat stated as plainly as Study A's.

**Plans:**
- [ ] 05-01: Run and publish Study B

---
*Roadmap created: 2026-09-14*
*Last updated: 2026-09-14*
